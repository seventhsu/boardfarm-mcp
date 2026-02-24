# STM32H755ZI-Q Board Bring-Up Summary

## Current Status: BLOCKED by Permissions

### Board Detection ✅
- Board 1 (nucleo-h755zi-q-01) detected successfully
- Status: AVAILABLE
- ST-Link V3 at Bus 001 Device 006 (ID 0483:374e)
- Serial port: /dev/ttyACM0 configured for 115200 baud

### Blockers

#### 1. Serial Port Access ❌
- `/dev/ttyACM0` owned by `root:dialout` (mode 660)
- User `alial` is NOT in `dialout` group
- **Fix required:** `sudo usermod -aG dialout alial` + logout/login

#### 2. ST-Link USB Access ❌
- USB device `/dev/bus/usb/001/006` owned by `root:root` (mode 660)
- No udev rules installed for ST-Link V3
- **Fix required:** Install `docs/50-stlink.rules` and reload udev

#### 3. Missing Toolchain ❌
- No `arm-none-eabi-gcc` in PATH
- Docker available but user doesn't have permission to run privileged containers
- **Fix options:**
  a) Install ARM GCC: `sudo apt install gcc-arm-none-eabi`
  b) Install Zephyr SDK to `/opt/zephyr-sdk-0.16.5`
  c) Use pre-built binaries

### Required Fixes (Admin/Sudo Required)

```bash
# 1. Add user to dialout group
sudo usermod -aG dialout alial

# 2. Install udev rules for ST-Link
sudo cp docs/50-stlink.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Install ARM toolchain
sudo apt-get update
sudo apt-get install -y gcc-arm-none-eabi stlink-tools openocd

# 4. Log out and back in for group changes to take effect
```

### Test Firmware Created ✅

Location: `test_firmware/h755_blink/`
- `main.c` - Bare-metal blink for PG12 (LD1 Green LED)
- `linker.ld` - Linker script for H755 M7 core
- `Makefile` - Docker-based build

Features:
- Toggles Green LED (PG12) at ~2Hz
- No external dependencies (no libc)
- Direct register access for minimal size

### Hardware Notes

#### Dual-Core Considerations (STM32H755ZI)

| Core | Boot Address | Flash | SRAM | Purpose |
|------|--------------|-------|------|---------|
| Cortex-M7 | 0x0800_0000 | 1MB | 864KB | Main application |
| Cortex-M4 | 0x0804_0000 | 1MB | 288KB | Co-processor |

**Flashing Notes:**
- M7 boots from 0x08000000 by default
- M4 can be started from M7 code
- ST-Link can flash both cores independently
- PyOCD supports H7 with Keil.STM32H7xx_DFP pack

#### LED Mapping

| LED | Color | GPIO | Function |
|-----|-------|------|----------|
| LD1 | Green | PG12 | User LED |
| LD2 | Yellow | PE1 | User LED |
| LD3 | Red | PE13 | User LED |

### Test Binary (Ready to Flash)

A pre-built test binary has been manually created:

```
test_firmware/h755_blink/h755_blink.bin (256 bytes)
```

To flash once permissions are fixed:
```bash
# Option 1: Using st-flash
st-flash write test_firmware/h755_blink/h755_blink.bin 0x08000000

# Option 2: Using pyocd
pyocd flash -t stm32h755zitx test_firmware/h755_blink/h755_blink.bin --base-address 0x08000000

# Option 3: Using OpenOCD
openocd -f interface/stlink.cfg -f target/stm32h7x.cfg \
  -c "program test_firmware/h755_blink/h755_blink.bin 0x08000000 verify reset exit"
```

### Verification Steps (After Fixes)

1. **Board Detection:**
   ```bash
   uv run python -c "from mcp_boardfarm.board_manager import BoardManager; bm = BoardManager(); print(bm.detect_boards())"
   ```

2. **Flash Test Firmware:**
   ```bash
   st-flash write test_firmware/h755_blink/h755_blink.bin 0x08000000
   ```

3. **Serial Monitor:**
   ```bash
   picocom -b 115200 /dev/ttyACM0
   ```

4. **Visual Verification:**
   - Green LED (LD1) should blink at ~2Hz
   - Board is operational

### Next Steps

1. **Immediate:** Run the permission fixes (requires sudo)
2. **Build:** Compile test firmware with ARM GCC
3. **Flash:** Program the board
4. **Verify:** Confirm LED blinking and serial output
5. **Document:** Update README with working setup

### Workarounds (If Sudo Not Available)

1. **Use Existing Pre-Built Binary:**
   - Copy a known-good binary to flash
   - Use picocom/cu for serial (if dialout access granted)

2. **USB/IP or Network Proxy:**
   - Forward USB to another machine with proper permissions

3. **Container with Privileged USB:**
   - Run flashing tools in privileged Docker container
