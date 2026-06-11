import os
import sys

# Limit CPU threads to avoid synchronization overhead on high-core VMs (like 64-core GCP)
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

import subprocess
import time
import urllib.request
import json
import argparse
import signal
from pathlib import Path


def start_xvfb(display_num=99):
    """Start a standalone Xvfb server and wait for it to be ready.
    
    Returns the Xvfb subprocess.Popen object.
    """
    # Kill any existing Xvfb on this display and clean up stale files
    lock_file = f"/tmp/.X{display_num}-lock"
    socket_file = f"/tmp/.X11-unix/X{display_num}"

    # Try to read PID from lock file and kill that process
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(old_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            print(f"  Killed stale Xvfb (PID {old_pid}) on display :{display_num}")
        except (ValueError, ProcessLookupError, PermissionError, FileNotFoundError):
            pass

    # Also pkill any Xvfb that might be on this display
    subprocess.run(
        ["pkill", "-f", f"Xvfb :{display_num}"],
        capture_output=True
    )
    time.sleep(0.3)

    for f in [lock_file, socket_file]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    print(f"Starting Xvfb on display :{display_num}...")
    xvfb_env = os.environ.copy()
    xvfb_env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
    xvfb_env["GALLIUM_DRIVER"] = "llvmpipe"
    xvfb_proc = subprocess.Popen(
        [
            "Xvfb", f":{display_num}",
            "-screen", "0", "1024x768x24",
            "-ac",  # disable access control for simplicity
            "+extension", "GLX",  # ensure GLX extension is loaded
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=xvfb_env
    )

    # Wait for Xvfb to be ready (lock file appears)
    for _ in range(50):  # up to 5 seconds
        if os.path.exists(lock_file):
            break
        # Check if process died
        if xvfb_proc.poll() is not None:
            stderr_output = xvfb_proc.stderr.read().decode(errors="ignore")
            raise RuntimeError(f"Xvfb failed to start (exit {xvfb_proc.returncode}): {stderr_output}")
        time.sleep(0.1)
    else:
        # Last chance check
        if not os.path.exists(lock_file):
            xvfb_proc.kill()
            raise RuntimeError(f"Xvfb did not create lock file {lock_file} within 5 seconds")

    print(f"Xvfb started successfully on :{display_num} (PID: {xvfb_proc.pid})")
    return xvfb_proc


def stop_xvfb(xvfb_proc):
    """Gracefully stop a Xvfb process."""
    if xvfb_proc is None:
        return
    try:
        xvfb_proc.terminate()
        xvfb_proc.wait(timeout=5)
    except Exception:
        try:
            xvfb_proc.kill()
        except Exception:
            pass
    print("Xvfb server stopped.")

def find_balatro_appdata(prefix_path):
    """Finds the Balatro AppData directory in a given Wine prefix."""
    users_dir = Path(prefix_path) / "drive_c" / "users"
    if not users_dir.exists():
        return None
    for p in users_dir.iterdir():
        if p.is_dir() and p.name not in (".", ".."):
            appdata_roaming = p / "AppData" / "Roaming" / "Balatro"
            if appdata_roaming.exists():
                return appdata_roaming
            appdata_alt = p / "Application Data" / "Balatro"
            if appdata_alt.exists():
                return appdata_alt
    return None

def get_or_create_balatro_appdata(prefix_path):
    """Gets or creates the Balatro AppData directory in a given Wine prefix."""
    users_dir = Path(prefix_path) / "drive_c" / "users"
    if not users_dir.exists():
        return None
    for p in users_dir.iterdir():
        if p.is_dir() and p.name not in (".", ".."):
            appdata_roaming = p / "AppData" / "Roaming"
            if appdata_roaming.exists():
                balatro_dir = appdata_roaming / "Balatro"
                balatro_dir.mkdir(parents=True, exist_ok=True)
                return balatro_dir
            appdata_alt = p / "Application Data"
            if appdata_alt.exists():
                balatro_dir = appdata_alt / "Balatro"
                balatro_dir.mkdir(parents=True, exist_ok=True)
                return balatro_dir
    return None

def check_health(port):
    url = f"http://127.0.0.1:{port}"
    data = {"jsonrpc": "2.0", "method": "health", "params": {}, "id": 1}
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200, None
    except Exception as e:
        return False, str(e)

def terminate_processes(processes):
    print("Terminating Balatro processes...")
    for p, stdout_file, stderr_file in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        finally:
            if stdout_file and hasattr(stdout_file, "close"):
                try:
                    stdout_file.close()
                except Exception:
                    pass
            if stderr_file and hasattr(stderr_file, "close"):
                try:
                    stderr_file.close()
                except Exception:
                    pass
    print("All Balatro processes cleaned up.")

def dump_instance_logs(port, original_balatro_dir, lines_count=40):
    """Prints the last N lines of stdout, stderr, and lovely logs for a given instance."""
    print(f"\n==========================================")
    print(f"  DIAGNOSTIC LOG DUMP FOR PORT {port}")
    print(f"==========================================")
    
    # 1. Balatro Stdout log
    stdout_log = original_balatro_dir / f"instance_{port}_stdout.log"
    if stdout_log.exists():
        print(f"\n[Last {lines_count} lines of {stdout_log.name}]:")
        try:
            with open(stdout_log, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                print("".join(lines[-lines_count:]))
        except Exception as e:
            print(f"Could not read stdout log: {e}")
    else:
        print(f"\nStdout log not found at {stdout_log}")
        
    # 2. Balatro Stderr log
    stderr_log = original_balatro_dir / f"instance_{port}_stderr.log"
    if stderr_log.exists():
        print(f"\n[Last {lines_count} lines of {stderr_log.name}]:")
        try:
            with open(stderr_log, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                print("".join(lines[-lines_count:]))
        except Exception as e:
            print(f"Could not read stderr log: {e}")
    else:
        print(f"\nStderr log not found at {stderr_log}")

    # 3. Lovely logs inside the Wine prefix (for Linux)
    if sys.platform == "linux":
        wineprefix_dir = Path(f"/tmp/wine_env_{port}")
        temp_balatro_dir = find_balatro_appdata(wineprefix_dir)
        if temp_balatro_dir:
            lovely_log_dir = temp_balatro_dir / "Mods" / "lovely" / "log"
            if lovely_log_dir.exists():
                log_files = list(lovely_log_dir.glob("lovely-*.log"))
                if log_files:
                    newest_log = max(log_files, key=os.path.getmtime)
                    print(f"\n[Last {lines_count} lines of Lovely log {newest_log.name}]:")
                    try:
                        with open(newest_log, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                            print("".join(lines[-lines_count:]))
                    except Exception as e:
                        print(f"Could not read Lovely log: {e}")
                else:
                    print("\nNo Lovely log files found.")
            else:
                print(f"\nLovely log directory not found at {lovely_log_dir}")
        else:
            print("\nCould not locate Balatro AppData inside prefix for Lovely logs.")
    print(f"==========================================\n")


def main():
    parser = argparse.ArgumentParser(description="Run parallel Balatro bot PPO training with managed instances.")
    parser.add_argument("--num-instances", type=int, default=2, help="Number of Balatro instances to run in parallel.")
    parser.add_argument("--total-timesteps", type=int, default=200000, help="Total training timesteps.")
    parser.add_argument("--resume", type=str, default=None, help="Path to a saved PPO model to resume training from.")
    parser.add_argument("--learning-rate", type=float, default=None, help="Override PPO learning rate.")
    parser.add_argument("--ent-coef", type=float, default=None, help="Override entropy coefficient.")
    parser.add_argument("--device", type=str, default=None, help="Override target device (cpu/cuda/auto).")
    parser.add_argument("--deck", type=str, default="YELLOW", help="Deck to use for training. Default: YELLOW.")
    parser.add_argument("--stake", type=str, default="WHITE", help="Stake level. Default: WHITE.")
    args = parser.parse_args()

    REPO_ROOT = Path(__file__).resolve().parent
    balatro_exe = REPO_ROOT / "Balatro.v1.0.0i" / "Balatro.exe"
    if not balatro_exe.exists():
        print(f"Error: Balatro.exe not found at {balatro_exe}")
        sys.exit(1)

    if sys.platform == "linux":
        # Resolve Wine prefix AppData path for master mods
        wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
        original_balatro_dir = find_balatro_appdata(wineprefix)
    else:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            print("Error: APPDATA environment variable not found.")
            sys.exit(1)
        original_balatro_dir = Path(appdata) / "Balatro"

    if not original_balatro_dir or not original_balatro_dir.exists():
        print("Error: Balatro AppData directory not found. Please run setup_mods.py first.")
        sys.exit(1)
        
    original_mods_dir = original_balatro_dir / "Mods"
    if not original_mods_dir.exists():
        print(f"Error: Mods directory not found at {original_mods_dir}")
        sys.exit(1)
    
    ports = [12346 + i for i in range(args.num_instances)]
    processes = []
    
    # Clean any orphaned Balatro processes first
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/f", "/im", "Balatro.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "Balatro.exe"], capture_output=True)
    except Exception:
        pass

    # Start Xvfb on Linux before launching any instances (unless a display server is already active)
    xvfb_proc = None
    xvfb_display = ":99"
    if sys.platform == "linux":
        display_active = False
        lock_file = "/tmp/.X99-lock"
        if os.path.exists(lock_file):
            try:
                with open(lock_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                display_active = True
            except ProcessLookupError:
                pass
            except PermissionError:
                display_active = True
            except Exception:
                pass
                
        if display_active:
            print("Detected an active display server on :99 (Xorg/Xvfb). Skipping Xvfb launch and using existing display...")
        else:
            try:
                xvfb_proc = start_xvfb(99)
            except RuntimeError as e:
                print(f"Error: Failed to start Xvfb: {e}")
                sys.exit(1)
            
        # Initialize master WINEPREFIX template once to avoid slow sequential wineboots
        master_prefix_dir = Path("/tmp/wine_master")
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

    print(f"Launching {args.num_instances} Balatro instances...")
    for port in ports:
        env = os.environ.copy()
        env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        env["GALLIUM_DRIVER"] = "llvmpipe"
        
        # Prevent Balatro/Wine processes from inheriting PyTorch's 1-thread limit
        for thread_env in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"]:
            if thread_env in env:
                del env[thread_env]
        
        if sys.platform == "linux":
            # Isolate via WINEPREFIX on Linux
            wineprefix_dir = f"/tmp/wine_env_{port}"
            if os.path.exists(wineprefix_dir):
                import shutil
                try:
                    shutil.rmtree(wineprefix_dir)
                except Exception as e:
                    print(f"Warning: Could not clean {wineprefix_dir}: {e}")
            
            # Clone WINEPREFIX from template
            print(f"  Cloning WINEPREFIX from template for port {port}...")
            import shutil
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
        else:
            instance_mods_dir = original_balatro_dir / f"Mods_Instance_{port}"
            # Clean and copy mods to isolated folder
            if instance_mods_dir.exists():
                import shutil
                try:
                    shutil.rmtree(instance_mods_dir)
                except Exception as e:
                    print(f"Warning: Could not clean {instance_mods_dir}: {e}")
            os.makedirs(instance_mods_dir, exist_ok=True)
            env["LOVELY_MOD_DIR"] = str(instance_mods_dir)
        
        print(f"Copying mods for instance on port {port}...")
        for mod_path in original_mods_dir.iterdir():
            if mod_path.is_dir() and mod_path.name.lower() != "lovely":
                import shutil
                shutil.copytree(mod_path, instance_mods_dir / mod_path.name)
        
        # Copy settings/profile files (.jkr) from master to instance
        # Without these, the game crashes with "attempt to index field 'tutorial_progress' (a nil value)"
        if sys.platform == "linux" and temp_balatro_dir:
            import shutil
            for jkr_file in original_balatro_dir.glob("*.jkr"):
                dest = temp_balatro_dir / jkr_file.name
                if not dest.exists():
                    shutil.copy2(jkr_file, dest)
                    print(f"  Copied {jkr_file.name} to instance prefix")
                
        env["BALATROBOT_HOST"] = "127.0.0.1"
        env["BALATROBOT_PORT"] = str(port)
        env["BALATROBOT_FAST"] = "1"
        env["BALATROBOT_GAMESPEED"] = "100000"  # Was 10000 — cranked up further for 12-instance CPU contention
        env["BALATROBOT_ANIMATION_FPS"] = "100000"  # Was 10000 — same rationale
        env["BALATROBOT_FPS_CAP"] = "250"
        env["BALATROBOT_NO_SHADERS"] = "1"
        env["BALATROBOT_HEADLESS"] = "1"
        env["BALATROBOT_RENDER_ON_API"] = "0"
        
        if sys.platform == "linux":
            env["DISPLAY"] = xvfb_display
            cmd_launch = [
                "wine",
                str(balatro_exe)
            ]
        else:
            cmd_launch = [str(balatro_exe)]
            
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
        print(f"Started instance on port {port} (PID: {p.pid})")
        time.sleep(2.0)
        
    print("Waiting for instances to initialize (polling for up to 120 seconds)...")
    t_start = time.time()
    all_healthy = False
    while time.time() - t_start < 120:
        time.sleep(2.0)
        
        # Check if any process has exited early
        for p, _, _ in processes:
            if p.poll() is not None:
                print(f"Warning: Balatro process (PID {p.pid}) terminated early with exit code {p.poll()}")
                
        # Check health of all instances
        current_healthy = True
        for port in ports:
            passed, error = check_health(port)
            if not passed:
                current_healthy = False
                break
        if current_healthy:
            print(f"All instances are healthy and initialized after {time.time() - t_start:.1f} seconds!")
            all_healthy = True
            break
    else:
        # Final evaluation check and log dump for failures
        all_healthy = True
        for port in ports:
            passed, error = check_health(port)
            if passed:
                print(f"Health check PASSED for port {port}")
            else:
                print(f"Health check FAILED for port {port}: {error}")
                all_healthy = False
                
                # Print process status
                idx = ports.index(port)
                proc = processes[idx][0]
                exit_code = proc.poll()
                print(f"Process PID: {proc.pid}, status (None=running, integer=exited): {exit_code}")
                
                try:
                    dump_instance_logs(port, original_balatro_dir)
                except Exception as de:
                    print(f"Failed to dump logs: {de}")
            
    if not all_healthy:
        print("Not all instances started successfully. Aborting training.")
        terminate_processes(processes)
        sys.exit(1)
        
    print(f"Starting training session for {args.total_timesteps} timesteps...")
    
    # Forward arguments to train.py
    cmd = [
        sys.executable, "-m", "src.training.train",
        "--total-timesteps", str(args.total_timesteps)
    ]
    if args.resume:
        cmd.extend(["--resume", args.resume])
    if args.learning_rate is not None:
        cmd.extend(["--learning-rate", str(args.learning_rate)])
    if args.ent_coef is not None:
        cmd.extend(["--ent-coef", str(args.ent_coef)])
    if args.device:
        cmd.extend(["--device", args.device])
    cmd.extend(["--deck", args.deck])
    cmd.extend(["--stake", args.stake])
    cmd.extend(["--num-instances", str(args.num_instances)])

    try:
        # Use python from active virtualenv if present
        if sys.platform == "win32":
            venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
        else:
            venv_python = REPO_ROOT / ".venv" / "bin" / "python"
            
        python_exe = str(venv_python) if venv_python.exists() else sys.executable
        cmd[0] = python_exe
        
        subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            check=True
        )
        print("Training session finished successfully!")
    except KeyboardInterrupt:
        print("Training interrupted by user. Cleaning up...")
        # Dump logs for all instances to help debug hang
        for port in ports:
            try:
                dump_instance_logs(port, original_balatro_dir)
            except Exception as de:
                print(f"Failed to dump logs for port {port}: {de}")
    except Exception as e:
        print(f"Error during training: {e}")
        # Dump logs for all instances
        for port in ports:
            try:
                dump_instance_logs(port, original_balatro_dir)
            except Exception as de:
                print(f"Failed to dump logs for port {port}: {de}")
    finally:
        terminate_processes(processes)
        stop_xvfb(xvfb_proc)

if __name__ == "__main__":
    main()
