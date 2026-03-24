#!/usr/bin/env python3
"""Test acquire-flash-release with PyOCD."""

import asyncio
import sys
sys.path.insert(0, 'src')

from mcp.server.fastmcp import FastMCP
from mcp_boardfarm.server import create_server, app_lifespan
from mcp_boardfarm.server import (
    list_boards, reserve_board_with_timeout, release_board,
    flash_firmware
)

async def test_cycle():
    """Test complete cycle."""
    print("="*70)
    print("PyOCD Test: Acquire-Flash-Release")
    print("="*70)
    
    mcp = create_server()
    
    async with app_lifespan(mcp) as state:
        ctx = type('Ctx', (), {'request_context': type('RC', (), {'lifespan_context': state})()})()
        
        board_id = "nucleo-h755zi-q-01"
        build_id = "docker_8b9967f4223e"
        
        print("\n1. ACQUIRE...")
        boards = await list_boards(ctx)
        print(f"   Available: {len([b for b in state.board_manager.list_boards() if b.status.name == 'AVAILABLE'])}")
        
        reserve = await reserve_board_with_timeout(ctx, board_id, "test-agent", minutes=10)
        print(f"   {reserve.split(chr(10))[0]}")
        
        # Setup mock build
        if build_id not in state._active_builds:
            from mcp_boardfarm.models import BuildResult
            state._active_builds[build_id] = {
                "board_id": board_id,
                "target": "zephyr/nucleo_h755zi_q",
                "framework": "zephyr",
                "result": BuildResult(
                    build_id=build_id,
                    success=True,
                    board_id=board_id,
                    framework="zephyr",
                    elf_path="/tmp/docker-builds/docker_8b9967f4223e/zephyr/zephyr.elf",
                    bin_path="/tmp/docker-builds/docker_8b9967f4223e/zephyr/zephyr.bin",
                    duration_seconds=17.0
                )
            }
        
        print(f"\n2. FLASH with PyOCD...")
        flash = await flash_firmware(ctx, board_id, build_id)
        print(f"   {flash.split(chr(10))[0]}")
        
        print(f"\n3. RELEASE...")
        release = await release_board(ctx, board_id, "test-agent")
        print(f"   {release.split(chr(10))[0]}")
        
        if "✓" in flash and "✓" in release:
            print("\n" + "="*70)
            print("✓ PYOCD CYCLE SUCCESS!")
            print("="*70)
            return True
        return False

if __name__ == "__main__":
    result = asyncio.run(test_cycle())
    sys.exit(0 if result else 1)
