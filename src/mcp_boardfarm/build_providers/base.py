"""Build provider interfaces for MCP Board Farm.

This module defines the abstract base classes and data models for the
pluggable build provider system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Set
from pathlib import Path


class BuildStatus(Enum):
    """Status of a build operation."""
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    TIMEOUT = auto()


class BuildProviderType(Enum):
    """Types of build providers."""
    LOCAL = "local"
    DOCKER = "docker"
    REMOTE = "remote"
    SSH = "ssh"


@dataclass
class BuildCapabilities:
    """Capabilities reported by a build provider.
    
    This helps agents understand what a provider can do before
    attempting a build.
    """
    provider_type: BuildProviderType
    supported_frameworks: List[str]
    supported_targets: Dict[str, List[str]]  # framework -> list of targets
    
    # Features
    supports_incremental_builds: bool = True
    supports_parallel_jobs: bool = True
    supports_custom_options: bool = True
    supports_env_injection: bool = False  # Security-sensitive
    
    # Limits
    max_parallel_jobs: int = 1
    max_build_time_seconds: int = 300
    
    # Provider info
    provider_name: str = ""
    provider_version: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "provider_type": self.provider_type.value,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "supported_frameworks": self.supported_frameworks,
            "supported_targets": self.supported_targets,
            "features": {
                "incremental_builds": self.supports_incremental_builds,
                "parallel_jobs": self.supports_parallel_jobs,
                "custom_options": self.supports_custom_options,
                "env_injection": self.supports_env_injection,
            },
            "limits": {
                "max_parallel_jobs": self.max_parallel_jobs,
                "max_build_time_seconds": self.max_build_time_seconds,
            }
        }


@dataclass
class BuildRequest:
    """Request to build firmware.
    
    This is the unified interface for all build providers.
    """
    # Required
    board_id: str
    source_path: str  # Path to source code (file or directory)
    target: str  # e.g., "zephyr/nucleo_h755zi_q", "arduino:avr:nano"
    
    # Optional
    output_path: Optional[str] = None  # Where to place build artifacts
    options: Dict[str, Any] = field(default_factory=dict)  # Framework-specific
    env_vars: Dict[str, str] = field(default_factory=dict)  # Env injection
    
    # Build settings
    build_type: str = "debug"  # debug, release
    clean_build: bool = False
    parallel_jobs: Optional[int] = None
    
    # Metadata
    requested_by: str = "mcp-client"
    request_time: datetime = field(default_factory=datetime.utcnow)
    
    def get_framework(self) -> str:
        """Extract framework from target string.
        
        Target format: "framework/board_or_variant"
        Examples:
            - "zephyr/nucleo_h755zi_q"
            - "arduino:avr:nano"
            - "platformio/stm32h7"
        """
        if "/" in self.target:
            return self.target.split("/")[0]
        elif ":" in self.target:
            return self.target.split(":")[0]
        return "unknown"
    
    def get_board_target(self) -> str:
        """Extract board target from target string."""
        if "/" in self.target:
            return self.target.split("/", 1)[1]
        elif ":" in self.target:
            parts = self.target.split(":")
            return ":".join(parts[1:]) if len(parts) > 1 else self.target
        return self.target


@dataclass
class BuildArtifact:
    """A single build artifact."""
    path: str
    artifact_type: str  # elf, bin, hex, uf2, map, etc.
    size_bytes: int = 0
    
    
@dataclass
class BuildResult:
    """Result of a firmware build."""
    build_id: str
    success: bool
    status: BuildStatus
    
    # Identifiers
    board_id: str = ""
    target: str = ""
    framework: str = ""
    
    # Paths
    build_dir: Optional[str] = None
    artifacts: List[BuildArtifact] = field(default_factory=list)
    
    # Output
    stdout: str = ""
    stderr: str = ""
    
    # Metadata
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Details
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    
    # Provider info
    provider_type: Optional[BuildProviderType] = None
    provider_name: str = ""
    
    def get_main_artifact(self) -> Optional[BuildArtifact]:
        """Get the main firmware artifact (usually ELF)."""
        for artifact in self.artifacts:
            if artifact.artifact_type in ("elf", "bin", "hex", "uf2"):
                return artifact
        return self.artifacts[0] if self.artifacts else None
    
    def get_artifact_by_type(self, artifact_type: str) -> Optional[BuildArtifact]:
        """Get artifact by type."""
        for artifact in self.artifacts:
            if artifact.artifact_type == artifact_type:
                return artifact
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "build_id": self.build_id,
            "success": self.success,
            "status": self.status.name,
            "board_id": self.board_id,
            "target": self.target,
            "framework": self.framework,
            "build_dir": self.build_dir,
            "artifacts": [
                {"path": a.path, "type": a.artifact_type, "size": a.size_bytes}
                for a in self.artifacts
            ],
            "stdout": self.stdout[-2000:] if len(self.stdout) > 2000 else self.stdout,
            "stderr": self.stderr[-1000:] if len(self.stderr) > 1000 else self.stderr,
            "duration_seconds": round(self.duration_seconds, 2),
            "warnings_count": len(self.warnings),
            "errors_count": len(self.errors),
            "error_message": self.error_message,
            "provider": {
                "type": self.provider_type.value if self.provider_type else None,
                "name": self.provider_name,
            } if self.provider_type else None,
        }


@dataclass
class BuildLogEntry:
    """A single build log entry for streaming."""
    timestamp: datetime
    level: str  # DEBUG, INFO, WARN, ERROR
    message: str
    source: str = ""  # Which step produced this log


class BuildProvider(ABC):
    """Abstract base class for build providers.
    
    Implementations must provide:
    1. Asynchronous build execution
    2. Capability reporting
    3. Optional: Log streaming, build status checking
    
    All implementations should handle their own security,
    including path sanitization and input validation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize provider with configuration.
        
        Args:
            config: Provider-specific configuration from boards.yaml
        """
        self.config = config
        self.provider_name = config.get("name", self.__class__.__name__)
        self.provider_version = config.get("version", "1.0.0")
    
    @abstractmethod
    async def build(self, request: BuildRequest) -> BuildResult:
        """Execute a build.
        
        Args:
            request: The build request
            
        Returns:
            BuildResult with full details
            
        Raises:
            BuildError: If build fails catastrophically
            TimeoutError: If build times out
        """
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> BuildCapabilities:
        """Get provider capabilities.
        
        Returns:
            BuildCapabilities describing what this provider can do
        """
        pass
    
    async def get_build_status(self, build_id: str) -> Optional[BuildStatus]:
        """Get status of a running or completed build.
        
        Args:
            build_id: The build identifier
            
        Returns:
            BuildStatus or None if build not found
            
        Default implementation returns None (synchronous builds).
        Override for async build support.
        """
        return None
    
    async def get_build_logs(self, build_id: str, lines: int = 100,
                             offset: int = 0) -> List[BuildLogEntry]:
        """Get build logs.
        
        Args:
            build_id: The build identifier
            lines: Number of lines to return
            offset: Line offset for pagination
            
        Returns:
            List of log entries
            
        Default implementation returns empty list.
        Override for log streaming support.
        """
        return []
    
    async def cancel_build(self, build_id: str) -> bool:
        """Cancel a running build.
        
        Args:
            build_id: The build identifier
            
        Returns:
            True if cancelled, False if not found or already complete
            
        Default implementation returns False.
        Override for async build support.
        """
        return False
    
    async def list_build_targets(self, framework: Optional[str] = None) -> List[str]:
        """List available build targets.
        
        Args:
            framework: Optional framework filter
            
        Returns:
            List of available targets
            
        Default implementation returns capabilities' targets.
        """
        caps = await self.get_capabilities()
        if framework:
            return caps.supported_targets.get(framework, [])
        all_targets = []
        for targets in caps.supported_targets.values():
            all_targets.extend(targets)
        return all_targets
    
    def validate_request(self, request: BuildRequest) -> Optional[str]:
        """Validate a build request before execution.
        
        Args:
            request: The build request to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        # Check required fields
        if not request.board_id:
            return "board_id is required"
        if not request.source_path:
            return "source_path is required"
        if not request.target:
            return "target is required"
        
        # Check target format
        if "/" not in request.target and ":" not in request.target:
            return f"Invalid target format: {request.target}. Expected 'framework/board' or 'framework:variant:board'"
        
        return None


class BuildError(Exception):
    """Exception raised for build-related errors."""
    
    def __init__(self, message: str, build_id: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.build_id = build_id
        self.details = details or {}
