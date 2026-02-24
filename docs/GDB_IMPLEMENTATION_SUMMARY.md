# GDB Debugging Implementation Summary

## Overview
GDB debugging support has been successfully added to the MCP Board Farm server. This provides an agent-friendly interface for debugging embedded targets using GDB and pyocd.

## Files Created/Modified

### New Files

1. **`src/mcp_boardfarm/gdb_models.py`**
   - Data models for GDB debugging
   - `GDBSessionState` enum (IDLE, CONNECTING, RUNNING, PAUSED, ERROR, DISCONNECTED)
   - `StepType` enum (INTO, OVER, OUT, INSTRUCTION)
   - Dataclasses: `Register`, `StackFrame`, `Breakpoint`, `MemoryRegion`, `Variable`
   - `GDBSessionInfo` - Session state tracking
   - `DebugOperationResult` - Structured operation results
   - `GDBServerConfig` - pyocd server configuration

2. **`src/mcp_boardfarm/gdb_debugger.py`**
   - `GDBDebugger` class - Main debugging interface
   - `GDBDebuggerManager` class - Manages multiple debug sessions
   - Methods for all debug operations (step, break, inspect, etc.)
   - GDB MI output parsing
   - Async-friendly API with timeout handling

3. **`test_firmware/gdb_test/`**
   - `main.c` - Test program with functions, variables, loops
   - `CMakeLists.txt` - Zephyr build configuration
   - `Makefile` - Standalone build configuration
   - `README.md` - Test firmware documentation

4. **`docs/GDB_DEBUGGING.md`**
   - Complete user documentation
   - API reference for all debug tools
   - Usage examples
   - Troubleshooting guide

### Modified Files

1. **`src/mcp_boardfarm/server.py`**
   - Added `debug_manager` to `ServerState`
   - Added 15 new MCP tools for debugging:
     - `debug_start_session(board_id, elf_path)`
     - `debug_stop_session(board_id)`
     - `debug_reset(board_id, halt)`
     - `debug_continue(board_id)`
     - `debug_pause(board_id)`
     - `debug_step(board_id, step_type)`
     - `debug_set_breakpoint(board_id, location)`
     - `debug_clear_breakpoint(board_id, bp_id)`
     - `debug_list_breakpoints(board_id)`
     - `debug_read_registers(board_id)`
     - `debug_read_register(board_id, register)`
     - `debug_read_memory(board_id, address, size)`
     - `debug_write_memory(board_id, address, data)`
     - `debug_get_stack_trace(board_id, max_frames)`
     - `debug_get_local_variables(board_id)`
     - `debug_get_state(board_id)`

2. **`pyproject.toml`**
   - Added `pygdbmi>=0.11.0.0` dependency

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ MCP Client  │────▶│ MCP Server   │────▶│ GDBDebugger │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                      ┌─────────────┐           │
                      │ pyocd gdb   │◀──────────┘
                      │ server      │
                      └──────┬──────┘
                             │
                             ▼
                      ┌─────────────┐
                      │ Target MCU  │
                      └─────────────┘
```

## Key Features

### Session Management
- Start/stop GDB sessions per board
- Automatic pyocd gdbserver management
- Session state tracking (idle, running, paused, error)

### Execution Control
- `reset()` - Reset target (with optional halt)
- `continue()` - Resume execution
- `pause()` / `halt()` - Stop execution
- `step()` - Single step (into, over, out, instruction)

### Breakpoints
- `set_breakpoint(location)` - Set by file:line, function, or address
- `clear_breakpoint(bp_id)` - Remove breakpoint
- `list_breakpoints()` - Show all breakpoints

### Inspection
- `read_registers()` - All registers as structured data
- `read_register(name)` - Specific register
- `read_memory(address, size)` - Memory dump with hex/ASCII
- `write_memory(address, data)` - Write bytes to memory
- `get_stack_trace()` - Call stack with file/line info
- `get_local_variables()` - Local vars (requires debug symbols)

### Agent-Friendly Features
- **Structured output**: JSON with consistent schema
- **Error handling**: Clear error messages in result
- **Timing**: Operation duration in milliseconds
- **State tracking**: No need to re-query GDB constantly
- **Timeout handling**: Configurable timeouts for operations

## Testing

### Unit Tests
All models and basic functionality verified via Python imports.

### Test Firmware
- Located in `test_firmware/gdb_test/`
- Includes functions, variables, loops, structures
- Compiled with `-g -O0` for best debug experience

### Manual Testing Steps
1. Build test firmware: `cd test_firmware/gdb_test && make`
2. Flash to board: `pyocd flash build/gdb_test.hex --target stm32h755xi`
3. Start MCP server: `mcp-boardfarm`
4. Use MCP tools to debug

## Usage Example

```python
# Start debugging
await debug_start_session("nucleo-h755zi-q-01", "build/gdb_test.elf")

# Set breakpoints
await debug_set_breakpoint("nucleo-h755zi-q-01", "main")
await debug_set_breakpoint("nucleo-h755zi-q-01", "main.c:85")

# Run and inspect
await debug_continue("nucleo-h755zi-q-01")
await debug_pause("nucleo-h755zi-q-01")

# Get state
regs = await debug_read_registers("nucleo-h755zi-q-01")
stack = await debug_get_stack_trace("nucleo-h755zi-q-01")
locals_vars = await debug_get_local_variables("nucleo-h755zi-q-01")

# Single step
await debug_step("nucleo-h755zi-q-01", step_type="over")

# Clean up
await debug_stop_session("nucleo-h755zi-q-01")
```

## Dependencies

```
pygdbmi>=0.11.0.0  # NEW: GDB MI interface
pyocd>=0.36.0      # EXISTING: GDB server for ARM
```

## Known Limitations

1. **Dual-core STM32H7**: Currently only debugs M7 core
2. **Memory writes**: Flash programming requires special handling
3. **Optimization**: Debug symbols work best with `-O0`

## Next Steps for Full Testing

1. Build and flash test firmware to nucleo-h755zi-q-01
2. Test each debug operation against real hardware
3. Document any board-specific quirks
4. Add automated integration tests

## Verification Status

- [x] Code implementation complete
- [x] All models created
- [x] All MCP tools defined
- [x] Test firmware created
- [x] Documentation written
- [ ] Hardware testing (requires physical board)
