import os
import sys
import time
import subprocess
import shutil
import argparse
from pathlib import Path

# Add root directory to python path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT))

import torch
try:
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.monitor import Monitor
from src.env.balatro_env import BalatroEnv

# Import helper functions from run_training
from run_training import (
    start_xvfb, stop_xvfb, find_balatro_appdata, get_or_create_balatro_appdata,
    check_health, terminate_processes
)

def kill_lingering_processes():
    print("Cleaning up any lingering Balatro or Wine processes...")
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/f", "/im", "Balatro.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "Balatro.exe"], capture_output=True)
            subprocess.run(["wineserver", "-k"], capture_output=True)
    except Exception:
        pass
    time.sleep(1.0)

def clean_shm_env_dirs():
    print("Cleaning up temp environments in /dev/shm...")
    for p in Path("/dev/shm").glob("wine_env_*"):
        try:
            shutil.rmtree(p)
        except Exception:
            pass

def launch_instances(num_instances, balatro_exe, original_balatro_dir, original_mods_dir, xvfb_display):
    master_prefix_dir = Path("/dev/shm/wine_master")
    if not (master_prefix_dir / "drive_c" / "users").exists():
        print("Initializing master WINEPREFIX template...")
        master_prefix_dir.mkdir(parents=True, exist_ok=True)
        boot_env = os.environ.copy()
        boot_env["WINEPREFIX"] = str(master_prefix_dir)
        boot_env["WINEDEBUG"] = "-all"
        boot_env["DISPLAY"] = xvfb_display
        boot_env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        boot_env["GALLIUM_DRIVER"] = "llvmpipe"
        subprocess.run(["wineboot", "-u"], env=boot_env, check=True)
        
        # Add DLL overrides registry entry to master template
        print("Adding DLL override registry entry to master WINEPREFIX...")
        reg_env = os.environ.copy()
        reg_env["WINEPREFIX"] = str(master_prefix_dir)
        reg_env["WINEDEBUG"] = "-all"
        reg_env["DISPLAY"] = xvfb_display
        reg_env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        reg_env["GALLIUM_DRIVER"] = "llvmpipe"
        subprocess.run(
            ["wine", "reg", "add", "HKCU\\Software\\Wine\\DllOverrides", "/v", "version", "/t", "REG_SZ", "/d", "n,b", "/f"],
            env=reg_env,
            check=True
        )
        
        # Disable Wine audio backend to prevent 30-second ALSA/OpenAL device timeouts in headless VMs
        print("Disabling Wine audio driver in master WINEPREFIX...")
        subprocess.run(
            ["wine", "reg", "add", "HKCU\\Software\\Wine\\Drivers", "/v", "Audio", "/t", "REG_SZ", "/d", "", "/f"],
            env=reg_env,
            check=True
        )
        
        # Wait for wineserver to completely flush registry and shut down before cloning
        print("Waiting for master wineserver to flush registries and shutdown...")
        wait_env = os.environ.copy()
        wait_env["WINEPREFIX"] = str(master_prefix_dir)
        subprocess.run(["wineserver", "-w"], env=wait_env)

    processes = []
    ports = [12346 + i for i in range(num_instances)]
    print(f"Launching {num_instances} isolated Balatro instances...")
    
    for i, port in enumerate(ports):
        env = os.environ.copy()
        env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        env["GALLIUM_DRIVER"] = "llvmpipe"
        
        # Prevent inheriting PyTorch's 1-thread limit
        for thread_env in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]:
            if thread_env in env:
                del env[thread_env]
        
        # Isolate via WINEPREFIX on Linux
        wineprefix_dir = f"/dev/shm/wine_env_{port}"
        if os.path.exists(wineprefix_dir):
            try:
                shutil.rmtree(wineprefix_dir)
            except Exception as e:
                pass
        
        # Clone WINEPREFIX from template
        shutil.copytree(master_prefix_dir, wineprefix_dir, symlinks=True)
        
        temp_balatro_dir = get_or_create_balatro_appdata(wineprefix_dir)
        if not temp_balatro_dir:
            print(f"Error: AppData creation failed for WINEPREFIX {wineprefix_dir}")
            sys.exit(1)
            
        instance_mods_dir = temp_balatro_dir / "Mods"
        os.makedirs(instance_mods_dir, exist_ok=True)
        
        env["WINEPREFIX"] = wineprefix_dir
        env["WINEDLLOVERRIDES"] = "version=n,b"
        env["WINEDEBUG"] = "-all"
        env["ALSOFT_DRIVERS"] = "null"
        env["SDL_AUDIODRIVER"] = "dummy"
        
        # Copy mods
        for mod_path in original_mods_dir.iterdir():
            if mod_path.is_dir() and mod_path.name.lower() != "lovely":
                shutil.copytree(mod_path, instance_mods_dir / mod_path.name)
        
        # Copy profile settings (.jkr)
        for jkr_file in original_balatro_dir.glob("*.jkr"):
            dest = temp_balatro_dir / jkr_file.name
            if not dest.exists():
                shutil.copy2(jkr_file, dest)
                
        env["BALATROBOT_HOST"] = "127.0.0.1"
        env["BALATROBOT_PORT"] = str(port)
        env["BALATROBOT_FAST"] = "1"
        env["BALATROBOT_GAMESPEED"] = "10"
        env["BALATROBOT_ANIMATION_FPS"] = "60"
        env["BALATROBOT_FPS_CAP"] = "250"
        env["BALATROBOT_NO_SHADERS"] = "1"
        env["BALATROBOT_HEADLESS"] = "1"
        env["BALATROBOT_RENDER_ON_API"] = "0"
        env["DISPLAY"] = xvfb_display
        
        cmd_launch = ["wine", str(balatro_exe)]
        
        stdout_log_path = original_balatro_dir / f"instance_{port}_stdout.log"
        stderr_log_path = original_balatro_dir / f"instance_{port}_stderr.log"
        stdout_file = open(stdout_log_path, "w", encoding="utf-8", errors="ignore")
        stderr_file = open(stderr_log_path, "w", encoding="utf-8", errors="ignore")
        
        p = subprocess.Popen(
            cmd_launch,
            cwd=str(balatro_exe.parent),
            env=env,
            stdout=stdout_file,
            stderr=stderr_file
        )
        processes.append((p, stdout_file, stderr_file))
        # Stagger slightly to avoid lock contention
        time.sleep(0.5)
        
    print("Waiting for instances to initialize...")
    t_start = time.time()
    all_healthy = False
    while time.time() - t_start < 120:
        time.sleep(1.0)
        current_healthy = True
        for port in ports:
            passed, _ = check_health(port)
            if not passed:
                current_healthy = False
                break
        if current_healthy:
            all_healthy = True
            break
            
    if not all_healthy:
        print(f"Warning: Not all instances started successfully for N={num_instances}")
        return False, processes
        
    return True, processes

