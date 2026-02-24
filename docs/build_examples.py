"""Build Provider Usage Examples

This file demonstrates how to use the MCP Board Farm build provider system
for firmware compilation across different backends.
"""

import asyncio
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_boardfarm.build_providers import (
    BuildProviderFactory,
    BuildRequest,
    BuildStatus,
)
from mcp_boardfarm.builder import BuildManager
from mcp_boardfarm.models import BuildConfig


# =============================================================================
# Example 1: Basic Local Build
# =============================================================================

async def example_local_build():
    """Build firmware using local toolchain."""
    
    # Create a local provider
    config = {
        "type": "local",
        "command": "west",
        "workdir": "/tmp/builds",
        "timeout": 300
    }
    provider = BuildProviderFactory.create(config)
    
    # Create build request
    request = BuildRequest(
        board_id="nucleo-h755zi-q-01",
        source_path="zephyr/samples/hello_world",
        target="zephyr/nucleo_h755zi_q",
        build_type="debug"
    )
    
    # Execute build
    print("Starting local build...")
    result = await provider.build(request)
    
    print(f"Build {'succeeded' if result.success else 'failed'}")
    print(f"Build ID: {result.build_id}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    
    if result.artifacts:
        print("\nArtifacts:")
        for artifact in result.artifacts:
            print(f"  - {artifact.artifact_type}: {artifact.path}")
    
    return result


# =============================================================================
# Example 2: Docker-based Build
# =============================================================================

async def example_docker_build():
    """Build firmware using Docker container."""
    
    config = {
        "type": "docker",
        "image": "zephyrprojectrtos/zephyr-build:latest",
        "timeout": 600,
        "memory_limit": "4g",
        "privileged": True
    }
    provider = BuildProviderFactory.create(config)
    
    request = BuildRequest(
        board_id="nucleo-h755zi-q-01",
        source_path="zephyr/samples/philosophers",
        target="zephyr/nucleo_h755zi_q",
        options={"cmake_args": ["-DCONFIG_DEBUG=y"]}
    )
    
    print("Starting Docker build...")
    result = await provider.build(request)
    
    print(f"Build {'succeeded' if result.success else 'failed'}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    return result


# =============================================================================
# Example 3: Using BuildManager
# =============================================================================

async def example_build_manager():
    """Use BuildManager to handle multiple frameworks."""
    
    # Initialize with configurations for multiple frameworks
    manager = BuildManager({
        "zephyr": {
            "type": "docker",
            "image": "zephyrprojectrtos/zephyr-build:latest",
            "timeout": 600
        },
        "arduino": {
            "type": "local",
            "command": "arduino-cli",
            "timeout": 120
        }
    })
    
    # Build for Zephyr
    zephyr_config = BuildConfig(
        framework="zephyr",
        board_id="nucleo-h755zi-q-01",
        zephyr_sample="hello_world"
    )
    
    print("Building Zephyr firmware...")
    result = await manager.build(zephyr_config)
    print(f"  Result: {'SUCCESS' if result.success else 'FAILED'}")
    
    # List available targets
    print("\nAvailable Zephyr targets:")
    targets = await manager.list_build_targets("zephyr")
    for target in targets[:5]:  # Show first 5
        print(f"  - {target}")
    
    # Get provider capabilities
    caps = await manager.get_provider_capabilities("zephyr")
    print(f"\nZephyr provider capabilities:")
    print(f"  Type: {caps['provider_type']}")
    print(f"  Max parallel jobs: {caps['limits']['max_parallel_jobs']}")
    print(f"  Supports incremental: {caps['features']['incremental_builds']}")
    
    return result


# =============================================================================
# Example 4: Arduino-style Target
# =============================================================================

async def example_arduino_build():
    """Build for Arduino using colon-style target."""
    
    request = BuildRequest(
        board_id="arduino-nano-01",
        source_path="/workspace/arduino_sketch",
        target="arduino:avr:nano",  # Arduino-style target
        options={"verbose": True}
    )
    
    print(f"Framework: {request.get_framework()}")  # "arduino"
    print(f"Board target: {request.get_board_target()}")  # "avr:nano"
    
    # Create provider and build
    config = {"type": "local", "command": "arduino-cli"}
    provider = BuildProviderFactory.create(config)
    
    # Note: This would fail without actual Arduino CLI installed
    # result = await provider.build(request)
    
    return request


# =============================================================================
# Example 5: Security Features
# =============================================================================

async def example_security():
    """Demonstrate security features."""
    
    from mcp_boardfarm.build_providers import LocalBuildProvider, BuildError
    
    provider = LocalBuildProvider({
        "type": "local",
        "workdir": "/tmp/builds"
    })
    
    # Attempt 1: Path traversal attack
    print("Testing path traversal protection...")
    try:
        provider._sanitize_path("../../../etc/passwd")
        print("  FAILED: Path traversal allowed!")
    except BuildError as e:
        print(f"  BLOCKED: {e}")
    
    # Attempt 2: Command injection in target
    print("\nTesting command injection protection...")
    is_valid = provider._validate_target("zephyr; rm -rf /")
    print(f"  {'BLOCKED' if not is_valid else 'ALLOWED'}: Command injection attempt")
    
    # Attempt 3: Valid target
    print("\nTesting valid target...")
    is_valid = provider._validate_target("zephyr/nucleo_h755zi_q")
    print(f"  {'ALLOWED' if is_valid else 'BLOCKED'}: Valid target")


# =============================================================================
# Example 6: Checking Build Status and Logs
# =============================================================================

async def example_build_tracking():
    """Demonstrate build status tracking and log retrieval."""
    
    from mcp_boardfarm.build_providers import RemoteBuildProvider
    
    # Create remote provider (stub implementation)
    provider = RemoteBuildProvider({
        "type": "remote",
        "url": "http://build-server:8080"
    })
    
    # Submit a build
    request = BuildRequest(
        board_id="test-board",
        source_path="/workspace/app",
        target="zephyr/nucleo_h755zi_q"
    )
    
    print("Submitting remote build...")
    result = await provider.build(request)
    build_id = result.build_id
    
    print(f"Build ID: {build_id}")
    
    # Check status (stub returns SUCCESS)
    status = await provider.get_build_status(build_id)
    print(f"Status: {status.name if status else 'Unknown'}")
    
    # Get logs
    logs = await provider.get_build_logs(build_id, lines=5)
    print(f"\nLast {len(logs)} log entries:")
    for entry in logs:
        print(f"  [{entry.level}] {entry.message}")


# =============================================================================
# Run Examples
# =============================================================================

async def main():
    """Run all examples."""
    
    print("=" * 60)
    print("MCP Board Farm - Build Provider Examples")
    print("=" * 60)
    
    print("\n" + "-" * 40)
    print("Example 1: Local Build (would need west installed)")
    print("-" * 40)
    # await example_local_build()  # Commented out - needs west
    
    print("\n" + "-" * 40)
    print("Example 2: Docker Build (would need Docker)")
    print("-" * 40)
    # await example_docker_build()  # Commented out - needs Docker
    
    print("\n" + "-" * 40)
    print("Example 3: BuildManager")
    print("-" * 40)
    # await example_build_manager()  # Commented out - needs Docker
    
    print("\n" + "-" * 40)
    print("Example 4: Arduino Target Format")
    print("-" * 40)
    await example_arduino_build()
    
    print("\n" + "-" * 40)
    print("Example 5: Security Features")
    print("-" * 40)
    await example_security()
    
    print("\n" + "-" * 40)
    print("Example 6: Build Tracking")
    print("-" * 40)
    await example_build_tracking()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
