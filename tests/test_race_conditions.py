"""Test race condition fixes in board_manager and board_queue.

This test simulates the multi-agent battle test scenario that exposed
the race conditions:
- Multiple agents simultaneously trying to reserve boards
- Board releases triggering queue assignments
- Concurrent state reads and writes
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime
from pathlib import Path
import tempfile
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mcp_boardfarm.models import Board, BoardState, DebuggerConfig, SerialConfig
from mcp_boardfarm.board_manager import BoardManager
from mcp_boardfarm.board_queue import BoardQueue, QueueStatus


@pytest.fixture
def temp_storage():
    """Create temporary storage for queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "queue.json"


@pytest_asyncio.fixture
async def board_manager_fixture(temp_storage):
    """Create a BoardManager with test boards."""
    queue = BoardQueue(storage_path=str(temp_storage))
    bm = BoardManager(config_path=None, board_queue=queue)

    # Create test boards
    bm.boards = {
        "board-01": Board(
            board_id="board-01",
            type="h755",
            model="Nucleo H755ZI-Q",
            mcu="STM32H755",
            status=BoardState.AVAILABLE,
            debugger=DebuggerConfig(),
            serial=SerialConfig(),
        ),
        "board-02": Board(
            board_id="board-02",
            type="h755",
            model="Nucleo H755ZI-Q",
            mcu="STM32H755",
            status=BoardState.AVAILABLE,
            debugger=DebuggerConfig(),
            serial=SerialConfig(),
        ),
    }

    bm.set_queue(queue)
    yield bm


