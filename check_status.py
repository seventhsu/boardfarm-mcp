#!/usr/bin/env python3
"""Check queue and board status."""
import sys
sys.path.insert(0, '/home/alial/.openclaw/workspace/mcp-boardfarm/src')

from mcp_boardfarm.board_queue import get_queue, QueueStatus
from mcp_boardfarm.board_manager import BoardManager

# Initialize
queue = get_queue('/home/alial/.openclaw/workspace/mcp-boardfarm/data/queue.json')
manager = BoardManager('/home/alial/.openclaw/workspace/mcp-boardfarm/config/boards.yaml', queue)

# Detect boards
boards = manager.detect_boards()

print("=== Board Status ===")
for board in boards:
    if board.type == 'h755':
        print(f"Board: {board.board_id}")
        print(f"  Status: {board.status.name}")
        print(f"  Reserved by: {board.reserved_by}")
        print(f"  Reserved until: {board.reserved_until}")
        print()

print("=== H755 Queue (Pending) ===")
h755_pending = queue.list_queue(board_type='h755', status=QueueStatus.PENDING)
for entry in h755_pending:
    print(f"  Queue ID: {entry.queue_id}")
    print(f"  Agent: {entry.agent_id}")
    print(f"  Priority: {entry.priority}")
    print(f"  Requested at: {entry.requested_at}")
    print()

print("=== H755 Queue (Assigned) ===")
h755_assigned = queue.list_queue(board_type='h755', status=QueueStatus.ASSIGNED)
for entry in h755_assigned:
    print(f"  Queue ID: {entry.queue_id}")
    print(f"  Agent: {entry.agent_id}")
    print(f"  Assigned board: {entry.assigned_board_id}")
    print()

# Check my position
my_entry = queue.get_entry("6862c889")
if my_entry:
    pos, _, desc = queue.get_position("6862c889")
    print(f"=== My Position (6862c889) ===")
    print(f"Position: {pos}")
    print(f"Status: {my_entry.status.name}")
    print(f"Description: {desc}")
