"""GDB Debugger implementation using pygdbmi and pyocd gdbserver."""

import os
import re
import json
import logging
import asyncio
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, Callable
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from pygdbmi.gdbcontroller import GdbController

from .gdb_models import (
    GDBSessionState, StepType, Register, StackFrame, Breakpoint,
    MemoryRegion, Variable, GDBSessionInfo, DebugOperationResult,
    GDBServerConfig
)
from .models import Board

logger = logging.getLogger(__name__)


class GDBDebugger:
    """GDB debugger interface for embedded targets."""
    
    def __init__(self, board: Board, config: Optional[GDBServerConfig] = None):
        self.board = board
        self.config = config or GDBServerConfig()
        
        self.session_info = GDBSessionInfo(
            board_id=board.board_id,
            state=GDBSessionState.IDLE,
            gdb_port=self.config.gdb_port,
            target_mcu=board.mcu
        )
        
        self._gdbserver_process: Optional[subprocess.Popen] = None
        self._gdb_controller: Optional[GdbController] = None
        self._breakpoints: Dict[int, Breakpoint] = {}
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._lock = asyncio.Lock()
        self._default_timeout = 10.0  # Increased default timeout for hardware communication
        
    async def start_session(self, elf_path: Optional[str] = None) -> DebugOperationResult:
        """Start a debug session."""
        start_time = time.time()
        
        async with self._lock:
            if self.session_info.state not in (GDBSessionState.IDLE, GDBSessionState.DISCONNECTED, GDBSessionState.ERROR):
                return DebugOperationResult(
                    success=False,
                    operation="start_session",
                    error=f"Session already in state: {self.session_info.state.name}"
                )
            
            try:
                self.session_info.state = GDBSessionState.CONNECTING
                server_started = await self._start_gdbserver()
                if not server_started:
                    self.session_info.state = GDBSessionState.ERROR
                    return DebugOperationResult(
                        success=False,
                        operation="start_session",
                        error="Failed to start pyocd gdbserver",
                        duration_ms=(time.time() - start_time) * 1000
                    )
                
                await asyncio.sleep(0.5)
                
                gdb_started = await self._start_gdb()
                if not gdb_started:
                    await self.stop_session()
                    self.session_info.state = GDBSessionState.ERROR
                    return DebugOperationResult(
                        success=False,
                        operation="start_session",
                        error="Failed to start GDB",
                        duration_ms=(time.time() - start_time) * 1000
                    )
                
                if elf_path and os.path.exists(elf_path):
                    await self._run_gdb_command(f"file {elf_path}")
                
                await self._run_gdb_command(
                    f"target remote {self.config.host}:{self.config.gdb_port}"
                )
                
                self.session_info.state = GDBSessionState.PAUSED
                self.session_info.connected_at = datetime.now()
                self.session_info.last_activity = datetime.now()
                
                await self._detect_target_info()
                
                duration = (time.time() - start_time) * 1000
                return DebugOperationResult(
                    success=True,
                    operation="start_session",
                    message=f"Debug session started on port {self.config.gdb_port}",
                    data=self.session_info.to_dict(),
                    duration_ms=duration
                )
                
            except Exception as e:
                logger.exception("Failed to start debug session")
                await self.stop_session()
                self.session_info.state = GDBSessionState.ERROR
                return DebugOperationResult(
                    success=False,
                    operation="start_session",
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000
                )
    
    async def stop_session(self) -> DebugOperationResult:
        """Stop the debug session."""
        start_time = time.time()
        
        async with self._lock:
            try:
                if self._gdb_controller:
                    try:
                        await self._run_gdb_command("disconnect")
                        self._gdb_controller.exit()
                    except Exception as e:
                        logger.warning(f"Error disconnecting GDB: {e}")
                    finally:
                        self._gdb_controller = None
                
                if self._gdbserver_process:
                    try:
                        self._gdbserver_process.terminate()
                        self._gdbserver_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._gdbserver_process.kill()
                    except Exception as e:
                        logger.warning(f"Error stopping gdbserver: {e}")
                    finally:
                        self._gdbserver_process = None
                
                self.session_info.state = GDBSessionState.DISCONNECTED
                self._breakpoints.clear()
                
                duration = (time.time() - start_time) * 1000
                return DebugOperationResult(
                    success=True,
                    operation="stop_session",
                    message="Debug session stopped",
                    duration_ms=duration
                )
                
            except Exception as e:
                logger.exception("Error stopping debug session")
                return DebugOperationResult(
                    success=False,
                    operation="stop_session",
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000
                )
    
    async def reset(self, halt: bool = True) -> DebugOperationResult:
        """Reset the target."""
        return await self._execute_debug_operation(
            "reset",
            f"monitor reset {'halt' if halt else 'run'}"
        )
    
    async def continue_execution(self) -> DebugOperationResult:
        """Resume execution."""
        start_time = time.time()
        
        await self._run_gdb_command("continue&")
        
        self.session_info.state = GDBSessionState.RUNNING
        self.session_info.last_activity = datetime.now()
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="continue",
            message="Target running",
            duration_ms=duration
        )
    
    async def pause(self) -> DebugOperationResult:
        """Pause/halt the target."""
        start_time = time.time()
        
        await self._run_gdb_command("interrupt")
        await self._update_execution_context()
        
        self.session_info.state = GDBSessionState.PAUSED
        self.session_info.last_activity = datetime.now()
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="pause",
            message="Target halted",
            data={
                "pc": f"0x{self.session_info.current_pc:08x}" if self.session_info.current_pc else None,
                "function": self.session_info.current_function
            },
            duration_ms=duration
        )
    
    async def step(self, step_type: StepType = StepType.INTO) -> DebugOperationResult:
        """Execute a single step."""
        commands = {
            StepType.INTO: "step",
            StepType.OVER: "next",
            StepType.OUT: "finish",
            StepType.INSTRUCTION: "stepi"
        }
        
        cmd = commands.get(step_type, "step")
        result = await self._execute_debug_operation(cmd, cmd)
        
        await self._update_execution_context()
        
        if result.success:
            result.data = {
                "pc": f"0x{self.session_info.current_pc:08x}" if self.session_info.current_pc else None,
                "function": self.session_info.current_function,
                "file": self.session_info.current_file,
                "line": self.session_info.current_line
            }
        
        return result
    
    async def set_breakpoint(self, location: str) -> DebugOperationResult:
        """Set a breakpoint."""
        start_time = time.time()
        
        result = await self._run_gdb_command(f"break {location}")
        
        bp_id = None
        for response in result:
            payload = self._extract_payload(response)
            match = re.search(r'Breakpoint\s+(\d+)', payload)
            if match:
                bp_id = int(match.group(1))
                break
        
        if bp_id:
            bp = Breakpoint(id=bp_id, type="breakpoint", location=location)
            self._breakpoints[bp_id] = bp
            
            duration = (time.time() - start_time) * 1000
            return DebugOperationResult(
                success=True,
                operation="set_breakpoint",
                message=f"Breakpoint {bp_id} set at {location}",
                data=bp.to_dict(),
                duration_ms=duration
            )
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=False,
            operation="set_breakpoint",
            error=f"Failed to set breakpoint at {location}",
            duration_ms=duration
        )
    
    async def set_breakpoint_function(self, function: str) -> DebugOperationResult:
        """Set a breakpoint at a function."""
        return await self.set_breakpoint(function)
    
    async def clear_breakpoint(self, bp_id: int) -> DebugOperationResult:
        """Remove a breakpoint."""
        start_time = time.time()
        
        await self._run_gdb_command(f"delete {bp_id}")
        
        if bp_id in self._breakpoints:
            del self._breakpoints[bp_id]
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="clear_breakpoint",
            message=f"Breakpoint {bp_id} cleared",
            duration_ms=duration
        )
    
    async def list_breakpoints(self) -> DebugOperationResult:
        """List all breakpoints."""
        start_time = time.time()
        
        breakpoints = [bp.to_dict() for bp in self._breakpoints.values()]
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="list_breakpoints",
            message=f"Found {len(breakpoints)} breakpoints",
            data={"breakpoints": breakpoints},
            duration_ms=duration
        )
    
    async def read_registers(self) -> DebugOperationResult:
        """Read all CPU registers."""
        start_time = time.time()
        
        result = await self._run_gdb_command("info registers")
        registers = self._parse_registers(result)
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="read_registers",
            message=f"Read {len(registers)} registers",
            data={"registers": [r.to_dict() for r in registers], "count": len(registers)},
            duration_ms=duration
        )
    
    async def read_register(self, name: str) -> DebugOperationResult:
        """Read a specific register."""
        start_time = time.time()
        
        result = await self._run_gdb_command(f"print/${name}")
        value = self._parse_register_value(result)
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="read_register",
            message=f"Register {name} = {value}",
            data={"name": name, "value": value},
            duration_ms=duration
        )
    
    async def read_memory(self, address: int, size: int) -> DebugOperationResult:
        """Read memory from target."""
        start_time = time.time()
        
        result = await self._run_gdb_command(f"x/{size}bx {address}")
        data = self._parse_memory_dump(result)
        
        mem_region = MemoryRegion(address=address, size=len(data), data=data)
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="read_memory",
            message=f"Read {len(data)} bytes from 0x{address:08x}",
            data=mem_region.to_dict(),
            duration_ms=duration
        )
    
    async def write_memory(self, address: int, data: Union[bytes, List[int], str]) -> DebugOperationResult:
        """Write memory to target."""
        start_time = time.time()
        
        if isinstance(data, str):
            if data.startswith('0x'):
                data = data[2:]
            data = bytes.fromhex(data)
        elif isinstance(data, list):
            data = bytes(data)
        
        for i, byte in enumerate(data):
            await self._run_gdb_command(f"set *((unsigned char *) {address + i}) = {byte}")
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="write_memory",
            message=f"Wrote {len(data)} bytes to 0x{address:08x}",
            data={"address": f"0x{address:08x}", "bytes_written": len(data)},
            duration_ms=duration
        )
    
    async def get_stack_trace(self, max_frames: int = 20) -> DebugOperationResult:
        """Get the call stack."""
        start_time = time.time()
        
        result = await self._run_gdb_command(f"backtrace {max_frames}")
        frames = self._parse_stack_trace(result)
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="get_stack_trace",
            message=f"Stack depth: {len(frames)} frames",
            data={"frames": [f.to_dict() for f in frames], "depth": len(frames)},
            duration_ms=duration
        )
    
    async def get_local_variables(self) -> DebugOperationResult:
        """Get local variables."""
        start_time = time.time()
        
        result = await self._run_gdb_command("info locals")
        variables = self._parse_variables(result)
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="get_local_variables",
            message=f"Found {len(variables)} local variables",
            data={"variables": [v.to_dict() for v in variables]},
            duration_ms=duration
        )
    
    async def get_global_variables(self) -> DebugOperationResult:
        """Get global variables."""
        start_time = time.time()
        
        duration = (time.time() - start_time) * 1000
        return DebugOperationResult(
            success=True,
            operation="get_global_variables",
            message="Use read_memory for specific global addresses",
            data={},
            duration_ms=duration
        )
    
    @property
    def state(self) -> DebugOperationResult:
        """Get current debug session state (property, not coroutine)."""
        return DebugOperationResult(
            success=True,
            operation="get_state",
            message=f"Session state: {self.session_info.state.name}",
            data=self.session_info.to_dict(),
            duration_ms=0
        )
    
    # Keep async version for backward compatibility
    async def get_state(self) -> DebugOperationResult:
        """Get current debug session state."""
        return self.state
    
    # Internal helper methods
    
    async def _start_gdbserver(self) -> bool:
        """Start pyocd gdbserver subprocess."""
        try:
            # Use the pyocd from the same Python environment
            import sys
            pyocd_exe = os.path.join(os.path.dirname(sys.executable), "pyocd")
            if not os.path.exists(pyocd_exe):
                pyocd_exe = "pyocd"  # Fall back to PATH
            
            cmd = [
                pyocd_exe, "gdbserver",
                "--port", str(self.config.gdb_port),
                "--telnet-port", str(self.config.telnet_port),
                "--frequency", str(self.config.frequency),
            ]
            
            if self.config.probe_uid:
                cmd.extend(["--uid", self.config.probe_uid])
            
            if self.config.target:
                cmd.extend(["--target", self.config.target])
            
            cmd.extend(self.config.extra_args)
            
            logger.info(f"Starting pyocd gdbserver: {' '.join(cmd)}")
            
            self._gdbserver_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            await asyncio.sleep(0.2)
            
            
            if self._gdbserver_process.poll() is not None:
                stdout, stderr = self._gdbserver_process.communicate()
                logger.error(f"pyocd failed: {stderr}")
                return False
            
            return True
            
        except Exception as e:
            logger.exception("Failed to start gdbserver")
            return False
    
    async def _start_gdb(self) -> bool:
        """Start GDB controller."""
        try:
            self._gdb_controller = GdbController()
            await asyncio.sleep(0.2)
            return True
        except Exception as e:
            logger.exception("Failed to start GDB")
            return False
    
    async def _run_gdb_command(self, command: str, timeout: Optional[float] = None) -> Any:
        """Run a GDB command and return the response."""
        if not self._gdb_controller:
            raise RuntimeError("GDB not initialized")
        
        if timeout is None:
            timeout = self._default_timeout
        
        loop = asyncio.get_event_loop()
        
        def run_cmd():
            return self._gdb_controller.write(command, timeout_sec=timeout)
        
        return await loop.run_in_executor(self._executor, run_cmd)
    
    async def _execute_debug_operation(self, operation: str, command: str, timeout: Optional[float] = None) -> DebugOperationResult:
        """Execute a debug operation with timing."""
        start_time = time.time()
        
        if timeout is None:
            timeout = self._default_timeout
        
        try:
            result = await self._run_gdb_command(command, timeout)
            
            duration = (time.time() - start_time) * 1000
            return DebugOperationResult(
                success=True,
                operation=operation,
                message=f"Operation {operation} completed",
                duration_ms=duration
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return DebugOperationResult(
                success=False,
                operation=operation,
                error=str(e),
                duration_ms=duration
            )
    
    async def _update_execution_context(self):
        """Update current execution context from GDB."""
        try:
            # Get current frame info
            result = await self._run_gdb_command("frame")
            
            for response in result:
                payload = self._extract_payload(response)
                
                # Parse file and line
                file_match = re.search(r'at\s+([^:]+):(\d+)', payload)
                if file_match:
                    self.session_info.current_file = file_match.group(1)
                    self.session_info.current_line = int(file_match.group(2))
                
                # Parse function
                func_match = re.search(r'#\d+\s+(?:0x[0-9a-fA-F]+\s+in\s+)?([^\s(]+)', payload)
                if func_match:
                    self.session_info.current_function = func_match.group(1)
            
            # Get PC
            pc_result = await self._run_gdb_command("print/$pc")
            for response in pc_result:
                payload = self._extract_payload(response)
                pc_match = re.search(r'=\s+(0x[0-9a-fA-F]+)', payload)
                if pc_match:
                    self.session_info.current_pc = int(pc_match.group(1), 16)
                    
        except Exception as e:
            logger.warning(f"Failed to update execution context: {e}")
    
    async def _detect_target_info(self):
        """Detect target architecture information."""
        try:
            result = await self._run_gdb_command("info target")
            # Could parse arch info here
            self.session_info.target_arch = "ARM"
        except Exception as e:
            logger.warning(f"Failed to detect target info: {e}")
    
    def _extract_payload(self, response: Any) -> str:
        """Extract payload from GDB response, handling various formats."""
        if isinstance(response, dict):
            payload = response.get('payload', '')
            # Handle case where payload itself is a dict
            if isinstance(payload, dict):
                return str(payload)
            return payload if payload else ''
        elif isinstance(response, str):
            return response
        else:
            return str(response) if response else ''

    def _normalize_response(self, result: Any) -> List[Dict[str, Any]]:
        """Normalize GDB response to List[Dict] format."""
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return result
        return [{'payload': str(result)}]

    def _parse_registers(self, result: Any) -> List[Register]:
        """Parse register info from GDB response using pygdbmi structured output."""
        registers = []
        
        # pygdbmi returns structured data - use it directly
        for response in self._normalize_response(result):
            if isinstance(response, dict) and 'payload' in response:
                payload = response['payload']
                if isinstance(payload, str):
                    lines = payload.split('\n')
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 2 and parts[0].isalnum():
                            try:
                                name = parts[0]
                                value_str = parts[1]
                                value = int(value_str, 16) if value_str.startswith('0x') else int(value_str)
                                registers.append(Register(name=name, value=value))
                            except (ValueError, IndexError):
                                continue
        
        return registers
    
    def _parse_register_value(self, result: Any) -> str:
        """Parse a single register value."""
        result = self._normalize_response(result)
        for response in result:
            payload = self._extract_payload(response)
            match = re.search(r'=\s+(0x[0-9a-fA-F]+|\d+)', payload)
            if match:
                return match.group(1)
        return "unknown"
    
    def _parse_memory_dump(self, result: Any) -> bytes:
        """Parse memory dump from GDB x command - simplified."""
        data = []
        
        for response in self._normalize_response(result):
            payload = self._extract_payload(response)
            if isinstance(payload, str):
                for part in payload.split():
                    try:
                        if part.startswith('0x'):
                            data.append(int(part, 16))
                    except ValueError:
                        continue
        
        return bytes(data)
    
    def _parse_stack_trace(self, result: Any) -> List[StackFrame]:
        """Parse stack trace from GDB backtrace - simplified."""
        frames = []
        
        for response in self._normalize_response(result):
            payload = self._extract_payload(response)
            if isinstance(payload, str):
                for line in payload.split('\n'):
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0].startswith('#'):
                        try:
                            level = int(parts[0][1:])
                            function = parts[2] if len(parts) > 2 and parts[1] == 'in' else parts[1]
                            file, line_num = None, None
                            if 'at' in parts:
                                at_idx = parts.index('at')
                                if at_idx + 1 < len(parts):
                                    loc = parts[at_idx + 1]
                                    if ':' in loc:
                                        file, line_str = loc.rsplit(':', 1)
                                        try:
                                            line_num = int(line_str)
                                        except ValueError:
                                            pass
                            frames.append(StackFrame(level=level, function=function, file=file, line=line_num))
                        except (ValueError, IndexError):
                            continue
        
        return frames
    
    def _parse_variables(self, result: Any) -> List[Variable]:
        """Parse local variables from GDB - simplified."""
        variables = []
        
        for response in self._normalize_response(result):
            payload = self._extract_payload(response)
            if isinstance(payload, str):
                for line in payload.split('\n'):
                    if '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            name = parts[0].strip()
                            value = parts[1].strip()
                            if name and value:
                                variables.append(Variable(name=name, type="unknown", value=value))
        
        return variables


class GDBDebuggerManager:
    """Manages multiple GDB debugger sessions."""
    
    def __init__(self):
        self._sessions: Dict[str, GDBDebugger] = {}
    
    def create_session(self, board: Board, config: Optional[GDBServerConfig] = None) -> GDBDebugger:
        """Create a new debug session for a board."""
        if board.board_id in self._sessions:
            raise ValueError(f"Debug session already exists for {board.board_id}")
        
        debugger = GDBDebugger(board, config)
        self._sessions[board.board_id] = debugger
        return debugger
    
    def get_session(self, board_id: str) -> Optional[GDBDebugger]:
        """Get an existing debug session."""
        return self._sessions.get(board_id)
    
    def remove_session(self, board_id: str) -> bool:
        """Remove a debug session."""
        if board_id in self._sessions:
            del self._sessions[board_id]
            return True
        return False
    
    def list_sessions(self) -> Dict[str, GDBSessionState]:
        """List all active sessions and their states."""
        return {board_id: debugger.session_info.state for board_id, debugger in self._sessions.items()}
