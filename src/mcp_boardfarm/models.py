"""Data models for MCP Board Farm."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, List, Any
from datetime import datetime


class BoardState(Enum):
    """Board state machine states."""
    OFFLINE = auto()
    AVAILABLE = auto()
    RESERVED = auto()
    BUILDING = auto()
    FLASHING = auto()
    RUNNING = auto()
    TESTING = auto()
    ERROR = auto()


@dataclass
class DebuggerConfig:
    """Debugger configuration."""
    type: str = "cmsis-dap"  # cmsis-dap, stlink, jlink
    transport: str = "swd"   # swd, jtag
    interface_cfg: Optional[str] = None  # OpenOCD interface config
    target_cfg: Optional[str] = None      # OpenOCD target config


@dataclass
class SerialConfig:
    """Serial port configuration."""
    port: str = "/dev/ttyACM0"
    baud: int = 115200
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "N"


@dataclass
class ZephyrConfig:
    """Zephyr-specific configuration."""
    board_name: str = ""
    soc: Optional[str] = None
    sysbuild: bool = False


@dataclass
class Board:
    """Represents a connected development board."""
    board_id: str
    type: str  # stm32, esp32, nordic, etc.
    model: str
    mcu: str
    description: str = ""
    
    # Memory specs (KB)
    flash_size: int = 512
    ram_size: int = 96
    
    # Configuration
    debugger: DebuggerConfig = field(default_factory=DebuggerConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    zephyr: Optional[ZephyrConfig] = None
    
    # Capabilities
    supported_frameworks: List[str] = field(default_factory=list)
    
    # Feature-based matching support
    features: List[str] = field(default_factory=list)  # e.g., ["ethernet", "can", "sd_card"]
    capabilities: Dict[str, Any] = field(default_factory=dict)  # e.g., {"ram_kb": 1024, "flash_kb": 2048}
    
    # Runtime state
    status: BoardState = BoardState.OFFLINE
    reserved_by: Optional[str] = None
    reserved_until: Optional[datetime] = None
    current_firmware: Optional[str] = None
    last_seen: Optional[datetime] = None
    
    # Dynamic info (populated at runtime)
    usb_path: Optional[str] = None
    serial_number: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert board to dictionary for JSON serialization."""
        return {
            "board_id": self.board_id,
            "type": self.type,
            "model": self.model,
            "mcu": self.mcu,
            "description": self.description,
            "flash_size_kb": self.flash_size,
            "ram_size_kb": self.ram_size,
            "features": self.features,
            "capabilities": self.capabilities,
            "debugger": {
                "type": self.debugger.type,
                "transport": self.debugger.transport,
            },
            "serial": {
                "port": self.serial.port,
                "baud": self.serial.baud,
            },
            "supported_frameworks": self.supported_frameworks,
            "status": self.status.name.lower(),
            "reserved_by": self.reserved_by,
            "current_firmware": self.current_firmware,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }
    
    def get_features_set(self) -> set:
        """Get features as a set for matching."""
        return set(self.features)
    
    def get_capabilities_dict(self) -> Dict[str, Any]:
        """Get capabilities dict with defaults from flash/ram sizes."""
        caps = dict(self.capabilities)
        # Ensure ram_kb and flash_kb are always present
        if "ram_kb" not in caps:
            caps["ram_kb"] = self.ram_size
        if "flash_kb" not in caps:
            caps["flash_kb"] = self.flash_size
        return caps


@dataclass
class BuildConfig:
    """Build configuration for firmware."""
    framework: str = "zephyr"  # zephyr, arduino, stm32cube
    board_id: str = ""
    source_path: str = ""
    build_type: str = "debug"  # debug, release
    
    # Zephyr-specific
    zephyr_board: Optional[str] = None
    zephyr_sample: Optional[str] = None  # e.g., "hello_world"
    
    # Build options
    extra_cmake_args: List[str] = field(default_factory=list)
    extra_make_args: List[str] = field(default_factory=list)
    
    # Output
    output_name: Optional[str] = None


@dataclass
class BuildResult:
    """Result of a firmware build."""
    build_id: str
    success: bool
    board_id: str
    framework: str
    
    # Paths
    build_dir: Optional[str] = None
    elf_path: Optional[str] = None
    bin_path: Optional[str] = None
    hex_path: Optional[str] = None
    
    # Output
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    
    # Errors
    error_message: Optional[str] = None


@dataclass
class FlashResult:
    """Result of flashing firmware to a board."""
    success: bool
    board_id: str
    build_id: str
    
    # Flash info
    bytes_written: int = 0
    verify_passed: bool = False
    
    # Output
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    
    # Errors
    error_message: Optional[str] = None


@dataclass
class LogEntry:
    """A single log entry from serial output."""
    timestamp: datetime
    board_id: str
    level: str  # DEBUG, INFO, WARN, ERROR
    message: str
    raw_bytes: Optional[bytes] = None


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "127.0.0.1"
    port: int = 8080
    
    # Limits
    max_concurrent_builds: int = 2
    max_build_time_seconds: int = 300
    default_board_timeout_minutes: int = 30
    
    # Paths
    log_dir: str = "./logs"
    cache_dir: str = "./cache"
    
    # Security (MVP: disabled)
    auth_required: bool = False
    api_key: Optional[str] = None
    
    # Logging
    log_level: str = "INFO"