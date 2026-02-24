"""Build system integration for firmware compilation."""

import os
import re
import json
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from .models import Board, BuildConfig, BuildResult

logger = logging.getLogger(__name__)


class ZephyrBuilder:
    """Builder for Zephyr RTOS projects."""
    
    def __init__(self, zephyr_sdk_path: Optional[str] = None, use_docker: bool = True):
        self.zephyr_sdk_path = zephyr_sdk_path or "/opt/zephyr-sdk-0.16.5"
        self.use_docker = use_docker
        self.docker_image = "zephyrprojectrtos/zephyr-build:latest"
        self.cache_dir = Path("./cache/builds")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def build(self, config: BuildConfig) -> BuildResult:
        """Build firmware for a board."""
        import time
        start_time = time.time()
        
        build_id = f"{config.board_id}_{int(start_time)}"
        
        logger.info(f"Starting build {build_id} for {config.board_id}")
        
        try:
            if config.framework == "zephyr":
                result = self._build_zephyr(config, build_id)
            else:
                result = BuildResult(
                    build_id=build_id,
                    success=False,
                    board_id=config.board_id,
                    framework=config.framework,
                    error_message=f"Framework '{config.framework}' not yet supported",
                    duration_seconds=time.time() - start_time
                )
            
            result.duration_seconds = time.time() - start_time
            return result
            
        except Exception as e:
            logger.exception(f"Build {build_id} failed")
            return BuildResult(
                build_id=build_id,
                success=False,
                board_id=config.board_id,
                framework=config.framework,
                error_message=str(e),
                duration_seconds=time.time() - start_time
            )
    
    def _build_zephyr(self, config: BuildConfig, build_id: str) -> BuildResult:
        """Build using Zephyr RTOS."""
        build_dir = self.cache_dir / build_id
        build_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine source to build
        if config.zephyr_sample:
            # Building a Zephyr sample
            source_path = f"/zephyr/zephyr/samples/{config.zephyr_sample}"
        elif config.source_path:
            source_path = config.source_path
        else:
            return BuildResult(
                build_id=build_id,
                success=False,
                board_id=config.board_id,
                framework="zephyr",
                error_message="No source path or Zephyr sample specified"
            )
        
        # Determine board name
        board_name = config.zephyr_board or config.board_id
        
        stdout_lines = []
        stderr_lines = []
        
        if self.use_docker:
            # Build using Docker
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{build_dir}:/build",
                "-e", f"BOARD={board_name}",
                self.docker_image,
                "west", "build",
                "-b", board_name,
                "-d", "/build",
                source_path
            ]
        else:
            # Build natively (requires Zephyr SDK installed)
            cmd = [
                "west", "build",
                "-b", board_name,
                "-d", str(build_dir),
                source_path
            ]
        
        logger.info(f"Running build command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=str(build_dir) if not self.use_docker else None
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            # Check for build artifacts
            elf_path = build_dir / "zephyr" / "zephyr.elf"
            bin_path = build_dir / "zephyr" / "zephyr.bin"
            hex_path = build_dir / "zephyr" / "zephyr.hex"
            
            success = result.returncode == 0 and elf_path.exists()
            
            return BuildResult(
                build_id=build_id,
                success=success,
                board_id=board_name,
                framework="zephyr",
                build_dir=str(build_dir),
                elf_path=str(elf_path) if elf_path.exists() else None,
                bin_path=str(bin_path) if bin_path.exists() else None,
                hex_path=str(hex_path) if hex_path.exists() else None,
                stdout=stdout,
                stderr=stderr,
                error_message=stderr if not success and stderr else None
            )
            
        except subprocess.TimeoutExpired:
            return BuildResult(
                build_id=build_id,
                success=False,
                board_id=board_name,
                framework="zephyr",
                error_message="Build timed out after 5 minutes",
                stdout="",
                stderr="Build process exceeded 300 second timeout"
            )
        except FileNotFoundError as e:
            return BuildResult(
                build_id=build_id,
                success=False,
                board_id=board_name,
                framework="zephyr",
                error_message=f"Build command not found: {e}. Is Docker or Zephyr SDK installed?",
                stdout="",
                stderr=str(e)
            )


class MockBuilder:
    """Mock builder for testing without actual build capability."""
    
    def __init__(self):
        self.cache_dir = Path("./cache/builds")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def build(self, config: BuildConfig) -> BuildResult:
        """Simulate a build."""
        import time
        import uuid
        
        start_time = time.time()
        build_id = f"mock_{int(start_time)}_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"[MOCK] Building {build_id} for {config.board_id}")
        
        # Simulate build time
        time.sleep(0.5)
        
        # Create mock build artifacts
        build_dir = self.cache_dir / build_id
        build_dir.mkdir(parents=True, exist_ok=True)
        zephyr_dir = build_dir / "zephyr"
        zephyr_dir.mkdir(exist_ok=True)
        
        # Create dummy files
        (zephyr_dir / "zephyr.elf").write_text("MOCK ELF FILE")
        (zephyr_dir / "zephyr.bin").write_bytes(b"\x00\x01\x02\x03")
        (zephyr_dir / "zephyr.hex").write_text(":00000001FF")
        
        duration = time.time() - start_time
        
        return BuildResult(
            build_id=build_id,
            success=True,
            board_id=config.board_id,
            framework=config.framework,
            build_dir=str(build_dir),
            elf_path=str(zephyr_dir / "zephyr.elf"),
            bin_path=str(zephyr_dir / "zephyr.bin"),
            hex_path=str(zephyr_dir / "zephyr.hex"),
            stdout=f"[MOCK] Build completed successfully in {duration:.2f}s",
            stderr="",
            duration_seconds=duration
        )