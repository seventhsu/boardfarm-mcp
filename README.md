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
- Zephyr SDK (for Zephyr builds)
- Docker (optional, for containerized builds)

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

## Status

**MVP in progress.** Target: Single Nucleo board, Zephyr builds, basic MCP tools.

## License

MIT

---

*Built with 🤖 by the MCP Board Farm team*
