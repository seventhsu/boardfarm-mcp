#!/usr/bin/env python3
import asyncio, sys
sys.path.insert(0, 'src')
from mcp.server.fastmcp import FastMCP
from mcp_boardfarm.server import create_server, app_lifespan, reserve_board_with_timeout, release_board, flash_firmware, start_debug_session, stop_debug_session, read_registers

async def test():
    mcp = create_server()
    async with app_lifespan(mcp) as state:
        ctx = type('Ctx', (), {'request_context': type('RC', (), {'lifespan_context': state})()})()
        board_id, build_id = "nucleo-h755zi-q-01", "docker_8b9967f4223e"
        
        print("1. ACQUIRE")
        print(f"   {(await reserve_board_with_timeout(ctx, board_id, 'test', minutes=10)).split(chr(10))[0]}")
        
        if build_id not in state._active_builds:
            from mcp_boardfarm.models import BuildResult
            state._active_builds[build_id] = {"board_id": board_id, "result": BuildResult(build_id=build_id, success=True, board_id=board_id, framework="zephyr", elf_path="/tmp/docker-builds/docker_8b9967f4223e/zephyr/zephyr.elf", bin_path="/tmp/docker-builds/docker_8b9967f4223e/zephyr/zephyr.bin", duration_seconds=17.0)}
        
        print("2. FLASH")
        f = await flash_firmware(ctx, board_id, build_id)
        print(f"   {f.split(chr(10))[0]}")
        
        if "✓" in f:
            print("3. DEBUG")
            d = await start_debug_session(ctx, board_id)
            print(f"   {d.split(chr(10))[0]}")
            if "✓" in d:
                print(f"   Registers: {len(await read_registers(ctx, board_id))} chars")
                await stop_debug_session(ctx, board_id)
        
        print("4. RELEASE")
        print(f"   {(await release_board(ctx, board_id, 'test')).split(chr(10))[0]}")
        
        print("\n✓ FULL CYCLE COMPLETE" if "✓" in f else "\n✗ FAILED")
        return "✓" in f

if __name__ == "__main__":
    sys.exit(0 if asyncio.run(test()) else 1)
