# MCP Board Farm - MVP TODO

## Week 1: Foundation

### Day 1-2: Project Setup
- [x] Create project structure
- [x] Write architecture document
- [x] Set up Python package (pyproject.toml)
- [ ] Initialize git repo
- [ ] Add LICENSE (MIT)

### Day 3-4: Core Server
- [ ] Implement MCP server skeleton
- [ ] Board detection (USB enumeration)
- [ ] Board state machine
- [ ] YAML config loading

### Day 5-7: Build System
- [ ] Zephyr build integration
- [ ] Docker container for builds
- [ ] Build artifact caching
- [ ] Basic error handling

## Week 2: Flash & Monitor

### Day 8-10: Flashing
- [ ] OpenOCD integration
- [ ] Flash with verification
- [ ] Reset handling (soft/hard)
- [ ] Auto-recovery from bad flash

### Day 11-12: Serial Monitor
- [ ] Serial port reading
- [ ] Real-time log streaming
- [ ] WebSocket for live logs
- [ ] Log persistence

### Day 13-14: Integration & Test
- [ ] End-to-end test: build → flash → monitor
- [ ] Claude Desktop integration
- [ ] Documentation
- [ ] Demo video/gif

## MVP Success Criteria

- [ ] Can list connected boards
- [ ] Can build Zephyr hello_world
- [ ] Can flash to Nucleo
- [ ] Can capture serial output
- [ ] Works with Claude Desktop
- [ ] 2+ boards supported
- [ ] < 2 min for full cycle

## Post-MVP Features

- [ ] Multiple toolchains (Arduino, STM32Cube)
- [ ] PyOCD support
- [ ] Test framework integration
- [ ] Web dashboard
- [ ] Multi-user auth
- [ ] Cloud deployment
- [ ] Logic analyzer integration
- [ ] GDB remote debugging

## Blockers/Risks

- USB device permissions on Linux
- OpenOCD stability with multiple boards
- Build time for Zephyr (too slow?)
- Docker vs native toolchain

## Notes

- Keep it simple: Zephyr-only for MVP
- Target: 2 Nucleo F401RE boards
- Local server only (no auth for MVP)
- Focus on reliability over features
