# HEARTBEAT.md

# MCP Board Farm Development Tasks
# (Bay Area job search cron runs separately at 8am)

## Current Phase: Phase 1 - Foundation (Week 1)
# Hardware: Awaiting NUCLEO-H755ZI-Q boards
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

### Pending Tasks (Phase 2 - Hardware Integration)
- [ ] OpenOCD integration (needs hardware)
- [ ] Real serial monitoring (needs hardware)
- [ ] End-to-end testing with real H755ZI
- [ ] Docker build container setup
- [ ] Unit tests with mock boards

### Blocked Tasks
- [ ] OpenOCD flashing (needs hardware)
- [ ] Serial monitoring (needs hardware)
- [ ] Real Zephyr builds (needs Docker or native SDK)

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

**Date:** 2026-02-17
**Phase 1 Status:** COMPLETE

All core MCP tools are implemented and tested with mock boards:
- Board management (list, reserve, release)
- Build system (mock Zephyr builds)
- Flash system (mock flashing)
- Monitor system (mock serial logs)
- Server status and control

The server can be run with: `mcp-boardfarm serve` or `python -m mcp_boardfarm.cli serve`

Claude Desktop integration ready - just needs config JSON.

## Git Workflow Reminders
- Commit at end of each work session [DONE]
- Descriptive commit messages [DONE]
- Ready to rebase onto upstream when provided

## Next Steps
1. Await NUCLEO-H755ZI-Q hardware arrival
2. Update config/boards.yaml with H755ZI-Q definitions
3. Implement real OpenOCD flashing
4. Implement real serial monitoring
5. Test full workflow with real hardware
