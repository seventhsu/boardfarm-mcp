#!/usr/bin/env python3
"""Queue for H755 board with priority 2 for 10 minutes."""
import sys
import os
sys.path.insert(0, '/home/alial/.openclaw/workspace/mcp-boardfarm/src')

from mcp_boardfarm.board_queue import get_queue, QueueStatus
from mcp_boardfarm.board_manager import BoardManager
from datetime import datetime

# Initialize queue
queue = get_queue('/home/alial/.openclaw/workspace/mcp-boardfarm/data/queue.json')

# Check current queue state
print("=== Current Queue State ===")
summary = queue.get_queue_summary()
print(f"Total entries: {summary['total_entries']}")
print(f"Pending: {summary['pending']}")
print(f"By board type: {summary['by_board_type']}")
print()

# Show existing H755 queue
h755_entries = queue.list_queue(board_type='h755')
print("=== H755 Queue ===")
for entry in h755_entries:
    print(f"  ID: {entry.queue_id}, Agent: {entry.agent_id}, Priority: {entry.priority}, Status: {entry.status.name}")
print()

# Queue for H755 board with priority 2, 10 minute reservation
agent_id = "battle-test-agent-3"
queue_id = queue.add_request(
    board_type='h755',
    priority=2,
    estimated_minutes=10,
    agent_id=agent_id,
    job_description='GDB debugging session - battle test',
    auto_accept=True
)

print(f"=== Queued for H755 Board ===")
print(f"Queue ID: {queue_id}")
print(f"Agent: {agent_id}")
print(f"Priority: 2")
print(f"Duration: 10 minutes")
print(f"Time: {datetime.now().isoformat()}")
print()

# Get position
position, same_priority, desc = queue.get_position(queue_id)
print(f"=== Queue Position ===")
print(f"Position: {position}")
print(f"Same priority count: {same_priority}")
print(f"Description: {desc}")

# Save queue state
queue._save()
print(f"\nQueue state saved.")
