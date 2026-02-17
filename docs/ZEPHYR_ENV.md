# Zephyr Build Environment Decision

## Options Considered

### Option 1: Docker (Recommended for MVP)
**Image:** `zephyrprojectrtos/zephyr-build:latest`

**Pros:**
- Guaranteed consistent environment
- No host system pollution
- Pre-installed: Zephyr SDK, toolchains, Python deps
- Easy to version pin
- Portable across machines
- Reproducible builds

**Cons:**
- Slight performance overhead
- File permissions between container and host
- Need to pass USB devices for flashing (or use host OpenOCD)

**Use case:** Primary build method for MVP

---

### Option 2: Native Zephyr Installation

**Pros:**
- Fastest build times
- Direct hardware access
- No Docker complexity

**Cons:**
- Host system gets polluted with toolchains
- Version conflicts possible
- Harder to reproduce on other machines
- Setup time for new developers

**Use case:** Optional optimization after MVP

---

## Decision: Docker First

**Rationale:**
1. MCP Board Farm is about **hardware orchestration**, not build optimization
2. Docker guarantees it works on your your machine and elsewhere
3. Can always optimize to native later
4. Cleaner separation: Docker for builds, host for flashing/monitoring

**Implementation:**
```python
# Build happens in container
# Result copied to host
# Flash happens via host OpenOCD (USB passthrough)
```

**Performance mitigation:**
- Use volume mounts for cache
- Enable ccache inside container
- Parallel builds (-j$(nproc))

---

## Future: Hybrid Mode

Post-MVP, support both:
```yaml
build:
  mode: docker  # or: native
  docker_image: zephyrprojectrtos/zephyr-build:latest
  # OR
  native_sdk_path: /opt/zephyr-sdk-0.16.5
```

---

**Status:** Docker-first for MVP, native support later
