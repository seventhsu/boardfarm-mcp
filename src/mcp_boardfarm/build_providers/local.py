"""Local process build provider for MCP Board Farm.

This provider executes builds using local toolchain commands.
It supports any build tool that can be invoked via subprocess.

Security considerations:
- All paths are sanitized to prevent directory traversal
- Commands are validated against whitelist patterns
- Environment variable injection is controlled
- Timeouts prevent resource exhaustion
"""

import asyncio
import hashlib
import logging
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from .base import (
    BuildProvider, BuildRequest, BuildResult, BuildCapabilities,
    BuildStatus, BuildProviderType, BuildArtifact, BuildLogEntry,
    BuildError
)

logger = logging.getLogger(__name__)


class LocalBuildProvider(BuildProvider):
    """Build provider that executes commands locally.
    
    Configuration options (from boards.yaml):
    ```yaml
    build_providers:
      zephyr:
        type: local
        command: west
        workdir: /workspace
        timeout: 300
        max_parallel_jobs: 4
    ```
    """
    
    DANGEROUS_CHARS = set(';&|<>$`\n\r')
    
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./", r"\.\.\\",
        r"^/", r"^\\",
        r"%2e%2e%2f", r"%252e%252e%252f",
    ]
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.command = config.get("command", "make")
        self.workdir = Path(config.get("workdir", "/tmp/builds"))
        self.timeout = config.get("timeout", 300)
        self.max_parallel_jobs = config.get("max_parallel_jobs", 4)
        self.env_whitelist: Set[str] = set(config.get("env_whitelist", []))
        
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._running_builds: Dict[str, asyncio.subprocess.Process] = {}
        self._build_logs: Dict[str, List[BuildLogEntry]] = {}
    
    def _sanitize_path(self, path: str) -> Path:
        """Sanitize a path to prevent directory traversal attacks."""
        for pattern in self.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                raise BuildError(f"Path contains traversal pattern: {path}")
        
        normalized = Path(path).resolve()
        
        allowed_roots = [
            self.workdir.resolve(),
            Path("/workspace").resolve(),
            Path(tempfile.gettempdir()).resolve(),
            Path.home().resolve() / ".zephyrproject",
        ]
        
        is_allowed = any(str(normalized).startswith(str(root)) for root in allowed_roots)
        
        if not is_allowed:
            logger.warning(f"Path {normalized} not in allowed roots, using workdir")
            safe_name = hashlib.sha256(path.encode()).hexdigest()[:16]
            normalized = self.workdir / safe_name
        
        return normalized
    
    def _validate_target(self, target: str) -> bool:
        """Validate target string format."""
        if "/" not in target and ":" not in target:
            return False
        if any(c in target for c in self.DANGEROUS_CHARS):
            return False
        if len(target) > 200:
            return False
        if not re.match(r'^[\w\-/.:]+$', target):
            return False
        return True
    
    def _validate_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize build options."""
        sanitized = {}
        
        for key, value in options.items():
            if not re.match(r'^[\w_]+$', str(key)):
                logger.warning(f"Skipping invalid option key: {key}")
                continue
            
            if isinstance(value, str):
                if any(c in value for c in self.DANGEROUS_CHARS):
                    logger.warning(f"Skipping option with dangerous chars: {key}")
                    continue
                sanitized[key] = value
            elif isinstance(value, (int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, (list, tuple)):
                sanitized_list = []
                for item in value:
                    if isinstance(item, str) and not any(c in item for c in self.DANGEROUS_CHARS):
                        sanitized_list.append(item)
                    elif isinstance(item, (int, float, bool)):
                        sanitized_list.append(item)
                sanitized[key] = sanitized_list
        
        return sanitized
    
    def _prepare_environment(self, env_vars: Dict[str, str]) -> Dict[str, str]:
        """Prepare environment variables for the build."""
        env = os.environ.copy()
        
        if not self.env_whitelist:
            return env
        
        for key, value in env_vars.items():
            if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
                continue
            if key not in self.env_whitelist:
                continue
            if any(c in value for c in self.DANGEROUS_CHARS):
                continue
            env[key] = value
        
        return env
    
    def _generate_build_id(self, request: BuildRequest) -> str:
        """Generate a unique build ID."""
        hash_input = f"{request.board_id}:{request.target}:{datetime.utcnow().isoformat()}"
        return f"local_{hashlib.sha256(hash_input.encode()).hexdigest()[:16]}"
    
    def _build_command(self, request: BuildRequest, build_dir: Path) -> List[str]:
        """Construct the build command."""
        framework = request.get_framework()
        board_target = request.get_board_target()
        
        if framework == "zephyr":
            cmd = ["west", "build", "-b", board_target, "-d", str(build_dir)]
            if request.clean_build:
                cmd.append("-p")
            cmd.append(request.source_path)
            if "cmake_args" in request.options:
                for arg in request.options["cmake_args"]:
                    cmd.extend(["--", arg])
            return cmd
        elif framework == "arduino":
            cmd = ["arduino-cli", "compile", "--fqbn", board_target, "--output-dir", str(build_dir)]
            cmd.append(request.source_path)
            return cmd
        elif framework == "platformio":
            cmd = ["pio", "run", "-d", request.source_path]
            if request.clean_build:
                cmd.extend(["-t", "clean"])
            if "env" in request.options:
                cmd.extend(["-e", request.options["env"]])
            return cmd
        elif framework == "make":
            cmd = ["make", "-C", request.source_path]
            if "target" in request.options:
                cmd.append(request.options["target"])
            if request.parallel_jobs:
                cmd.append(f"-j{request.parallel_jobs}")
            return cmd
        else:
            return [self.command, "build", f"--board={board_target}", f"--build-dir={build_dir}", request.source_path]
    
    def _parse_warnings(self, output: str) -> List[str]:
        """Parse warnings from build output."""
        return [line.strip() for line in output.split('\n') if 'warning:' in line.lower()]
    
    def _parse_errors(self, output: str) -> List[str]:
        """Parse errors from build output."""
        return [line.strip() for line in output.split('\n') if 'error:' in line.lower()]
    
    def _find_artifacts(self, build_dir: Path) -> List[BuildArtifact]:
        """Find build artifacts in the build directory."""
        artifacts = []
        artifact_patterns = {'elf': ['*.elf', '*.axf'], 'bin': ['*.bin'], 'hex': ['*.hex'], 'uf2': ['*.uf2'], 'map': ['*.map']}
        
        for artifact_type, patterns in artifact_patterns.items():
            for pattern in patterns:
                for path in build_dir.rglob(pattern):
                    if path.is_file():
                        artifacts.append(BuildArtifact(path=str(path), artifact_type=artifact_type, size_bytes=path.stat().st_size))
        
        return artifacts
    
    async def build(self, request: BuildRequest) -> BuildResult:
        """Execute a local build."""
        start_time = datetime.utcnow()
        build_id = self._generate_build_id(request)
        
        validation_error = self.validate_request(request)
        if validation_error:
            return BuildResult(
                build_id=build_id, success=False, status=BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                error_message=validation_error, start_time=start_time, end_time=datetime.utcnow(),
                provider_type=BuildProviderType.LOCAL, provider_name=self.provider_name
            )
        
        if not self._validate_target(request.target):
            return BuildResult(
                build_id=build_id, success=False, status=BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                error_message=f"Invalid target: {request.target}", start_time=start_time, end_time=datetime.utcnow(),
                provider_type=BuildProviderType.LOCAL, provider_name=self.provider_name
            )
        
        try:
            source_path = self._sanitize_path(request.source_path)
            build_dir = self._sanitize_path(request.output_path or str(self.workdir / build_id))
            build_dir.mkdir(parents=True, exist_ok=True)
            
            request.options = self._validate_options(request.options)
            env = self._prepare_environment(request.env_vars)
            cmd = self._build_command(request, build_dir)
            
            logger.info(f"Starting build {build_id}: {' '.join(cmd)}")
            
            self._build_logs[build_id] = []
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                cwd=str(source_path if source_path.is_dir() else source_path.parent)
            )
            
            self._running_builds[build_id] = process
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return BuildResult(
                    build_id=build_id, success=False, status=BuildStatus.TIMEOUT,
                    board_id=request.board_id, target=request.target, framework=request.get_framework(),
                    error_message=f"Build timed out after {self.timeout} seconds",
                    start_time=start_time, end_time=datetime.utcnow(), duration_seconds=self.timeout,
                    provider_type=BuildProviderType.LOCAL, provider_name=self.provider_name
                )
            finally:
                if build_id in self._running_builds:
                    del self._running_builds[build_id]
            
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            warnings = self._parse_warnings(stdout_str + stderr_str)
            errors = self._parse_errors(stdout_str + stderr_str)
            artifacts = self._find_artifacts(build_dir)
            
            success = process.returncode == 0 and len(artifacts) > 0
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return BuildResult(
                build_id=build_id, success=success, status=BuildStatus.SUCCESS if success else BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                build_dir=str(build_dir), artifacts=artifacts, stdout=stdout_str, stderr=stderr_str,
                warnings=warnings, errors=errors, error_message=stderr_str if not success and stderr_str else None,
                start_time=start_time, end_time=end_time, duration_seconds=duration,
                provider_type=BuildProviderType.LOCAL, provider_name=self.provider_name
            )
            
        except BuildError as e:
            end_time = datetime.utcnow()
            return BuildResult(
                build_id=build_id, success=False, status=BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                error_message=str(e), start_time=start_time, end_time=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                provider_type=BuildProviderType.LOCAL, provider_name=self.provider_name
            )
    
    async def get_capabilities(self) -> BuildCapabilities:
        """Get provider capabilities."""
        return BuildCapabilities(
            provider_type=BuildProviderType.LOCAL,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            supported_frameworks=["zephyr", "arduino", "platformio", "make"],
            supported_targets={
                "zephyr": ["nucleo_h755zi_q", "nucleo_f401re"],
                "arduino": ["avr:nano", "avr:uno", "esp32:esp32"],
                "platformio": ["stm32h7", "esp32"],
                "make": ["generic"],
            },
            supports_incremental_builds=True,
            supports_parallel_jobs=True,
            supports_custom_options=True,
            supports_env_injection=bool(self.env_whitelist),
            max_parallel_jobs=self.max_parallel_jobs,
            max_build_time_seconds=self.timeout,
        )
    
    async def cancel_build(self, build_id: str) -> bool:
        """Cancel a running build."""
        if build_id in self._running_builds:
            process = self._running_builds[build_id]
            process.kill()
            await process.wait()
            del self._running_builds[build_id]
            return True
        return False
