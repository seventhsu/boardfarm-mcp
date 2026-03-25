#!/usr/bin/env python3
"""Test full cycle with pyocd - flash then debug."""
import asyncio, sys
sys.path.insert(0, 'src')
from mcp.server.fastmcp import FastMCP
from mcp_boardfarm.server import create_server, app_lifespan, reserve_board_with_timeout, release_board, flash_firmware, start_debug_session, stop_debug_session, read_registers

async def test():
    mcp = create_server()
    async with app_lifespan(mcp) as state:
        ctx = type('Ctx', (), {'request_context': type('RC', (), {'lifespan_context': state})()})()
        board_id = "nucleo-h755zi-q-01"
        build_id = "docker_8b9967f4223e"
        
        print("1. ACQUIRE")
        r = await reserve_board_with_timeout(ctx, board_id, "test", minutes=10)
        print(f"   {r.split(chr(10))[0]}")
        
        if build_id not in state._active_builds:
            from mcp_boardfarm.models import BuildResult
            state._active_builds[build_id] = {"board_id": board_id, "target": "zephyr/nucleo_h755zi_q", "framework": "zephyr", "result": BuildResult(build_id=build_id, success=True, board_id=board_id, framework="zephyr", elf_path="/tmp/docker-builds/docker_8b9967f4223e/zephyr/zephyr.elf", bin_path="/tmp/docker-builds/docker_8b9967f4223e/zephyr/zephyr.bin", duration_seconds=17.0)}
        
        print("2. FLASH")
        f = await flash_firmware(ctx, board_id, build_id)
        print(f"   {f.split(chr(10))[0]}")
        
        if "✓" in f:
            print("3. DEBUG")
            d = await start_debug_session(ctx, board_id)
            print(f"   {d.split(chr(10))[0]}")
            
            if "✓" in d:
                regs = await read_registers(ctx, board_id)
                print(f"   Registers: {len(regs)} chars")
                await stop_debug_session(ctx, board_id)
        else:
            print("3. DEBUG (skipped - flash failed)")
        
        print("4. RELEASE")
        rel = await release_board(ctx, board_id, "test")
        print(f"   {rel.split(chr(10))[0]}")
        
        success = "✓" in f and "✓" in rel
        print(f"\n{'✓' if success else '✗'} FULL CYCLE {'COMPLETE' if success else 'FAILED'}")
        return success

if __name__ == "__main__":
    sys.exit(0 if asyncio.run(test()) else 1)
