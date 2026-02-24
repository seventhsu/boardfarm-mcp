#!/bin/bash
# Docker Shell - Interactive shell into zephyr-builder container
# Usage: ./docker-shell.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Ensure container is running
cd "$PROJECT_ROOT"
if ! docker compose ps | grep -q "zephyr-builder"; then
    echo "Starting zephyr-builder container..."
    docker compose up -d zephyr-builder
    sleep 2
fi

echo "========================================"
echo "Entering Zephyr Builder Container"
echo "========================================"
echo "ZEPHYR_BASE:          /home/user/zephyrproject/zephyr"
echo "ZEPHYR_SDK:           /opt/zephyr-sdk"
echo "Available samples:    /home/user/zephyrproject/zephyr/samples"
echo ""
echo "Example commands:"
echo "  west build -b nucleo_h743zi zephyr/samples/philosophers"
echo "  west boards | grep nucleo"
echo "========================================"
echo ""

# Open interactive shell
docker compose exec zephyr-builder bash -c "export ZEPHYR_BASE=/home/user/zephyrproject/zephyr && cd /home/user/zephyrproject && bash"
