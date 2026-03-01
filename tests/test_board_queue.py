"""Tests for the priority-based FIFO queue system."""

import os
import sys
import json
import pytest
import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_boardfarm.board_queue import (
    BoardQueue, QueueEntry, QueueStatus, QueueStats, get_queue
)


class TestQueueEntry:
    """Test QueueEntry dataclass and methods."""
    
    def test_queue_entry_creation(self):
        """Test creating a QueueEntry."""
        entry = QueueEntry(
            queue_id="test-001",
            board_type="h755",
            priority=2,
            agent_id="agent-1",
            job_description="Test job",
            estimated_minutes=60,
            requested_at=datetime.now(),
            status=QueueStatus.PENDING,
            required_features=["ethernet", "can"],
            optional_features=["sd_card"],
            min_capabilities={"ram_kb": 512},
        )
        
        assert entry.queue_id == "test-001"
        assert entry.board_type == "h755"
        assert entry.priority == 2
        assert entry.required_features == ["ethernet", "can"]
        assert entry.optional_features == ["sd_card"]
        assert entry.min_capabilities == {"ram_kb": 512}
    
    def test_matches_board_all_required_present(self):
        """Test board matching when all required features present."""
        entry = QueueEntry(
            queue_id="test-001",
            board_type="h755",
            priority=2,
            agent_id="agent-1",
            job_description="Test job",
            estimated_minutes=60,
            requested_at=datetime.now(),
            status=QueueStatus.PENDING,
            required_features=["ethernet", "can"],
            optional_features=["sd_card"],
        )
        
        board_features = {"ethernet", "can", "usb", "sd_card"}
        board_capabilities = {"ram_kb": 1024, "flash_kb": 2048}
        
        matches, score = entry.matches_board(board_features, board_capabilities)
        
        assert matches is True
        assert score > 0  # Should have score for optional feature
    
    def test_matches_board_missing_required(self):
        """Test board matching fails when required feature missing."""
        entry = QueueEntry(
            queue_id="test-001",
            board_type="h755",
            priority=2,
            agent_id="agent-1",
            job_description="Test job",
            estimated_minutes=60,
            requested_at=datetime.now(),
            status=QueueStatus.PENDING,
            required_features=["ethernet", "can"],
        )
        
        board_features = {"ethernet", "usb"}  # Missing "can"
        board_capabilities = {}
        
        matches, score = entry.matches_board(board_features, board_capabilities)
        
        assert matches is False
        assert score == 0.0
    
    def test_matches_board_capability_minimum(self):
        """Test board matching with capability minimums."""
        entry = QueueEntry(
            queue_id="test-001",
            board_type="h755",
            priority=2,
            agent_id="agent-1",
            job_description="Test job",
            estimated_minutes=60,
            requested_at=datetime.now(),
            status=QueueStatus.PENDING,
            min_capabilities={"ram_kb": 512},
        )
        
        board_features = set()
        
        # Board exceeds minimum
        board_capabilities = {"ram_kb": 1024}
        matches, score = entry.matches_board(board_features, board_capabilities)
        assert matches is True
        assert score > 0  # Bonus for extra capacity
        
        # Board meets minimum exactly
        board_capabilities = {"ram_kb": 512}
        matches, score = entry.matches_board(board_features, board_capabilities)
        assert matches is True
        
        # Board below minimum
        board_capabilities = {"ram_kb": 256}
        matches, score = entry.matches_board(board_features, board_capabilities)
        assert matches is False
    
    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        original = QueueEntry(
            queue_id="test-001",
            board_type="h755",
            priority=2,
            agent_id="agent-1",
            job_description="Test job",
            estimated_minutes=60,
            requested_at=datetime.now(),
            status=QueueStatus.PENDING,
            required_features=["ethernet"],
        )
        
        data = original.to_dict()
        restored = QueueEntry.from_dict(data)
        
        assert restored.queue_id == original.queue_id
        assert restored.board_type == original.board_type
        assert restored.priority == original.priority
        assert restored.required_features == original.required_features
        assert restored.status == original.status


