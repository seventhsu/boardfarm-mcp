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
from .board_queue import BoardQueue, QueueStatus, get_queue
from .builder import BuildManager
from .build_providers import (
    BuildRequest, BuildProviderFactory, BuildStatus,
    LocalBuildProvider, DockerBuildProvider
)
from .flasher import STLinkFlasher
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
        self.board_queue: Optional[BoardQueue] = None
        self.build_manager: Optional[BuildManager] = None
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
    
    # Initialize board queue first
    state.board_queue = get_queue()
    await state.board_queue.start()
    
    # Initialize board manager and connect to queue
    state.board_manager = BoardManager(config_path, board_queue=state.board_queue)
    state.board_manager.load_config()
    state.board_manager.detect_boards()
    state.board_manager.set_queue(state.board_queue)
    
    # Initialize new build manager with provider configuration
    build_providers_config = _load_build_config(config_path)
    state.build_manager = BuildManager(build_providers_config)
    state.flasher = STLinkFlasher()
    state.monitor = SerialMonitor()
    state.debug_manager = GDBDebuggerManager()
    logger.info(f"Server ready. Detected {len(state.board_manager.list_boards())} boards.")
    yield state
    logger.info("Shutting down MCP Board Farm server...")
    if state.monitor:
        await state.monitor.close_all()
    if state.board_queue:
        await state.board_queue.stop()


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
    await bm.update_board_state(board_id, BoardState.BUILDING)
    
    try:
        # Use build manager
        # Extract zephyr board name from target if applicable
        zephyr_board = None
        if framework == "zephyr" and "/" in target:
            zephyr_board = target.split("/", 1)[1]
        
        result = await state.build_manager.build(
            BuildConfig(
                framework=framework,
                board_id=board_id,
                source_path=source,
                build_type=build_type,
                zephyr_board=zephyr_board,
            )
        )
        
        # Store build info for status tracking
        state._active_builds[result.build_id] = {
            "board_id": board_id,
            "target": target,
            "framework": framework,
            "result": result,
        }
        
        await bm.update_board_state(board_id, old_status)
        
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
        await bm.update_board_state(board_id, old_status)
        logger.exception(f"Build failed: {e}")
        return f"Error: Build failed with exception: {e}"


@mcp.tool()
async def flash_firmware(ctx: Context, board_id: str, build_id: str,
                         core: Optional[str] = None) -> str:
    """Flash firmware to a reserved board using OpenOCD.

    Programs the built firmware onto the target board. The board must be
    in RESERVED state before flashing.

    Args:
        board_id: The board to flash (must be reserved)
        build_id: The build ID from build_firmware
        core: For dual-core MCUs (H7), specify 'M7' or 'M4' (default: M7)

    Returns:
        Flash operation result

    Example:
        flash_firmware("nucleo-h755zi-q-01", "build_12345")
    """
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    flasher = state.flasher

    if not flasher:
        return "Error: Flasher not initialized."

    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."

    if board.status != BoardState.RESERVED:
        return f"Error: Board '{board_id}' is not reserved. Current status: {board.status.name}"

    if build_id not in state._active_builds:
        return f"Error: Build '{build_id}' not found."

    build_info = state._active_builds[build_id]
    build_result = build_info["result"]

    if not build_result.success:
        return f"Error: Build '{build_id}' was not successful. Cannot flash failed build."

    if not build_result.elf_path:
        return f"Error: Build '{build_id}' has no ELF file."

    old_status = board.status
    await bm.update_board_state(board_id, BoardState.FLASHING)

    try:
        logger.info(f"Flashing build {build_id} to {board_id}")
        flash_result = flasher.flash(board, build_result, core=core)

        await bm.update_board_state(board_id, old_status)

        if flash_result.success:
            lines = [
                f"✓ Flash successful!",
                f"Board: {board_id}",
                f"Build: {build_id}",
                f"Duration: {flash_result.duration_seconds:.2f}s",
            ]
            if flash_result.bytes_written:
                lines.append(f"Bytes written: {flash_result.bytes_written}")
            if flash_result.verify_passed:
                lines.append("Verification: PASSED")
            return "\n".join(lines)
        else:
            lines = [
                f"✗ Flash failed!",
                f"Board: {board_id}",
                f"Error: {flash_result.error_message}",
            ]
            if flash_result.stderr:
                lines.append(f"\nStderr:\n{flash_result.stderr[:500]}")
            return "\n".join(lines)

    except Exception as e:
        await bm.update_board_state(board_id, old_status)
        logger.exception(f"Flash failed: {e}")
        return f"Error: Flash failed with exception: {e}"


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