def make_env(url):
    def _init():
        return Monitor(BalatroEnv(base_url=url, deck="YELLOW", stake="WHITE"))
    return _init

def benchmark_n_instances(num_instances, balatro_exe, original_balatro_dir, original_mods_dir, xvfb_display):
    print(f"\n==========================================")
    print(f"BENCHMARKING N = {num_instances} INSTANCES")
    print(f"==========================================")
    
    # 1. Kill lingering processes
    kill_lingering_processes()
    
    # 2. Launch Balatro
    success, processes = launch_instances(num_instances, balatro_exe, original_balatro_dir, original_mods_dir, xvfb_display)
    if not success:
        print(f"Skipping benchmark for N={num_instances} due to startup failures.")
        terminate_processes(processes)
        return None
        
    # 3. Setup vectorized environment
    api_urls = [f"http://127.0.0.1:{12346 + i}" for i in range(num_instances)]
    print(f"Initializing SubprocVecEnv with {num_instances} environments...")
    env = SubprocVecEnv([make_env(url) for url in api_urls])
    
    # 4. Create model and run benchmark
    n_steps = 128
    batch_size = min(2048, n_steps * num_instances)
    
    model = PPO(
        "MultiInputPolicy",
        env,
        verbose=0,
        n_steps=n_steps,
        batch_size=batch_size,
        n_epochs=4,
        learning_rate=1e-4,
        clip_range=0.1,
        device="cpu",
    )
    
    print("Warming up (running 1 rollout iteration)...")
    try:
        model.learn(total_timesteps=n_steps * num_instances)
        print("Warmup complete. Starting benchmark (collecting 2 rollout iterations)...")
        
        t_start = time.time()
        model.learn(total_timesteps=n_steps * num_instances * 2)
        elapsed = time.time() - t_start
        steps = n_steps * num_instances * 2
        sps = steps / elapsed
        print(f"\nResult for N={num_instances}: {sps:.2f} steps/second (took {elapsed:.1f}s)")
    except Exception as e:
        print(f"Error during benchmark run: {e}")
        sps = None
        
    # 5. Cleanup current run
    env.close()
    terminate_processes(processes)
    clean_shm_env_dirs()
    
    return sps

