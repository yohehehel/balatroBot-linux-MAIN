#!/bin/bash
# setup_linux_env.sh - Automates system and python dependencies setup for headless Linux Balatro-Bot.
set -e

echo "====================================================="
echo "  Setting up Balatro-Bot headless Linux environment  "
echo "====================================================="

# 1. Install system dependencies
echo "[1/3] Installing system packages..."
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wine64 wine xvfb python3-pip python3-venv zip unrar nvidia-driver-535 nvidia-utils-535 xserver-xorg-video-nvidia-535 xserver-xorg-core

# 2. Configure Python Virtual Environment
echo "[2/3] Initializing virtual environment (.venv)..."
if [ -d ".venv" ]; then
    echo "  .venv already exists. Skipping creation."
else
    python3 -m venv .venv
    echo "  Virtual environment created."
fi

# Activate virtualenv
source .venv/bin/activate

# 3. Install Python dependencies
echo "[3/3] Installing Python dependencies..."

# Check if uv is installed
if command -v uv &> /dev/null; then
    echo "  uv package manager detected. Using 'uv pip' for fast installation..."
    uv pip install --upgrade pip
    uv pip install torch --index-url https://download.pytorch.org/whl/cu121
    uv pip install -e .
    uv pip install tensorboard
else
    echo "  Using standard pip..."
    pip install --upgrade pip
    pip install torch --index-url https://download.pytorch.org/whl/cu121
    pip install -e .
    pip install tensorboard
fi

echo "====================================================="
echo "  Setup complete! To start using the environment:    "
echo "  source .venv/bin/activate                          "
echo "                                                     "
echo "  IMPORTANT: If NVIDIA drivers were installed for    "
echo "  the first time, please reboot the VM:              "
echo "  sudo reboot                                        "
echo "====================================================="
