import os
import sys
import shutil
import time
import subprocess
import urllib.request
import json
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
BALATRO_EXE = REPO_ROOT / "Balatro.v1.0.0i" / "Balatro.exe"
VERSION_DLL = REPO_ROOT / "Balatro.v1.0.0i" / "version.dll"

def get_system_metrics():
    print("--- [1/6] System Performance & Resources ---")
    # CPU info
    cpu_count = os.cpu_count()
    print(f"  CPU Cores Count: {cpu_count}")
    
    # Load Average (Linux only)
    if sys.platform == "linux":
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip()
                print(f"  System Load Average (1m, 5m, 15m): {load}")
        except Exception as e:
            print(f"  Failed to read load average: {e}")
            
        try:
            with open("/proc/meminfo", "r") as f:
                mem_lines = f.readlines()
            mem_total = 0
            mem_free = 0
            mem_available = 0
            for line in mem_lines:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1]) // 1024
                elif line.startswith("MemFree:"):
                    mem_free = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1]) // 1024
            print(f"  Memory: Total={mem_total}MB, Available={mem_available}MB, Free={mem_free}MB")
        except Exception as e:
            print(f"  Failed to read memory info: {e}")
    else:
        print("  System metrics only fully supported on Linux.")
        
    # Disk Usage
    try:
        total, used, free = shutil.disk_usage("/")
        print(f"  Disk Usage (/): Total={total // (2**30)}GB, Used={used // (2**30)}GB, Free={free // (2**30)}GB")
    except Exception as e:
        print(f"  Failed to read disk usage: {e}")

def check_dependencies():
    print("\n--- [2/6] Dependencies & Path Integrity ---")
    # Game Exe
    if BALATRO_EXE.exists():
        print(f"  [OK] Balatro.exe found: {BALATRO_EXE}")
        print(f"       File Size: {BALATRO_EXE.stat().st_size / (1024*1024):.2f} MB")
    else:
        print(f"  [FAIL] Balatro.exe NOT found at {BALATRO_EXE}")
        
    # version.dll (Lovely)
    if VERSION_DLL.exists():
        print(f"  [OK] version.dll (Lovely Injector) found: {VERSION_DLL}")
        print(f"       File Size: {VERSION_DLL.stat().st_size / 1024:.2f} KB")
    else:
        print(f"  [FAIL] version.dll NOT found at {VERSION_DLL}. Lovely injection will fail!")
        
    # Executables on PATH
    for cmd in ["wine", "Xvfb", "wineserver"]:
        path = shutil.which(cmd)
        if path:
            print(f"  [OK] '{cmd}' available on PATH: {path}")
        else:
            print(f"  [FAIL] '{cmd}' is NOT available on PATH!")

def run_api_call(port, method, params=None):
    url = f"http://127.0.0.1:{port}"
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 999
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    t_start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode('utf-8'))
            dt = time.monotonic() - t_start
            return res, dt, None
    except Exception as e:
        dt = time.monotonic() - t_start
        return None, dt, str(e)

def find_balatro_appdata(prefix_path):
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

