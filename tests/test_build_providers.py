"""Tests for the build provider system.

This module contains tests for the pluggable build provider architecture,
including LocalBuildProvider, DockerBuildProvider, and RemoteBuildProvider.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_boardfarm.build_providers import (
    BuildProviderFactory, BuildRequest, BuildResult, BuildCapabilities,
    BuildStatus, BuildProviderType, BuildArtifact, BuildLogEntry, BuildError,
    LocalBuildProvider, DockerBuildProvider, RemoteBuildProvider,
)
from mcp_boardfarm.builder import BuildManager, ZephyrBuilder, MockBuilder
from mcp_boardfarm.models import BuildConfig


# =============================================================================
# Build Provider Factory Tests
# =============================================================================

class TestBuildProviderFactory:
    """Tests for the BuildProviderFactory."""
    
    def test_create_local_provider(self):
        """Test creating a local build provider."""
        config = {"type": "local", "command": "make"}
        provider = BuildProviderFactory.create(config)
        
        assert isinstance(provider, LocalBuildProvider)
        assert provider.provider_name == "LocalBuildProvider"
    
    def test_create_docker_provider(self):
        """Test creating a Docker build provider."""
        config = {"type": "docker", "image": "zephyrprojectrtos/zephyr-build:latest"}
        provider = BuildProviderFactory.create(config)
        
        assert isinstance(provider, DockerBuildProvider)
        assert provider.image == "zephyrprojectrtos/zephyr-build:latest"
    
    def test_create_remote_provider(self):
        """Test creating a remote build provider."""
        config = {"type": "remote", "url": "http://build-server:8080"}
        provider = BuildProviderFactory.create(config)
        
        assert isinstance(provider, RemoteBuildProvider)
        assert provider.url == "http://build-server:8080"
    
    def test_create_unknown_provider_raises_error(self):
        """Test that unknown provider type raises ValueError."""
        config = {"type": "unknown"}
        
        with pytest.raises(ValueError, match="Unknown build provider type"):
            BuildProviderFactory.create(config)
    
    def test_list_providers(self):
        """Test listing available provider types."""
        providers = BuildProviderFactory.list_providers()
        
        assert "local" in providers
        assert "docker" in providers
        assert "remote" in providers
        assert "ssh" in providers


# =============================================================================
# Build Request Tests
# =============================================================================

class TestBuildRequest:
    """Tests for BuildRequest data model."""
    
    def test_basic_request_creation(self):
        """Test creating a basic build request."""
        request = BuildRequest(
            board_id="nucleo-h755zi-q-01",
            source_path="/workspace/my_app",
            target="zephyr/nucleo_h755zi_q"
        )
        
        assert request.board_id == "nucleo-h755zi-q-01"
        assert request.source_path == "/workspace/my_app"
        assert request.target == "zephyr/nucleo_h755zi_q"
    
    def test_get_framework_from_slash_target(self):
        """Test extracting framework from target with slash."""
        request = BuildRequest(
            board_id="test",
            source_path=".",
            target="zephyr/nucleo_h755zi_q"
        )
        
        assert request.get_framework() == "zephyr"
        assert request.get_board_target() == "nucleo_h755zi_q"
    
    def test_get_framework_from_colon_target(self):
        """Test extracting framework from Arduino-style target."""
        request = BuildRequest(
            board_id="test",
            source_path=".",
            target="arduino:avr:nano"
        )
        
        assert request.get_framework() == "arduino"
        assert request.get_board_target() == "avr:nano"


# =============================================================================
# Local Build Provider Tests
# =============================================================================

class TestLocalBuildProvider:
    """Tests for LocalBuildProvider."""
    
    @pytest.fixture
    def provider(self):
        """Create a test provider with temp workdir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "type": "local",
                "command": "make",
                "workdir": tmpdir,
                "timeout": 60
            }
            yield LocalBuildProvider(config)
    
    @pytest.mark.asyncio
    async def test_get_capabilities(self, provider):
        """Test getting provider capabilities."""
        caps = await provider.get_capabilities()
        
        assert isinstance(caps, BuildCapabilities)
        assert caps.provider_type == BuildProviderType.LOCAL
        assert "zephyr" in caps.supported_frameworks
    
    def test_sanitize_path_blocks_traversal(self, provider):
        """Test that path sanitization blocks directory traversal."""
        with pytest.raises(BuildError):
            provider._sanitize_path("../../../etc/passwd")
    
    def test_validate_target_blocks_dangerous_chars(self, provider):
        """Test that target validation blocks dangerous characters."""
        assert provider._validate_target("zephyr/board") is True
        assert provider._validate_target("zephyr;rm -rf /") is False


# =============================================================================
# Build Manager Tests
# =============================================================================

class TestBuildManager:
    """Tests for BuildManager."""
    
    def test_initialization(self):
        """Test BuildManager initialization."""
        manager = BuildManager()
        
        assert manager.providers_config == {}
        assert manager._providers == {}
    
    def test_get_provider_creates_new_instance(self):
        """Test that get_provider creates provider instances."""
        manager = BuildManager({"zephyr": {"type": "local"}})
        provider = manager._get_provider("zephyr")
        
        assert provider is not None
        assert "zephyr" in manager._providers


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurity:
    """Security-focused tests for build providers."""
    
    def test_path_traversal_patterns_blocked(self):
        """Test that path traversal patterns are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = LocalBuildProvider({"type": "local", "workdir": tmpdir})
            
            blocked_paths = [
                "../../../etc/passwd",
                "..\\windows\\system32",
                "/etc/passwd",
            ]
            
            for path in blocked_paths:
                with pytest.raises(BuildError):
                    provider._sanitize_path(path)
    
    def test_dangerous_chars_blocked_in_target(self):
        """Test that dangerous characters are blocked in targets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = LocalBuildProvider({"type": "local", "workdir": tmpdir})
            
            dangerous_targets = [
                "zephyr;rm -rf /",
                "zephyr|cat /etc/passwd",
                "zephyr&&reboot",
            ]
            
            for target in dangerous_targets:
                assert provider._validate_target(target) is False
