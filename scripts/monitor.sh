#!/bin/bash
# Serial Monitor - Connect to board serial output
# Usage: ./monitor.sh [device] [baudrate]

set -e

DEVICE="${1:-/dev/ttyACM0}"
BAUDRATE="${2:-115200}"

echo "========================================"
echo "Serial Monitor"
echo "========================================"
echo "Device:   $DEVICE"
echo "Baudrate: $BAUDRATE"
echo "========================================"
echo ""
echo "Press Ctrl+A then X to exit"
echo ""

# Check for picocom
if command -v picocom &> /dev/null; then
    picocom -b "$BAUDRATE" "$DEVICE"
elif command -v minicom &> /dev/null; then
    minicom -D "$DEVICE" -b "$BAUDRATE"
else
    echo "Error: No serial monitor found. Install picocom or minicom:"
    echo "  sudo apt install picocom"
    exit 1
fi
