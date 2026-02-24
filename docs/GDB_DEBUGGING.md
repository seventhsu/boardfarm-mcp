# GDB Debugging Support for MCP Board Farm

This document describes the GDB debugging interface for the MCP Board Farm server.

## Overview

The GDB debugging feature provides an agent-friendly interface for debugging embedded targets. It uses:

- **pyocd gdbserver**: GDB server for ARM Cortex-M targets
- **pygdbmi**: Machine-interface library for GDB communication
- **Structured output**: JSON responses instead of raw GDB MI output

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐
│   MCP Client    │────▶│ MCP Server   │────▶│  GDBDebugger │
│  (IDE/Agent)    │◀────│              │◀────│              │
└─────────────────┘     └──────────────┘     └──────┬───────┘
                                                    │
                       ┌──────────────┐            │
                       │ pyocd server │◀───────────┘
                       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ Target Board │
                       │  (STM32/etc) │
                       └──────────────┘
```

## MCP Debug Tools

### Session Management

#### `debug_start_session(board_id, elf_path=None)`
Start a GDB debug session for a board.

**Parameters:**
- `board_id`: Board identifier (e.g., "nucleo-h755zi-q-01")
- `elf_path`: Optional path to ELF file with debug symbols

**Returns:**
```json
{
  "success": true,
  "operation": "start_session",
  "message": "Debug session started on port 3333",
  "data": {
    "board_id": "nucleo-h755zi-q-01",
    "state": "PAUSED",
    "gdb_port": 3333,
    "target_mcu": "STM32H755ZI",
    "created_at": "2024-02-23T20:00:00",
    "connected_at": "2024-02-23T20:00:01",
    "current_context": null
  },
  "duration_ms": 1250.5
}
```

#### `debug_stop_session(board_id)`
Stop the debug session and clean up.

#### `debug_get_state(board_id)`
Get current session state.

**Returns:**
```json
{
  "success": true,
  "operation": "get_state",
  "data": {
    "board_id": "nucleo-h755zi-q-01",
    "state": "PAUSED",
    "current_context": {
      "file": "main.c",
      "line": 85,
      "function": "main",
      "pc": "0x08001234"
    }
  }
}
```

### Execution Control

#### `debug_reset(board_id, halt=True)`
Reset the target. Set `halt=True` to stop at reset vector.

#### `debug_continue(board_id)`
Resume execution.

#### `debug_pause(board_id)`
Halt the target.

#### `debug_step(board_id, step_type="into")`
Execute a single step.

**Step Types:**
- `"into"`: Step into function calls
- `"over"`: Step over function calls
- `"out"`: Step out of current function
- `"instruction"`: Single instruction step

### Breakpoints

#### `debug_set_breakpoint(board_id, location)`
Set a breakpoint at a location.

**Location formats:**
- `"main.c:42"` - File and line number
- `"main"` - Function name
- `"*0x08001234"` - Address

**Returns:**
```json
{
  "success": true,
  "operation": "set_breakpoint",
  "message": "Breakpoint 1 set at main",
  "data": {
    "id": 1,
    "type": "breakpoint",
    "location": "main",
    "enabled": true,
    "hits": 0
  }
}
```

#### `debug_clear_breakpoint(board_id, bp_id)`
Remove a breakpoint by ID.

#### `debug_list_breakpoints(board_id)`
List all breakpoints.

### Inspection

#### `debug_read_registers(board_id)`
Read all CPU registers.

**Returns:**
```json
{
  "success": true,
  "operation": "read_registers",
  "data": {
    "registers": [
      {"name": "r0", "value": "0x20000400", "value_dec": 536871936, "size_bits": 32},
      {"name": "r1", "value": "0x00000000", "value_dec": 0, "size_bits": 32},
      {"name": "pc", "value": "0x08001234", "value_dec": 134221876, "size_bits": 32},
      {"name": "sp", "value": "0x20010000", "value_dec": 536936448, "size_bits": 32}
    ],
    "count": 16
  }
}
```

#### `debug_read_register(board_id, register)`
Read a specific register (e.g., "pc", "sp", "r0").

#### `debug_read_memory(board_id, address, size)`
Read memory from target.

**Example:**
```
debug_read_memory("nucleo-h755zi-q-01", "0x20000000", 16)
```

**Returns:**
```json
{
  "success": true,
  "operation": "read_memory",
  "data": {
    "address": "0x20000000",
    "size": 16,
    "hex": "00000000000000000000000000000000",
    "ascii": "................"
  }
}
```

#### `debug_write_memory(board_id, address, data)`
Write memory to target. Data can be a hex string.

**Example:**
```
debug_write_memory("nucleo-h755zi-q-01", "0x20000000", "deadbeef")
```

#### `debug_get_stack_trace(board_id, max_frames=20)`
Get the call stack.

**Returns:**
```json
{
  "success": true,
  "operation": "get_stack_trace",
  "data": {
    "frames": [
      {"level": 0, "function": "update_global", "file": "main.c", "line": 65},
      {"level": 1, "function": "main", "file": "main.c", "line": 95}
    ],
    "depth": 2
  }
}
```

#### `debug_get_local_variables(board_id)`
Get local variables (requires debug symbols `-g`).

**Returns:**
```json
{
  "success": true,
  "operation": "get_local_variables",
  "data": {
    "variables": [
      {"name": "i", "type": "uint32_t", "value": "42"},
      {"name": "result", "type": "int", "value": "-1"}
    ]
  }
}
```

## Usage Examples

### Basic Debugging Session

```python
# 1. Reserve the board
await reserve_board("nucleo-h755zi-q-01")

