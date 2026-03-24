"""Docker container build provider for MCP Board Farm.

This provider executes builds inside Docker containers.
Provides full isolation and reproducible builds.

Security considerations:
- Container isolation provides sandboxing
- No host filesystem access except mounted volumes
- Resource limits (CPU, memory) can be applied
- Network isolation options
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base import (
    BuildProvider, BuildRequest, BuildResult, BuildCapabilities,
    BuildStatus, BuildProviderType, BuildArtifact, BuildLogEntry,
    BuildError
)

logger = logging.getLogger(__name__)


class DockerBuildProvider(BuildProvider):
    """Build provider that executes builds in Docker containers."""
    
    DANGEROUS_CHARS = set(';&|<>$`\n\r')
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.image = config.get("image", "zephyrprojectrtos/zephyr-build:latest")
        self.workdir = config.get("workdir", "/workspace")
        self.timeout = config.get("timeout", 600)
        self.network_mode = config.get("network_mode", "bridge")
        self.memory_limit = config.get("memory_limit", None)
        self.cpu_limit = config.get("cpu_limit", None)
        self.privileged = config.get("privileged", False)
        self.volumes = config.get("volumes", [])
        self.env = config.get("env", {})
        self.host_workdir = Path(config.get("host_workdir", "/tmp/docker-builds"))
        
        self.host_workdir.mkdir(parents=True, exist_ok=True)
        self._running_containers: Dict[str, str] = {}
    
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
    
    def _generate_build_id(self, request: BuildRequest) -> str:
        """Generate a unique build ID."""
        hash_input = f"{request.board_id}:{request.target}:{datetime.utcnow().isoformat()}"
        return f"docker_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"
    
    def _generate_container_name(self, build_id: str) -> str:
        """Generate a container name from build ID."""
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', build_id)
        return f"mcp-build-{safe_name}"
    
    def _build_docker_command(self, request: BuildRequest, 
                              host_build_dir: Path, container_build_dir: str) -> List[str]:
        """Build the docker run command."""
        cmd = ["docker", "run", "--rm"]
        
        build_id = self._generate_build_id(request)
        container_name = self._generate_container_name(build_id)
        cmd.extend(["--name", container_name])
        
        if self.network_mode:
            cmd.extend(["--network", self.network_mode])
        
        if self.memory_limit:
            cmd.extend(["--memory", self.memory_limit])
        if self.cpu_limit:
            cmd.extend(["--cpus", str(self.cpu_limit)])
        
        if self.privileged:
            cmd.append("--privileged")
        
        cmd.extend(["-w", self.workdir])
        cmd.extend(["-v", f"{host_build_dir}:{container_build_dir}"])
        
        source_path = Path(request.source_path)
        if source_path.exists():
            container_source = f"{self.workdir}/source"
            cmd.extend(["-v", f"{source_path.resolve()}:{container_source}:ro"])
        
        for vol in self.volumes:
            cmd.extend(["-v", vol])
        
        for key, value in self.env.items():
            cmd.extend(["-e", f"{key}={value}"])
        
        for key, value in request.env_vars.items():
            if re.match(r'^[A-Z_][A-Z0-9_]*$', key):
                if not any(c in value for c in self.DANGEROUS_CHARS):
                    cmd.extend(["-e", f"{key}={value}"])
        
        cmd.append(self.image)
        
        framework = request.get_framework()
        board_target = request.get_board_target()
        
        if framework == "zephyr":
            build_cmd = self._build_zephyr_command(request, container_build_dir, board_target)
        elif framework == "arduino":
            build_cmd = self._build_arduino_command(request, container_build_dir, board_target)
        elif framework == "platformio":
            build_cmd = self._build_platformio_command(request, container_build_dir, board_target)
        else:
            build_cmd = ["sh", "-c", f"echo 'Framework {framework} not configured' && exit 1"]
        
        cmd.extend(build_cmd)
        return cmd
    
    def _build_zephyr_command(self, request: BuildRequest, build_dir: str, board: str) -> List[str]:
        """Build command for Zephyr/west inside container with workspace init."""
        cmd = ["sh", "-c"]
        
        # Properly initialize Zephyr workspace and build
        shell_cmd = f"""
        set -e
        export ZEPHYR_BASE=/workspace/zephyr
        export PATH=$PATH:/root/.local/bin
        
        # Initialize workspace if needed
        if [ ! -d /workspace/zephyr/.git ]; then
            cd /workspace
            west init -m https://github.com/zephyrproject-rtos/zephyr.git --mr v3.7.0
            west update --narrow -o=--depth=1 2>&1 | tail -20
        fi
        
        # Determine source path
        if [ -d "{request.source_path}" ]; then
            SOURCE="{request.source_path}"
        elif [ -d "/workspace/zephyr/{request.source_path}" ]; then
            SOURCE="/workspace/zephyr/{request.source_path}"
        elif [ -d "/workspace/zephyr/samples/{request.source_path}" ]; then
            SOURCE="/workspace/zephyr/samples/{request.source_path}"
        else
            SOURCE="/workspace/zephyr/samples/basic/blinky"
        fi
        
        # Build
        cd /workspace
        west build -b {board} -d {build_dir} $SOURCE 2>&1
        """
        
        cmd.append(shell_cmd)
        return cmd
    
    def _build_arduino_command(self, request: BuildRequest, build_dir: str, board: str) -> List[str]:
        """Build command for Arduino CLI inside container."""
        return ["arduino-cli", "compile", "--fqbn", board, "--output-dir", build_dir, f"{self.workdir}/source"]
    
    def _build_platformio_command(self, request: BuildRequest, build_dir: str, board: str) -> List[str]:
        """Build command for PlatformIO inside container."""
        cmd = ["pio", "run", "-d", f"{self.workdir}/source"]
        if request.clean_build:
            cmd.extend(["-t", "clean"])
        if "env" in request.options:
            cmd.extend(["-e", request.options["env"]])
        return cmd
    
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
        """Execute a build in a Docker container."""
        start_time = datetime.utcnow()
        build_id = self._generate_build_id(request)
        
        validation_error = self.validate_request(request)
        if validation_error:
            return BuildResult(
                build_id=build_id, success=False, status=BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                error_message=validation_error, start_time=start_time, end_time=datetime.utcnow(),
                provider_type=BuildProviderType.DOCKER, provider_name=self.provider_name
            )
        
        if not self._validate_target(request.target):
            return BuildResult(
                build_id=build_id, success=False, status=BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                error_message=f"Invalid target: {request.target}", start_time=start_time, end_time=datetime.utcnow(),
                provider_type=BuildProviderType.DOCKER, provider_name=self.provider_name
            )
        
        try:
            host_build_dir = self.host_workdir / build_id
            host_build_dir.mkdir(parents=True, exist_ok=True)
            container_build_dir = f"{self.workdir}/build"
            
            cmd = self._build_docker_command(request, host_build_dir, container_build_dir)
            
            logger.info(f"Starting Docker build {build_id}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            self._running_containers[build_id] = self._generate_container_name(build_id)
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError:
                await self._kill_container(build_id)
                return BuildResult(
                    build_id=build_id, success=False, status=BuildStatus.TIMEOUT,
                    board_id=request.board_id, target=request.target, framework=request.get_framework(),
                    error_message=f"Build timed out after {self.timeout} seconds",
                    start_time=start_time, end_time=datetime.utcnow(), duration_seconds=self.timeout,
                    provider_type=BuildProviderType.DOCKER, provider_name=self.provider_name
                )
            finally:
                if build_id in self._running_containers:
                    del self._running_containers[build_id]
            
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            warnings = [line.strip() for line in (stdout_str + stderr_str).split('\n') if 'warning:' in line.lower()]
            errors = [line.strip() for line in (stdout_str + stderr_str).split('\n') if 'error:' in line.lower()]
            artifacts = self._find_artifacts(host_build_dir)
            
            success = process.returncode == 0 and len(artifacts) > 0
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return BuildResult(
                build_id=build_id, success=success, status=BuildStatus.SUCCESS if success else BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                build_dir=str(host_build_dir), artifacts=artifacts, stdout=stdout_str, stderr=stderr_str,
                warnings=warnings, errors=errors, error_message=stderr_str if not success and stderr_str else None,
                start_time=start_time, end_time=end_time, duration_seconds=duration,
                provider_type=BuildProviderType.DOCKER, provider_name=self.provider_name
            )
            
        except Exception as e:
            end_time = datetime.utcnow()
            logger.exception(f"Docker build {build_id} failed")
            return BuildResult(
                build_id=build_id, success=False, status=BuildStatus.FAILED,
                board_id=request.board_id, target=request.target, framework=request.get_framework(),
                error_message=str(e), start_time=start_time, end_time=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                provider_type=BuildProviderType.DOCKER, provider_name=self.provider_name
            )
    
    async def _kill_container(self, build_id: str):
        """Kill a running container."""
        if build_id in self._running_containers:
            container_name = self._running_containers[build_id]
            try:
                kill_proc = await asyncio.create_subprocess_exec(
                    "docker", "kill", container_name,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                await asyncio.wait_for(kill_proc.wait(), timeout=10)
            except Exception as e:
                logger.warning(f"Failed to kill container {container_name}: {e}")
    
    async def get_capabilities(self) -> BuildCapabilities:
        """Get provider capabilities."""
        docker_available = await self._check_docker_available()
        
        return BuildCapabilities(
            provider_type=BuildProviderType.DOCKER,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            supported_frameworks=["zephyr", "arduino", "platformio"] if docker_available else [],
            supported_targets={
                "zephyr": ["nucleo_h755zi_q", "nucleo_f401re", "stm32h7"],
                "arduino": ["avr:nano", "avr:uno", "esp32:esp32"],
                "platformio": ["stm32h7", "esp32"],
            } if docker_available else {},
            supports_incremental_builds=True,
            supports_parallel_jobs=True,
            supports_custom_options=True,
            supports_env_injection=True,
            max_parallel_jobs=4,
            max_build_time_seconds=self.timeout,
        )
    
    async def _check_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "version",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            return proc.returncode == 0
        except Exception:
            return False
    
    async def cancel_build(self, build_id: str) -> bool:
        """Cancel a running build by killing its container."""
        await self._kill_container(build_id)
        return build_id in self._running_containers
