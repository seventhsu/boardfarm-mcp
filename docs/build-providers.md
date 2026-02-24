# Build Provider System

The MCP Board Farm build provider system is a pluggable architecture for firmware compilation that supports local builds, Docker containers, and remote build servers. This system replaces the previous hardcoded ZephyrBuilder with a flexible, extensible approach.

## Overview

The build provider system consists of:

- **Abstract Base Class** (`BuildProvider`): Defines the interface all providers must implement
- **Concrete Providers**: Local, Docker, and Remote implementations
- **Factory Pattern** (`BuildProviderFactory`): Creates providers from configuration
- **BuildManager**: High-level coordinator that manages multiple providers

## Quick Start

### Basic Usage

```python
from mcp_boardfarm.build_providers import BuildProviderFactory, BuildRequest

# Create a provider from configuration
config = {
    "type": "docker",
    "image": "zephyrprojectrtos/zephyr-build:latest",
    "timeout": 300
}
provider = BuildProviderFactory.create(config)

# Create a build request
request = BuildRequest(
    board_id="nucleo-h755zi-q-01",
    source_path="/workspace/my_app",
    target="zephyr/nucleo_h755zi_q",
    build_type="debug"
)

# Execute the build
result = await provider.build(request)

if result.success:
    print(f"Build successful: {result.elf_path}")
else:
    print(f"Build failed: {result.error_message}")
```

### Using BuildManager

```python
from mcp_boardfarm.builder import BuildManager
from mcp_boardfarm.models import BuildConfig

# Initialize with provider configurations
manager = BuildManager({
    "zephyr": {
        "type": "docker",
        "image": "zephyrprojectrtos/zephyr-build:latest"
    },
    "arduino": {
        "type": "local",
        "command": "arduino-cli",
        "timeout": 120
    }
})

# Build using the appropriate provider
config = BuildConfig(
    framework="zephyr",
    board_id="nucleo-h755zi-q-01",
    zephyr_sample="hello_world"
)

result = await manager.build(config)
```

## Provider Types

### LocalBuildProvider

Executes builds using local toolchain commands (west, arduino-cli, platformio, make).

**Configuration:**
```yaml
build_providers:
  zephyr:
    type: local
    command: west
    workdir: /tmp/builds
    timeout: 300
    max_parallel_jobs: 4
    env_whitelist:
      - ZEPHYR_BASE
      - ZEPHYR_SDK_INSTALL_DIR
```

**Security Features:**
- Path sanitization prevents directory traversal attacks
- Command validation against whitelist patterns
- Environment variable injection controlled via whitelist
- Timeout prevents resource exhaustion

### DockerBuildProvider

Executes builds inside Docker containers for full isolation and reproducibility.

**Configuration:**
```yaml
build_providers:
  zephyr:
    type: docker
    image: zephyrprojectrtos/zephyr-build:latest
    timeout: 600
    network_mode: bridge
    memory_limit: "4g"
    cpu_limit: 2.0
    privileged: false
    volumes:
      - /dev:/dev
    env:
      ZEPHYR_BASE: /home/user/zephyrproject/zephyr
```

**Features:**
- Container isolation provides sandboxing
- Resource limits (CPU, memory)
- Network isolation options
- Persistent volumes for caching

### RemoteBuildProvider

Delegates builds to a remote build server via HTTP API or SSH (stub implementation).

**Configuration:**
```yaml
build_providers:
  zephyr:
    type: remote
    url: http://build-server:8080
    api_key: ${REMOTE_BUILD_API_KEY}
    timeout: 600
    protocol: http
    max_retries: 3
    retry_delay: 5
```

**Note:** The RemoteBuildProvider is currently a stub. Full implementation would include HTTP client with auth, SSH connection management, and async job polling.

## Agent-Friendly MCP Tools

The server provides three primary MCP tools for agents:

### build_firmware

```python
@mcp.tool()
async def build_firmware(
    ctx: Context,
    board_id: str,
    source: str,
    target: str,
    options: Optional[Dict[str, Any]] = None,
    build_type: str = "debug"
) -> str:
    """Build firmware for a board.
    
    Args:
        board_id: The board to build for (e.g., "nucleo-h755zi-q-01")
        source: Path to source code or sample name
        target: Build target in format "framework/board"
                (e.g., "zephyr/nucleo_h755zi_q", "arduino:avr:nano")
        options: Optional framework-specific build options
        build_type: "debug" or "release"
    
    Returns:
        Build result summary with build_id for status tracking
    """
```

**Example:**
```
build_firmware(
    board_id="nucleo-h755zi-q-01",
    source="hello_world",
    target="zephyr/nucleo_h755zi_q"
)
```

### build_status

```python
@mcp.tool()
async def build_status(ctx: Context, build_id: str) -> str:
    """Check the status of a build.
    
    Args:
        build_id: The build identifier returned by build_firmware
        
    Returns:
        Current build status and details
    """
```

### get_build_logs

```python
@mcp.tool()
async def get_build_logs(ctx: Context, build_id: str, lines: int = 100) -> str:
    """Get logs from a build.
    
    Args:
        build_id: The build identifier
        lines: Number of log lines to return (default: 100)
        
    Returns:
        Build logs
    """
```

## Target Format

Build targets use a standardized format:

- **Zephyr**: `zephyr/<board_name>` (e.g., `zephyr/nucleo_h755zi_q`)
- **Arduino**: `arduino:<arch>:<board>` (e.g., `arduino:avr:nano`)
- **PlatformIO**: `platformio/<board>` (e.g., `platformio/stm32h7`)
- **Make**: `make/<target>` (e.g., `make/generic`)

The framework is extracted from the target string to select the appropriate provider.

## Security Considerations

### Path Sanitization

All providers implement path sanitization to prevent directory traversal attacks:

```python
def _sanitize_path(self, path: str) -> Path:
    """Sanitize a path to prevent directory traversal attacks."""
    # Block traversal patterns
    for pattern in [r"\.\./", r"\.\.\\", r"^/", r"^\\"]:
        if re.search(pattern, path, re.IGNORECASE):
            raise BuildError(f"Path contains traversal pattern: {path}")
    
    # Ensure path is within allowed roots
    normalized = Path(path).resolve()
    # ... validation logic
```

### Input Validation

- **Target strings**: Validated against dangerous characters (`;`, `|`, `&`, `<`, `>`, `$`, `` ` ``)
- **Options**: Keys and values are sanitized to prevent injection
- **Environment variables**: Whitelist-based approach for controlled injection

### Timeouts

All providers implement configurable timeouts to prevent resource exhaustion:

```yaml
build_providers:
  zephyr:
    type: docker
    timeout: 600  # 10 minutes max build time
```

## Adding Custom Providers

You can extend the system with custom build providers:

```python
from mcp_boardfarm.build_providers import BuildProvider, BuildRequest, BuildResult

class CustomBuildProvider(BuildProvider):
    """Custom build provider implementation."""
    
    async def build(self, request: BuildRequest) -> BuildResult:
        # Implement build logic
        pass
    
    async def get_capabilities(self) -> BuildCapabilities:
        # Report capabilities
        pass

# Register the provider
from mcp_boardfarm.build_providers import BuildProviderFactory

BuildProviderFactory.register("custom", CustomBuildProvider)

# Use it
config = {"type": "custom", "custom_option": "value"}
provider = BuildProviderFactory.create(config)
```

## Backward Compatibility

The system maintains backward compatibility with existing code:

```python
# Old style (still works)
from mcp_boardfarm.builder import ZephyrBuilder
from mcp_boardfarm.models import BuildConfig

builder = ZephyrBuilder()
config = BuildConfig(
    board_id="nucleo-h755zi-q-01",
    framework="zephyr",
    zephyr_sample="hello_world"
)
result = await builder.build(config)

# New style (recommended)
from mcp_boardfarm.builder import BuildManager

manager = BuildManager()
result = await manager.build(config)
```

The `ZephyrBuilder` class now delegates to `BuildManager` internally, providing a migration path.

## Configuration File

Provider configurations are loaded from `config/boards.yaml`:

```yaml
build_providers:
  zephyr:
    type: docker
    image: zephyrprojectrtos/zephyr-build:latest
    timeout: 600
    memory_limit: "4g"
  
  arduino:
    type: local
    command: arduino-cli
    timeout: 120
  
  platformio:
    type: local
    command: pio
    timeout: 300

boards:
  nucleo-h755zi-q-01:
    model: NUCLEO-H755ZI-Q
    mcu: STM32H755ZI
    supported_frameworks:
      - zephyr
      - arduino
```

## Testing

Run the build provider tests:

```bash
cd mcp-boardfarm
python -m pytest tests/test_build_providers.py -v
```

The test suite includes:
- Factory creation tests
- Provider capability tests
- Security tests (path traversal, injection attempts)
- Build request validation tests
- Backward compatibility tests

## Troubleshooting

### Build fails with "Path contains traversal pattern"

The source path or output path contains characters that look like directory traversal attempts. Ensure paths:
- Don't start with `..`
- Don't contain `../` or `..\`
- Are within the allowed workspace directories

### Provider not found

Ensure the provider type is registered:

```python
from mcp_boardfarm.build_providers import BuildProviderFactory

print(BuildProviderFactory.list_providers())
```

### Docker builds fail

Check that Docker is installed and running:

```bash
docker version
docker compose up -d zephyr-builder
```

### Timeout errors

Increase the timeout in your configuration:

```yaml
build_providers:
  zephyr:
    type: docker
    timeout: 1200  # 20 minutes for large builds
```

## API Reference

### BuildProvider (Abstract Base)

```python
class BuildProvider(ABC):
    async def build(self, request: BuildRequest) -> BuildResult
    async def get_capabilities(self) -> BuildCapabilities
    async def get_build_status(self, build_id: str) -> Optional[BuildStatus]
    async def get_build_logs(self, build_id: str, lines: int = 100) -> List[BuildLogEntry]
    async def cancel_build(self, build_id: str) -> bool
    def validate_request(self, request: BuildRequest) -> Optional[str]
```

### Data Models

```python
@dataclass
class BuildRequest:
    board_id: str
    source_path: str
    target: str
    output_path: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    env_vars: Dict[str, str] = field(default_factory=dict)
    build_type: str = "debug"
    clean_build: bool = False

@dataclass
class BuildResult:
    build_id: str
    success: bool
    status: BuildStatus
    artifacts: List[BuildArtifact]
    stdout: str
    stderr: str
    duration_seconds: float
```

## See Also

- [Docker Build System](docker-build-system.md) - Docker-specific build documentation
- [Architecture Overview](ARCHITECTURE.md) - System architecture
- [API Documentation](GDB_DEBUGGING.md) - Debugging tools