class TestRaceConditions:
    """Test cases for race condition fixes."""

    @pytest.mark.asyncio
    async def test_concurrent_reservations(self, board_manager_fixture):
        """Test that only one agent can reserve a board when racing.

        Simulates the battle test scenario:
        - Agent 1 and Agent 2 try to reserve the same board simultaneously
        - Only one should succeed
        """
        bm = board_manager_fixture

        results = []

        async def try_reserve(agent_id):
            """Try to reserve board-01."""
            success = await bm.reserve_board("board-01", agent_id, timeout_minutes=30)
            results.append((agent_id, success))
            return success

        # Two agents race to reserve the same board
        await asyncio.gather(
            try_reserve("agent-1"),
            try_reserve("agent-2"),
            return_exceptions=True
        )

        # Count successes
        successes = [r for r in results if r[1]]
        failures = [r for r in results if not r[1]]

        # Exactly one should succeed
        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
        assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}: {results}"

        # Verify board is reserved
        board = bm.get_board("board-01")
        assert board.status == BoardState.RESERVED
        assert board.reserved_by == successes[0][0]

    @pytest.mark.asyncio
    async def test_reserve_after_release_race(self, board_manager_fixture):
        """Test race between release and reserve.

        Simulates:
        - Agent 1 releases a board
        - Agent 2 tries to reserve at the same time
        - Queue tries to assign to waiting agent
        """
        bm = board_manager_fixture

        # First, agent-1 reserves the board
        success = await bm.reserve_board("board-01", "agent-1", timeout_minutes=30)
        assert success, "Initial reservation should succeed"

        results = []

        async def release_and_wait():
            """Agent 1 releases the board."""
            await asyncio.sleep(0.01)  # Small delay to create race window
            success = await bm.release_board("board-01", "agent-1")
            results.append(("release", success))
            return success

        async def try_reserve():
            """Agent 2 tries to reserve after a short delay."""
            await asyncio.sleep(0.015)  # Slightly longer delay
            success = await bm.reserve_board("board-01", "agent-2", timeout_minutes=30)
            results.append(("reserve", success))
            return success

        # Run both operations
        await asyncio.gather(
            release_and_wait(),
            try_reserve(),
            return_exceptions=True
        )

        # Verify final state is valid
        board = bm.get_board("board-01")
        assert board.status in [BoardState.AVAILABLE, BoardState.RESERVED]

        if board.status == BoardState.RESERVED:
            # Someone got it
            assert board.reserved_by in ["agent-1", "agent-2"]

    @pytest.mark.asyncio
    async def test_multiple_agents_multiple_boards(self, board_manager_fixture):
        """Test the full battle test scenario.

        3 agents, 2 boards:
        - All 3 try to get boards simultaneously
        - 2 should get boards, 1 should wait/queue
        - When a board is released, the waiting agent should get it
        """
        bm = board_manager_fixture

        reservation_order = []

        async def agent_work(agent_id, delay=0):
            """Simulate an agent trying to get a board."""
            await asyncio.sleep(delay)

            # Try to reserve any available board
            for board_id in ["board-01", "board-02"]:
                success = await bm.reserve_board(board_id, agent_id, timeout_minutes=30)
                if success:
                    reservation_order.append((agent_id, board_id))
                    return board_id

            # No boards available
            return None

        # All 3 agents try simultaneously
        results = await asyncio.gather(
            agent_work("agent-1", delay=0),
            agent_work("agent-2", delay=0.001),
            agent_work("agent-3", delay=0.002),
            return_exceptions=True
        )

        # Check that 2 agents got boards
        successful_reservations = [r for r in results if r is not None and not isinstance(r, Exception)]
        assert len(successful_reservations) == 2, f"Expected 2 reservations, got {len(successful_reservations)}: {results}"

        # Verify both boards are reserved
        board1 = bm.get_board("board-01")
        board2 = bm.get_board("board-02")

        reserved_count = sum(1 for b in [board1, board2] if b.status == BoardState.RESERVED)
        assert reserved_count == 2, f"Expected 2 reserved boards, got {reserved_count}"

        print(f"Reservation order: {reservation_order}")

    @pytest.mark.asyncio
    async def test_invalid_state_transitions(self, board_manager_fixture):
        """Test that invalid state transitions are rejected."""
        bm = board_manager_fixture

        # Reserve a board
        success = await bm.reserve_board("board-01", "agent-1", timeout_minutes=30)
        assert success

        # Try to reserve already-reserved board
        success = await bm.reserve_board("board-01", "agent-2", timeout_minutes=30)
        assert not success, "Should not be able to reserve already-reserved board"

        # Release it
        success = await bm.release_board("board-01", "agent-1")
        assert success

        # Try to release already-available board
        success = await bm.release_board("board-01", "agent-1")
        assert not success, "Should not be able to release available board"

    @pytest.mark.asyncio
    async def test_concurrent_list_and_reserve(self, board_manager_fixture):
        """Test that listing boards is consistent during concurrent reservations."""
        bm = board_manager_fixture

        available_counts = []

        async def list_boards():
            """List available boards."""
            for _ in range(10):
                boards = bm.list_boards(only_available=True)
                available_counts.append(len(boards))
                await asyncio.sleep(0.005)

        async def reserve_and_release():
            """Reserve and release boards."""
            for i in range(5):
                await bm.reserve_board("board-01", f"agent-{i}", timeout_minutes=30)
                await asyncio.sleep(0.01)
                await bm.release_board("board-01", f"agent-{i}")
                await asyncio.sleep(0.01)

        # Run both operations concurrently
        await asyncio.gather(
            list_boards(),
            reserve_and_release(),
            return_exceptions=True
        )

        # Verify counts are always valid (0, 1, or 2)
        for count in available_counts:
            assert count in [0, 1, 2], f"Invalid available count: {count}"

    @pytest.mark.asyncio
    async def test_queue_assignment_atomicity(self, board_manager_fixture):
        """Test that queue assignment and board reservation are atomic."""
        bm = board_manager_fixture
        queue = bm._queue

        # First reserve the board so we can release it
        await bm.reserve_board("board-01", "holder", timeout_minutes=30)

        # Add a queue request
        queue_id = queue.add_request(
            board_type="h755",
            priority=1,
            estimated_minutes=30,
            agent_id="queued-agent",
            job_description="Test job",
        )

        # Now release it - this should trigger queue processing
        await bm.release_board("board-01", "holder")

        # Give time for queue processing
        await asyncio.sleep(0.1)

        # Check queue entry status
        entry = queue.get_entry(queue_id)
        if entry and entry.status == QueueStatus.ASSIGNED:
            # Verify board is reserved for the queued agent
            board = bm.get_board("board-01")
            assert board.status == BoardState.RESERVED
            assert board.reserved_by == "queued-agent"


class TestStateTransitions:
    """Test state transition validation."""

    def test_valid_transitions(self):
        """Test that valid state transitions are allowed."""
        valid = BoardManager.VALID_TRANSITIONS

        # Should be able to go from AVAILABLE to RESERVED
        assert (BoardState.AVAILABLE, BoardState.RESERVED) in valid

        # Should be able to go from RESERVED to AVAILABLE
        assert (BoardState.RESERVED, BoardState.AVAILABLE) in valid

        # Create a dummy manager to test the method
        bm = BoardManager.__new__(BoardManager)
        # Same state should always be valid
        for state in BoardState:
            assert bm._is_valid_transition(state, state)

    def test_invalid_transitions(self):
        """Test that invalid state transitions are rejected."""
        # Can't go from OFFLINE directly to RUNNING
        assert (BoardState.OFFLINE, BoardState.RUNNING) not in BoardManager.VALID_TRANSITIONS

        # Can't go from ERROR directly to RUNNING
        assert (BoardState.ERROR, BoardState.RUNNING) not in BoardManager.VALID_TRANSITIONS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
