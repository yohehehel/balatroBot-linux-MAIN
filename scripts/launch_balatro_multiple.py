import os
import sys
import subprocess
import argparse
import shutil
import time
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
    xvfb_proc = subprocess.Popen(
        [
            "Xvfb", f":{display_num}",
            "-screen", "0", "1024x768x24",
            "-ac",  # disable access control for simplicity
            "+extension", "GLX",  # ensure GLX extension is loaded
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
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

def main():
    parser = argparse.ArgumentParser(description="Launch multiple Balatro instances configured for parallel bot training.")
    parser.add_argument("--num-instances", type=int, default=2, help="Number of Balatro instances to launch.")
    parser.add_argument("--visible", action="store_true", help="Launch visible windows instead of headless.")
    parser.add_argument("--base-port", type=int, default=12346, help="Starting port for JSON-RPC API.")
    args = parser.parse_args()

    REPO_ROOT = Path(__file__).resolve().parent.parent
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
        print(f"Error: Mods directory not found at {original_mods_dir}. Please run setup_mods.py first.")
        sys.exit(1)

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
            subprocess.run(["wineboot", "-u"], env=boot_env, check=True)
            
            # Add DLL overrides registry entry to master template
            print("Adding DLL override registry entry to master WINEPREFIX...")
            reg_env = os.environ.copy()
            reg_env["WINEPREFIX"] = str(master_prefix_dir)
            reg_env["WINEDEBUG"] = "-all"
            reg_env["DISPLAY"] = xvfb_display
            subprocess.run(
                ["wine", "reg", "add", "HKCU\\Software\\Wine\\DllOverrides", "/v", "version", "/t", "REG_SZ", "/d", "n,b", "/f"],
                env=reg_env,
                check=True
            )
            
            # Wait for wineserver to completely flush registry and shut down before cloning
            print("Waiting for master wineserver to flush registries and shutdown...")
            wait_env = os.environ.copy()
            wait_env["WINEPREFIX"] = str(master_prefix_dir)
            subprocess.run(["wineserver", "-w"], env=wait_env)

    processes = []
    print(f"Launching {args.num_instances} isolated Balatro instances starting on port {args.base_port}...")
    
    for i in range(args.num_instances):
        port = args.base_port + i
        env = os.environ.copy()
        
        if sys.platform == "linux":
            # Isolate via WINEPREFIX on Linux
            wineprefix_dir = f"/tmp/wine_env_{port}"
            if os.path.exists(wineprefix_dir):
                try:
                    shutil.rmtree(wineprefix_dir)
                except Exception as e:
                    print(f"  Warning: Could not clean {wineprefix_dir}: {e}")
            
            # Clone WINEPREFIX from template
            print(f"  Cloning WINEPREFIX from template for port {port}...")
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
            # Isolate mod folder for this port to prevent log collisions
            instance_mods_dir = original_balatro_dir / f"Mods_Instance_{port}"
            
            # Remove any existing instance mods dir to start fresh and avoid sharing state
            if instance_mods_dir.exists():
                try:
                    shutil.rmtree(instance_mods_dir)
                except Exception as e:
                    print(f"  Warning: Could not clean {instance_mods_dir}: {e}")
                        
            os.makedirs(instance_mods_dir, exist_ok=True)
            env["LOVELY_MOD_DIR"] = str(instance_mods_dir)
        
        # Copy required mod directories (smods, balatrobot)
        # We skip 'lovely' directory because it contains large log/dump files and will be auto-created
        print(f"  Copying mods for instance on port {port}...")
        for mod_path in original_mods_dir.iterdir():
            if mod_path.is_dir() and mod_path.name.lower() != "lovely":
                target_path = instance_mods_dir / mod_path.name
                shutil.copytree(mod_path, target_path)

        # Copy settings/profile files (.jkr) from master to instance
        # Without these, the game crashes with "attempt to index field 'tutorial_progress' (a nil value)"
        if sys.platform == "linux" and temp_balatro_dir:
            for jkr_file in original_balatro_dir.glob("*.jkr"):
                dest = temp_balatro_dir / jkr_file.name
                if not dest.exists():
                    shutil.copy2(jkr_file, dest)
                    print(f"    Copied {jkr_file.name} to instance prefix")
        env["BALATROBOT_HOST"] = "127.0.0.1"
        env["BALATROBOT_PORT"] = str(port)
        env["BALATROBOT_FAST"] = "1"
        env["BALATROBOT_GAMESPEED"] = "100"
        env["BALATROBOT_ANIMATION_FPS"] = "600"
        env["BALATROBOT_FPS_CAP"] = "250"
        env["BALATROBOT_NO_SHADERS"] = "1"
        
        if args.visible:
            print(f"  [{i+1}/{args.num_instances}] Launching VISIBLE instance on port {port}...")
            env["BALATROBOT_HEADLESS"] = "0"
            if sys.platform != "linux":
                env["BALATROBOT_RENDER_ON_API"] = "1"
            else:
                env["BALATROBOT_RENDER_ON_API"] = "1"
        else:
            print(f"  [{i+1}/{args.num_instances}] Launching HEADLESS instance on port {port}...")
            env["BALATROBOT_HEADLESS"] = "1"
            env["BALATROBOT_RENDER_ON_API"] = "0"
            
        # Keep file handles open in a list to prevent them from being closed
        # immediately on Windows before Balatro has finished starting up.
        if 'opened_files' not in locals():
            opened_files = []
            
        try:
            if sys.platform == "linux":
                env["DISPLAY"] = xvfb_display
                cmd_launch = [
                    "wine",
                    str(balatro_exe)
                ]
            else:
                cmd_launch = [str(balatro_exe)]
                
            process = subprocess.Popen(
                cmd_launch,
                cwd=str(balatro_exe.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(process)
            print(f"    Started successfully (PID: {process.pid}) at http://127.0.0.1:{port}")
        except Exception as e:
            print(f"    Failed to launch instance on port {port}: {e}")
            
        # Stagger the launches to avoid concurrent file lock collisions on settings.jkr on startup
        if i < args.num_instances - 1:
            print("  Waiting 2 seconds before launching the next instance to prevent startup collisions...")
            time.sleep(2.0)
            
    print("\nAll isolated instances started successfully.")
    print("You can now run your training script: python -m src.training.train")
    
    # We intentionally do not close the file handles here.
    # On Windows, closing them or letting them close when the launcher script exits
    # can cause the child processes to crash if the handles are not kept alive.
    # The OS will clean them up when the child processes themselves exit.

if __name__ == "__main__":
    main()
