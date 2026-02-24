#!/bin/bash
# ST-Link and Serial Port Setup Script for MCP Board Farm
# Run with sudo

set -e

echo "=== MCP Board Farm Hardware Setup ==="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo: sudo $0"
    exit 1
fi

echo "[1/4] Installing udev rules for ST-Link..."
cp 50-stlink.rules /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger
echo "      Done!"

echo
echo "[2/4] Adding user to dialout group..."
usermod -aG dialout alial
echo "      Done!"

echo
echo "[3/4] Installing ARM toolchain..."
apt-get update
apt-get install -y gcc-arm-none-eabi stlink-tools openocd picocom
echo "      Done!"

echo
echo "[4/4] Verifying installation..."
if command -v arm-none-eabi-gcc &> /dev/null; then
    echo "      ARM GCC: $(arm-none-eabi-gcc --version | head -1)"
else
    echo "      WARNING: ARM GCC not found in PATH"
fi

if command -v st-flash &> /dev/null; then
    echo "      st-flash: $(st-flash --version 2>&1 | head -1)"
else
    echo "      WARNING: st-flash not found"
fi

if command -v openocd &> /dev/null; then
    echo "      OpenOCD: $(openocd --version 2>&1 | head -1)"
else
    echo "      WARNING: OpenOCD not found"
fi

echo
echo "=== Setup Complete ==="
echo
echo "IMPORTANT: Please log out and log back in for group changes to take effect."
echo
echo "After re-login, test with:"
echo "  pyocd list"
echo "  ls -la /dev/ttyACM0"
echo "  st-flash --probe"
echo