@mcp.tool()
async def queue_for_board(
    ctx: Context,
    board_type: str,
    priority: int,
    estimated_minutes: int,
    agent_id: str,
    job_description: str,
    required_features: Optional[List[str]] = None,
    optional_features: Optional[List[str]] = None,
    min_capabilities: Optional[Dict[str, Any]] = None,
    auto_accept: bool = False
) -> str:
    """Queue for a board reservation with priority and feature matching.
    
    This adds your request to the board queue. When a matching board becomes
    available, it will be assigned based on priority and wait time.
    
    Args:
        board_type: Type of board needed (e.g., "h755", "esp32", "nucleo")
        priority: Priority level 1-5 (1 is highest priority)
        estimated_minutes: How long you need the board (max 8 hours = 480 min)
        agent_id: Your agent identifier
        job_description: Description of what you're testing/building
        required_features: List of features the board MUST have (e.g., ["ethernet", "can"])
        optional_features: Nice-to-have features for better matching
        min_capabilities: Minimum specs required (e.g., {"ram_kb": 512})
        auto_accept: If True, automatically reserve the board when available
        
    Returns:
        Queue ID for tracking your request
        
    Example:
        queue_for_board(
            board_type="h755",
            priority=2,
            estimated_minutes=120,
            agent_id="sabine-42",
            job_description="CH57x BLE driver testing",
            required_features=["ethernet", "dual_core"],
            min_capabilities={"ram_kb": 512}
        )
    """
    state: ServerState = ctx.request_context.lifespan_context
    queue = state.board_queue
    
    queue_id = queue.add_request(
        board_type=board_type,
        priority=priority,
        estimated_minutes=estimated_minutes,
        agent_id=agent_id,
        job_description=job_description,
        required_features=required_features or [],
        optional_features=optional_features or [],
        min_capabilities=min_capabilities or {},
        auto_accept=auto_accept
    )
    
    position, _, desc = queue.get_position(queue_id)
    
    return f"Queue ID: {queue_id}\nPosition: {desc}\nStatus: PENDING"


@mcp.tool()
async def get_queue_position(ctx: Context, queue_id: str) -> str:
    """Get the current position of a queue request.
    
    Args:
        queue_id: The queue ID returned by queue_for_board
        
    Returns:
        Queue position information
    """
    state: ServerState = ctx.request_context.lifespan_context
    queue = state.board_queue
    
    entry = queue.get_entry(queue_id)
    if not entry:
        return f"Error: Queue ID '{queue_id}' not found."
    
    position, same_priority, desc = queue.get_position(queue_id)
    
    lines = [
        f"Queue ID: {queue_id}",
        f"Board Type: {entry.board_type}",
        f"Priority: {entry.priority}",
        f"Status: {entry.status.name}",
        f"Position: {desc}",
        f"Requested: {entry.requested_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Estimated Duration: {entry.estimated_minutes} minutes",
        f"Job: {entry.job_description}",
    ]
    
    if entry.status == QueueStatus.ASSIGNED and entry.assigned_board_id:
        lines.append(f"\n✓ Board Assigned: {entry.assigned_board_id}")
    
    if entry.required_features:
        lines.append(f"\nRequired Features: {', '.join(entry.required_features)}")
    if entry.optional_features:
        lines.append(f"Optional Features: {', '.join(entry.optional_features)}")
    
    return "\n".join(lines)


@mcp.tool()
async def cancel_queue_request(ctx: Context, queue_id: str, agent_id: str) -> str:
    """Cancel a pending queue request.
    
    Args:
        queue_id: The queue ID to cancel
        agent_id: Your agent ID (must match the request)
        
    Returns:
        Success or error message
    """
    state: ServerState = ctx.request_context.lifespan_context
    queue = state.board_queue
    
    entry = queue.get_entry(queue_id)
    if not entry:
        return f"Error: Queue ID '{queue_id}' not found."
    
    if entry.agent_id != agent_id:
        return f"Error: Agent ID mismatch. This request belongs to {entry.agent_id}."
    
    if entry.status not in (QueueStatus.PENDING, QueueStatus.ASSIGNED):
        return f"Error: Cannot cancel - status is {entry.status.name}"
    
    success = queue.cancel_request(queue_id, agent_id)
    
    if success:
        return f"Queue request {queue_id} cancelled successfully."
    else:
        return f"Failed to cancel queue request {queue_id}."


