"""MCP Server for Board Farm - FastMCP implementation."""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP, Context

from .models import (
    Board, BoardState, BuildConfig, BuildResult, FlashResult,
    LogEntry, ServerConfig
)
from .board_manager import BoardManager
from .builder import ZephyrBuilder, MockBuilder
from .flasher import OpenOCDFlasher, MockFlasher
from .monitor import SerialMonitor, MockMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state (managed via lifespan)
class ServerState:
    def __init__(self):
        self.board_manager: Optional[BoardManager] = None
        self.builder: Optional[ZephyrBuilder] = None
        self.flasher: Optional[OpenOCDFlasher] = None
        self.monitor: Optional[SerialMonitor] = None
        self.config: Optional[ServerConfig] = None
        self._monitor: Optional[MockMonitor] = None


# Create FastMCP instance
mcp = FastMCP("mcp-boardfarm")


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Manage application lifecycle."""
    logger.info("Starting MCP Board Farm server...")
    state = ServerState()
    config_path = os.environ.get('BOARDFARM_CONFIG', 'config/boards.yaml')
    state.board_manager = BoardManager(config_path)
    state.board_manager.load_config()
    state.board_manager.detect_boards()
    state.builder = ZephyrBuilder()
    state.flasher = OpenOCDFlasher()
    state.monitor = SerialMonitor()
    logger.info(f"Server ready. Detected {len(state.board_manager.list_boards())} boards.")
    yield state
    logger.info("Shutting down MCP Board Farm server...")
    if state.monitor:
        await state.monitor.close_all()


mcp._lifespan = app_lifespan


@mcp.tool()
async def list_boards(ctx: Context) -> str:
    """List all connected boards and their status."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    boards = bm.list_boards()
    if not boards:
        return "No boards configured. Check config/boards.yaml"
    lines = ["Connected Boards:", "=" * 60]
    for board in boards:
        status_icon = {
            BoardState.OFFLINE: "[OFF]",
            BoardState.AVAILABLE: "[OK]",
            BoardState.RESERVED: "[LOCK]",
            BoardState.BUILDING: "[BUILD]",
            BoardState.FLASHING: "[FLASH]",
            BoardState.RUNNING: "[RUN]",
            BoardState.TESTING: "[TEST]",
            BoardState.ERROR: "[ERR]",
        }.get(board.status, "[?]")
        lines.append(f"\n{status_icon} {board.board_id}")
        lines.append(f"   Model: {board.model} ({board.mcu})")
        lines.append(f"   Status: {board.status.name}")
        if board.reserved_by:
            lines.append(f"   Reserved by: {board.reserved_by}")
            if board.reserved_until:
                remaining = board.reserved_until - datetime.now()
                mins = int(remaining.total_seconds() / 60)
                lines.append(f"   Time remaining: {mins} min")
        if board.serial.port:
            lines.append(f"   Serial: {board.serial.port} @ {board.serial.baud} baud")
        if board.supported_frameworks:
            lines.append(f"   Frameworks: {', '.join(board.supported_frameworks)}")
    available = len([b for b in boards if b.status == BoardState.AVAILABLE])
    lines.append(f"\n{'=' * 60}")
    lines.append(f"Summary: {available}/{len(boards)} boards available")
    return "\n".join(lines)


