"""CLI for MCP Board Farm."""

import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_boardfarm.server import mcp
from mcp_boardfarm.board_manager import BoardManager


def setup_logging(level: str = "INFO"):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_serve(args):
    """Run the MCP server."""
    setup_logging(args.log_level)
    
    # Set config path from environment or argument
    if args.config:
        os.environ['BOARDFARM_CONFIG'] = args.config
    
    print(f"Starting MCP Board Farm server...")
    print(f"Transport: {args.transport}")
    
    if args.transport == "stdio":
        # Run with stdio transport (for Claude Desktop)
        mcp.run(transport='stdio')
    else:
        # Run with SSE transport
        mcp.run(transport='sse', port=args.port)


def cmd_detect(args):
    """Detect connected boards."""
    setup_logging(args.log_level)
    
    config_path = args.config or "config/boards.yaml"
    bm = BoardManager(config_path)
    bm.load_config()
    
    print("Scanning for connected boards...")
    boards = bm.detect_boards()
    
    available = [b for b in boards if b.status.name == "AVAILABLE"]
    offline = [b for b in boards if b.status.name == "OFFLINE"]
    
    print(f"\nFound {len(available)} available, {len(offline)} offline (of {len(boards)} configured)")
    
    for board in boards:
        status_icon = "🟢" if board.status.name == "AVAILABLE" else "⚫"
        print(f"\n{status_icon} {board.board_id}")
        print(f"   Model: {board.model} ({board.mcu})")
        print(f"   Serial: {board.serial.port}")
        if board.usb_path:
            print(f"   USB: {board.usb_path}")


def cmd_config(args):
    """Show configuration."""
    import yaml
    
    config_path = args.config or "config/boards.yaml"
    
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(1)
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    print("Board Farm Configuration")
    print("=" * 50)
    
    boards = config.get('boards', {})
    print(f"\nConfigured Boards: {len(boards)}")
    
    for board_id, board_config in boards.items():
        print(f"\n  • {board_id}")
        print(f"    Model: {board_config.get('model')}")
        print(f"    MCU: {board_config.get('mcu')}")
        print(f"    Serial: {board_config.get('serial', {}).get('port')}")
    
    server_config = config.get('server', {})
    print(f"\nServer Settings:")
    print(f"  Host: {server_config.get('host', '127.0.0.1')}")
    print(f"  Port: {server_config.get('port', 8080)}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='mcp-boardfarm',
        description='MCP Board Farm - AI-controllable embedded hardware'
    )
    
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file (default: config/boards.yaml)'
    )
    parser.add_argument(
        '--log-level', '-l',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Serve command
    serve_parser = subparsers.add_parser('serve', help='Run MCP server')
    serve_parser.add_argument(
        '--transport', '-t',
        default='stdio',
        choices=['stdio', 'sse'],
        help='Transport type (stdio for Claude Desktop, sse for web)'
    )
    serve_parser.add_argument(
        '--port', '-p',
        type=int,
        default=8080,
        help='Port for SSE transport'
    )
    serve_parser.set_defaults(func=cmd_serve)
    
    # Detect command
    detect_parser = subparsers.add_parser('detect', help='Detect connected boards')
    detect_parser.set_defaults(func=cmd_detect)
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Show configuration')
    config_parser.set_defaults(func=cmd_config)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()