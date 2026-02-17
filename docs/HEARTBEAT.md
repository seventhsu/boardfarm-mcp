# HEARTBEAT.md

# MCP Board Farm Development Tasks
# (Bay Area job search cron runs separately at 8am)

## Current Phase: Phase 1 - Foundation (Week 1)
# Hardware: Awaiting NUCLEO-H755ZI-Q boards
# Daily dev time: 1-2 hours

## Task Tracking

### Active Tasks (In Progress)
- [ ] Create MCP server skeleton (FastMCP)
- [ ] Implement board detection system
- [ ] Build configuration loader (YAML)
- [ ] State machine for board management

### Pending Tasks
- [ ] MCP tool: list_boards
- [ ] MCP tool: get_board_info  
- [ ] Zephyr build integration
- [ ] Docker build container setup
- [ ] Unit tests with mock boards

### Blocked Tasks
- [ ] OpenOCD integration (needs hardware)
- [ ] Serial monitoring (needs hardware)
- [ ] End-to-end testing (needs hardware)

## Triggers

### On Hardware Arrival
1. Immediately begin Phase 2
2. Test board detection with real H755ZI
3. Verify OpenOCD connectivity
4. Run first successful flash

### On Phase Completion
- Phase 1 done → Notify user, await hardware
- Phase 2 done → Demo with user, gather feedback
- Phase 3 done → Tag v0.1.0, prepare upstream push

### On Blockers
- If stuck > 2 hours → Document, ask user
- If OpenOCD issues → Try pyocd fallback
- If build too slow → Optimize or notify

## Git Workflow Reminders
- Commit at end of each work session
- Descriptive commit messages
- Feature branches for major changes
- Ready to rebase onto upstream when provided

## Job Search Priority
# Reminder: 8am daily job search continues
# Board farm is secondary work stream
# Can pause if job search heats up (interviews, etc.)
