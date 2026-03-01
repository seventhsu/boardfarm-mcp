"""Priority-based FIFO queue system for board reservations with feature matching.

This module provides a fair allocation system for board reservations with:
- Per-board-type FIFO queues
- Priority levels (1-5, 1=highest) within each queue
- Feature-based board matching (required/optional features, capabilities)
- Custom reservation duration
- Queue position tracking
- Automatic assignment when boards become available
- Fairness algorithms to prevent starvation
- Persistence across server restarts
"""

import os
import json
import uuid
import logging
import asyncio
import inspect
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable, Tuple, Set, Union
from threading import Lock

# Type alias for callbacks that can be sync or async
QueueCallback = Callable[[str, "QueueEntry"], None]
AssignmentCallback = Callable[[str, str], None]  # queue_id, board_id

logger = logging.getLogger(__name__)


class QueueStatus(Enum):
    """Queue entry status."""
    PENDING = auto()
    ASSIGNED = auto()
    COMPLETED = auto()
    CANCELLED = auto()
    EXPIRED = auto()


@dataclass
class QueueEntry:
    """Represents a queue request for a board."""
    queue_id: str
    board_type: str  # "h755", "esp32", etc.
    priority: int  # 1-5, 1 is highest
    agent_id: str
    job_description: str
    estimated_minutes: int
    requested_at: datetime
    status: QueueStatus
    
    # Feature matching
    required_features: List[str] = field(default_factory=list)
    optional_features: List[str] = field(default_factory=list)
    min_capabilities: Dict[str, Any] = field(default_factory=dict)
    
    # Assignment tracking
    assigned_at: Optional[datetime] = None
    assigned_board_id: Optional[str] = None
    completed_at: Optional[datetime] = None
    
    # Fairness tracking
    priority_boost_count: int = 0
    last_boost_at: Optional[datetime] = None
    
    # Options
    auto_accept: bool = False  # Auto-reserve when board available
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "queue_id": self.queue_id,
            "board_type": self.board_type,
            "priority": self.priority,
            "agent_id": self.agent_id,
            "job_description": self.job_description,
            "estimated_minutes": self.estimated_minutes,
            "requested_at": self.requested_at.isoformat(),
            "status": self.status.name,
            "required_features": self.required_features,
            "optional_features": self.optional_features,
            "min_capabilities": self.min_capabilities,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "assigned_board_id": self.assigned_board_id,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "priority_boost_count": self.priority_boost_count,
            "last_boost_at": self.last_boost_at.isoformat() if self.last_boost_at else None,
            "auto_accept": self.auto_accept,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueEntry":
        """Create QueueEntry from dictionary."""
        return cls(
            queue_id=data["queue_id"],
            board_type=data["board_type"],
            priority=data["priority"],
            agent_id=data["agent_id"],
            job_description=data["job_description"],
            estimated_minutes=data["estimated_minutes"],
            requested_at=datetime.fromisoformat(data["requested_at"]),
            status=QueueStatus[data["status"]],
            required_features=data.get("required_features", []),
            optional_features=data.get("optional_features", []),
            min_capabilities=data.get("min_capabilities", {}),
            assigned_at=datetime.fromisoformat(data["assigned_at"]) if data.get("assigned_at") else None,
            assigned_board_id=data.get("assigned_board_id"),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            priority_boost_count=data.get("priority_boost_count", 0),
            last_boost_at=datetime.fromisoformat(data["last_boost_at"]) if data.get("last_boost_at") else None,
            auto_accept=data.get("auto_accept", False),
        )
    
    def matches_board(self, board_features: Set[str], board_capabilities: Dict[str, Any]) -> Tuple[bool, float]:
        """Check if this entry matches a board's features and capabilities.
        
        Args:
            board_features: Set of features the board has
            board_capabilities: Dict of board capabilities
            
        Returns:
            Tuple of (matches_required, score) where higher score is better match
        """
        # Check required features - board must have ALL required features
        required_set = set(self.required_features)
        if not required_set.issubset(board_features):
            return False, 0.0
        
        # Calculate score based on optional features and capabilities
        score = 0.0
        
        # Optional features match (1 point each)
        optional_set = set(self.optional_features)
        matched_optional = optional_set.intersection(board_features)
        score += len(matched_optional)
        
        # Bonus for capability headroom
        for cap_key, min_val in self.min_capabilities.items():
            board_val = board_capabilities.get(cap_key)
            if board_val is None:
                continue
            if isinstance(min_val, (int, float)) and isinstance(board_val, (int, float)):
                if board_val < min_val:
                    return False, 0.0  # Doesn't meet minimum
                # Bonus for extra capacity (diminishing returns)
                ratio = board_val / max(min_val, 1)
                score += min(ratio - 1.0, 2.0)  # Cap bonus at 2.0
        
        return True, score