@mcp.tool()
async def get_board_info(ctx: Context, board_id: str) -> str:
    """Get detailed information about a specific board."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    lines = [
        f"Board: {board.board_id}",
        "=" * 50,
        f"Type: {board.type}",
        f"Model: {board.model}",
        f"MCU: {board.mcu}",
        f"Description: {board.description}",
        "",
        "Memory:",
        f"  Flash: {board.flash_size} KB",
        f"  RAM: {board.ram_size} KB",
        "",
        "Debugger:",
        f"  Type: {board.debugger.type}",
        f"  Transport: {board.debugger.transport}",
        "",
        "Serial:",
        f"  Port: {board.serial.port}",
        f"  Baud: {board.serial.baud}",
        "",
        "Capabilities:",
        f"  Frameworks: {', '.join(board.supported_frameworks)}",
        "",
        "Status:",
        f"  State: {board.status.name}",
    ]
    if board.reserved_by:
        lines.append(f"  Reserved by: {board.reserved_by}")
        if board.reserved_until:
            lines.append(f"  Reserved until: {board.reserved_until.isoformat()}")
    if board.current_firmware:
        lines.append(f"  Current firmware: {board.current_firmware}")
    if board.last_seen:
        lines.append(f"  Last seen: {board.last_seen.isoformat()}")
    return "\n".join(lines)


@mcp.tool()
async def reserve_board(ctx: Context, board_id: str, timeout_minutes: int = 30) -> str:
    """Reserve a board for exclusive use."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    user = "mcp-client"
    success = bm.reserve_board(board_id, user, timeout_minutes)
    if success:
        return f"Board '{board_id}' reserved for {timeout_minutes} minutes."
    else:
        board = bm.get_board(board_id)
        if not board:
            return f"Board '{board_id}' not found."
        elif board.status == BoardState.RESERVED:
            return f"Board '{board_id}' is already reserved by {board.reserved_by}."
        else:
            return f"Board '{board_id}' is not available (status: {board.status.name})."


