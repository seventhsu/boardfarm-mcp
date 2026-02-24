"""Build providers for MCP Board Farm.

This module provides pluggable build backends for firmware compilation.

Usage:
    from mcp_boardfarm.build_providers import BuildProviderFactory
    
    # Create provider from configuration
    provider = BuildProviderFactory.create({
        "type": "docker",
        "image": "zephyrprojectrtos/zephyr-build:latest"
    })
    
    # Execute build
    result = await provider.build(request)

Providers:
    - LocalBuildProvider: Executes builds using local toolchain commands
    - DockerBuildProvider: Executes builds inside Docker containers
    - RemoteBuildProvider: Delegates builds to remote build servers

Adding New Providers:
    1. Create a new module in this package
    2. Inherit from BuildProvider base class
    3. Implement build() and get_capabilities()
    4. Register in BuildProviderFactory._providers
"""

from .base import (
    BuildProvider,
    BuildRequest,
    BuildResult,
    BuildCapabilities,
    BuildStatus,
    BuildProviderType,
    BuildArtifact,
    BuildLogEntry,
    BuildError,
)
from .local import LocalBuildProvider
from .docker import DockerBuildProvider
from .remote import RemoteBuildProvider

__all__ = [
    # Base classes
    "BuildProvider",
    "BuildRequest",
    "BuildResult",
    "BuildCapabilities",
    "BuildStatus",
    "BuildProviderType",
    "BuildArtifact",
    "BuildLogEntry",
    "BuildError",
    # Providers
    "LocalBuildProvider",
    "DockerBuildProvider",
    "RemoteBuildProvider",
    # Factory
    "BuildProviderFactory",
]


class BuildProviderFactory:
    """Factory for creating build providers.
    
    Maps provider types to implementations and creates instances
    from configuration dictionaries.
    """
    
    _providers = {
        BuildProviderType.LOCAL.value: LocalBuildProvider,
        BuildProviderType.DOCKER.value: DockerBuildProvider,
        BuildProviderType.REMOTE.value: RemoteBuildProvider,
        "ssh": RemoteBuildProvider,  # Alias for remote with SSH protocol
    }
    
    @classmethod
    def create(cls, config: dict) -> BuildProvider:
        """Create a build provider from configuration.
        
        Args:
            config: Provider configuration dict with at least 'type' key
            
        Returns:
            Configured BuildProvider instance
            
        Raises:
            ValueError: If provider type is unknown
            
        Example:
            provider = BuildProviderFactory.create({
                "type": "docker",
                "image": "zephyrprojectrtos/zephyr-build:latest",
                "timeout": 600
            })
        """
        provider_type = config.get("type", "local")
        
        if provider_type not in cls._providers:
            raise ValueError(
                f"Unknown build provider type: {provider_type}. "
                f"Available: {list(cls._providers.keys())}"
            )
        
        provider_class = cls._providers[provider_type]
        return provider_class(config)
    
    @classmethod
    def register(cls, provider_type: str, provider_class: type):
        """Register a custom build provider.
        
        Args:
            provider_type: Unique identifier for this provider type
            provider_class: Class inheriting from BuildProvider
            
        Example:
            class MyCustomProvider(BuildProvider):
                async def build(self, request): ...
            
            BuildProviderFactory.register("custom", MyCustomProvider)
        """
        if not issubclass(provider_class, BuildProvider):
            raise TypeError(f"Provider must inherit from BuildProvider")
        
        cls._providers[provider_type] = provider_class
    
    @classmethod
    def list_providers(cls) -> list:
        """List available provider types."""
        return list(cls._providers.keys())
    
    @classmethod
    def get_provider_class(cls, provider_type: str) -> type:
        """Get provider class by type."""
        return cls._providers.get(provider_type)
