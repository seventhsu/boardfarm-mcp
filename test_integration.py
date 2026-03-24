#!/usr/bin/env python3
"""Quick integration test for refactored MCP Board Farm."""

import asyncio
import sys
sys.path.insert(0, 'src')

from mcp_boardfarm.board_queue import BoardQueue, QueueStatus
from mcp_boardfarm.board_manager import BoardManager

async def test_queue():
    """Test the simplified queue system."""
    print("Testing BoardQueue...")
    queue = BoardQueue(storage_path="./test_queue.json")
    await queue.start()
    
    # Add a request
    queue_id = await queue.add_request(
        board_type="h755",
        priority=2,
        estimated_minutes=30,
        agent_id="test-agent",
        job_description="Integration test",
        required_features=["ethernet"],
    )
    print(f"✓ Added queue request: {queue_id}")
    
    # Check position
    entry = await queue.get_entry(queue_id)
    print(f"✓ Retrieved entry: {entry.board_type}, priority {entry.priority}")
    
    # Cancel it
    success = await queue.cancel_request(queue_id, "test-agent")
    print(f"✓ Cancelled request: {success}")
    
    await queue.stop()
    print("✓ Queue test passed!")
    return True

def test_board_manager():
    """Test board manager with real hardware detection."""
    print("\nTesting BoardManager...")
    
    bm = BoardManager(config_path="config/boards.yaml")
    bm.load_config()
    boards = bm.detect_boards()
    
    print(f"✓ Detected {len(boards)} boards:")
    for board in boards:
        print(f"  - {board.board_id}: {board.status.name} ({board.model})")
    
    available = [b for b in boards if b.status.name == "AVAILABLE"]
    print(f"✓ {len(available)} boards available")
    
    return len(boards) > 0

async def main():
    print("="*60)
    print("MCP Board Farm Refactoring Integration Test")
    print("="*60)
    
    try:
        # Test queue
        queue_ok = await test_queue()
        
        # Test board manager
        boards_ok = test_board_manager()
        
        print("\n" + "="*60)
        if queue_ok and boards_ok:
            print("✓ All tests passed!")
            return 0
        else:
            print("✗ Some tests failed")
            return 1
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))
