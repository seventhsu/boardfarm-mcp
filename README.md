# MCP Board Farm

Let AI coding agents interact with physical embedded hardware through the Model Context Protocol.

```
┌─────────────┐     MCP Protocol     ┌──────────────┐     USB/JTAG     ┌─────────┐
│  AI Agent   │ ◄──────────────────► │ Board Server │ ◄──────────────► │  Nucleo │
│ (Claude/    │   build, flash,      │              │                  │  Boards │
│  Cursor)    │   debug, test        │              │                  │         │
└─────────────┘                      └──────────────┘                  └─────────┘
```

## Quick Start

### Hardware Requirements
- 2x STM32 Nucleo boards (F401RE recommended)
- USB cables
- Linux host (your your machine)

### Software Requirements
- Python 3.11+
- OpenOCD
- ARM GCC (`gcc-arm-none-eabi`)
- stlink-tools (for ST-Link V2/V3)
- Zephyr SDK (for Zephyr builds)
- Docker (optional, for containerized builds)

### Hardware Setup (First Time)

For ST-Link V3 debuggers and serial access:

```bash
# Run the setup script with sudo
cd docs
sudo ./setup_hardware.sh

# Log out and back in for group changes to take effect
```

This will:
1. Install udev rules for ST-Link V2/V3
2. Add your user to the `dialout` group (for serial port access)
3. Install ARM toolchain, stlink-tools, and OpenOCD

### Install
```bash
git clone https://github.com/yourusername/mcp-boardfarm.git
cd mcp-boardfarm
pip install -e .
```

### Configure
Edit `config/boards.yaml` to define your connected boards.

### Run Server
```bash
mcp-boardfarm serve
```

### Test with Claude Desktop
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "boardfarm": {
      "command": "python",
      "args": ["-m", "mcp_boardfarm"],
      "env": {
        "BOARDFARM_CONFIG": "/path/to/config"
      }
    }
  }
}
```

### Try It
Ask Claude:
> "Build the Zephyr hello_world sample for STM32F401RE, flash it to board-01, and show me the serial output."

## Features

- 🔧 **Build System:** Zephyr, Arduino, STM32Cube, bare metal
- ⚡ **Flash:** OpenOCD, pyocd, serial bootloader
- 📊 **Monitor:** Real-time serial logging, RTT, SWO
- 🧪 **Test:** pytest-embedded, Robot Framework
- 🔒 **Safe:** Board isolation, sandboxes, rate limits
- 🔌 **Extensible:** Add new boards, debuggers, protocols

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full system design.

## Supported Boards

| Board | MCU | Cores | Status |
|-------|-----|-------|--------|
| Nucleo-H755ZI-Q | STM32H755ZI | Cortex-M7 + M4 | ✅ Detected, needs toolchain |
| Nucleo-F401RE | STM32F401RE | Cortex-M4 | ✅ Configured (mock) |

### Nucleo-H755ZI-Q Bring-Up

The H755ZI-Q is a dual-core board (Cortex-M7 @ 480MHz + Cortex-M4 @ 240MHz).

**Current Status:** Board detected, awaiting permission fixes for flashing.

See [docs/H755_BRINGUP_STATUS.md](docs/H755_BRINGUP_STATUS.md) for detailed bring-up log.

Quick test once permissions are fixed:
```bash
# Flash test firmware
cd test_firmware/h755_blink
st-flash write h755_blink.bin 0x08000000

# Watch serial output
picocom -b 115200 /dev/ttyACM0
```

## Status

**MVP in progress.** Target: Single Nucleo board, Zephyr builds, basic MCP tools.

## License

MIT

---

*Built with 🤖 by the MCP Board Farm team*
