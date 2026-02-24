# GDB Test Firmware

A simple test program for testing GDB debugging capabilities on STM32 boards.

## Features

- **Multiple functions** for call stack testing (`add_numbers`, `multiply_numbers`, `calculate_result`)
- **Global and local variables** for memory inspection (`g_counter`, `g_iterations`, `g_result`)
- **Loops** for breakpoint and single-step testing
- **Structure operations** for complex data type inspection
- **Debug symbols** enabled (`-g -O0`)

## Building

### With Zephyr RTOS

```bash
# Set Zephyr environment
source ~/zephyrproject/.venv/bin/activate
export ZEPHYR_BASE=~/zephyrproject/zephyr

# Build
west build -b nucleo_h755zi_q .
```

### Baremetal (Standalone)

```bash
# Requires arm-none-eabi-gcc toolchain
make
```

## Key Test Locations

### Breakpoint Test Locations

1. **Initial breakpoint**: Line with `__asm__("nop")` in `main()`
2. **Loop entry**: Beginning of `while(1)` loop
3. **Function calls**: `update_global()`, `add_numbers()`, `multiply_numbers()`
4. **Conditional code**: Inside the `if (g_counter % 2 == 0)` block

### Variables to Inspect

**Global Variables:**
- `g_counter` - Counter incremented in main loop
- `g_iterations` - Incremented by 10 each iteration
- `g_result` - Result of calculations
- `g_test_data` - Structure with fields `a`, `b`, `sum`

**Local Variables:**
- `local_var` in `main()`
- `result` in `main()`
- `local_counter` in `infinite_loop()`

### Functions for Call Stack Testing

1. `main()` → `calculate_result()` → `add_numbers()`/`multiply_numbers()`
2. `main()` → `update_global()`
3. `infinite_loop()` → `update_global()`

## GDB Test Sequence

```gdb
# Start debugging
(gdb) target remote localhost:3333
(gdb) file build/gdb_test.elf

# Set breakpoints
(gdb) break main
(gdb) break update_global
(gdb) break main.c:115  # Inside while loop

# Run
(gdb) continue

# Inspect variables
(gdb) info locals
(gdb) print g_counter
(gdb) print g_result
(gdb) x/4wx &g_test_data

# Step through code
(gdb) step
(gdb) next
(gdb) finish

# Stack trace
(gdb) backtrace

# Continue
(gdb) continue
```

## Expected Behavior

1. After reset, `g_counter` starts at 0
2. Each loop iteration increments `g_counter` by 1
3. `g_iterations` increments by 10 each iteration
4. `g_result` contains the result of arithmetic operations
5. The main loop runs indefinitely

## Memory Layout

The program uses minimal memory:
- Stack: ~1KB
- Globals: ~100 bytes
- Code: ~5KB

This fits easily in the STM32H755ZI's memory:
- 2MB Flash
- 1MB RAM
