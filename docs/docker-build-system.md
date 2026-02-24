# Docker-Based Zephyr Build System

This document describes the Docker-based Zephyr RTOS build system for MCP Board Farm.

## Overview

The build system uses the official `zephyrprojectrtos/zephyr-build` Docker image to provide a consistent, reproducible build environment without requiring native Zephyr SDK installation.

## Quick Start

### 1. Start the Build Container

```bash
cd mcp-boardfarm
docker compose up -d zephyr-builder
```

### 2. Build a Zephyr Sample

```bash
./scripts/zephyr-build.sh nucleo_h743zi zephyr/samples/philosophers
```

### 3. Flash to Board (requires connected board)

```bash
./scripts/flash.sh build
```

### 4. Monitor Serial Output

```bash
./scripts/monitor.sh /dev/ttyACM0 115200
```

## Docker Configuration

### docker-compose.yml

```yaml
services:
  zephyr-builder:
    image: zephyrprojectrtos/zephyr-build:latest
    volumes:
      - .:/workspace           # Project workspace
      - zephyr-cache:/home/user/zephyrproject  # Persistent Zephyr installation
      - /dev:/dev              # USB device access
    environment:
      - ZEPHYR_BASE=/home/user/zephyrproject/zephyr
      - ZEPHYR_SDK_INSTALL_DIR=/opt/zephyr-sdk
    privileged: true
```

### Volumes

- **Workspace** (`/workspace`): Maps to project root for build output
- **Zephyr Cache** (`zephyr-cache`): Persistent Zephyr installation and modules (downloaded once)

## Build Scripts

### zephyr-build.sh

Wrapper script for building Zephyr samples inside the container.

**Usage:**
```bash
./scripts/zephyr-build.sh <board> <sample_path> [build_dir]
```

**Examples:**
```bash
# Build philosophers sample for Nucleo H743
./scripts/zephyr-build.sh nucleo_h743zi zephyr/samples/philosophers

# Build hello_world for Nucleo F767
./scripts/zephyr-build.sh nucleo_f767zi zephyr/samples/hello_world my_build
```

### docker-shell.sh

Opens an interactive shell into the zephyr-builder container for debugging.

**Usage:**
```bash
./scripts/docker-shell.sh
```

### flash.sh

Flashes a built binary to a connected board using st-flash.

**Usage:**
```bash
./scripts/flash.sh [build_dir] [address]
```

**Example:**
```bash
./scripts/flash.sh build 0x08000000
```

### monitor.sh

Opens a serial monitor (picocom or minicom) to view board output.

**Usage:**
```bash
./scripts/monitor.sh [device] [baudrate]
```

## MCP Server Integration

The builder.py module automatically uses Docker for all Zephyr builds:

```python
from mcp_boardfarm.builder import ZephyrBuilder
from mcp_boardfarm.models import BuildConfig

builder = ZephyrBuilder()
config = BuildConfig(
    board_id="nucleo_h743zi",
    framework="zephyr",
    zephyr_sample="philosophers"
)
result = builder.build(config)
```

## Build Output

After a successful build, the following files are generated in the build directory:

- `build/zephyr/zephyr.elf` - ELF file (for debugging)
- `build/zephyr/zephyr.bin` - Raw binary (for flashing)
- `build/zephyr/zephyr.hex` - Intel HEX file (for flashing)

## Troubleshooting

### Container Won't Start

**Problem:** Permission denied errors

**Solution:** Ensure Docker is running and user is in docker group:
```bash
sudo usermod -aG docker $USER
# Log out and back in
```

### Build Fails: Board Not Found

**Problem:** Board name incorrect

**Solution:** List available boards:
```bash
docker compose exec zephyr-builder bash -c "west boards | grep nucleo"
```

### Build Fails: picolibc Errors

**Problem:** SDK/Zephyr version mismatch

**Solution:** The container uses latest Zephyr SDK. Update west:
```bash
docker compose exec zephyr-builder bash -c "cd ~/zephyrproject && west update"
```

### Slow First Build

**Problem:** Initial west init and update takes time

**Solution:** This is normal - modules are cached in the zephyr-cache volume. Subsequent builds are faster.

### Flash Fails: No ST-Link Detected

**Problem:** Board not connected or udev rules missing

**Solution:**
1. Connect board via USB
2. Install udev rules:
```bash
sudo apt install stlink-tools
sudo st-info --probe
```

### Serial Monitor Won't Connect

**Problem:** Device busy or wrong permissions

**Solution:**
```bash
# Check device
ls -la /dev/ttyACM*

# Fix permissions
sudo chmod 666 /dev/ttyACM0

# Or add user to dialout group
sudo usermod -aG dialout $USER
```

## Available Boards

Common ST Nucleo boards:
- `nucleo_h743zi` - STM32H743 (tested)
- `nucleo_f767zi` - STM32F767
- `nucleo_f746zg` - STM32F746
- `nucleo_f429zi` - STM32F429
- `nucleo_f446re` - STM32F446
- `nucleo_f411re` - STM32F411
- `nucleo_f303re` - STM32F303
- `nucleo_f103rb` - STM32F103
- `nucleo_l476rg` - STM32L476
- `nucleo_l432kc` - STM32L432

List all boards:
```bash
docker compose exec zephyr-builder bash -c "west boards"
```

## Advanced Usage

### Custom Source Path

Build a custom application:
```bash
docker compose exec -T zephyr-builder bash -c "
  export ZEPHYR_BASE=/home/user/zephyrproject/zephyr
  cd /home/user/zephyrproject
  west build -b nucleo_h743zi -d /workspace/build /workspace/my_app
"
```

### Build with Custom Config

```bash
docker compose exec -T zephyr-builder bash -c "
  export ZEPHYR_BASE=/home/user/zephyrproject/zephyr
  cd /home/user/zephyrproject
  west build -b nucleo_h743zi -d /workspace/build zephyr/samples/philosophers -- -DCONFIG_DEBUG=y
"
```

### Clean Build

```bash
docker compose exec -T zephyr-builder bash -c "
  export ZEPHYR_BASE=/home/user/zephyrproject/zephyr
  cd /home/user/zephyrproject
  west build -b nucleo_h743zi -d /workspace/build --pristine
"
```

## Version Information

- **Docker Image:** zephyrprojectrtos/zephyr-build:latest
- **Zephyr Version:** 4.3.99 (main branch)
- **Zephyr SDK:** 0.17.4
- **West Version:** 1.5.0

## See Also

- [Zephyr Project Documentation](https://docs.zephyrproject.org/)
- [Zephyr West Tool](https://docs.zephyrproject.org/latest/develop/west/)
- [ST-Link Tools](https://github.com/stlink-org/stlink)
