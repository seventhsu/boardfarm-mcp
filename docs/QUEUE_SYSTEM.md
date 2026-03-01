# Priority-Based FIFO Queue System

The MCP Board Farm now includes a sophisticated priority-based FIFO queue system for board reservations. This system enables fair allocation of boards among multiple agents with support for priority levels, custom reservation times, and feature-based matching.

## Overview

The queue system provides:

- **Per-board-type queues**: Separate FIFO queues for each board type (h755, esp32, etc.)
- **Priority levels**: 1-5 (1 is highest priority)
- **Feature matching**: Required features, optional features, and capability requirements
- **Automatic assignment**: Boards are automatically assigned to the best matching queue entry when available
- **Fairness**: Priority boost for long-waiting requests to prevent starvation
- **Persistence**: Queue state survives server restarts

## Queue Entry States

```
PENDING → ASSIGNED → COMPLETED
   ↓
CANCELLED/EXPIRED
```

## MCP Tools

### 1. queue_for_board

Add a request to the queue for a specific board type with optional feature requirements.

```python
queue_id = await queue_for_board(
    board_type="h755",
    priority=2,
    estimated_minutes=120,
    agent_id="sabine-42",
    job_description="CH57x BLE driver testing",
    required_features=["ethernet", "dual_core"],
    optional_features=["sd_card", "can"],
    min_capabilities={"ram_kb": 512},
    auto_accept=True
)
```

**Parameters:**
- `board_type` (str): Type of board needed (e.g., "h755", "esp32")
- `priority` (int): Priority level 1-5 (1 is highest)
- `estimated_minutes` (int): How long you need the board (max 480 minutes = 8 hours)
- `agent_id` (str): Your unique agent identifier
- `job_description` (str): Description of what you're testing/building
- `required_features` (List[str], optional): Features the board MUST have
- `optional_features` (List[str], optional): Nice-to-have features for better matching
- `min_capabilities` (Dict[str, Any], optional): Minimum capability requirements
- `auto_accept` (bool, optional): Automatically reserve when board available

**Returns:** Queue ID string for tracking your request

### 2. get_queue_position

Check your position in the queue.

```python
position_info = await get_queue_position(queue_id="abc12345")
```

**Returns:** Formatted string with position, status, and estimated wait information.

### 3. cancel_queue_request

Cancel a pending queue request.

```python
result = await cancel_queue_request(
    queue_id="abc12345",
    agent_id="sabine-42"
)
```

**Note:** You can only cancel your own requests.

### 4. list_queue

List all queued requests.

```python
queue_status = await list_queue(
    board_type="h755",  # Optional filter
    agent_id="sabine-42",  # Optional filter
    show_completed=True  # Include completed/cancelled
)
```

### 5. reserve_board_with_timeout

Reserve a specific board with a custom timeout (replaces fixed 30-minute timeout).

```python
result = await reserve_board_with_timeout(
    board_id="nucleo-h755zi-q-01",
    agent_id="sabine-42",
    minutes=120  # 2 hours
)
```

### 6. release_board

Release a reserved board.

```python
result = await release_board(
    board_id="nucleo-h755zi-q-01",
    agent_id="sabine-42"
)
```

### 7. get_board_features

Get features and capabilities of a board.

```python
features = await get_board_features(board_id="nucleo-h755zi-q-01")
```

## Board Configuration

Boards can now define features and capabilities in `boards.yaml`:

```yaml
boards:
  nucleo-h755zi-q-01:
    type: h755
    model: NUCLEO-H755ZI-Q
    mcu: STM32H755ZI
    features:
      - ethernet
      - dual_core
      - usb
      - can
      - sd_card
    capabilities:
      ram_kb: 1024
      flash_kb: 2048
      cpu_mhz: 480
    
  esp32-devkit-v4:
    type: esp32
    model: ESP32-DevKitC
    mcu: ESP32-WROOM-32
    features:
      - wifi
      - bluetooth
      - dual_core
    capabilities:
      ram_kb: 520
      flash_kb: 4096
```

## Feature Matching Algorithm

When a board becomes available, the queue system:

1. **Filters by required features**: Board must have ALL required features
2. **Filters by capabilities**: Board must meet ALL minimum capability requirements
3. **Scores by optional features**: Each matched optional feature adds to the score
4. **Scores by capability headroom**: Extra capacity beyond minimum gives bonus points
5. **Selects best match**: Highest priority (lowest number) + highest score + earliest request

