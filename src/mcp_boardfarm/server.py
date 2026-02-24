"""MCP Server for Board Farm - FastMCP implementation.

This module provides the MCP server with agent-friendly tools for:
- Board management (list, reserve, release)
- Firmware building (build_firmware, build_status, get_build_logs)
- Flashing and debugging
- Serial monitoring

The new build system uses a pluggable provider architecture that supports
local builds, Docker containers, and remote build servers.
"""

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
    Board, BoardState, BuildConfig, BuildResult as OldBuildResult, FlashResult,
    LogEntry, ServerConfig
)
from .board_manager import BoardManager
from .builder import BuildManager, ZephyrBuilder, MockBuilder
from .build_providers import (
    BuildRequest, BuildProviderFactory, BuildStatus,
    LocalBuildProvider, DockerBuildProvider
)
from .flasher import OpenOCDFlasher, MockFlasher
from .monitor import SerialMonitor, MockMonitor
from .gdb_debugger import GDBDebuggerManager, GDBDebugger, StepType
from .gdb_models import GDBServerConfig

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
        self.build_manager: Optional[BuildManager] = None
        self.builder: Optional[ZephyrBuilder] = None  # Legacy
        self.flasher: Optional[OpenOCDFlasher] = None
        self.monitor: Optional[SerialMonitor] = None
        self.debug_manager: Optional[GDBDebuggerManager] = None
        self.config: Optional[ServerConfig] = None
        self._monitor: Optional[MockMonitor] = None
        self._active_builds: Dict[str, Any] = {}  # build_id -> build info


# Create FastMCP instance
mcp = FastMCP("mcp-boardfarm")


