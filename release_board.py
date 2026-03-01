#!/usr/bin/env python3
"""Release the board after debugging."""
import sys
sys.path.insert(0, '/home/alial/.openclaw/workspace/mcp-boardfarm/src')

from mcp_boardfarm.board_queue import get_queue
from mcp_boardfarm.board_manager import BoardManager
from datetime import datetime

# Load board info
try:
    with open('/tmp/board_assignment_info.txt', 'r') as f:
        info = dict(line.strip().split('=') for line in f)
    board_id = info.get('board_id', 'nucleo-h755zi-q-01')
    agent_id = info.get('agent_id', 'battle-test-agent-3')
    queue_id = info.get('queue_id', '6862c889')
except:
    board_id = 'nucleo-h755zi-q-01'
    agent_id = 'battle-test-agent-3'
    queue_id = '6862c889'

# Initialize
queue = get_queue('/home/alial/.openclaw/workspace/mcp-boardfarm/data/queue.json')
manager = BoardManager('/home/alial/.openclaw/workspace/mcp-boardfarm/config/boards.yaml', queue)

# Detect boards
boards = manager.detect_boards()

print("=== Releasing Board ===")
print(f"Board: {board_id}")
print(f"Agent: {agent_id}")
print(f"Queue ID: {queue_id}")
print(f"Released at: {datetime.now().isoformat()}")
print()

# Release board
released = manager.release_board(board_id, agent_id)
if released:
    print("✓ Board released successfully")
else:
    print("⚠ Could not release board (may already be released)")

# Complete queue entry
completed = queue.complete_job(queue_id)
if completed:
    print("✓ Queue entry marked as completed")
else:
    print("⚠ Could not complete queue entry")

queue._save()
print("\nDone!")
