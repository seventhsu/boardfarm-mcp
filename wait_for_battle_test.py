#!/usr/bin/env python3
"""Wait for board assignment and report wait time."""
import sys
import os
import time
sys.path.insert(0, '/home/alial/.openclaw/workspace/mcp-boardfarm/src')

from mcp_boardfarm.board_queue import get_queue, QueueStatus
from datetime import datetime

# Initialize queue
queue = get_queue('/home/alial/.openclaw/workspace/mcp-boardfarm/data/queue.json')

queue_id = "d5ddb09d"
agent_id = "battle-test-agent-3"

start_time = datetime.now()
print(f"Waiting for board assignment... (started at {start_time.isoformat()})")
print(f"Queue ID: {queue_id}")
print()

# Poll until assigned
wait_seconds = 0
assigned_board = None

while wait_seconds < 600:  # Max 10 minutes wait
    # Reload queue state
    queue._load()
    
    entry = queue.get_entry(queue_id)
    if entry is None:
        print("ERROR: Queue entry not found!")
        sys.exit(1)
    
    if entry.status == QueueStatus.ASSIGNED:
        assigned_board = entry.assigned_board_id
        end_time = datetime.now()
        wait_seconds = (end_time - start_time).total_seconds()
        print(f"\n=== BOARD ASSIGNED ===")
        print(f"Board ID: {assigned_board}")
        print(f"Wait time: {wait_seconds:.2f} seconds ({wait_seconds/60:.2f} minutes)")
        print(f"Assigned at: {end_time.isoformat()}")
        
        # Save info for next script
        with open('/tmp/board_assignment_info.txt', 'w') as f:
            f.write(f"board_id={assigned_board}\n")
            f.write(f"queue_id={queue_id}\n")
            f.write(f"wait_seconds={wait_seconds}\n")
            f.write(f"assigned_at={end_time.isoformat()}\n")
        print("Board info saved to /tmp/board_assignment_info.txt")
        break
    
    if entry.status == QueueStatus.PENDING:
        position, _, desc = queue.get_position(queue_id)
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[{elapsed:.0f}s] Position: {position}, Status: {desc}")
    
    time.sleep(5)
    wait_seconds += 5

if assigned_board is None:
    print("ERROR: Timed out waiting for board assignment")
    sys.exit(1)

print(f"\nBoard {assigned_board} ready for debugging!")