def _load_build_config(config_path: str) -> Dict[str, Any]:
    """Load build provider configuration from boards.yaml."""
    import yaml
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return config.get("build_providers", {})
    except Exception as e:
        logger.warning(f"Could not load build config: {e}")
        return {}


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Manage application lifecycle."""
    logger.info("Starting MCP Board Farm server...")
    state = ServerState()
    config_path = os.environ.get('BOARDFARM_CONFIG', 'config/boards.yaml')
    state.board_manager = BoardManager(config_path)
    state.board_manager.load_config()
    state.board_manager.detect_boards()
    
    # Initialize new build manager with provider configuration
    build_providers_config = _load_build_config(config_path)
    state.build_manager = BuildManager(build_providers_config)
    
    # Legacy builder for backward compatibility
    state.builder = ZephyrBuilder()
    state.flasher = OpenOCDFlasher()
    state.monitor = SerialMonitor()
    state.debug_manager = GDBDebuggerManager()
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
async def build_firmware(
    ctx: Context,
    board_id: str,
    source: str,
    target: str,
    options: Optional[Dict[str, Any]] = None,
    build_type: str = "debug"
) -> str:
    """Build firmware for a board.
    
    This is the primary agent-friendly build interface. It uses the new
    pluggable provider system that supports local builds, Docker containers,
    and remote build servers.
    
    Args:
        board_id: The board to build for (e.g., "nucleo-h755zi-q-01")
        source: Path to source code or sample name
                (e.g., "/workspace/my_app" or "hello_world")
        target: Build target in format "framework/board"
                (e.g., "zephyr/nucleo_h755zi_q", "arduino:avr:nano")
        options: Optional framework-specific build options
        build_type: "debug" or "release"
    
    Returns:
        Build result summary with build_id for status tracking
        
    Example:
        build_firmware(
            board_id="nucleo-h755zi-q-01",
            source="hello_world",
            target="zephyr/nucleo_h755zi_q"
        )
    """
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    board = bm.get_board(board_id)
    
    if not board:
        return f"Error: Board '{board_id}' not found."
    
    # Create build request
    request = BuildRequest(
        board_id=board_id,
        source_path=source,
        target=target,
        options=options or {},
        build_type=build_type,
    )
    
    framework = request.get_framework()
    logger.info(f"Building {target} for {board_id} (framework: {framework})")
    
    old_status = board.status
    bm.update_board_state(board_id, BoardState.BUILDING)
    
    try:
        # Use new build manager
        if state.build_manager:
            result = await state.build_manager.build(
                BuildConfig(
                    framework=framework,
                    board_id=board_id,
                    source_path=source,
                    build_type=build_type,
                )
            )
        else:
            # Fallback to legacy builder
            builder = MockBuilder()
            result = await builder.build(
                BuildConfig(
                    framework=framework,
                    board_id=board_id,
                    source_path=source,
                    build_type=build_type,
                )
            )
        
        # Store build info for status tracking
        state._active_builds[result.build_id] = {
            "board_id": board_id,
            "target": target,
            "framework": framework,
            "result": result,
        }
        
        bm.update_board_state(board_id, old_status)
        
        # Format response
        lines = [
            f"Build Result: {'SUCCESS' if result.success else 'FAILED'}",
            f"Build ID: {result.build_id}",
            f"Target: {target}",
            f"Framework: {framework}",
            f"Duration: {result.duration_seconds:.2f}s",
            "",
        ]
        
        if result.elf_path:
            lines.append(f"ELF: {result.elf_path}")
        if result.bin_path:
            lines.append(f"BIN: {result.bin_path}")
        if result.hex_path:
            lines.append(f"HEX: {result.hex_path}")
        
        if result.warnings:
            lines.append(f"\nWarnings: {len(result.warnings)}")
        if result.errors:
            lines.append(f"Errors: {len(result.errors)}")
        
        if result.error_message:
            lines.append(f"\nError: {result.error_message[:500]}")
        
        lines.append("\n--- Build Output (last 50 lines) ---")
        if result.stdout:
            stdout_lines = result.stdout.split('\n')
            lines.extend(stdout_lines[-50:])
        
        return "\n".join(lines)
        
    except Exception as e:
        bm.update_board_state(board_id, old_status)
        logger.exception(f"Build failed: {e}")
        return f"Error: Build failed with exception: {e}"


@mcp.tool()
async def build_status(ctx: Context, build_id: str) -> str:
    """Check the status of a build.
    
    Args:
        build_id: The build identifier returned by build_firmware
        
    Returns:
        Current build status and details
    """
    state: ServerState = ctx.request_context.lifespan_context
    
    if build_id in state._active_builds:
        build_info = state._active_builds[build_id]
        result = build_info["result"]
        
        lines = [
            f"Build ID: {build_id}",
            f"Status: {'SUCCESS' if result.success else 'FAILED'}",
            f"Board: {build_info['board_id']}",
            f"Target: {build_info['target']}",
            f"Framework: {build_info['framework']}",
            f"Duration: {result.duration_seconds:.2f}s",
        ]
        
        if result.elf_path:
            lines.append(f"ELF: {result.elf_path}")
        
        return "\n".join(lines)
    
    return f"Build '{build_id}' not found. It may have completed and been cleaned up."


@mcp.tool()
async def get_build_logs(ctx: Context, build_id: str, lines: int = 100) -> str:
    """Get logs from a build.
    
    Args:
        build_id: The build identifier
        lines: Number of log lines to return (default: 100)
        
    Returns:
        Build logs
    """
    state: ServerState = ctx.request_context.lifespan_context
    
    if build_id not in state._active_builds:
        return f"Build '{build_id}' not found."
    
    result = state._active_builds[build_id]["result"]
    
    output_lines = []
    if result.stdout:
        output_lines.extend(result.stdout.split('\n'))
    if result.stderr:
        output_lines.extend([f"[stderr] {line}" for line in result.stderr.split('\n')])
    
    return_lines = output_lines[-lines:] if len(output_lines) > lines else output_lines
    
    header = f"Build logs for {build_id} (last {len(return_lines)} lines):"
    return f"{header}\n{'=' * len(header)}\n" + "\n".join(return_lines)


@mcp.tool()
async def list_build_targets(ctx: Context, board_id: Optional[str] = None,
                             framework: Optional[str] = None) -> str:
    """List available build targets.
    
    Args:
        board_id: Optional board to filter by
        framework: Optional framework to filter by (zephyr, arduino, etc.)
        
    Returns:
        List of available build targets
    """
    state: ServerState = ctx.request_context.lifespan_context
    
    lines = ["Available Build Targets:", "=" * 50]
    
    if framework:
        targets = await state.build_manager.list_build_targets(framework)
        lines.append(f"\nFramework: {framework}")
        for target in targets[:50]:  # Limit output
            lines.append(f"  - {target}")
        if len(targets) > 50:
            lines.append(f"  ... and {len(targets) - 50} more")
    else:
        # Show all frameworks
        frameworks = ["zephyr", "arduino", "platformio"]
        for fw in frameworks:
            try:
                targets = await state.build_manager.list_build_targets(fw)
                lines.append(f"\n{fw}:")
                for target in targets[:10]:
                    lines.append(f"  - {target}")
                if len(targets) > 10:
                    lines.append(f"  ... and {len(targets) - 10} more")
            except Exception as e:
                lines.append(f"\n{fw}: Error loading targets - {e}")
    
    return "\n".join(lines)


def create_server() -> FastMCP:
    """Create and return the MCP server instance."""
    return mcp
