# Priority-Based FIFO Queue System - Implementation Summary

## Overview

Implemented a complete priority-based FIFO queue system for MCP Board Farm board reservations with feature-based matching, fairness algorithms, and persistence.

## Files Created/Modified

### New Files

1. **`src/mcp_boardfarm/board_queue.py`** (570 lines)
   - `QueueStatus` enum: PENDING, ASSIGNED, COMPLETED, CANCELLED, EXPIRED
   - `QueueEntry` dataclass: Represents a queue request with feature matching logic
   - `QueueStats` dataclass: Queue statistics tracking
   - `BoardQueue` class: Main queue manager with per-type queues

2. **`tests/test_board_queue.py`** (500+ lines)
   - Comprehensive test suite for queue functionality
   - Tests for feature matching, priority ordering, persistence, callbacks

3. **`docs/QUEUE_SYSTEM.md`** (300+ lines)
   - Complete documentation for the queue system
   - Usage examples and best practices

### Modified Files

1. **`src/mcp_boardfarm/models.py`**
   - Added `features: List[str]` to Board dataclass
   - Added `capabilities: Dict[str, Any]` to Board dataclass
   - Added `get_features_set()` method
   - Added `get_capabilities_dict()` method

2. **`src/mcp_boardfarm/board_manager.py`**
   - Added BoardQueue integration
   - Added `set_queue()` method to connect queue
   - Modified `release_board()` to check queue
   - Added `_check_queue_for_board()` method
   - Added `_on_board_assigned()` callback

3. **`src/mcp_boardfarm/server.py`**
   - Added BoardQueue to ServerState
   - Updated `app_lifespan()` to initialize queue
   - Added 7 new MCP tools:
     - `queue_for_board()` - Add queue request with features
     - `get_queue_position()` - Check queue position
     - `cancel_queue_request()` - Cancel request
     - `list_queue()` - List all queue entries
     - `reserve_board_with_timeout()` - Reserve with custom timeout
     - `release_board()` - Release reserved board
     - `get_board_features()` - Get board features/capabilities

4. **`src/mcp_boardfarm/__init__.py`**
   - Added exports for BoardQueue, QueueEntry, QueueStatus, get_queue

5. **`config/boards.yaml`**
   - Updated board type from "stm32" to "h755" for H755 boards
   - Added `features` and `capabilities` examples for all boards
   - Added ESP32 example configuration

## Key Features Implemented

### 1. Per-Type Queues
- Separate FIFO queues for each board type (h755, esp32, etc.)
- Type-specific queue management and matching

### 2. Priority-Based Ordering
- Priority levels 1-5 (1 is highest)
- FIFO within same priority
- Priority validation and clamping

### 3. Feature-Based Matching
- **Required features**: Board must have ALL (e.g., `["ethernet", "can"]`)
- **Optional features**: Score bonus for matches (e.g., `["sd_card", "wifi"]`)
- **Capability minimums**: Minimum specs required (e.g., `{"ram_kb": 512}`)
- Scoring algorithm considers capability headroom

### 4. Fairness (Anti-Starvation)
- Priority boost after 30 minutes of waiting
- Maximum 3 boosts per request
- Background task checks every 10 minutes

### 5. Automatic Assignment
- When board released, queue is checked automatically
- Best match selected using priority + feature score + FIFO
- Optional auto-accept mode for automatic reservation

### 6. Persistence
- JSON file storage (default: `./data/queue.json`)
- Auto-save every 30 seconds and on state changes
- Loads on startup, resets assigned entries to pending

### 7. Background Tasks
- Auto-save (30s interval)
- Cleanup expired entries (hourly, 24h retention)
- Priority boost (10m interval)

## Example Usage

```python
# Queue for a board with specific requirements
queue_id = await queue_for_board(
    board_type="h755",
    priority=2,
    estimated_minutes=120,
    agent_id="sabine-42",
    job_description="CH57x BLE driver testing",
    required_features=["ethernet", "dual_core"],
    optional_features=["sd_card"],
    min_capabilities={"ram_kb": 512},
    auto_accept=True
)

# Check position
position = await get_queue_position(queue_id)
# Returns: "2nd in queue for h755, priority 2 (1 ahead at same priority)"

# When assigned, auto-reserve happens if auto_accept=True
# Otherwise manually reserve
await reserve_board_with_timeout("nucleo-h755zi-q-01", agent_id="sabine-42", minutes=120)

# Release when done
await release_board("nucleo-h755zi-q-01", agent_id="sabine-42")
```

## Configuration

### Environment Variables
- `BOARDFARM_QUEUE_PATH`: Path to queue storage JSON (default: `./data/queue.json`)

### Board Configuration (boards.yaml)
```yaml
boards:
  nucleo-h755zi-q-01:
    type: h755
    features:
      - ethernet
      - usb
      - dual_core
      - sd_card
      - can
    capabilities:
      ram_kb: 1024
      flash_kb: 2048
      cpu_mhz: 480
```

## Testing

Basic verification passed:
```
✓ board_queue imports successful
✓ models imports successful
✓ board_manager imports successful
✓ Added queue request: abeeba39
✓ Feature matching: matches=True, score=1.00
✓ Queue position: Next in line!
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     BoardQueue                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Queue[h755] │  │ Queue[esp32]│  │ Queue[stm32]│         │
│  │ ┌───┐┌───┐  │  │ ┌───┐┌───┐  │  │ ┌───┐      │         │
│  │ │P=1││P=2│  │  │ │P=2││P=3│  │  │ │P=3│      │         │
│  │ └───┘└───┘  │  │ └───┘└───┘  │  │ └───┘      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                              │
│  Features:                                                   │
│  - Priority boost (fairness)                                │
│  - Feature matching                                         │
│  - Persistence (JSON)                                       │
│  - Background tasks                                         │
└─────────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ BoardManager│   │  Server  │   │   Disk   │
   │ (releases)  │   │  (MCP)   │   │  (JSON)  │
   └──────────┘   └──────────┘   └──────────┘
```

## Constants

```python
PRIORITY_LEVELS = 5                    # 1-5, 1 is highest
DEFAULT_TIMEOUT_MINUTES = 30
MAX_RESERVATION_MINUTES = 480          # 8 hours max
PRIORITY_BOOST_AFTER_MINUTES = 30      # Boost after 30 min wait
MAX_BOOST_COUNT = 3                    # Max 3 boosts
CLEANUP_AFTER_HOURS = 24               # Remove completed after 24h
SAVE_INTERVAL_SECONDS = 30             # Auto-save interval
```

## Future Enhancements

Potential improvements:
- WebSocket notifications for queue position changes
- Queue position estimates (ETA based on average job times)
- Queue analytics and reporting
- Multi-board allocation (request 2+ boards at once)
- Reservation extensions
- Queue policies (max requests per agent, priority limits)
