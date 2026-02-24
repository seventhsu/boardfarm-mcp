#!/bin/bash
# Zephyr Build Script - Wrapper for Docker-based builds
# Usage: ./zephyr-build.sh <board_name> <sample_path> [build_dir]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments
BOARD_NAME="${1:-nucleo_h743zi}"
SAMPLE_PATH="${2:-zephyr/samples/philosophers}"
BUILD_DIR="${3:-build}"

# Ensure Docker Compose is running
if ! docker compose ps | grep -q "zephyr-builder"; then
    echo "Starting zephyr-builder container..."
    cd "$PROJECT_ROOT"
    docker compose up -d zephyr-builder
    sleep 2
fi

echo "========================================"
echo "Zephyr Docker Build"
echo "========================================"
echo "Board:    $BOARD_NAME"
echo "Sample:   $SAMPLE_PATH"
echo "Build:    $BUILD_DIR"
echo "========================================"

# Run the build in container
cd "$PROJECT_ROOT"
docker compose exec -T zephyr-builder bash -c "
  export ZEPHYR_BASE=/home/user/zephyrproject/zephyr
  cd /home/user/zephyrproject
  west build -b '$BOARD_NAME' -d '/workspace/$BUILD_DIR' '$SAMPLE_PATH'
" 2>&1

BUILD_STATUS=$?

echo ""
echo "========================================"
if [ $BUILD_STATUS -eq 0 ]; then
    echo "✓ Build completed successfully!"
    echo "========================================"
    echo "Output files:"
    ls -la "$PROJECT_ROOT/$BUILD_DIR/zephyr/zephyr.elf" 2>/dev/null && echo "  - ELF: $BUILD_DIR/zephyr/zephyr.elf"
    ls -la "$PROJECT_ROOT/$BUILD_DIR/zephyr/zephyr.bin" 2>/dev/null && echo "  - BIN: $BUILD_DIR/zephyr/zephyr.bin"
    ls -la "$PROJECT_ROOT/$BUILD_DIR/zephyr/zephyr.hex" 2>/dev/null && echo "  - HEX: $BUILD_DIR/zephyr/zephyr.hex"
    exit 0
else
    echo "✗ Build failed!"
    echo "========================================"
    exit 1
fi
