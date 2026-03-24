#!/usr/bin/env python3
"""Test actual board operations on real hardware."""

import asyncio
import sys
sys.path.insert(0, 'src')

from mcp.server.fastmcp import FastMCP
from mcp_boardfarm.server import create_server, app_lifespan
from mcp_boardfarm.server import (
    list_boards, reserve_board_with_timeout, release_board,
    get_board_features, analyze_fault_arm_cortex_m
)

async def test_board_operations():
    """Test board operations on the H755."""
    print("="*70)
    print("MCP Board Farm Hardware Test")
    print("="*70)
    
    mcp = create_server()
    
    async with app_lifespan(mcp) as state:
        print("\n1. Listing boards...")
        ctx = type('Ctx', (), {'request_context': type('RC', (), {'lifespan_context': state})()})()
        
        boards_output = await list_boards(ctx)
        print(boards_output)
        
        # Get the H755 board
        board_id = "nucleo-h755zi-q-01"
        board = state.board_manager.get_board(board_id)
        
        if not board:
            print(f"\n✗ Board {board_id} not found!")
            return False
        
        if board.status.name != "AVAILABLE":
            print(f"\n✗ Board {board_id} not available (status: {board.status.name})")
            return False
        
        print(f"\n✓ Found board: {board_id}")
        
        # 2. Get board features
        print(f"\n2. Getting board features...")
        features = await get_board_features(ctx, board_id)
        print(features)
        
        # 3. Reserve it
        print(f"\n3. Reserving {board_id}...")
        reserve_result = await reserve_board_with_timeout(ctx, board_id, "test-agent", minutes=10)
        print(reserve_result)
        
        if "Error" in reserve_result:
            return False
        
        # 4. Try fault analysis (needs GDB session, will fail but tests code path)
        print(f"\n4. Testing fault analysis (expects error - no GDB session)...")
        try:
            fault_result = await analyze_fault_arm_cortex_m(ctx, board_id)
            print(fault_result[:500] + "..." if len(fault_result) > 500 else fault_result)
        except Exception as e:
            print(f"Expected error (no GDB session): {type(e).__name__}")
        
        # 5. Release board
        print(f"\n5. Releasing {board_id}...")
        release_result = await release_board(ctx, board_id, "test-agent")
        print(release_result)
        
        if "Error" in release_result:
            return False
        
        print("\n" + "="*70)
        print("✓ Board operations test completed!")
        print("="*70)
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_board_operations())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
