"""Data models for GDB debugging."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, List, Any, Union
from datetime import datetime


class GDBSessionState(Enum):
    """GDB debug session states."""
    IDLE = auto()      # Session created but not started
    CONNECTING = auto()  # Connecting to target
    RUNNING = auto()   # Target is running
    PAUSED = auto()    # Target is halted/breakpoint
    ERROR = auto()     # Error state
    DISCONNECTED = auto()  # Session ended


class StepType(Enum):
    """Types of step operations."""
    INTO = "into"      # Step into function calls
    OVER = "over"      # Step over function calls
    OUT = "out"        # Step out of current function
    INSTRUCTION = "instruction"  # Single instruction step


@dataclass
class Register:
    """Represents a CPU register."""
    name: str
    value: int
    size: int = 32  # bits
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": f"0x{self.value:08x}" if self.size >= 32 else f"0x{self.value:04x}",
            "value_dec": self.value,
            "size_bits": self.size
        }


@dataclass
class StackFrame:
    """Represents a stack frame (call stack entry)."""
    level: int
    function: str
    file: Optional[str] = None
    line: Optional[int] = None
    pc: Optional[int] = None  # Program counter
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "level": self.level,
            "function": self.function,
        }
        if self.file:
            result["file"] = self.file
        if self.line:
            result["line"] = self.line
        if self.pc is not None:
            result["pc"] = f"0x{self.pc:08x}"
        return result


@dataclass
class Breakpoint:
    """Represents a GDB breakpoint."""
    id: int
    type: str  # "breakpoint", "watchpoint", "catchpoint"
    location: str  # File:line, function name, or address
    enabled: bool = True
    hits: int = 0
    
    # Optional details
    file: Optional[str] = None
    line: Optional[int] = None
    function: Optional[str] = None
    address: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "type": self.type,
            "location": self.location,
            "enabled": self.enabled,
            "hits": self.hits
        }
        if self.file:
            result["file"] = self.file
        if self.line:
            result["line"] = self.line
        if self.function:
            result["function"] = self.function
        if self.address is not None:
            result["address"] = f"0x{self.address:08x}"
        return result


@dataclass
class MemoryRegion:
    """Represents a region of memory."""
    address: int
    size: int
    data: bytes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": f"0x{self.address:08x}",
            "size": self.size,
            "hex": self.data.hex(),
            "ascii": self._to_ascii()
        }
    
    def _to_ascii(self) -> str:
        """Convert bytes to printable ASCII representation."""
        return ''.join(chr(b) if 32 <= b < 127 else '.' for b in self.data)


@dataclass
class Variable:
    """Represents a variable (local or global)."""
    name: str
    type: str
    value: str
    address: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type,
            "value": self.value
        }
        if self.address is not None:
            result["address"] = f"0x{self.address:08x}"
        return result


@dataclass
class GDBSessionInfo:
    """Information about a GDB debug session."""
    board_id: str
    state: GDBSessionState
    gdb_port: int
    target_arch: Optional[str] = None
    target_mcu: Optional[str] = None
    
    # Session metadata
    created_at: datetime = field(default_factory=datetime.now)
    connected_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    
    # Current execution context (when paused)
    current_file: Optional[str] = None
    current_line: Optional[int] = None
    current_function: Optional[str] = None
    current_pc: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "board_id": self.board_id,
            "state": self.state.name,
            "gdb_port": self.gdb_port,
            "target_arch": self.target_arch,
            "target_mcu": self.target_mcu,
            "created_at": self.created_at.isoformat(),
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "current_context": {
                "file": self.current_file,
                "line": self.current_line,
                "function": self.current_function,
                "pc": f"0x{self.current_pc:08x}" if self.current_pc else None
            } if self.state == GDBSessionState.PAUSED else None
        }


@dataclass
class DebugOperationResult:
    """Result of a debug operation."""
    success: bool
    operation: str
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "operation": self.operation,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2)
        }
        if self.data:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class GDBServerConfig:
    """Configuration for GDB server (pyocd)."""
    host: str = "localhost"
    gdb_port: int = 3333  # Default GDB port
    telnet_port: int = 4444  # pyocd telnet port
    
    # pyocd specific options
    probe_uid: Optional[str] = None  # Probe serial number
    target: Optional[str] = None  # Target override
    frequency: int = 1000000  # SWD/JTAG frequency in Hz
    
    # Additional arguments
    extra_args: List[str] = field(default_factory=list)
