# HEARTBEAT.md

# MCP Board Farm Development Tasks
# (Bay Area job search cron runs separately at 8am)

## Current Phase: Phase 2 - Hardware Integration (Week 2)
# Hardware: NUCLEO-H755ZI-Q Board 1 connected and detected
# Daily dev time: 1-2 hours

## Task Tracking

### Completed Tasks (Phase 1 Foundation)
- [x] Create MCP server skeleton (FastMCP)
- [x] Implement board detection system
- [x] Build configuration loader (YAML)
- [x] State machine for board management
- [x] MCP tool: list_boards
- [x] MCP tool: get_board_info  
- [x] MCP tool: reserve_board
- [x] MCP tool: release_board
- [x] MCP tool: build_firmware (MockBuilder)
- [x] MCP tool: flash_board (MockFlasher)
- [x] MCP tool: reset_board
- [x] MCP tool: start_logging
- [x] MCP tool: stop_logging
- [x] MCP tool: get_logs
- [x] MCP tool: get_server_status
- [x] CLI entry point with detect/serve/config commands
- [x] First git commit with complete Phase 1

### Completed Tasks (Phase 2 - Hardware Integration)
- [x] Board 1 (H755ZI-Q) physically detected via USB
- [x] ST-Link V3 recognized at Bus 001 Device 006
- [x] Serial port /dev/ttyACM0 mapped correctly
- [x] Board detection Python API working
- [x] Test firmware created (bare-metal blink for PG12)
- [x] pyocd installed and STM32H755 pack identified
- [x] Documentation: udev rules, setup script, bring-up status

### Pending Tasks (Phase 2 - Hardware Integration)
- [ ] Fix permissions (user in dialout group, udev rules)
- [ ] Install ARM toolchain (gcc-arm-none-eabi)
- [ ] Flash test firmware to Board 1
- [ ] Verify serial output from test firmware
- [ ] Real Zephyr builds (needs SDK or Docker)

### Blocked Tasks
- [ ] OpenOCD flashing (needs sudo for udev rules + toolchain install)
- [ ] Serial monitoring (needs dialout group membership)
- [ ] Real Zephyr builds (needs Docker perms or native SDK)

## Triggers

### On Hardware Arrival
1. Immediately begin Phase 2
2. Test board detection with real H755ZI
3. Verify OpenOCD connectivity
4. Run first successful flash

### On Phase Completion
- Phase 1 done -> Notify user, await hardware [DONE]
- Phase 2 done -> Demo with user, gather feedback
- Phase 3 done -> Tag v0.1.0, prepare upstream push

### On Blockers
- If stuck > 2 hours -> Document, ask user
- If OpenOCD issues -> Try pyocd fallback
- If build too slow -> Optimize or notify

## Current Status

**Date:** 2026-02-23
**Phase 2 Status:** IN PROGRESS - Hardware detected, blocked on permissions/toolchain

**Hardware Status:**
- Board 1 (nucleo-h755zi-q-01): CONNECTED and DETECTED
  - ST-Link V3 at USB Bus 001 Device 006 (ID 0483:374e)
  - Serial port /dev/ttyACM0 configured at 115200 baud
  - Board Manager reports status: AVAILABLE
- Board 2 (nucleo-h755zi-q-02): CONFIGURED (awaiting physical connection)

**Blockers:**
1. User `alial` not in `dialout` group → cannot access /dev/ttyACM0
2. No udev rules for ST-Link → pyocd/st-flash cannot access USB debug probe
3. No ARM GCC toolchain → cannot compile firmware

**Test Firmware Ready:**
- Location: `test_firmware/h755_blink/h755_blink.bin`
- Function: Blinks green LED (PG12) at ~2Hz
- Size: 1KB bare-metal binary
- Ready to flash once permissions are fixed

## Git Workflow Reminders
- Commit at end of each work session [DONE]
- Descriptive commit messages [DONE]
- Ready to rebase onto upstream when provided

## Next Steps
1. **URGENT:** Run `sudo docs/setup_hardware.sh` to fix permissions
2. Log out and back in for group changes
3. Test: `pyocd list` should show ST-Link
4. Flash test firmware to Board 1
5. Verify: Green LED blinking
6. Test serial: `picocom -b 115200 /dev/ttyACM0`
7. Document successful bring-up procedure

## Dev Agent Memory
**Dev sub-agents must read:** `docs/DEV_MEMORY.md`  
Contains: Project status, MVP scope, hardware wishlist, blockers, next actions  
**MVP Priority:** Single-core workflow first — dual-core is POST-MVP  
**Dual-core support:** Next goal after MVP ships, not part of initial release