@mcp.tool()
async def list_queue(
    ctx: Context,
    board_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    show_completed: bool = False
) -> str:
    """List all queued board requests.
    
    Args:
        board_type: Filter by board type
        agent_id: Filter by agent ID
        show_completed: Include completed/cancelled requests
        
    Returns:
        Formatted queue listing
    """
    state: ServerState = ctx.request_context.lifespan_context
    queue = state.board_queue
    
    # Get pending entries
    pending = queue.list_queue(status=QueueStatus.PENDING, board_type=board_type, agent_id=agent_id)
    assigned = queue.list_queue(status=QueueStatus.ASSIGNED, board_type=board_type, agent_id=agent_id)
    
    lines = ["Board Queue Status", "=" * 70]
    
    # Summary
    summary = queue.get_queue_summary()
    lines.append(f"\nSummary: {summary['pending']} pending, {summary['assigned']} assigned")
    
    # Pending requests
    if pending:
        lines.append(f"\n📋 Pending Requests ({len(pending)}):")
        lines.append("-" * 70)
        for i, entry in enumerate(pending[:20], 1):  # Limit to 20
            pos, _, _ = queue.get_position(entry.queue_id)
            lines.append(f"\n{i}. [{entry.priority}] {entry.board_type} - {entry.agent_id}")
            lines.append(f"   Queue ID: {entry.queue_id}")
            lines.append(f"   Job: {entry.job_description}")
            lines.append(f"   Wait: {pos} in queue, requested {entry.requested_at.strftime('%H:%M')}")
            if entry.required_features:
                lines.append(f"   Required: {', '.join(entry.required_features)}")
        if len(pending) > 20:
            lines.append(f"\n... and {len(pending) - 20} more")
    else:
        lines.append("\n📋 No pending requests")
    
    # Assigned requests
    if assigned:
        lines.append(f"\n🔒 Assigned Boards ({len(assigned)}):")
        lines.append("-" * 70)
        for entry in assigned:
            lines.append(f"\n• {entry.assigned_board_id} → {entry.agent_id}")
            lines.append(f"  Job: {entry.job_description}")
            if entry.assigned_at:
                lines.append(f"  Assigned at: {entry.assigned_at.strftime('%H:%M:%S')}")
    
    # Show completed if requested
    if show_completed:
        completed = queue.list_queue(status=QueueStatus.COMPLETED, board_type=board_type, agent_id=agent_id)
        cancelled = queue.list_queue(status=QueueStatus.CANCELLED, board_type=board_type, agent_id=agent_id)
        
        if completed:
            lines.append(f"\n✓ Completed ({len(completed)}):")
            for entry in completed[:10]:
                lines.append(f"  {entry.queue_id}: {entry.board_type} - {entry.job_description}")
        
        if cancelled:
            lines.append(f"\n✗ Cancelled ({len(cancelled)}):")
            for entry in cancelled[:10]:
                lines.append(f"  {entry.queue_id}: {entry.board_type} - {entry.job_description}")
    
    return "\n".join(lines)