def diagnose_logs(port, wineprefix_dir):
    print("\n--- [5/6] Analysing Instance Log Outputs ---")
    stdout_log = Path(f"/tmp/balatro_diag_stdout.log")
    stderr_log = Path(f"/tmp/balatro_diag_stderr.log")
    
    # Analyze stderr for Wine/graphics issues
    if stderr_log.exists():
        print(f"\n[Last 15 lines of Stderr]:")
        with open(stderr_log, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for l in lines[-15:]:
                print(f"  stderr: {l.strip()}")
                
    # Analyze Lovely Log for hooks status
    temp_balatro_dir = find_balatro_appdata(wineprefix_dir)
    if temp_balatro_dir:
        lovely_log_dir = temp_balatro_dir / "Mods" / "lovely" / "log"
        if lovely_log_dir.exists():
            log_files = list(lovely_log_dir.glob("lovely-*.log"))
            if log_files:
                newest_log = max(log_files, key=os.path.getmtime)
                print(f"\n[Lovely Log contents: {newest_log.name}]:")
                with open(newest_log, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # Check for our Diagnostic outputs
                print(f"  - Total log lines: {len(content.splitlines())}")
                
                # Highlight hooks
                lovely_injected = "version.dll" in content or "lovely" in content.lower()
                print(f"  - Lovely Injector loaded: {'[OK]' if lovely_injected else '[FAIL]'}")
                
                moveable_active = "[DIAGNOSTIC] Moveable.move_xy" in content
                print(f"  - Moveable.move_xy easing bypass hook executed: {'[OK]' if moveable_active else '[FAIL/NOT_TRIGGERED_YET]'}")
                
                event_active = "[DIAGNOSTIC] EventManager.update" in content
                print(f"  - EventManager.update 10x multiplier hook executed: {'[OK]' if event_active else '[FAIL/NOT_TRIGGERED_YET]'}")
                
                # Show any error logs in Lovely
                errors = [line for line in content.splitlines() if "error" in line.lower() or "fail" in line.lower()]
                if errors:
                    print(f"  - [WARNING] Found {len(errors)} error/fail references in Lovely Log:")
                    for e in errors[:5]:
                        print(f"    * {e}")
                else:
                    print("  - [OK] No error/fail lines in Lovely Log.")
            else:
                print("  - [FAIL] No Lovely log files found inside logs directory.")
        else:
            print(f"  - [FAIL] Lovely log directory NOT found at {lovely_log_dir}")
    else:
        print("  - [FAIL] Could not locate Balatro AppData inside prefix.")

def test_debug_instance():
    print("\n--- [3/6] Starting Debug isolated Instance ---")
    port = 12350
    wineprefix_dir = Path("/tmp/wine_diag")
    master_prefix_dir = Path("/tmp/wine_master")
    
    # 1. Clean up old prefix
    if wineprefix_dir.exists():
        shutil.rmtree(wineprefix_dir)
        
    # 2. Clone prefix from master if exists, otherwise initialize fresh prefix
    if master_prefix_dir.exists():
        print(f"  Cloning WINEPREFIX from template /tmp/wine_master...")
        shutil.copytree(master_prefix_dir, wineprefix_dir, symlinks=True)
    else:
        print(f"  Master prefix template NOT found. Initializing fresh WINEPREFIX at {wineprefix_dir}...")
        wineprefix_dir.mkdir(parents=True, exist_ok=True)
        boot_env = os.environ.copy()
        boot_env["WINEPREFIX"] = str(wineprefix_dir)
        boot_env["WINEDEBUG"] = "-all"
        boot_env["DISPLAY"] = ":99"
        boot_env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        boot_env["GALLIUM_DRIVER"] = "llvmpipe"
        subprocess.run(["wineboot", "-u"], env=boot_env, check=True)
        
        # Add DLL overrides registry entry
        print("  Adding DLL override registry entry to debug WINEPREFIX...")
        reg_env = os.environ.copy()
        reg_env["WINEPREFIX"] = str(wineprefix_dir)
        reg_env["WINEDEBUG"] = "-all"
        reg_env["DISPLAY"] = ":99"
        reg_env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
        reg_env["GALLIUM_DRIVER"] = "llvmpipe"
        subprocess.run(
            ["wine", "reg", "add", "HKCU\\Software\\Wine\\DllOverrides", "/v", "version", "/t", "REG_SZ", "/d", "n,b", "/f"],
            env=reg_env,
            check=True
        )
        
        # Wait for wineserver to flush registry
        print("  Waiting for wineserver to flush registry...")
        wait_env = os.environ.copy()
        wait_env["WINEPREFIX"] = str(wineprefix_dir)
        subprocess.run(["wineserver", "-w"], env=wait_env)
        
    # Resolve original_balatro_dir
    wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
    original_balatro_dir = find_balatro_appdata(wineprefix)
    if not original_balatro_dir or not original_balatro_dir.exists():
        print("  [FAIL] Original Balatro AppData directory not found in ~/.wine.")
        return

    # Check isolated AppData mods copy
    temp_balatro_dir = get_or_create_balatro_appdata(wineprefix_dir)
    if not temp_balatro_dir:
        print("  [FAIL] AppData folder creation failed inside debug WINEPREFIX.")
        return
        
    # Copy mods and profile
    print("  Copying mods to debug WINEPREFIX...")
    instance_mods_dir = temp_balatro_dir / "Mods"
    instance_mods_dir.mkdir(parents=True, exist_ok=True)
    
    original_mods_dir = original_balatro_dir / "Mods"
    if original_mods_dir.exists():
        for mod_path in original_mods_dir.iterdir():
            if mod_path.is_dir() and mod_path.name.lower() != "lovely":
                shutil.copytree(mod_path, instance_mods_dir / mod_path.name, dirs_exist_ok=True)
                
    # Copy profile files (.jkr)
    print("  Copying profile files to debug WINEPREFIX...")
    for jkr_file in original_balatro_dir.glob("*.jkr"):
        dest = temp_balatro_dir / jkr_file.name
        if not dest.exists():
            shutil.copy2(jkr_file, dest)
        
    # Launch via Wine + Xvfb
    print("  Launching Balatro under Xvfb (display :99)...")
    env = os.environ.copy()
    env["WINEPREFIX"] = str(wineprefix_dir)
    env["WINEDLLOVERRIDES"] = "version=n,b"
    env["WINEDEBUG"] = "-all"
    env["DISPLAY"] = ":99"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    
    env["BALATROBOT_HOST"] = "127.0.0.1"
    env["BALATROBOT_PORT"] = str(port)
    env["BALATROBOT_FAST"] = "1"
    env["BALATROBOT_GAMESPEED"] = "100"
    env["BALATROBOT_ANIMATION_FPS"] = "600"
    env["BALATROBOT_FPS_CAP"] = "250"
    env["BALATROBOT_NO_SHADERS"] = "1"
    env["BALATROBOT_HEADLESS"] = "1"
    env["BALATROBOT_RENDER_ON_API"] = "0"

    stdout_log = open("/tmp/balatro_diag_stdout.log", "w")
    stderr_log = open("/tmp/balatro_diag_stderr.log", "w")
    
    proc = subprocess.Popen(
        ["wine", str(BALATRO_EXE)],
        cwd=str(BALATRO_EXE.parent),
        env=env,
        stdout=stdout_log,
        stderr=stderr_log
    )
    
    print(f"  Instance started with PID {proc.pid}. Waiting for boot healthcheck...")
    
    booted = False
    for attempt in range(35):
        time.sleep(1.0)
        res, dt, err = run_api_call(port, "health")
        if res and res.get("result") == "ok":
            print(f"  [OK] Health check passed in {dt:.3f}s after {attempt+1} seconds.")
            booted = True
            break
        elif proc.poll() is not None:
            print(f"  [FAIL] Balatro process terminated early with exit code {proc.poll()}.")
            break
    else:
        print("  [FAIL] API failed to respond within 35 seconds.")
        
    if booted:
        print("\n--- [4/6] Running API Transactions & Latency Test ---")
        
        # 1. Fetch gamestate
        print("  --> Fetching Initial Gamestate...")
        res, dt, err = run_api_call(port, "gamestate")
        if res and "result" in res:
            state_name = res["result"].get("state", "UNKNOWN")
            print(f"      [OK] Received state '{state_name}' in {dt:.3f}s.")
        else:
            print(f"      [FAIL] Failed to fetch gamestate: {err or res}")
            
        # 2. Start Game Run
        print("  --> Starting new game run (YELLOW, WHITE)...")
        res, dt, err = run_api_call(port, "start", {"deck": "YELLOW", "stake": "WHITE"})
        if res and "result" in res:
            state_name = res["result"].get("state", "UNKNOWN")
            print(f"      [OK] Game started successfully. Transitioned to '{state_name}' in {dt:.3f}s.")
        else:
            print(f"      [FAIL] Failed to start run: {err or res}")
            
        # 3. Select Blind
        print("  --> Selecting Small Blind...")
        res, dt, err = run_api_call(port, "select")
        if res and "result" in res:
            state_name = res["result"].get("state", "UNKNOWN")
            print(f"      [OK] Selected blind. State is '{state_name}' in {dt:.3f}s.")
        else:
            print(f"      [FAIL] Failed to select blind: {err or res}")
            
        # 4. Play a card (Let's fetch hands and play card 0)
        print("  --> Simulating play action (card index 0)...")
        # Play first card in the hand index [0]
        res, dt, err = run_api_call(port, "play", {"cards": [0]})
        if res and "result" in res:
            state_name = res["result"].get("state", "UNKNOWN")
            print(f"      [OK] Play action completed. State is '{state_name}' in {dt:.3f}s.")
            print(f"      [METRIC] Play latency: {dt:.3f} seconds.")
        else:
            print(f"      [FAIL] Play action failed or timed out: {err or res}")
            print(f"      [METRIC] Action took {dt:.3f}s before failing/timing out.")
            
    # Cleanup logs and process
    print("\n--- [6/6] Tearing down and cleaning up ---")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    stdout_log.close()
    stderr_log.close()
    
    # Print diagnostics report
    diagnose_logs(port, wineprefix_dir)
    
    # Remove diag prefix
    if wineprefix_dir.exists():
        shutil.rmtree(wineprefix_dir)
    print("\nDiagnostics complete!")

if __name__ == "__main__":
    get_system_metrics()
    check_dependencies()
    test_debug_instance()