def main():
    parser = argparse.ArgumentParser(description="Benchmark Balatro training speed across different instance counts.")
    parser.add_argument(
        "--instances", 
        type=str, 
        default="16,32,48,64,80", 
        help="Comma-separated list of instance counts (e.g. 16,32), or ranges (e.g. 1-96 or 1-96-4)."
    )
    args = parser.parse_args()
    
    # Parse instances list or ranges
    instance_counts = []
    try:
        for part in args.instances.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                subparts = part.split("-")
                if len(subparts) == 2:
                    start = int(subparts[0])
                    end = int(subparts[1])
                    instance_counts.extend(range(start, end + 1))
                elif len(subparts) == 3:
                    start = int(subparts[0])
                    end = int(subparts[1])
                    step = int(subparts[2])
                    instance_counts.extend(range(start, end + 1, step))
                else:
                    raise ValueError(f"Invalid range format: {part}")
            elif part.isdigit():
                instance_counts.append(int(part))
            else:
                raise ValueError(f"Invalid format: {part}")
    except Exception as e:
        print(f"Error parsing --instances: {e}")
        print("Provide a comma-separated list like '16,32,48' or ranges like '1-96' or '1-96-4'")
        sys.exit(1)
        
    if not instance_counts:
        print("Error: No instance counts to test.")
        sys.exit(1)
        
    # Remove duplicates and sort to run from smallest to largest
    instance_counts = sorted(list(set(instance_counts)))
    print(f"Configurations to test: {instance_counts}")
    
    # Find Balatro paths
    balatro_exe = REPO_ROOT / "Balatro.v1.0.0i" / "Balatro.exe"
    if not balatro_exe.exists():
        print(f"Error: Balatro.exe not found at {balatro_exe}")
        sys.exit(1)
        
    wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
    original_balatro_dir = find_balatro_appdata(wineprefix)
    if not original_balatro_dir or not original_balatro_dir.exists():
        print(f"Error: Balatro AppData not found. Please run setup_mods.py first.")
        sys.exit(1)
        
    original_mods_dir = original_balatro_dir / "Mods"
    if not original_mods_dir.exists():
        print(f"Error: Mods directory not found at {original_mods_dir}")
        sys.exit(1)
        
    # Start Xvfb once
    xvfb_proc = None
    xvfb_display = ":99"
    display_active = False
    lock_file = "/tmp/.X99-lock"
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            display_active = True
        except (ProcessLookupError, PermissionError, ValueError, FileNotFoundError):
            pass
            
    if display_active:
        print("Reusing active display server on :99...")
    else:
        try:
            xvfb_proc = start_xvfb(99)
        except RuntimeError as e:
            print(f"Error starting Xvfb: {e}")
            sys.exit(1)
            
    results = {}
    
    try:
        for n in instance_counts:
            sps = benchmark_n_instances(n, balatro_exe, original_balatro_dir, original_mods_dir, xvfb_display)
            if sps is not None:
                results[n] = sps
                
        # Print final report
        print("\n\n==========================================")
        print("          BENCHMARK FINAL REPORT          ")
        print("==========================================")
        print(f"{'Instances':<15} | {'Steps/Second (SPS)':<20} | {'SPS per Instance':<20}")
        print("-" * 62)
        
        best_n = None
        best_sps = 0.0
        
        for n in sorted(results.keys()):
            sps = results[n]
            sps_per_inst = sps / n
            print(f"{n:<15} | {sps:<20.2f} | {sps_per_inst:<20.2f}")
            if sps > best_sps:
                best_sps = sps
                best_n = n
                
        print("-" * 62)
        if best_n is not None:
            print(f"\nOptimal configuration: {best_n} instances (yielding {best_sps:.2f} steps/second)")
        else:
            print("\nBenchmark failed to complete successfully for any configuration.")
        print("==========================================\n")
        
    finally:
        # Final cleanup
        kill_lingering_processes()
        clean_shm_env_dirs()
        if xvfb_proc:
            stop_xvfb(xvfb_proc)

if __name__ == "__main__":
    main()