## Priority Boost (Fairness)

To prevent starvation of lower-priority requests:

- After waiting 30 minutes, priority is boosted by 1 level
- Maximum of 3 priority boosts per request
- Boost happens automatically every 10 minutes

Example:
```
Initial priority: 4 (low)
After 30 min wait: priority 3
After 60 min wait: priority 2
After 90 min wait: priority 1 (highest)
```

## Example Workflows

### Basic Queue Usage

```python
# Queue for any h755 board
queue_id = await queue_for_board(
    board_type="h755",
    priority=3,
    estimated_minutes=60,
    agent_id="agent-1",
    job_description="Basic firmware test"
)

# Check position
pos = await get_queue_position(queue_id)

# When board is assigned, you'll be notified
# Then reserve it
await reserve_board_with_timeout("nucleo-h755zi-q-01", agent_id="agent-1", minutes=60)

# Do your work...

# Release when done
await release_board("nucleo-h755zi-q-01", agent_id="agent-1")
```

### Feature-Based Matching

```python
# Need a board with specific features
queue_id = await queue_for_board(
    board_type="h755",
    priority=2,
    estimated_minutes=120,
    agent_id="agent-1",
    job_description="Ethernet driver testing",
    required_features=["ethernet"],  # Must have ethernet
    optional_features=["dual_core", "can"],  # Nice to have
    min_capabilities={"ram_kb": 512}  # Need at least 512KB RAM
)
```

### Auto-Accept Mode

```python
# Automatically reserve when board available
queue_id = await queue_for_board(
    board_type="esp32",
    priority=2,
    estimated_minutes=30,
    agent_id="agent-1",
    job_description="Quick test",
    auto_accept=True  # Will auto-reserve when assigned
)
```

## Queue Persistence

The queue is automatically saved to disk (default: `./data/queue.json`) every 30 seconds and on every state change. This ensures:

- Queue survives server restarts
- No lost requests during crashes
- Can recover and continue after maintenance

On restart, assigned boards are reset to pending (since the board may have been released).

## Monitoring the Queue

Use `list_queue()` to see:
- All pending requests
- Currently assigned boards
- Queue statistics by board type and priority

Example output:
```
Board Queue Status
======================================================================

Summary: 5 pending, 2 assigned

📋 Pending Requests (5):
----------------------------------------------------------------------

1. [2] h755 - agent-2
   Queue ID: a1b2c3d4
   Job: Ethernet driver test
   Wait: 1 in queue for h755, priority 2
   Required: ethernet, dual_core

2. [2] h755 - agent-1
   Queue ID: e5f6g7h8
   Job: CAN bus testing
   Wait: 2 in queue for h755, priority 2 (1 ahead at same priority)
   Required: can
```

## Configuration

Set the queue storage path via environment variable:
```bash
export BOARDFARM_QUEUE_PATH=/var/lib/boardfarm/queue.json
```

## Implementation Details

### Key Classes

- **BoardQueue**: Main queue manager with per-type queues
- **QueueEntry**: Individual queue request with matching logic
- **QueueStatus**: Enum for entry states (PENDING, ASSIGNED, COMPLETED, CANCELLED)

### Background Tasks

- **Auto-save**: Every 30 seconds
- **Cleanup**: Removes completed entries older than 24 hours (hourly)
- **Priority boost**: Applies fairness boosts every 10 minutes

### Thread Safety

All queue operations are protected by a threading.Lock for safe concurrent access from multiple agents.

## Best Practices

1. **Use appropriate priority**: Don't abuse priority 1 for routine work
2. **Set realistic time estimates**: Helps with planning and fairness
3. **Specify required features accurately**: Ensures you get a board that works
4. **Cancel unused requests**: Frees up the queue for others
5. **Release boards promptly**: When done or if plans change

## Troubleshooting

**Queue position not changing?**
- Check if higher priority requests are ahead of you
- Priority boost will eventually move you up

**Board not assigned even though available?**
- Check if your required_features match the board
- Use `get_board_features()` to see board capabilities

**Lost queue entry after restart?**
- Check if the entry was in ASSIGNED state (reset to pending on restart)
- Check storage path permissions

**Getting "wrong agent" error?**
- Ensure agent_id matches what you used when queuing
- Agent IDs are case-sensitive