class TestBoardQueue:
    """Test BoardQueue functionality."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        yield path
        os.unlink(path)
    
    @pytest.fixture
    def queue(self, temp_storage):
        """Create a BoardQueue with temporary storage."""
        return BoardQueue(storage_path=temp_storage)
    
    def test_add_request(self, queue):
        """Test adding a queue request."""
        queue_id = queue.add_request(
            board_type="h755",
            priority=2,
            estimated_minutes=60,
            agent_id="agent-1",
            job_description="Test job",
        )
        
        assert queue_id is not None
        assert len(queue_id) > 0
        
        entry = queue.get_entry(queue_id)
        assert entry is not None
        assert entry.board_type == "h755"
        assert entry.priority == 2
        assert entry.status == QueueStatus.PENDING
    
    def test_priority_normalization(self, queue):
        """Test that priority is clamped to valid range."""
        # Too high
        queue_id1 = queue.add_request(
            board_type="h755",
            priority=10,  # Should be clamped to 5
            estimated_minutes=30,
            agent_id="agent-1",
            job_description="Test",
        )
        entry1 = queue.get_entry(queue_id1)
        assert entry1.priority == 5
        
        # Too low
        queue_id2 = queue.add_request(
            board_type="h755",
            priority=0,  # Should be clamped to 1
            estimated_minutes=30,
            agent_id="agent-1",
            job_description="Test",
        )
        entry2 = queue.get_entry(queue_id2)
        assert entry2.priority == 1
    
    def test_queue_position(self, queue):
        """Test queue position tracking."""
        # Add multiple requests
        id1 = queue.add_request("h755", 3, 30, "agent-1", "Job 1")
        id2 = queue.add_request("h755", 2, 30, "agent-2", "Job 2")  # Higher priority
        id3 = queue.add_request("h755", 3, 30, "agent-3", "Job 3")  # Same priority as 1
        
        # Position should be: id2 (priority 2), id1 (priority 3, first), id3 (priority 3, second)
        pos1, _, desc1 = queue.get_position(id1)
        pos2, _, desc2 = queue.get_position(id2)
        pos3, _, desc3 = queue.get_position(id3)
        
        assert pos2 == 1  # Highest priority
        assert pos1 == 2  # Same priority, requested first
        assert pos3 == 3  # Same priority, requested second
    
    def test_find_best_match_fifo(self, queue):
        """Test FIFO ordering within same priority."""
        id1 = queue.add_request("h755", 2, 30, "agent-1", "Job 1")
        id2 = queue.add_request("h755", 2, 30, "agent-2", "Job 2")
        id3 = queue.add_request("h755", 2, 30, "agent-3", "Job 3")
        
        # All same priority, should be FIFO
        match = queue.get_next_for_board("h755", "board-1")
        assert match.queue_id == id1
    
    def test_find_best_match_with_features(self, queue):
        """Test feature-based matching."""
        # Request with required features
        id1 = queue.add_request(
            "h755", 2, 30, "agent-1", "Job 1",
            required_features=["ethernet"],
        )
        id2 = queue.add_request(
            "h755", 2, 30, "agent-2", "Job 2",
            required_features=["can"],
        )
        
        # Board with ethernet but not can
        board_features = {"ethernet", "usb"}
        board_capabilities = {}
        
        match = queue.find_best_match("h755", "board-1", board_features, board_capabilities)
        assert match.queue_id == id1
        
        # Board with can but not ethernet
        board_features = {"can", "usb"}
        match = queue.find_best_match("h755", "board-2", board_features, board_capabilities)
        assert match.queue_id == id2
    
    def test_find_best_match_score(self, queue):
        """Test that feature scoring works correctly."""
        # Two requests, same priority
        id1 = queue.add_request(
            "h755", 2, 30, "agent-1", "Job 1",
            optional_features=["sd_card"],
        )
        id2 = queue.add_request(
            "h755", 2, 30, "agent-2", "Job 2",
            optional_features=["wifi"],
        )
        
        # Board with sd_card but not wifi
        board_features = {"ethernet", "sd_card"}
        board_capabilities = {}
        
        match = queue.find_best_match("h755", "board-1", board_features, board_capabilities)
        assert match.queue_id == id1  # Better match due to sd_card
    
    def test_assign_board(self, queue):
        """Test board assignment."""
        queue_id = queue.add_request("h755", 2, 30, "agent-1", "Test job")

        success = queue.assign_board_sync(queue_id, "board-1")
        assert success is True

        entry = queue.get_entry(queue_id)
        assert entry.status == QueueStatus.ASSIGNED
        assert entry.assigned_board_id == "board-1"
        assert entry.assigned_at is not None

    def test_complete_job(self, queue):
        """Test completing a job."""
        queue_id = queue.add_request("h755", 2, 30, "agent-1", "Test job")
        queue.assign_board_sync(queue_id, "board-1")
        
        success = queue.complete_job(queue_id)
        assert success is True
        
        entry = queue.get_entry(queue_id)
        assert entry.status == QueueStatus.COMPLETED
        assert entry.completed_at is not None
    
    def test_cancel_request(self, queue):
        """Test cancelling a request."""
        queue_id = queue.add_request("h755", 2, 30, "agent-1", "Test job")
        
        # Wrong agent
        success = queue.cancel_request(queue_id, "agent-2")
        assert success is False
        
        # Correct agent
        success = queue.cancel_request(queue_id, "agent-1")
        assert success is True
        
        entry = queue.get_entry(queue_id)
        assert entry.status == QueueStatus.CANCELLED
    
    def test_list_queue(self, queue):
        """Test listing queue entries."""
        queue.add_request("h755", 2, 30, "agent-1", "Job 1")
        queue.add_request("h755", 3, 30, "agent-2", "Job 2")
        queue.add_request("esp32", 2, 30, "agent-3", "Job 3")
        
        # List all pending
        pending = queue.list_queue(status=QueueStatus.PENDING)
        assert len(pending) == 3
        
        # Filter by board type
        h755_only = queue.list_queue(status=QueueStatus.PENDING, board_type="h755")
        assert len(h755_only) == 2
        
        # Filter by agent
        agent1_only = queue.list_queue(status=QueueStatus.PENDING, agent_id="agent-1")
        assert len(agent1_only) == 1
    
    def test_queue_summary(self, queue):
        """Test getting queue summary."""
        queue.add_request("h755", 2, 30, "agent-1", "Job 1")
        queue.add_request("h755", 2, 30, "agent-2", "Job 2")
        queue.add_request("esp32", 3, 30, "agent-3", "Job 3")
        
        summary = queue.get_queue_summary()
        
        assert summary["pending"] == 3
        assert summary["by_board_type"]["h755"] == 2
        assert summary["by_board_type"]["esp32"] == 1
        assert summary["by_priority"][2] == 2
        assert summary["by_priority"][3] == 1
    
    def test_persistence(self, temp_storage):
        """Test saving and loading queue state."""
        # Create queue and add entries
        queue1 = BoardQueue(storage_path=temp_storage)
        id1 = queue1.add_request("h755", 2, 30, "agent-1", "Job 1")
        id2 = queue1.add_request("h755", 3, 30, "agent-2", "Job 2")
        queue1._save()
        
        # Create new queue instance, should load from disk
        queue2 = BoardQueue(storage_path=temp_storage)
        
        assert id1 in queue2._entries
        assert id2 in queue2._entries
        assert queue2._stats.total_requests == 2
    
    def test_cleanup_expired(self, queue):
        """Test cleanup of old entries."""
        # Add and complete an entry
        queue_id = queue.add_request("h755", 2, 30, "agent-1", "Old job")
        queue.assign_board_sync(queue_id, "board-1")
        queue.complete_job(queue_id)
        
        # Manually set completion time to long ago
        entry = queue.get_entry(queue_id)
        entry.completed_at = datetime.now() - timedelta(hours=48)
        
        # Cleanup should remove it
        removed = queue.cleanup_expired()
        assert removed == 1
        assert queue.get_entry(queue_id) is None
    
    def test_priority_boost(self, queue):
        """Test priority boost for long-waiting entries."""
        # Add entry
        queue_id = queue.add_request("h755", 3, 30, "agent-1", "Waiting job")
        
        # Manually set request time to long ago
        entry = queue.get_entry(queue_id)
        entry.requested_at = datetime.now() - timedelta(minutes=45)
        
        # Apply boost
        boosted = queue.apply_priority_boost()
        assert boosted >= 1
        
        # Check priority was boosted
        entry = queue.get_entry(queue_id)
        assert entry.priority == 2  # Boosted from 3 to 2
        assert entry.priority_boost_count == 1
    
    def test_max_reservation_time(self, queue):
        """Test that max reservation time is enforced."""
        # Try to request more than max
        queue_id = queue.add_request(
            "h755", 2, 1000, "agent-1", "Long job"  # 1000 minutes > 480 max
        )
        
        entry = queue.get_entry(queue_id)
        assert entry.estimated_minutes == 480  # Clamped to max
