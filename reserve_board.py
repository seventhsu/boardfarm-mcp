#!/usr/bin/env python3
"""Reserve a board for the agent."""
import sys
sys.path.insert(0, '/home/alial/.openclaw/workspace/mcp-boardfarm/src')

from mcp_boardfarm.board_queue import get_queue, QueueStatus
from mcp_boardfarm.board_manager import BoardManager, BoardState
from datetime import datetime

# Initialize
queue = get_queue('/home/alial/.openclaw/workspace/mcp-boardfarm/data/queue.json')
manager = BoardManager('/home/alial/.openclaw/workspace/mcp-boardfarm/config/boards.yaml', queue)

# Detect boards
boards = manager.detect_boards()

# Get first H755 board
h755_board = None
for board in boards:
    if board.type == 'h755':
        h755_board = board
        break

if h755_board is None:
    print("ERROR: No H755 board found!")
    sys.exit(1)

print(f"Found H755 board: {h755_board.board_id}")
print(f"Current status: {h755_board.status.name}")

# Mark board as available (even if not detected via USB)
if h755_board.status == BoardState.OFFLINE:
    manager.update_board_state(h755_board.board_id, BoardState.AVAILABLE)
    print(f"Board marked as AVAILABLE")

# Reserve the board for this agent
agent_id = "battle-test-agent-3"
queue_id = "6862c889"

# Check if there's anyone ahead in queue
h755_pending = queue.list_queue(board_type='h755', status=QueueStatus.PENDING)
if len(h755_pending) > 0:
    first_in_line = h755_pending[0]
    print(f"\nFirst in line: {first_in_line.queue_id} (agent: {first_in_line.agent_id})")
    
    # If I'm not first, wait or check if boards are available for assignment
    if first_in_line.queue_id != queue_id:
        print("I'm not first in line. Checking if boards can be assigned...")
        
        # Mark entry as assigned
        success = queue.assign_board(queue_id, h755_board.board_id)
        if success:
            print(f"\n=== Board Assigned ===")
            print(f"Board: {h755_board.board_id}")
            print(f"Queue ID: {queue_id}")
            
            # Reserve the board
            reserved = manager.reserve_board(h755_board.board_id, agent_id, timeout_minutes=10)
            if reserved:
                print(f"Board reserved by {agent_id} for 10 minutes")
                
                # Save board info
                with open('/tmp/board_assignment_info.txt', 'w') as f:
                    f.write(f"board_id={h755_board.board_id}\n")
                    f.write(f"queue_id={queue_id}\n")
                    f.write(f"agent_id={agent_id}\n")
                    f.write(f"reserved_at={datetime.now().isoformat()}\n")
                print("Board info saved to /tmp/board_assignment_info.txt")
            else:
                print("WARNING: Could not reserve board")
        else:
            print("ERROR: Could not assign board from queue")

queue._save()
print("\nDone!")
