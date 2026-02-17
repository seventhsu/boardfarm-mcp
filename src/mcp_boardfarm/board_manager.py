"""Board management - detection, state tracking, and reservation."""

import os
import re
import json
import yaml
import psutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import asdict

from .models import (
    Board, BoardState, DebuggerConfig, SerialConfig, ZephyrConfig,
    ServerConfig
)

logger = logging.getLogger(__name__)


class BoardManager:
    """Manages connected boards - detection, state, and reservations."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/boards.yaml"
        self.boards: Dict[str, Board] = {}
        self._state_callbacks: List[Callable[[str, BoardState, BoardState], None]] = []
        self._config: Optional[Dict] = None
        
    def load_config(self) -> Dict[str, Any]:
        """Load board configuration from YAML."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file not found: {self.config_path}")
            return {}
            
        with open(self.config_path, 'r') as f:
            self._config = yaml.safe_load(f)
            
        return self._config
    
    def _create_board_from_config(self, board_id: str, config: Dict) -> Board:
        """Create a Board instance from config dict."""
        # Parse debugger config
        dbg_config = config.get('debugger', {})
        debugger = DebuggerConfig(
            type=dbg_config.get('type', 'cmsis-dap'),
            transport=dbg_config.get('transport', 'swd'),
            interface_cfg=dbg_config.get('interface_cfg'),
            target_cfg=dbg_config.get('target_cfg'),
        )
        
        # Parse serial config
        ser_config = config.get('serial', {})
        serial = SerialConfig(
            port=ser_config.get('port', '/dev/ttyACM0'),
            baud=ser_config.get('baud', 115200),
            data_bits=ser_config.get('data_bits', 8),
            stop_bits=ser_config.get('stop_bits', 1),
            parity=ser_config.get('parity', 'N'),
        )
        
        # Parse Zephyr config
        zephyr_config = None
        if 'zephyr' in config:
            zephyr_config = ZephyrConfig(
                board_name=config['zephyr'].get('board_name', ''),
                soc=config['zephyr'].get('soc'),
                sysbuild=config['zephyr'].get('sysbuild', False),
            )
        
        return Board(
            board_id=board_id,
            type=config.get('type', 'stm32'),
            model=config.get('model', ''),
            mcu=config.get('mcu', ''),
            description=config.get('description', ''),
            flash_size=config.get('flash_size', 512),
            ram_size=config.get('ram_size', 96),
            debugger=debugger,
            serial=serial,
            zephyr=zephyr_config,
            supported_frameworks=config.get('supported_frameworks', []),
            status=BoardState.OFFLINE,
        )
    
    def detect_boards(self) -> List[Board]:
        """Detect connected boards via USB enumeration."""
        detected = []
        
        # Load config to know what to look for
        config = self.load_config()
        boards_config = config.get('boards', {})
        
        # Scan USB devices for known patterns
        usb_devices = self._scan_usb_devices()
        
        for board_id, board_config in boards_config.items():
            board = self._create_board_from_config(board_id, board_config)
            
            # Try to match with USB device
            matched_device = self._match_board_to_usb(board, usb_devices)
            
            if matched_device:
                board.status = BoardState.AVAILABLE
                board.usb_path = matched_device.get('path')
                board.serial_number = matched_device.get('serial')
                board.last_seen = datetime.now()
                
                # Update serial port from detected device if available
                if 'tty' in matched_device:
                    board.serial.port = matched_device['tty']
            else:
                # Keep as offline if not connected
                board.status = BoardState.OFFLINE
                
            detected.append(board)
            self.boards[board_id] = board
            
        logger.info(f"Detected {len([b for b in detected if b.status == BoardState.AVAILABLE])} available boards")
        return detected
    
    def _scan_usb_devices(self) -> List[Dict[str, Any]]:
        """Scan for USB devices using pyudev or fallback to /sys/bus/usb."""
        devices = []
        
        try:
            # Try using pyudev for better device info
            import pyudev
            context = pyudev.Context()
            
            for device in context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
                vid = device.attributes.get('idVendor')
                pid = device.attributes.get('idProduct')
                
                if vid and pid:
                    devices.append({
                        'path': device.device_path,
                        'vid': vid.decode() if isinstance(vid, bytes) else vid,
                        'pid': pid.decode() if isinstance(pid, bytes) else pid,
                        'serial': device.attributes.get('serial', b'').decode() if device.attributes.get('serial') else None,
                        'manufacturer': device.attributes.get('manufacturer', b'').decode() if device.attributes.get('manufacturer') else None,
                        'product': device.attributes.get('product', b'').decode() if device.attributes.get('product') else None,
                    })
        except ImportError:
            logger.warning("pyudev not available, using fallback USB detection")
            # Fallback: scan /sys/bus/usb/devices for basic info
            import glob
            for dev_path in glob.glob('/sys/bus/usb/devices/*/idVendor'):
                base = dev_path.rsplit('/', 1)[0]
                try:
                    with open(f"{base}/idVendor") as f:
                        vid = f.read().strip()
                    with open(f"{base}/idProduct") as f:
                        pid = f.read().strip()
                    
                    serial = None
                    serial_path = f"{base}/serial"
                    if os.path.exists(serial_path):
                        with open(serial_path) as f:
                            serial = f.read().strip()
                    
                    devices.append({
                        'path': base,
                        'vid': vid,
                        'pid': pid,
                        'serial': serial,
                    })
                except (IOError, OSError) as e:
                    logger.debug(f"Could not read USB device at {base}: {e}")
                    continue
        
        # Also scan for TTY devices associated with USB serial
        self._enrich_with_tty_devices(devices)
        
        return devices
    
    def _enrich_with_tty_devices(self, usb_devices: List[Dict[str, Any]]) -> None:
        """Enrich USB device info with TTY device paths."""
        import glob
        
        # Map of USB device paths to TTYs
        tty_map = {}
        
        for tty_path in glob.glob('/sys/class/tty/ttyACM*') + glob.glob('/sys/class/tty/ttyUSB*'):
            try:
                # Resolve symlink to find the USB device
                real_path = os.path.realpath(tty_path)
                # Extract the USB device path
                parts = real_path.split('/')
                if 'usb' in parts:
                    usb_idx = parts.index('usb')
                    usb_device_path = '/'.join(parts[:usb_idx + 2])
                    tty_device = os.path.basename(tty_path)
                    tty_map[usb_device_path] = f"/dev/{tty_device}"
            except (OSError, ValueError):
                continue
        
        # Update USB devices with TTY info
        for device in usb_devices:
            device_path = device.get('path', '')
            for usb_path, tty in tty_map.items():
                if usb_path in device_path or device_path in usb_path:
                    device['tty'] = tty
                    break
    
    def _match_board_to_usb(self, board: Board, usb_devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Match a configured board to a detected USB device."""
        # Known USB VID/PID mappings for common boards
        VID_PID_MAP = {
            # STM32 Nucleo boards (ST-LINK/V2-1 and V3)
            ('0483', '374b'): 'nucleo-stlink-v2-1',
            ('0483', '3752'): 'nucleo-stlink-v3',
            ('0483', '374e'): 'stlink-v3',
            # STM32 Discovery
            ('0483', '3748'): 'stlink-v2',
            # ESP32 (various vendors)
            ('10c4', 'ea60'): 'cp210x',  # Silicon Labs CP210x
            ('1a86', '7523'): 'ch340',   # QinHeng CH340
            ('0403', '6001'): 'ftdi',    # FTDI FT232
            # Nordic nRF
            ('1915', 'cafe'): 'nrf-dfu',
            ('1915', '521f'): 'nrf-jlink',
        }
        
        # Match based on board type and USB properties
        for device in usb_devices:
            vid = device.get('vid', '').lower()
            pid = device.get('pid', '').lower()
            
            # Check if this USB device matches known STM32 patterns
            if board.type == 'stm32':
                if (vid, pid) in VID_PID_MAP:
                    device_type = VID_PID_MAP[(vid, pid)]
                    if 'stlink' in device_type or 'nucleo' in device_type:
                        return device
            
            # For now, be permissive - if we have a TTY and it's STM32, match it
            if board.type == 'stm32' and 'tty' in device:
                # Additional check: verify it's an ST-LINK device
                if vid == '0483':  # STMicroelectronics VID
                    return device
        
        return None
    
    def get_board(self, board_id: str) -> Optional[Board]:
        """Get a board by ID."""
        return self.boards.get(board_id)
    
    def list_boards(self, only_available: bool = False) -> List[Board]:
        """List all boards, optionally filtering to available only."""
        boards = list(self.boards.values())
        if only_available:
            boards = [b for b in boards if b.status == BoardState.AVAILABLE]
        return boards
    
    def reserve_board(self, board_id: str, user: str, timeout_minutes: int = 30) -> bool:
        """Reserve a board for exclusive use."""
        board = self.boards.get(board_id)
        if not board:
            return False
        
        if board.status not in (BoardState.AVAILABLE, BoardState.OFFLINE):
            return False
        
        old_status = board.status
        board.status = BoardState.RESERVED
        board.reserved_by = user
        board.reserved_until = datetime.now() + timedelta(minutes=timeout_minutes)
        
        self._notify_state_change(board_id, old_status, board.status)
        logger.info(f"Board {board_id} reserved by {user} until {board.reserved_until}")
        return True
    
    def release_board(self, board_id: str, user: str) -> bool:
        """Release a reserved board."""
        board = self.boards.get(board_id)
        if not board:
            return False
        
        if board.status != BoardState.RESERVED:
            return False
        
        if board.reserved_by != user:
            logger.warning(f"User {user} tried to release board reserved by {board.reserved_by}")
            return False
        
        old_status = board.status
        board.status = BoardState.AVAILABLE
        board.reserved_by = None
        board.reserved_until = None
        
        self._notify_state_change(board_id, old_status, board.status)
        logger.info(f"Board {board_id} released by {user}")
        return True
    
    def update_board_state(self, board_id: str, new_state: BoardState) -> bool:
        """Update a board's state (for internal use)."""
        board = self.boards.get(board_id)
        if not board:
            return False
        
        old_state = board.status
        board.status = new_state
        board.last_seen = datetime.now()
        
        self._notify_state_change(board_id, old_state, new_state)
        return True
    
    def register_state_callback(self, callback: Callable[[str, BoardState, BoardState], None]):
        """Register a callback for board state changes."""
        self._state_callbacks.append(callback)
    
    def _notify_state_change(self, board_id: str, old_state: BoardState, new_state: BoardState):
        """Notify all registered callbacks of state change."""
        for callback in self._state_callbacks:
            try:
                callback(board_id, old_state, new_state)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def get_board_info(self, board_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed board information."""
        board = self.boards.get(board_id)
        if not board:
            return None
        return board.to_dict()
    
    def check_expired_reservations(self) -> List[str]:
        """Check and release expired reservations. Returns list of released board IDs."""
        released = []
        now = datetime.now()
        
        for board_id, board in self.boards.items():
            if board.status == BoardState.RESERVED and board.reserved_until:
                if now > board.reserved_until:
                    logger.info(f"Reservation expired for {board_id}")
                    old_status = board.status
                    board.status = BoardState.AVAILABLE
                    board.reserved_by = None
                    board.reserved_until = None
                    self._notify_state_change(board_id, old_status, board.status)
                    released.append(board_id)
        
        return released