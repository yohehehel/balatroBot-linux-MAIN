import os
import sys
import subprocess
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Launch Balatro configured for optimal bot training speed.")
    parser.add_argument("--headless", action="store_true", help="Launch in headless mode (no window, fastest).")
    parser.add_argument("--visible-fast", action="store_true", help="Launch visible window but at 10x game speed (default).")
    args = parser.parse_args()

    # Default to visible fast mode if nothing is specified
    headless = args.headless
    
    # Path configuration
    balatro_exe = Path(r"c:\Users\Thomas\Desktop\python\balatroBot\Balatro.v1.0.0i\Balatro.exe")
    
    if not balatro_exe.exists():
        print(f"Error: Balatro.exe not found at {balatro_exe}")
        sys.exit(1)

    # Set up environment variables for BalatroBot mod
    env = os.environ.copy()
    env["BALATROBOT_HOST"] = "127.0.0.1"
    env["BALATROBOT_PORT"] = "12346"
    
    # Fast mode configuration (10x gamespeed, 60 FPS animations)
    env["BALATROBOT_FAST"] = "1"
    env["BALATROBOT_GAMESPEED"] = "10"
    env["BALATROBOT_ANIMATION_FPS"] = "60"
    env["BALATROBOT_FPS_CAP"] = "120"
    env["BALATROBOT_NO_SHADERS"] = "1"
    
    if headless:
        print("Launching Balatro in HEADLESS mode (no window, max simulation speed)...")
        env["BALATROBOT_HEADLESS"] = "1"
        env["BALATROBOT_RENDER_ON_API"] = "0"
    else:
        print("Launching Balatro in VISIBLE FAST mode (10x game speed, window visible)...")
        env["BALATROBOT_HEADLESS"] = "0"
        # Render on API mode only draws frames when requests are received, reducing GPU load
        env["BALATROBOT_RENDER_ON_API"] = "0"

    try:
        # Start Balatro process
        process = subprocess.Popen(
            [str(balatro_exe)],
            cwd=str(balatro_exe.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"Balatro started successfully (PID: {process.pid}).")
        print("You can now run your training script in another terminal.")
    except Exception as e:
        print(f"Failed to launch Balatro: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
