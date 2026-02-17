# MCP Board Farm

An MCP (Model Context Protocol) server that enables AI coding agents to interact with physical embedded hardware. Connect STM32 Nucleo boards (and others) to a central server and let LLMs build, flash, debug, and test firmware on real hardware.

---

## Vision

"Docker for embedded hardware" — AI agents can spin up physical boards, flash firmware, run tests, capture traces, and tear down, all through a standardized protocol.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Coding Agent                          │
│              (Claude Code, Cursor, etc.)                    │
│                        │                                    │
│                        │ MCP Protocol                       │
│                        ▼                                    │
├─────────────────────────────────────────────────────────────┤
│                  MCP Board Farm Server                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Builder    │  │   Flasher    │  │   Monitor    │      │
│  │  (zephyr/    │  │  (openocd/   │  │  (logging/   │      │
│  │   make/gcc)  │  │   pyocd)     │  │   tracing)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Board      │  │   Scope/     │  │   Test       │      │
│  │   Manager    │  │   Analyzer   │  │   Runner     │      │
│  │  (state/     │  │  (sigrok/    │  │  (pytest/    │      │
│  │   queue)     │  │   saleae)    │  │   robot)     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ STM32    │  │ STM32    │  │  Future  │
    │ Nucleo   │  │ Nucleo   │  │  boards  │
    │ (dev)    │  │ (test)   │  │          │
    └──────────┘  └──────────┘  └──────────┘
         │               │
         └───────────────┘
              USB/JTAG
```

---

## Core Components

### 1. MCP Server (`src/server.py`)
- Implements Model Context Protocol
- Exposes tools (functions) to AI agents
- Handles authentication, rate limiting, request validation
- Manages concurrent access to shared hardware

### 2. Board Manager (`src/board_manager.py`)
- Maintains state of all connected boards
- Handles board reservation, release, health checks
- Automatic recovery from hangs/crashes
- Queue management for board access

### 3. Build System (`src/builder.py`)
- Integrates with Zephyr, Arduino, STM32Cube, bare-metal
- Supports incremental builds
- Caches build artifacts
- Returns build logs and binary artifacts

### 4. Flasher (`src/flasher.py`)
- OpenOCD integration for JTAG/SWD
- PyOCD for CMSIS-DAP
- DFU/serial bootloader support
- Verifies flash integrity
- Rollback support for A/B partitions

### 5. Monitor (`src/monitor.py`)
- Serial port logging (RTT, UART, SWO)
- Real-time log streaming via WebSocket
- Log filtering and formatting
- Persistent log storage

### 6. Test Runner (`src/test_runner.py`)
- Runs pytest-embedded tests
- Robot Framework integration
- Custom test protocol support
- Captures test results, coverage, timing

### 7. Scope/Analyzer (`src/analyzer.py`) — Future
- Sigrok integration for logic analyzers
- Saleae API support
- Oscilloscope control (SCPI)
- Capture traces on test failure

---

## MCP Tools (AI-Agent Facing)

### Board Management
- `list_boards()` — Show available boards, their status, capabilities
- `reserve_board(board_id, timeout)` — Lock a board for exclusive use
- `release_board(board_id)` — Unlock board
- `get_board_info(board_id)` — MCU type, flash size, peripherals, current firmware

### Build & Flash
- `build_firmware(source_files, config)` — Compile project, return binary
- `flash_board(board_id, binary)` — Program board, verify, reset
- `flash_board_url(board_id, url)` — Flash from remote binary

### Debug & Monitor
- `start_logging(board_id)` — Begin capturing serial output
- `stop_logging(board_id)` — Stop logging, return captured data
- `get_logs(board_id, since)` — Retrieve recent logs
- `reset_board(board_id, type)` — Soft reset, hard reset, power cycle
- `run_gdb_command(board_id, command)` — Execute GDB command remotely

### Testing
- `run_tests(board_id, test_suite)` — Execute test suite on board
- `get_test_results(board_id)` — Retrieve pass/fail, logs, coverage
- `capture_trace(board_id, duration, triggers)` — Logic analyzer capture

### System
- `get_server_status()` — Board farm health, queue depth, build status
- `get_build_artifacts(build_id)` — Download compiled binaries

---

## Data Models

### Board State Machine
```
OFFLINE → AVAILABLE → RESERVED → BUILDING → FLASHING → RUNNING → TESTING
              ↑           │           │          │         │         │
              └───────────┴───────────┴──────────┴─────────┴─────────┘
                              (release_board or timeout)
```

### Board Configuration
```json
{
  "board_id": "nucleo-f401re-01",
  "type": "stm32",
  "model": "nucleo-f401re",
  "mcu": "STM32F401RET6",
  "flash_size": 512,
  "ram_size": 96,
  "debugger": "cmsis-dap",
  "serial_port": "/dev/ttyACM0",
  "jtag_iface": "swd",
  "capabilities": ["zephyr", "arduino", "stlink"],
  "status": "available",
  "reserved_by": null,
  "reserved_until": null,
  "current_firmware": "blink-v1.2.3"
}
```

---

## Security Model

- **Sandboxed builds:** Containerized/VM builds to prevent malicious code
- **Board isolation:** Each board reserved exclusively per session
- **Resource limits:** Max build time, max flash cycles, rate limiting
- **Authentication:** API keys, optional OAuth for multi-user setups
- **Audit logging:** All operations logged with user/agent attribution

---

## MVP Scope (First 2 Weeks)

1. **Single board support:** STM32 Nucleo-F401RE
2. **Zephyr RTOS only** (bare metal later)
3. **Core tools:** list_boards, build_firmware, flash_board, start_logging, reset_board
4. **Local server:** Single-user, no auth
5. **CLI client:** Python script to test MCP tools
6. **Integration:** Works with Claude Desktop

---

## Future Features

- Multi-board support (ESP32, nRF52, RP2040)
- Cloud deployment (Kubernetes board farm)
- Per-minute billing for hosted service
- CI/CD integration (GitHub Actions, GitLab CI)
- Web dashboard (board status, logs, history)
- Snapshot/restore board state
- Collaborative debugging (multiple agents on same board)

---

## Tech Stack

- **Server:** Python 3.11+, FastMCP (or custom MCP impl)
- **Build:** Docker containers for toolchains
- **Flash:** OpenOCD, pyocd
- **Logs:** pyserial, WebSocket streaming
- **Testing:** pytest-embedded, Robot Framework
- **Config:** YAML for board definitions
- **State:** SQLite or Redis for board state

---

## Name

**MCP Board Farm** — clear, descriptive, searchable.

Alternative: **Ferrous** (iron + hardware), **HardMCP**, **MCP-HIL**

---

## Success Criteria

1. AI agent can build, flash, and get "Hello World" from board in < 2 minutes
2. 99% flash success rate (recovery from bad firmware)
3. < 5 second latency for simple commands
4. Handles 2+ concurrent boards without interference

---

## Open Questions

1. How to handle boards that need physical button presses (boot mode)?
2. USB passthrough for Dockerized builds?
3. Cost model for cloud service (per-minute, per-flash, subscription)?
4. How to version firmware artifacts?

---

*Drafted: 2026-02-16*
*Next: Implement MVP server + first board*
