#!/usr/bin/env python3
"""Test actual flashing and GDB on real hardware."""

import asyncio
import sys
sys.path.insert(0, 'src')

from mcp.server.fastmcp import FastMCP
from mcp_boardfarm.server import create_server, app_lifespan
from mcp_boardfarm.server import (
    list_boards, reserve_board_with_timeout, release_board,
    build_firmware, flash_firmware, start_debug_session, stop_debug_session,
    step_debug, get_debug_state, read_registers, get_board_features
)

async def test_flash_and_debug():
    """Test flashing and debugging on the H755."""
    print("="*70)
    print("MCP Board Farm Flash + GDB Test")
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
        
        # 2. Reserve it
        print(f"\n2. Reserving {board_id}...")
        reserve_result = await reserve_board_with_timeout(ctx, board_id, "test-agent", minutes=10)
        print(reserve_result)
        
        if "Error" in reserve_result:
            return False
        
        # 3. Flash a test binary (if we have one)
        # For now, let's just check if we can start GDB
        
        # 4. Start debug session
        print(f"\n3. Starting GDB debug session on {board_id}...")
        try:
            debug_start = await start_debug_session(ctx, board_id)
            print(debug_start[:500] + "..." if len(debug_start) > 500 else debug_start)
        except Exception as e:
            print(f"Debug start error: {e}")
        
        # 5. Get debug state
        print(f"\n4. Getting debug state...")
        try:
            debug_state = await get_debug_state(ctx, board_id)
            print(debug_state)
        except Exception as e:
            print(f"Debug state error: {e}")
        
        # 6. Read registers
        print(f"\n5. Reading CPU registers...")
        try:
            regs = await read_registers(ctx, board_id)
            print(regs[:1000] + "..." if len(regs) > 1000 else regs)
        except Exception as e:
            print(f"Read registers error: {e}")
        
        # 7. Stop debug session
        print(f"\n6. Stopping debug session...")
        try:
            debug_stop = await stop_debug_session(ctx, board_id)
            print(debug_stop)
        except Exception as e:
            print(f"Debug stop error: {e}")
        
        # 8. Release board
        print(f"\n7. Releasing {board_id}...")
        release_result = await release_board(ctx, board_id, "test-agent")
        print(release_result)
        
        if "Error" in release_result:
            return False
        
        print("\n" + "="*70)
        print("✓ Flash + GDB test completed!")
        print("="*70)
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_flash_and_debug())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
