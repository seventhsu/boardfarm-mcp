# MCP Board Farm - Development Timeline

**Project:** mcp-boardfarm  
**Goal:** AI-controllable embedded hardware board farm  
**Hardware:** 2× NUCLEO-H755ZI-Q (dual-core Cortex-M7/M4)  
**Duration:** 3 weeks to MVP  
**Runs parallel to:** Bay Area job search (separate work stream)

---

## Phase 1: Foundation (Week 1)
**Hardware status:** Boards not yet arrived

### Days 1-3: Server Skeleton
- [ ] MCP server scaffold (FastMCP)
- [ ] Board detection/management system
- [ ] Configuration system (YAML)
- [ ] State machine implementation
- [ ] Basic MCP tools: `list_boards`, `get_board_info`

### Days 4-5: Build System
- [ ] Zephyr toolchain integration
- [ ] Docker build container (optional)
- [ ] Build artifact management
- [ ] MCP tool: `build_firmware`

### Days 6-7: Testing & Hardening
- [ ] Unit tests for board manager
- [ ] Mock board for testing without hardware
- [ ] Error handling, logging
- [ ] Documentation

**Deliverable:** Server runs, detects mock boards, can trigger builds

---

## Phase 2: Hardware Integration (Week 2)
**Trigger:** User confirms boards arrived

### Days 8-10: Flash & Debug
- [ ] OpenOCD integration for H755ZI
- [ ] Flash programming (both cores)
- [ ] Reset handling (M7/M4 independently)
- [ ] MCP tool: `flash_board`, `reset_board`

### Days 11-12: Monitoring
- [ ] Serial port reading (VCP)
- [ ] Real-time log streaming
- [ ] WebSocket for live logs
- [ ] MCP tools: `start_logging`, `stop_logging`, `get_logs`

### Days 13-14: End-to-End
- [ ] Full pipeline: build → flash → monitor
- [ ] Dual-core coordination (M7 runs, M4 sleeps/parked)
- [ ] Error recovery from bad flash
- [ ] Integration tests with real hardware

**Deliverable:** Complete workflow working on real H755ZI boards

---

## Phase 3: Polish & Integration (Week 3)

### Days 15-17: AI Integration
- [ ] Claude Desktop MCP config
- [ ] Tool descriptions optimized for LLM use
- [ ] Example prompts/workflows
- [ ] Error messages that guide LLM to fix issues

### Days 18-19: Advanced Features
- [ ] Dual-core debugging (attach to M4 while M7 runs)
- [ ] Fault injection testing
- [ ] Performance metrics (build time, flash time)
- [ ] Board health monitoring

### Days 20-21: Documentation & Demo
- [ ] Full README with examples
- [ ] Architecture documentation updates
- [ ] Demo video/GIF
- [ ] Blog post draft (for visibility)

**Deliverable:** Public-ready MVP, works with Claude, 2 boards supported

---

## Work Schedule

**Daily time allocation:**
- 1-2 hours: MCP Board Farm development
- Remaining: Bay Area job search (existing 8am cron continues)

**Check-ins:**
- End of each phase: Report progress, blockers, next steps
- Asynchronous updates via Telegram for milestones

**Triggers:**
- [ ] Hardware arrival → Begin Phase 2 immediately
- [ ] Phase 1 complete → Notify user, await boards
- [ ] Phase 2 complete → Test with user, gather feedback
- [ ] Phase 3 complete → Tag v0.1.0, push to upstream

---

## Git Workflow

**Branching:**
- `main` — stable, working code
- `develop` — integration branch
- `feature/*` — individual features
- `mvp` — MVP release branch

**Commits:**
- Frequent, descriptive commits
- Reference this timeline document
- Tag milestones

**Upstream:**
- Awaiting GitHub repo from user
- Will rebase local work onto upstream when provided

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Boards delayed | Phase 1 uses mock boards, no blocker |
| OpenOCD issues | Fallback to pyocd, STM32CubeProgrammer |
| Zephyr build slow | Use ccache, parallel builds |
| Dual-core complexity | Start with M7-only, add M4 later |
| Job search priority | Board farm is secondary, can pause if needed |

---

## Success Metrics

- [ ] Server starts without errors
- [ ] Detects both H755ZI boards automatically
- [ ] Build Zephyr sample in < 2 minutes
- [ ] Flash firmware in < 30 seconds
- [ ] Capture serial output in real-time
- [ ] Full cycle (build→flash→monitor) in < 3 minutes
- [ ] Works with Claude Desktop (AI can use all tools)
- [ ] 99% flash success rate with auto-recovery

---

**Started:** 2026-02-16  
**Target MVP:** 2026-03-09  
**Status:** Phase 1, Day 1 — Foundation
