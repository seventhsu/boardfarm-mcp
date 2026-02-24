"""Build system integration for firmware compilation.

This module provides the high-level BuildManager that coordinates
builds across multiple providers. It replaces the old hardcoded
ZephyrBuilder with a flexible, provider-based system.
"""

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from .models import BuildConfig, BuildResult
from .build_providers import (
    BuildProviderFactory, BuildRequest, BuildProviderType,
    BuildStatus
)

logger = logging.getLogger(__name__)


class BuildManager:
    """Manages firmware builds across multiple providers.
    
    This class replaces the old ZephyrBuilder with a flexible
    provider-based system that supports:
    - Local builds (west, arduino-cli, platformio, make)
    - Docker container builds
    - Remote build servers
    
    Configuration is loaded from boards.yaml build_providers section.
    
    Example:
        build_providers:
          zephyr:
            type: docker
            image: zephyrprojectrtos/zephyr-build:latest
          
          arduino:
            type: local
            command: arduino-cli
            timeout: 120
    """
    
    def __init__(self, providers_config: Optional[Dict[str, Any]] = None):
        """Initialize the build manager.
        
        Args:
            providers_config: Dict mapping framework names to provider configs.
                            If None, uses default configuration.
        """
        self.providers_config = providers_config or {}
        self._providers: Dict[str, Any] = {}  # framework -> provider instance
        self._default_provider_config = {
            "type": "docker",
            "image": "zephyrprojectrtos/zephyr-build:latest",
            "timeout": 300,
        }
    
    def _get_provider(self, framework: str):
        """Get or create provider for a framework.
        
        Args:
            framework: Framework name (zephyr, arduino, etc.)
            
        Returns:
            BuildProvider instance
        """
        if framework not in self._providers:
            # Get config for this framework
            config = self.providers_config.get(framework, self._default_provider_config)
            
            # Create provider
            try:
                provider = BuildProviderFactory.create(config)
                self._providers[framework] = provider
                logger.info(f"Created {config.get('type', 'local')} provider for {framework}")
            except Exception as e:
                logger.error(f"Failed to create provider for {framework}: {e}")
                # Fall back to local provider
                config = {"type": "local", "command": "make"}
                provider = BuildProviderFactory.create(config)
                self._providers[framework] = provider
        
        return self._providers[framework]
    
    async def build(self, config: BuildConfig) -> BuildResult:
        """Build firmware using appropriate provider.
        
        Args:
            config: Build configuration
            
        Returns:
            BuildResult with artifacts and status
        """
        framework = config.framework or "zephyr"
        provider = self._get_provider(framework)
        
        # Convert old BuildConfig to new BuildRequest
        request = self._convert_config_to_request(config)
        
        logger.info(f"Starting {framework} build for {config.board_id} using {provider.provider_name}")
        
        try:
            result = await provider.build(request)
            return self._convert_result_to_model(result)
        except Exception as e:
            logger.exception(f"Build failed for {config.board_id}")
            import time
            return BuildResult(
                build_id=f"error_{int(time.time())}",
                success=False,
                board_id=config.board_id,
                framework=framework,
                error_message=str(e),
                duration_seconds=0
            )
    
    def _convert_config_to_request(self, config: BuildConfig) -> BuildRequest:
        """Convert old BuildConfig to new BuildRequest.
        
        This maintains backward compatibility with existing code.
        """
        # Determine target string
        if config.zephyr_board:
            target = f"zephyr/{config.zephyr_board}"
        else:
            target = f"{config.framework}/{config.board_id}"
        
        # Determine source path
        if config.zephyr_sample:
            source_path = f"zephyr/samples/{config.zephyr_sample}"
        else:
            source_path = config.source_path or "."
        
        # Build options
        options = {}
        if config.extra_cmake_args:
            options["cmake_args"] = config.extra_cmake_args
        if config.extra_make_args:
            options["make_args"] = config.extra_make_args
        
        return BuildRequest(
            board_id=config.board_id,
            source_path=source_path,
            target=target,
            build_type=config.build_type,
            options=options,
            clean_build=False,  # Could add to BuildConfig
        )
    
    def _convert_result_to_model(self, result) -> BuildResult:
        """Convert new BuildResult to old BuildResult model."""
        # Get main artifact paths
        elf_path = None
        bin_path = None
        hex_path = None
        
        for artifact in result.artifacts:
            if artifact.artifact_type == "elf":
                elf_path = artifact.path
            elif artifact.artifact_type == "bin":
                bin_path = artifact.path
            elif artifact.artifact_type == "hex":
                hex_path = artifact.path
        
        return BuildResult(
            build_id=result.build_id,
            success=result.success,
            board_id=result.board_id,
            framework=result.framework,
            build_dir=result.build_dir,
            elf_path=elf_path,
            bin_path=bin_path,
            hex_path=hex_path,
            stdout=result.stdout,
            stderr=result.stderr,
            warnings=result.warnings,
            errors=result.errors,
            error_message=result.error_message,
            duration_seconds=result.duration_seconds,
        )
    
    async def get_provider_capabilities(self, framework: str) -> Dict[str, Any]:
        """Get capabilities of the provider for a framework."""
        provider = self._get_provider(framework)
        caps = await provider.get_capabilities()
        return caps.to_dict()
    
    async def list_build_targets(self, framework: Optional[str] = None) -> list:
        """List available build targets."""
        if framework:
            provider = self._get_provider(framework)
            return await provider.list_build_targets(framework)
        
        # List targets for all providers
        all_targets = []
        for fw in self.providers_config.keys():
            provider = self._get_provider(fw)
            targets = await provider.list_build_targets(fw)
            all_targets.extend(targets)
        return all_targets


# ============================================================================
# Legacy Classes (for backward compatibility)
# ============================================================================

class ZephyrBuilder:
    """Legacy Zephyr builder - now delegates to BuildManager.
    
    Maintains backward compatibility with existing code.
    """
    
    def __init__(self, zephyr_sdk_path: Optional[str] = None, 
                 use_docker: bool = True, 
                 project_root: Optional[str] = None):
        """Initialize legacy Zephyr builder."""
        self.zephyr_sdk_path = zephyr_sdk_path or "/opt/zephyr-sdk-0.17.4"
        self.use_docker = use_docker
        self.docker_image = "zephyrprojectrtos/zephyr-build:latest"
        self.project_root = Path(project_root) if project_root else Path.cwd()
        
        # Create internal build manager
        provider_config = {"type": "docker" if use_docker else "local"}
        if use_docker:
            provider_config["image"] = self.docker_image
        
        self._manager = BuildManager({
            "zephyr": provider_config
        })
    
    async def build(self, config: BuildConfig) -> BuildResult:
        """Build firmware (legacy interface)."""
        return await self._manager.build(config)
    
    def build_sync(self, config: BuildConfig) -> BuildResult:
        """Synchronous build (for legacy compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.build(config))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.build(config))


class MockBuilder:
    """Mock builder for testing without actual build capability."""
    
    def __init__(self):
        self.cache_dir = Path("./cache/builds")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def build(self, config: BuildConfig) -> BuildResult:
        """Simulate a build."""
        start_time = time.time()
        build_id = f"mock_{int(start_time)}_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"[MOCK] Building {build_id} for {config.board_id}")
        
        # Simulate build time
        await asyncio.sleep(0.5)
        
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
