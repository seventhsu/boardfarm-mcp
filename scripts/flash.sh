#!/bin/bash
# Flash Zephyr binary to target board
# Usage: ./flash.sh [build_dir] [address]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

BUILD_DIR="${1:-build}"
FLASH_ADDR="${2:-0x08000000}"
BIN_FILE="$PROJECT_ROOT/$BUILD_DIR/zephyr/zephyr.bin"

echo "========================================"
echo "Flash Zephyr Binary"
echo "========================================"
echo "Binary:   $BIN_FILE"
echo "Address:  $FLASH_ADDR"
echo "========================================"

# Check if binary exists
if [ ! -f "$BIN_FILE" ]; then
    echo "Error: Binary file not found: $BIN_FILE"
    echo "Did you build the project first?"
    exit 1
fi

# Check for st-flash
if ! command -v st-flash &> /dev/null; then
    echo "Error: st-flash not found. Install stlink-tools:"
    echo "  sudo apt install stlink-tools"
    exit 1
fi

# Flash the binary
echo "Flashing..."
st-flash write "$BIN_FILE" "$FLASH_ADDR"

echo ""
echo "✓ Flash completed!"