# 2. Flash test firmware
await flash_board("nucleo-h755zi-q-01", build_id="gdb_test")

# 3. Start debug session
await debug_start_session("nucleo-h755zi-q-01", elf_path="build/gdb_test.elf")

# 4. Set breakpoints
await debug_set_breakpoint("nucleo-h755zi-q-01", "main")
await debug_set_breakpoint("nucleo-h755zi-q-01", "main.c:85")

# 5. Run and pause
await debug_continue("nucleo-h755zi-q-01")
# ... wait for breakpoint or timeout ...
await debug_pause("nucleo-h755zi-q-01")

# 6. Inspect state
await debug_get_stack_trace("nucleo-h755zi-q-01")
await debug_read_registers("nucleo-h755zi-q-01")
await debug_get_local_variables("nucleo-h755zi-q-01")

# 7. Single step
await debug_step("nucleo-h755zi-q-01", step_type="over")

# 8. Clean up
await debug_stop_session("nucleo-h755zi-q-01")
await release_board("nucleo-h755zi-q-01")
```

### Automated Test Pattern

```python
async def test_function_call_tracing(board_id):
    """Test that traces function calls."""
    # Start session
    await debug_start_session(board_id)
    
    # Set breakpoint on target function
    await debug_set_breakpoint(board_id, "calculate_result")
    
    # Run to breakpoint
    await debug_continue(board_id)
    await asyncio.sleep(2)  # Wait for breakpoint
    
    # Get stack trace
    result = await debug_get_stack_trace(board_id)
    
    # Verify expected call stack
    frames = json.loads(result)["data"]["frames"]
    assert frames[0]["function"] == "calculate_result"
    
    # Clean up
    await debug_stop_session(board_id)
```

## Testing Against Real Hardware

### Prerequisites

1. **Hardware**: STM32 Nucleo board (H755ZI-Q recommended)
2. **Software**: pyocd, arm-none-eabi-gcc (for building test firmware)
3. **Permissions**: User must have access to USB devices

### Test Procedure

1. **Build test firmware:**
```bash
cd test_firmware/gdb_test
make
```

2. **Flash and test:**
```bash
# Flash the firmware
pyocd flash build/gdb_test.hex --target stm32h755xi

# Start GDB server manually (for testing)
pyocd gdbserver --port 3333
```

3. **Run automated tests:**
```python
# Test all operations
await debug_start_session("nucleo-h755zi-q-01")
await debug_reset("nucleo-h755zi-q-01")
await debug_set_breakpoint("nucleo-h755zi-q-01", "main")
await debug_continue("nucleo-h755zi-q-01")
await debug_pause("nucleo-h755zi-q-01")
await debug_step("nucleo-h755zi-q-01", "into")
await debug_read_registers("nucleo-h755zi-q-01")
await debug_read_memory("nucleo-h755zi-q-01", "0x20000000", 16)
await debug_get_stack_trace("nucleo-h755zi-q-01")
await debug_stop_session("nucleo-h755zi-q-01")
```

## Known Quirks

1. **Dual-core STM32H7**: The M4 and M7 cores have separate debug ports. Currently only the M7 core is debugged.

2. **Optimization levels**: For best debugging experience, compile with `-O0` (no optimization). Higher optimization levels may make single-stepping unpredictable.

3. **Reset behavior**: After reset, the target may need a moment to initialize before breakpoints are hit.

4. **Memory read size**: Very large memory reads (>1KB) may timeout. Use smaller chunks for large regions.

5. **Flash programming**: Writing to flash requires special handling (erase before write). Use `flash_board` for firmware updates.

## Troubleshooting

### "Failed to start pyocd gdbserver"
- Check board connection: `pyocd list`
- Verify user has USB permissions
- Check if another gdbserver is already running on port 3333

### "Failed to connect to target"
- Ensure board is powered
- Try resetting the board: `debug_reset()`
- Check SWD connection (for external debuggers)

### "No debug symbols"
- Recompile with `-g` flag
- Verify ELF file path is correct
- Check that optimization level is `-O0`

### "Stepping behaves unexpectedly"
- Compile with `-O0` (no optimization)
- Use `stepi` for instruction-level stepping
- Check if function is inlined by compiler