@mcp.tool()
async def reserve_board_with_timeout(
    ctx: Context,
    board_id: str,
    agent_id: str,
    minutes: int = 30
) -> str:
    """Reserve a specific board with custom timeout.
    
    Args:
        board_id: The board to reserve (e.g., "nucleo-h755zi-q-01")
        agent_id: Your agent identifier
        minutes: Reservation duration (1-480 minutes, default 30)
        
    Returns:
        Reservation confirmation or error
    """
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    
    # Limit timeout
    minutes = max(1, min(480, minutes))
    
    success = await bm.reserve_board(board_id, agent_id, minutes)
    
    if success:
        until = datetime.now() + __import__('datetime').timedelta(minutes=minutes)
        return (
            f"✓ Board '{board_id}' reserved successfully!\n"
            f"  Reserved by: {agent_id}\n"
            f"  Duration: {minutes} minutes\n"
            f"  Expires at: {until.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        if board.status == BoardState.RESERVED:
            return f"Error: Board '{board_id}' is already reserved by {board.reserved_by}."
        elif board.status == BoardState.OFFLINE:
            return f"Error: Board '{board_id}' is offline."
        else:
            return f"Error: Cannot reserve board '{board_id}' (status: {board.status.name})."


@mcp.tool()
async def release_board(ctx: Context, board_id: str, agent_id: str) -> str:
    """Release a reserved board.
    
    Args:
        board_id: The board to release
        agent_id: Your agent identifier (must match reservation)
        
    Returns:
        Success or error message
    """
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    
    if board.status != BoardState.RESERVED:
        return f"Error: Board '{board_id}' is not reserved (status: {board.status.name})."
    
    if board.reserved_by != agent_id:
        return f"Error: Board reserved by {board.reserved_by}, not {agent_id}."
    
    success = await bm.release_board(board_id, agent_id)
    
    if success:
        # Check if board was assigned from queue
        return f"✓ Board '{board_id}' released successfully."
    else:
        return f"Error: Failed to release board '{board_id}'."


@mcp.tool()
async def analyze_fault_arm_cortex_m(ctx: Context, board_id: str) -> str:
    """Analyze ARM Cortex-M fault status registers.
    
    Reads and decodes CFSR (Configurable Fault Status Register),
    HFSR (HardFault Status Register), MMFAR (MemManage Address),
    and BFAR (BusFault Address) to diagnose the cause of a HardFault
    or other exception.
    
    Args:
        board_id: The board to analyze (must have active GDB session)
        
    Returns:
        Structured fault analysis with decoded bit fields
    """
    state: ServerState = ctx.request_context.lifespan_context
    dm = state.debug_manager
    
    if not dm:
        return "Error: Debug manager not initialized."
    
    debugger = dm.get_session(board_id)
    if not debugger:
        return f"Error: No active GDB session for board '{board_id}'. Start a debug session first."
    
    # ARM Cortex-M fault register addresses
    CFSR_ADDR = 0xE000ED28
    HFSR_ADDR = 0xE000ED2C
    MMFAR_ADDR = 0xE000ED34
    BFAR_ADDR = 0xE000ED38
    
    try:
        # Read fault registers via GDB
        cfsr_result = await debugger.read_memory(CFSR_ADDR, 4)
        hfsr_result = await debugger.read_memory(HFSR_ADDR, 4)
        mmfar_result = await debugger.read_memory(MMFAR_ADDR, 4)
        bfar_result = await debugger.read_memory(BFAR_ADDR, 4)
        
        if not cfsr_result.success:
            return f"Error reading fault registers: {cfsr_result.message}"
        
        # Extract values (little-endian)
        cfsr = int.from_bytes(cfsr_result.data.get('data', [0, 0, 0, 0]), 'little')
        hfsr = int.from_bytes(hfsr_result.data.get('data', [0, 0, 0, 0]), 'little')
        mmfar = int.from_bytes(mmfar_result.data.get('data', [0, 0, 0, 0]), 'little')
        bfar = int.from_bytes(bfar_result.data.get('data', [0, 0, 0, 0]), 'little')
        
        # Parse CFSR subregisters
        mmfsr = cfsr & 0xFF           # MemManage Fault Status
        bfsr = (cfsr >> 8) & 0xFF     # BusFault Status
        ufsr = (cfsr >> 16) & 0xFFFF  # UsageFault Status
        
        # Build analysis
        lines = ["=" * 50, "ARM CORTEX-M FAULT ANALYSIS", "=" * 50, ""]
        lines.append(f"Raw Register Values:")
        lines.append(f"  CFSR: 0x{cfsr:08X}")
        lines.append(f"  HFSR: 0x{hfsr:08X}")
        lines.append(f"  MMFAR: 0x{mmfar:08X}")
        lines.append(f"  BFAR: 0x{bfar:08X}")
        lines.append("")
        
        faults_found = []
        
        # Decode MMFSR (MemManage Fault)
        if mmfsr:
            lines.append("MemManage Fault (MMFSR):")
            if mmfsr & 0x01:
                faults_found.append("IACCVIOL: Instruction access violation")
            if mmfsr & 0x02:
                faults_found.append("DACCVIOL: Data access violation")
                if mmfsr & 0x80:
                    lines.append(f"  -> MMFAR valid: 0x{mmfar:08X}")
            if mmfsr & 0x08:
                faults_found.append("MUNSTKERR: MemManage fault on unstacking")
            if mmfsr & 0x10:
                faults_found.append("MSTKERR: MemManage fault on stacking")
            if mmfsr & 0x20:
                faults_found.append("MLSPERR: MemManage fault during FP lazy state preservation")
            for fault in faults_found:
                lines.append(f"  ✗ {fault}")
            lines.append("")
        
        # Decode BFSR (BusFault)
        if bfsr:
            lines.append("BusFault (BFSR):")
            bus_faults = []
            if bfsr & 0x01:
                bus_faults.append("IBUSERR: Instruction bus error")
            if bfsr & 0x02:
                bus_faults.append("PRECISERR: Precise data bus error")
                if bfsr & 0x80:
                    lines.append(f"  -> BFAR valid: 0x{bfar:08X}")
            if bfsr & 0x04:
                bus_faults.append("IMPRECISERR: Imprecise data bus error")
            if bfsr & 0x08:
                bus_faults.append("UNSTKERR: BusFault on unstacking")
            if bfsr & 0x10:
                bus_faults.append("STKERR: BusFault on stacking")
            if bfsr & 0x20:
                bus_faults.append("LSPERR: BusFault during FP lazy state preservation")
            for fault in bus_faults:
                lines.append(f"  ✗ {fault}")
            lines.append("")
        
        # Decode UFSR (UsageFault)
        if ufsr:
            lines.append("UsageFault (UFSR):")
            usage_faults = []
            if ufsr & 0x0001:
                usage_faults.append("UNDEFINSTR: Undefined instruction")
            if ufsr & 0x0002:
                usage_faults.append("INVSTATE: Invalid state ( Thumb mode violation)")
            if ufsr & 0x0004:
                usage_faults.append("INVPC: Invalid PC (bad EXC_RETURN value)")
            if ufsr & 0x0008:
                usage_faults.append("NOCP: No coprocessor (accessed disabled FPU)")
            if ufsr & 0x0100:
                usage_faults.append("UNALIGNED: Unaligned access")
            if ufsr & 0x0200:
                usage_faults.append("DIVBYZERO: Divide by zero")
            for fault in usage_faults:
                lines.append(f"  ✗ {fault}")
            lines.append("")
        
        # Decode HFSR
        if hfsr:
            lines.append("HardFault (HFSR):")
            if hfsr & 0x40000000:
                lines.append("  ✗ FORCED: Escalated from configurable fault (maskable)")
            if hfsr & 0x80000000:
                lines.append("  ✗ DEBUGEVT: Debug event occurred")
            if hfsr & 0x00000002:
                lines.append("  ✗ VECTBL: Vector table read fault")
            lines.append("")
        
        # Summary
        if not faults_found and not mmfsr and not bfsr and not ufsr and not hfsr:
            lines.append("No active fault flags detected.")
            lines.append("Possible causes:")
            lines.append("  - Fault was cleared (read-on-clear registers)")
            lines.append("  - Check stacked PC/LR for faulting location")
        else:
            lines.append("=" * 50)
            lines.append("DIAGNOSIS SUMMARY")
            lines.append("=" * 50)
            
            if mmfsr:
                lines.append("→ MemManage Fault: Memory protection violation")
                lines.append("  Check MPU configuration and memory access permissions")
            if bfsr:
                lines.append("→ BusFault: External bus error or invalid address")
                lines.append("  Check address validity and peripheral state")
            if ufsr:
                lines.append("→ UsageFault: Program execution error")
                lines.append("  Check instruction sequence and register values")
            if hfsr & 0x40000000:
                lines.append("→ HardFault (escalated): Configurable fault was masked")
                lines.append("  Check fault handler configuration in SHCSR")
        
        lines.append("")
        lines.append("Recommended Actions:")
        lines.append("1. Read stacked PC (R14/LR) to find faulting instruction")
        lines.append("2. Check SP to determine if stack overflow occurred")
        lines.append("3. Review memory map for accessed addresses")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error analyzing fault: {str(e)}"


@mcp.tool()
# Debug session management tools

@mcp.tool()
async def start_debug_session(ctx: Context, board_id: str) -> str:
    """Start a GDB debug session for a reserved board.
    
    Args:
        board_id: The board to debug (must be reserved)
        
    Returns:
        Session start result
    """
    state: ServerState = ctx.request_context.lifespan_context
    dm = state.debug_manager
    bm = state.board_manager
    
    if not dm:
        return "Error: Debug manager not initialized."
    
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    
    if board.status != BoardState.RESERVED:
        return f"Error: Board '{board_id}' must be reserved before debugging."
    
    # Check if debugger already exists
    if dm.get_session(board_id):
        return f"Debug session already active for '{board_id}'."
    
    # Create debugger
    debugger = dm.create_session(board)
    
    # Start session
    result = await debugger.start_session()
    
    if result.success:
        return f"✓ Debug session started for '{board_id}'\nGDB server listening on port {debugger.config.gdb_port}"
    else:
        return f"✗ Failed to start debug session: {result.message}"


@mcp.tool()
async def stop_debug_session(ctx: Context, board_id: str) -> str:
    """Stop the GDB debug session for a board.
    
    Args:
        board_id: The board to stop debugging
        
    Returns:
        Session stop result
    """
    state: ServerState = ctx.request_context.lifespan_context
    dm = state.debug_manager
    
    if not dm:
        return "Error: Debug manager not initialized."
    
    debugger = dm.get_session(board_id)
    if not debugger:
        return f"No active debug session for '{board_id}'."
    
    result = await debugger.stop_session()
    dm.remove_session(board_id)
    
    if result.success:
        return f"✓ Debug session stopped for '{board_id}'"
    else:
        return f"✗ Failed to stop debug session: {result.message}"


@mcp.tool()
async def step_debug(ctx: Context, board_id: str, step_type: str = "into") -> str:
    """Step execution in the debugger.
    
    Args:
        board_id: The board being debugged
        step_type: "into", "over", or "out"
        
    Returns:
        Step result with new location
    """
    state: ServerState = ctx.request_context.lifespan_context
    dm = state.debug_manager
    
    if not dm:
        return "Error: Debug manager not initialized."
    
    debugger = dm.get_session(board_id)
    if not debugger:
        return f"Error: No active GDB session for '{board_id}'. Start a debug session first."
    
    from .gdb_debugger import StepType
    st = StepType.INTO
    if step_type == "over":
        st = StepType.OVER
    elif step_type == "out":
        st = StepType.OUT
    
    result = await debugger.step(st)
    
    if result.success:
        return f"✓ Stepped {step_type}\n{result.data}"
    else:
        return f"✗ Step failed: {result.message}"


@mcp.tool()
async def get_debug_state(ctx: Context, board_id: str) -> str:
    """Get the current debug state (running, stopped, etc.).
    
    Args:
        board_id: The board being debugged
        
    Returns:
        Current debug state
    """
    state: ServerState = ctx.request_context.lifespan_context
    dm = state.debug_manager
    
    if not dm:
        return "Error: Debug manager not initialized."
    
    debugger = dm.get_session(board_id)
    if not debugger:
        return f"Error: No active GDB session for '{board_id}'."
    
    result = await debugger.get_state()
    
    if result.success:
        return f"Debug state: {result.data}"
    else:
        return f"Error: {result.message}"


@mcp.tool()
async def read_registers(ctx: Context, board_id: str) -> str:
    """Read CPU registers from the debug target.
    
    Args:
        board_id: The board being debugged
        
    Returns:
        Register values
    """
    state: ServerState = ctx.request_context.lifespan_context
    dm = state.debug_manager
    
    if not dm:
        return "Error: Debug manager not initialized."
    
    debugger = dm.get_session(board_id)
    if not debugger:
        return f"Error: No active GDB session for '{board_id}'. Start a debug session first."
    
    result = await debugger.read_registers()
    
    if result.success:
        lines = ["CPU Registers:", "-" * 40]
        for reg in result.data.get('registers', []):
            lines.append(f"  {reg['name']:8s}: 0x{reg['value']:08X}")
        return "\n".join(lines)
    else:
        return f"Error reading registers: {result.message}"
async def get_board_features(ctx: Context, board_id: str) -> str:
    """Get features and capabilities of a board.
    
    Args:
        board_id: The board to query
        
    Returns:
        Board features and capabilities
    """
    state: ServerState = ctx.request_context.lifespan_context
    bm = state.board_manager
    
    board = bm.get_board(board_id)
    if not board:
        return f"Error: Board '{board_id}' not found."
    
    lines = [
        f"Board: {board.board_id}",
        f"Type: {board.type}",
        f"Model: {board.model}",
        f"MCU: {board.mcu}",
        "",
        "Features:",
    ]
    
    if board.features:
        for feat in board.features:
            lines.append(f"  ✓ {feat}")
    else:
        lines.append("  (none defined)")
    
    lines.append("\nCapabilities:")
    caps = board.get_capabilities_dict()
    for key, value in caps.items():
        lines.append(f"  {key}: {value}")
    
    if board.supported_frameworks:
        lines.append(f"\nSupported Frameworks: {', '.join(board.supported_frameworks)}")
    
    return "\n".join(lines)


def create_server() -> FastMCP:
    """Create and return the MCP server instance."""
    return mcp
