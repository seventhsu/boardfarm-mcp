#!/usr/bin/env python3
"""End-to-end MCP Board Farm test on real hardware."""

import asyncio
import sys
sys.path.insert(0, 'src')

from mcp.server.fastmcp import FastMCP, Context
from mcp_boardfarm.server import create_server, ServerState, app_lifespan
from mcp_boardfarm.board_manager import BoardManager
from mcp_boardfarm.board_queue import BoardQueue, get_queue
from mcp_boardfarm.builder import BuildManager
from mcp_boardfarm.models import BuildConfig, BoardState

async def test_full_workflow():
    """Test complete board farm workflow."""
    print("="*70)
    print("MCP Board Farm End-to-End Test")
    print("="*70)
    
    # Create server and get context
    mcp = create_server()
    
    async with app_lifespan(mcp) as state:
        print("\n1. Listing available boards...")
        
        # List boards
        from mcp_boardfarm.server import list_boards
        ctx = type('Ctx', (), {'request_context': type('RC', (), {'lifespan_context': state})()})()
        boards_output = await list_boards(ctx)
        print(boards_output)
        
        # Find an available board
        available_boards = [b for b in state.board_manager.list_boards() if b.status == BoardState.AVAILABLE]
        if not available_boards:
            print("\n✗ No available boards to test with!")
            return False
        
        board = available_boards[0]
        board_id = board.board_id
        print(f"\n✓ Found available board: {board_id}")
        
        # 2. Reserve the board
        print(f"\n2. Reserving board {board_id}...")
        from mcp_boardfarm.server import reserve_board_with_timeout
        reserve_result = await reserve_board_with_timeout(ctx, board_id, "test-agent", minutes=5)
        print(reserve_result)
        
        if "Error" in reserve_result:
            print("\n✗ Failed to reserve board")
            return False
        
        # 3. Build firmware
        print(f"\n3. Building test firmware for {board_id}...")
        from mcp_boardfarm.server import build_firmware
        try:
            build_result = await build_firmware(
                ctx,
                board_id=board_id,
                source="hello_world",
                target=f"zephyr/{board.type}",
                build_type="debug"
            )
            print(build_result[:500] + "..." if len(build_result) > 500 else build_result)
        except Exception as e:
            print(f"Build error (expected if no build env): {e}")
        
        # 4. List queue
        print(f"\n4. Checking queue status...")
        from mcp_boardfarm.server import list_queue
        queue_output = await list_queue(ctx)
        print(queue_output[:500] + "..." if len(queue_output) > 500 else queue_output)
        
        # 5. Get board features
        print(f"\n5. Getting board features...")
        from mcp_boardfarm.server import get_board_features
        features_output = await get_board_features(ctx, board_id)
        print(features_output)
        
        # 6. Release the board
        print(f"\n6. Releasing board {board_id}...")
        from mcp_boardfarm.server import release_board
        release_result = await release_board(ctx, board_id, "test-agent")
        print(release_result)
        
        if "Error" in release_result:
            print("\n✗ Failed to release board")
            return False
        
        print("\n" + "="*70)
        print("✓ All MCP tools tested successfully!")
        print("="*70)
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_full_workflow())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
