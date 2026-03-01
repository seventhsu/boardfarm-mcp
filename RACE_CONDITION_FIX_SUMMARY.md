# Race Condition Fix Summary

## Problem
During multi-agent battle testing with 3 agents and 2 boards:
- Agent 1 got Board 01, worked, released it
- Agent 2 reported "0 H755 boards available" and timed out (incorrect)
- Agent 3 waited 3-4 min, got Board 01 after Agent 1 released (correct)
- Board 02 was never assigned despite being physically available

## Root Causes

### 1. No Locking in BoardManager
- `reserve_board()`, `release_board()`, and `update_board_state()` had no synchronization
- Multiple agents could simultaneously check `board.status == AVAILABLE` and both proceed to reserve
- The `_is_valid_transition()` method incorrectly allowed RESERVED→RESERVED transitions

### 2. Race Between Queue Assignment and Board Reservation
- `_check_queue_for_board()` held the lock while calling `await self._queue.assign_board()`
- The callback `_on_board_assigned()` tried to acquire the same lock → **DEADLOCK**
- Board could be taken between queue assignment and reservation

### 3. Async/Sync Mismatch
- `BoardQueue` used `threading.Lock` (sync)
- `BoardManager` had no lock but was called from async contexts
- Callbacks could be sync or async, causing inconsistencies

## Changes Made

### board_manager.py

1. **Added `asyncio.Lock`** (`self._lock`) for atomic board operations

2. **Made methods async** with proper locking:
   - `reserve_board()` - Now requires `board.status == BoardState.AVAILABLE` explicitly
   - `release_board()` - Validates reservation before releasing
   - `update_board_state()` - Validates state transitions
   - `check_expired_reservations()` - Checks queue after releasing
   - `_check_queue_for_board()` - Three-phase: find→assign→finalize
   - `_on_board_assigned()` - Async verification callback

3. **Added state transition validation** (`VALID_TRANSITIONS` set and `_is_valid_transition()`)

4. **Fixed queue assignment atomicity**:
   - Reserve board immediately with temporary holder (`assigning:{queue_id}`)
   - Release lock before calling queue (prevents deadlock)
   - Call `assign_board()` without holding lock
   - Finalize reservation after successful assignment

### board_queue.py

1. **Added async support for callbacks**:
   - `assign_board()` - Now async, supports both sync and async callbacks
   - `assign_board_sync()` - Synchronous version for non-async contexts
   - Uses `inspect.iscoroutinefunction()` to detect async callbacks

2. **Added type aliases** for callback types

### server.py

1. **Updated all callers** to use `await` for async board manager methods:
   - `await bm.reserve_board()`
   - `await bm.release_board()`
   - `await bm.update_board_state()`

### Tests

1. **Added comprehensive race condition tests** (`tests/test_race_conditions.py`):
   - `test_concurrent_reservations` - Verifies only one agent gets board
   - `test_reserve_after_release_race` - Tests release/reserve race
   - `test_multiple_agents_multiple_boards` - Full battle test scenario
   - `test_invalid_state_transitions` - Validates state machine
   - `test_concurrent_list_and_reserve` - Tests list consistency
   - `test_queue_assignment_atomicity` - Tests queue integration

2. **Updated existing tests** to use `assign_board_sync()` where needed

## Verification

All 43 tests pass:
- 21 existing board queue tests
- 14 existing build provider tests
- 8 new race condition tests

## Key Design Decisions

1. **Explicit status check**: `reserve_board()` explicitly checks `board.status == BoardState.AVAILABLE` rather than relying solely on transition validation

2. **Three-phase queue assignment**: 
   - Phase 1: Find match and mark board as reserved (with temporary holder)
   - Phase 2: Call queue without holding lock (prevents deadlock)
   - Phase 3: Finalize reservation after successful assignment

3. **Async-first design**: All board manager methods are async with proper locking, supporting concurrent agent access

4. **Backward compatibility**: Added `assign_board_sync()` for sync contexts while making primary API async