@mcp.tool()
async def release_board(ctx: Context, board_id: str) -> str:
    """Release a previously reserved board."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    user = "mcp-client"
    success = bm.release_board(board_id, user)
    if success:
        return f"Board '{board_id}' released."
    else:
        board = bm.get_board(board_id)
        if not board:
            return f"Board '{board_id}' not found."
        elif board.status != BoardState.RESERVED:
            return f"Board '{board_id}' is not reserved (status: {board.status.name})."
        else:
            return f"You don't have permission to release board '{board_id}'."


@mcp.tool()
async def build_firmware(ctx: Context, board_id: str, zephyr_sample: str = "hello_world",
                        build_type: str = "debug") -> str:
    """Build firmware for a board using Zephyr."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    if board.status not in (BoardState.AVAILABLE, BoardState.RESERVED):
        return f"Error: Board '{board_id}' is not available (status: {board.status.name})."
    zephyr_board = board.zephyr.board_name if board.zephyr else board_id.replace('-', '_')
    logger.info(f"Building {zephyr_sample} for {board_id}")
    old_status = board.status
    bm.update_board_state(board_id, BoardState.BUILDING)
    try:
        config = BuildConfig(
            framework="zephyr",
            board_id=board_id,
            zephyr_board=zephyr_board,
            zephyr_sample=zephyr_sample,
            build_type=build_type
        )
        builder = MockBuilder()
        result = builder.build(config)
        bm.update_board_state(board_id, old_status)
        lines = [
            f"Build Result: {'SUCCESS' if result.success else 'FAILED'}",
            f"Build ID: {result.build_id}",
            f"Duration: {result.duration_seconds:.2f}s",
            ""
        ]
        if result.elf_path:
            lines.append(f"ELF: {result.elf_path}")
        lines.append("")
        lines.append("--- Build Output ---")
        if result.stdout:
            lines.append(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        return "\n".join(lines)
    except Exception as e:
        bm.update_board_state(board_id, old_status)
        logger.exception(f"Build failed: {e}")
        return f"Error: Build failed with exception: {e}"


@mcp.tool()
async def flash_board(ctx: Context, board_id: str, build_id: str = "") -> str:
    """Flash firmware to a board."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    if board.status != BoardState.RESERVED:
        return f"Error: Board '{board_id}' must be reserved before flashing."
    logger.info(f"Flashing build to {board_id}")
    bm.update_board_state(board_id, BoardState.FLASHING)
    try:
        import time
        mock_result = BuildResult(
            build_id=build_id or f"mock_{int(time.time())}",
            success=True,
            board_id=board_id,
            framework="zephyr",
            elf_path=f"./cache/builds/mock_{board_id}/zephyr/zephyr.elf",
        )
        flasher = MockFlasher()
        result = flasher.flash(board, mock_result)
        if result.success:
            board.current_firmware = mock_result.build_id
            bm.update_board_state(board_id, BoardState.RUNNING)
        else:
            bm.update_board_state(board_id, BoardState.RESERVED)
        lines = [
            f"Flash Result: {'SUCCESS' if result.success else 'FAILED'}",
            f"Duration: {result.duration_seconds:.2f}s",
        ]
        return "\n".join(lines)
    except Exception as e:
        bm.update_board_state(board_id, BoardState.RESERVED)
        logger.exception(f"Flash failed: {e}")
        return f"Error: Flash failed with exception: {e}"


@mcp.tool()
async def reset_board(ctx: Context, board_id: str, reset_type: str = "soft") -> str:
    """Reset a board."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    logger.info(f"Resetting {board_id}")
    try:
        flasher = MockFlasher()
        success = flasher.reset(board, reset_type)
        if success:
            bm.update_board_state(board_id, BoardState.RUNNING)
            return f"Board '{board_id}' reset successfully."
        else:
            return f"Failed to reset board '{board_id}'."
    except Exception as e:
        logger.exception(f"Reset failed: {e}")
        return f"Error: Reset failed with exception: {e}"


@mcp.tool()
async def start_logging(ctx: Context, board_id: str) -> str:
    """Start capturing serial output from a board."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    if not hasattr(state, '_monitor') or state._monitor is None:
        state._monitor = MockMonitor()
    success = await state._monitor.start_monitoring(board)
    if success:
        return f"Started logging for board '{board_id}'. Use get_logs() to retrieve output."
    else:
        return f"Failed to start logging for board '{board_id}'."


@mcp.tool()
async def stop_logging(ctx: Context, board_id: str) -> str:
    """Stop capturing serial output from a board."""
    state: ServerState = ctx.request_context.lifespan_context
    if not hasattr(state, '_monitor') or state._monitor is None:
        return f"Error: No monitoring active for board '{board_id}'."
    logs = state._monitor.get_logs(board_id)
    await state._monitor.stop_monitoring(board_id)
    lines = [f"Logging stopped for board '{board_id}'.", "", f"Captured {len(logs)} log lines:", "-" * 50]
    for entry in logs[-100:]:
        ts = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
        lines.append(f"[{ts}] {entry.message}")
    return "\n".join(lines)


@mcp.tool()
async def get_logs(ctx: Context, board_id: str, max_lines: int = 50) -> str:
    """Get recent serial output from a board."""
    state: ServerState = ctx.request_context.lifespan_context
    if not hasattr(state, '_monitor') or state._monitor is None:
        return f"Error: No monitoring active for board '{board_id}'."
    logs = state._monitor.get_logs(board_id, max_lines=max_lines)
    if not logs:
        return f"No logs captured yet for board '{board_id}'."
    lines = [f"Recent logs from board '{board_id}' (last {len(logs)} lines):", "-" * 50]
    for entry in logs:
        ts = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
        lines.append(f"[{ts}] {entry.message}")
    return "\n".join(lines)


@mcp.tool()
async def get_server_status(ctx: Context) -> str:
    """Get overall server status and health."""
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    boards = bm.list_boards()
    status_counts = {}
    for board in boards:
        status_name = board.status.name
        status_counts[status_name] = status_counts.get(status_name, 0) + 1
    lines = ["MCP Board Farm Server Status", "=" * 50, "", f"Total Boards: {len(boards)}", "Board Status:"]
    for status, count in sorted(status_counts.items()):
        lines.append(f"  {status}: {count}")
    available = status_counts.get('AVAILABLE', 0)
    lines.append("")
    lines.append(f"Available for use: {available}")
    if hasattr(state, '_monitor') and state._monitor:
        monitored = state._monitor.get_monitored_boards()
        if monitored:
            lines.append("")
            lines.append(f"Active monitors: {', '.join(monitored)}")
    return "\n".join(lines)


def create_server() -> FastMCP:
    """Create and return the MCP server instance."""
    return mcp