@dataclass
class QueueStats:
    """Statistics for the queue."""
    total_requests: int = 0
    completed_requests: int = 0
    cancelled_requests: int = 0
    expired_requests: int = 0
    avg_wait_time_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "completed_requests": self.completed_requests,
            "cancelled_requests": self.cancelled_requests,
            "expired_requests": self.expired_requests,
            "avg_wait_time_seconds": self.avg_wait_time_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueStats":
        return cls(**data)


class BoardQueue:
    """Priority-based FIFO queue for board reservations with feature matching."""
    
    # Configuration constants
    PRIORITY_LEVELS = 5  # 1-5, 1 is highest
    DEFAULT_TIMEOUT_MINUTES = 30
    MAX_RESERVATION_MINUTES = 480  # 8 hours max reservation
    PRIORITY_BOOST_AFTER_MINUTES = 30  # Boost priority after waiting this long
    MAX_BOOST_COUNT = 3  # Maximum number of priority boosts
    CLEANUP_AFTER_HOURS = 24  # Remove completed entries after this time
    SAVE_INTERVAL_SECONDS = 30  # Auto-save interval
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the board queue.
        
        Args:
            storage_path: Path to JSON file for persistence (default: ./data/queue.json)
        """
        # Per-type queues: board_type -> List[QueueEntry]
        self._queues: Dict[str, List[QueueEntry]] = {}
        # All entries indexed by queue_id
        self._entries: Dict[str, QueueEntry] = {}
        
        self._lock = Lock()
        self._callbacks: List[QueueCallback] = []
        self._assignment_callbacks: List[AssignmentCallback] = []
        self._async_lock = asyncio.Lock()  # For async operations
        
        # Set up storage path
        if storage_path is None:
            storage_path = os.environ.get("BOARDFARM_QUEUE_PATH", "./data/queue.json")
        self._storage_path = Path(storage_path)
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Statistics
        self._stats = QueueStats()
        
        # Background tasks
        self._save_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._boost_task: Optional[asyncio.Task] = None
        
        # Load existing queue
        self._load()
    
    async def start(self):
        """Start background tasks."""
        self._save_task = asyncio.create_task(self._auto_save())
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._boost_task = asyncio.create_task(self._periodic_priority_boost())
        logger.info("BoardQueue background tasks started")
    
    async def stop(self):
        """Stop background tasks and save state."""
        if self._save_task:
            self._save_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._boost_task:
            self._boost_task.cancel()
        
        # Final save
        self._save()
        logger.info("BoardQueue stopped")
    
    def add_request(
        self,
        board_type: str,
        priority: int,
        estimated_minutes: int,
        agent_id: str,
        job_description: str,
        required_features: Optional[List[str]] = None,
        optional_features: Optional[List[str]] = None,
        min_capabilities: Optional[Dict[str, Any]] = None,
        auto_accept: bool = False
    ) -> str:
        """Add a new queue request.
        
        Args:
            board_type: Type of board needed (e.g., "h755", "esp32")
            priority: Priority level 1-5 (1 is highest)
            estimated_minutes: Estimated time needed with the board
            agent_id: Unique identifier for the requesting agent
            job_description: Description of the job
            required_features: List of features the board MUST have
            optional_features: List of features that improve the match
            min_capabilities: Dict of minimum capability requirements
            auto_accept: If True, auto-reserve when board becomes available
            
        Returns:
            queue_id: Unique identifier for this queue request
        """
        # Validate priority
        priority = max(1, min(self.PRIORITY_LEVELS, priority))
        
        # Validate estimated minutes
        estimated_minutes = min(estimated_minutes, self.MAX_RESERVATION_MINUTES)
        
        queue_id = str(uuid.uuid4())[:8]  # Short UUID for readability
        
        entry = QueueEntry(
            queue_id=queue_id,
            board_type=board_type.lower(),
            priority=priority,
            agent_id=agent_id,
            job_description=job_description,
            estimated_minutes=estimated_minutes,
            requested_at=datetime.now(),
            status=QueueStatus.PENDING,
            required_features=required_features or [],
            optional_features=optional_features or [],
            min_capabilities=min_capabilities or {},
            auto_accept=auto_accept,
        )
        
        with self._lock:
            # Add to per-type queue
            if entry.board_type not in self._queues:
                self._queues[entry.board_type] = []
            self._queues[entry.board_type].append(entry)
            
            # Add to global entries index
            self._entries[queue_id] = entry
            self._stats.total_requests += 1
            
            # Keep queue sorted by priority, then time
            self._sort_queue(entry.board_type)
        
        self._save()
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback("added", entry)
            except Exception as e:
                logger.error(f"Queue callback error: {e}")
        
        logger.info(f"Queue request added: {queue_id} for {board_type} (priority {priority}) by {agent_id}")
        return queue_id
    
    def _sort_queue(self, board_type: str):
        """Sort a per-type queue by priority (ascending), then request time."""
        if board_type in self._queues:
            self._queues[board_type].sort(key=lambda e: (e.priority, e.requested_at))
    
    def get_entry(self, queue_id: str) -> Optional[QueueEntry]:
        """Get a queue entry by ID."""
        with self._lock:
            return self._entries.get(queue_id)
    
    def get_position(self, queue_id: str) -> Tuple[int, int, str]:
        """Get queue position information.
        
        Returns:
            Tuple of (position_within_queue, total_pending_at_priority, descriptive_string)
        """
        with self._lock:
            entry = self._entries.get(queue_id)
            if not entry:
                return (-1, 0, "Queue entry not found")
            
            if entry.status != QueueStatus.PENDING:
                if entry.status == QueueStatus.ASSIGNED:
                    return (0, 0, f"Board assigned: {entry.assigned_board_id}")
                return (-1, 0, f"Status: {entry.status.name}")
            
            # Get queue for this board type
            queue = self._queues.get(entry.board_type, [])
            pending = [e for e in queue if e.status == QueueStatus.PENDING]
            
            # Find position
            try:
                position = pending.index(entry) + 1
            except ValueError:
                position = -1
            
            # Count entries at same priority
            same_priority_count = len([e for e in pending if e.priority == entry.priority])
            same_priority_ahead = len([
                e for e in pending
                if e.priority == entry.priority and e.requested_at < entry.requested_at
            ])
            
            # Build descriptive string
            if position == 1:
                desc = "Next in line!"
            else:
                desc = f"{position}th in queue for {entry.board_type}, priority {entry.priority}"
                if same_priority_ahead > 0:
                    desc += f" ({same_priority_ahead} ahead at same priority)"
            
            return (position, same_priority_count, desc)
    
    def find_best_match(
        self,
        board_type: str,
        board_id: str,
        board_features: Set[str],
        board_capabilities: Dict[str, Any]
    ) -> Optional[QueueEntry]:
        """Find the best matching queue entry for a specific board.
        
        Uses priority + FIFO ordering with feature matching scoring.
        
        Args:
            board_type: The type of the board
            board_id: The board ID that became available
            board_features: Set of features this board has
            board_capabilities: Dict of board capabilities
            
        Returns:
            QueueEntry or None if no pending requests match
        """
        with self._lock:
            queue = self._queues.get(board_type, [])
            
            # Get all pending entries for this board type
            candidates = [e for e in queue if e.status == QueueStatus.PENDING]
            
            if not candidates:
                return None
            
            # Score each candidate
            scored_candidates = []
            for entry in candidates:
                matches, score = entry.matches_board(board_features, board_capabilities)
                if matches:
                    # Combine priority (primary) with feature score (secondary)
                    # Lower priority number = higher priority
                    # Higher feature score = better match
                    combined_score = (entry.priority, -score, entry.requested_at)
                    scored_candidates.append((combined_score, entry))
            
            if not scored_candidates:
                return None
            
            # Sort by combined score and return best match
            scored_candidates.sort(key=lambda x: x[0])
            return scored_candidates[0][1]
    
    def get_next_for_board(
        self,
        board_type: str,
        board_id: str,
        board_features: Optional[Set[str]] = None,
        board_capabilities: Optional[Dict[str, Any]] = None
    ) -> Optional[QueueEntry]:
        """Get the next queue entry for a specific board (legacy, uses FIFO only).
        
        For feature-based matching, use find_best_match().
        """
        with self._lock:
            queue = self._queues.get(board_type, [])
            
            # Get all pending entries for this board type
            pending = [e for e in queue if e.status == QueueStatus.PENDING]
            
            if not pending:
                return None
            
            # Return highest priority (lowest number), oldest request
            return pending[0]
    
    async def assign_board(self, queue_id: str, board_id: str) -> bool:
        """Assign a board to a queue entry.
        
        Args:
            queue_id: The queue entry ID
            board_id: The board to assign
            
        Returns:
            True if assignment succeeded
        """
        with self._lock:
            entry = self._entries.get(queue_id)
            if not entry:
                return False
            
            if entry.status != QueueStatus.PENDING:
                logger.warning(f"Cannot assign board to {queue_id}: status is {entry.status.name}")
                return False
            
            entry.status = QueueStatus.ASSIGNED
            entry.assigned_at = datetime.now()
            entry.assigned_board_id = board_id
        
        self._save()
        
        # Notify assignment callbacks (support both sync and async)
        for callback in self._assignment_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(queue_id, board_id)
                else:
                    callback(queue_id, board_id)
            except Exception as e:
                logger.error(f"Assignment callback error: {e}")
        
        logger.info(f"Board {board_id} assigned to queue entry {queue_id}")
        return True
    
    def assign_board_sync(self, queue_id: str, board_id: str) -> bool:
        """Synchronous version of assign_board for non-async contexts.
        
        Args:
            queue_id: The queue entry ID
            board_id: The board to assign
            
        Returns:
            True if assignment succeeded
        """
        with self._lock:
            entry = self._entries.get(queue_id)
            if not entry:
                return False
            
            if entry.status != QueueStatus.PENDING:
                logger.warning(f"Cannot assign board to {queue_id}: status is {entry.status.name}")
                return False
            
            entry.status = QueueStatus.ASSIGNED
            entry.assigned_at = datetime.now()
            entry.assigned_board_id = board_id
        
        self._save()
        logger.info(f"Board {board_id} assigned to queue entry {queue_id} (sync)")
        return True
    
    def complete_job(self, queue_id: str) -> bool:
        """Mark a queue entry as completed.
        
        Args:
            queue_id: The queue entry ID
            
        Returns:
            True if marked as completed
        """
        with self._lock:
            entry = self._entries.get(queue_id)
            if not entry:
                return False
            
            if entry.status not in (QueueStatus.ASSIGNED, QueueStatus.PENDING):
                return False
            
            entry.status = QueueStatus.COMPLETED
            entry.completed_at = datetime.now()
            self._stats.completed_requests += 1
            
            # Update average wait time
            if entry.assigned_at and entry.requested_at:
                wait_seconds = (entry.assigned_at - entry.requested_at).total_seconds()
                # Rolling average
                n = self._stats.completed_requests
                self._stats.avg_wait_time_seconds = (
                    (self._stats.avg_wait_time_seconds * (n - 1) + wait_seconds) / n
                )
        
        self._save()
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback("completed", entry)
            except Exception as e:
                logger.error(f"Queue callback error: {e}")
        
        logger.info(f"Queue entry {queue_id} marked as completed")
        return True
    
    def cancel_request(self, queue_id: str, agent_id: Optional[str] = None) -> bool:
        """Cancel a queue request.
        
        Args:
            queue_id: The queue entry ID
            agent_id: Optional agent ID for verification
            
        Returns:
            True if cancelled
        """
        with self._lock:
            entry = self._entries.get(queue_id)
            if not entry:
                return False
            
            # Verify agent if provided
            if agent_id and entry.agent_id != agent_id:
                logger.warning(f"Agent {agent_id} tried to cancel entry owned by {entry.agent_id}")
                return False
            
            if entry.status not in (QueueStatus.PENDING, QueueStatus.ASSIGNED):
                return False
            
            entry.status = QueueStatus.CANCELLED
            entry.completed_at = datetime.now()
            self._stats.cancelled_requests += 1
        
        self._save()
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback("cancelled", entry)
            except Exception as e:
                logger.error(f"Queue callback error: {e}")
        
        logger.info(f"Queue entry {queue_id} cancelled")
        return True
    
    def list_queue(
        self,
        status: Optional[QueueStatus] = None,
        board_type: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> List[QueueEntry]:
        """List queue entries with optional filtering.
        
        Returns:
            List of QueueEntry objects sorted by priority then time
        """
        with self._lock:
            entries = list(self._entries.values())
            
            if status:
                entries = [e for e in entries if e.status == status]
            if board_type:
                entries = [e for e in entries if e.board_type == board_type.lower()]
            if agent_id:
                entries = [e for e in entries if e.agent_id == agent_id]
            
            # Sort by board_type, then priority (ascending), then by request time
            entries.sort(key=lambda e: (e.board_type, e.priority, e.requested_at))
            
            return entries
    
    def get_queue_summary(self) -> Dict[str, Any]:
        """Get a summary of the queue state."""
        with self._lock:
            pending = [e for e in self._entries.values() if e.status == QueueStatus.PENDING]
            assigned = [e for e in self._entries.values() if e.status == QueueStatus.ASSIGNED]
            
            # Group pending by board type
            by_board_type: Dict[str, int] = {}
            for e in pending:
                by_board_type[e.board_type] = by_board_type.get(e.board_type, 0) + 1
            
            # Group by priority
            by_priority: Dict[int, int] = {}
            for e in pending:
                by_priority[e.priority] = by_priority.get(e.priority, 0) + 1
            
            return {
                "total_entries": len(self._entries),
                "pending": len(pending),
                "assigned": len(assigned),
                "by_board_type": by_board_type,
                "by_priority": by_priority,
                "stats": self._stats.to_dict(),
            }
    
    def register_callback(self, callback: Callable[[str, QueueEntry], None]):
        """Register a callback for queue events.
        
        Callback receives (event_type, entry) where event_type is:
        - "added": New entry added
        - "completed": Entry completed
        - "cancelled": Entry cancelled
        """
        self._callbacks.append(callback)
    
    def register_assignment_callback(self, callback: Callable[[str, str], None]):
        """Register a callback for board assignment events.
        
        Callback receives (queue_id, board_id)
        """
        self._assignment_callbacks.append(callback)
    
    def cleanup_expired(self) -> int:
        """Remove old completed/cancelled entries.
        
        Returns:
            Number of entries removed
        """
        cutoff = datetime.now() - timedelta(hours=self.CLEANUP_AFTER_HOURS)
        removed = 0
        
        with self._lock:
            to_remove = []
            for queue_id, entry in self._entries.items():
                if entry.status in (QueueStatus.COMPLETED, QueueStatus.CANCELLED, QueueStatus.EXPIRED):
                    if entry.completed_at and entry.completed_at < cutoff:
                        to_remove.append(queue_id)
            
            for queue_id in to_remove:
                entry = self._entries.pop(queue_id)
                # Also remove from per-type queue
                if entry.board_type in self._queues:
                    self._queues[entry.board_type] = [
                        e for e in self._queues[entry.board_type]
                        if e.queue_id != queue_id
                    ]
                removed += 1
        
        if removed > 0:
            self._save()
            logger.info(f"Cleaned up {removed} expired queue entries")
        
        return removed
    
    def apply_priority_boost(self) -> int:
        """Apply priority boost to entries waiting too long.
        
        Returns:
            Number of entries boosted
        """
        cutoff = datetime.now() - timedelta(minutes=self.PRIORITY_BOOST_AFTER_MINUTES)
        boosted = 0
        
        with self._lock:
            for entry in self._entries.values():
                if entry.status == QueueStatus.PENDING:
                    if entry.requested_at < cutoff:
                        if entry.priority_boost_count < self.MAX_BOOST_COUNT:
                            entry.priority = max(1, entry.priority - 1)  # Boost priority
                            entry.priority_boost_count += 1
                            entry.last_boost_at = datetime.now()
                            boosted += 1
                            logger.info(f"Priority boost applied to {entry.queue_id}: now priority {entry.priority}")
            
            # Re-sort all queues after boosting
            for board_type in self._queues:
                self._sort_queue(board_type)
        
        if boosted > 0:
            self._save()
        
        return boosted
    
    def _save(self):
        """Save queue state to disk."""
        try:
            data = {
                "entries": {k: v.to_dict() for k, v in self._entries.items()},
                "stats": self._stats.to_dict(),
                "saved_at": datetime.now().isoformat(),
            }
            
            # Write to temp file first, then rename for atomicity
            temp_path = self._storage_path.with_suffix(".tmp")
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            temp_path.rename(self._storage_path)
            
        except Exception as e:
            logger.error(f"Failed to save queue state: {e}")
    
    def _load(self):
        """Load queue state from disk."""
        if not self._storage_path.exists():
            logger.info("No existing queue state found, starting fresh")
            return
        
        try:
            with open(self._storage_path, 'r') as f:
                data = json.load(f)
            
            # Load entries
            entries_data = data.get("entries", {})
            for queue_id, entry_data in entries_data.items():
                try:
                    entry = QueueEntry.from_dict(entry_data)
                    self._entries[queue_id] = entry
                    
                    # Add to per-type queue
                    if entry.board_type not in self._queues:
                        self._queues[entry.board_type] = []
                    self._queues[entry.board_type].append(entry)
                except Exception as e:
                    logger.warning(f"Failed to load queue entry {queue_id}: {e}")
            
            # Load stats
            if "stats" in data:
                self._stats = QueueStats.from_dict(data["stats"])
            
            # Sort all queues
            for board_type in self._queues:
                self._sort_queue(board_type)
            
            # Reset assigned entries to pending (boards may have been released)
            for entry in self._entries.values():
                if entry.status == QueueStatus.ASSIGNED:
                    entry.status = QueueStatus.PENDING
                    entry.assigned_at = None
                    entry.assigned_board_id = None
            
            logger.info(f"Loaded {len(self._entries)} queue entries")
            
        except Exception as e:
            logger.error(f"Failed to load queue state: {e}")
    
    async def _auto_save(self):
        """Background task to periodically save queue state."""
        while True:
            try:
                await asyncio.sleep(self.SAVE_INTERVAL_SECONDS)
                self._save()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-save error: {e}")
    
    async def _periodic_cleanup(self):
        """Background task to periodically clean up expired entries."""
        while True:
            try:
                # Run cleanup every hour
                await asyncio.sleep(3600)
                self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")
    
    async def _periodic_priority_boost(self):
        """Background task to periodically apply priority boosts."""
        while True:
            try:
                # Check every 10 minutes
                await asyncio.sleep(600)
                self.apply_priority_boost()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Priority boost error: {e}")


# Singleton instance for global access
_queue_instance: Optional[BoardQueue] = None


def get_queue(storage_path: Optional[str] = None) -> BoardQueue:
    """Get or create the global BoardQueue instance."""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = BoardQueue(storage_path)
    return _queue_instance