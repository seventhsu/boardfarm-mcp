"""Board management - detection, state tracking, and reservation."""

import os
import re
import json
import yaml
import psutil
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import asdict

from .models import (
    Board, BoardState, DebuggerConfig, SerialConfig, ZephyrConfig,
    ServerConfig
)
from .board_queue import BoardQueue, QueueEntry, QueueStatus

logger = logging.getLogger(__name__)


class BoardManager:
    """Manages connected boards - detection, state, and reservations."""
    
    # Valid state transitions (from_state, to_state)
    VALID_TRANSITIONS = {
        # From OFFLINE
        (BoardState.OFFLINE, BoardState.AVAILABLE),
        (BoardState.OFFLINE, BoardState.RESERVED),
        # From AVAILABLE
        (BoardState.AVAILABLE, BoardState.OFFLINE),
        (BoardState.AVAILABLE, BoardState.RESERVED),
        (BoardState.AVAILABLE, BoardState.BUILDING),
        (BoardState.AVAILABLE, BoardState.TESTING),
        # From RESERVED
        (BoardState.RESERVED, BoardState.AVAILABLE),
        (BoardState.RESERVED, BoardState.BUILDING),
        (BoardState.RESERVED, BoardState.FLASHING),
        (BoardState.RESERVED, BoardState.RUNNING),
        (BoardState.RESERVED, BoardState.TESTING),
        (BoardState.RESERVED, BoardState.ERROR),
        # From BUILDING
        (BoardState.BUILDING, BoardState.RESERVED),
        (BoardState.BUILDING, BoardState.ERROR),
        # From FLASHING
        (BoardState.FLASHING, BoardState.RESERVED),
        (BoardState.FLASHING, BoardState.RUNNING),
        (BoardState.FLASHING, BoardState.ERROR),
        # From RUNNING
        (BoardState.RUNNING, BoardState.RESERVED),
        (BoardState.RUNNING, BoardState.ERROR),
        # From TESTING
        (BoardState.TESTING, BoardState.RESERVED),
        (BoardState.TESTING, BoardState.AVAILABLE),
        (BoardState.TESTING, BoardState.ERROR),
        # From ERROR
        (BoardState.ERROR, BoardState.AVAILABLE),
        (BoardState.ERROR, BoardState.OFFLINE),
        (BoardState.ERROR, BoardState.RESERVED),
    }
    
    def __init__(self, config_path: Optional[str] = None, board_queue: Optional[BoardQueue] = None):
        self.config_path = config_path or "config/boards.yaml"
        self.boards: Dict[str, Board] = {}
        self._state_callbacks: List[Callable[[str, BoardState, BoardState], None]] = []
        self._config: Optional[Dict] = None
        self._queue: Optional[BoardQueue] = board_queue
        self._lock = asyncio.Lock()  # Lock for atomic board operations
        
    def set_queue(self, queue: BoardQueue):
        """Set the board queue for automatic assignment."""
        self._queue = queue
        # Register for assignment callbacks (async callback supported)
        queue.register_assignment_callback(self._on_board_assigned)
        
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
        
        # Parse features and capabilities
        features = config.get('features', [])
        capabilities = config.get('capabilities', {})
        
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
            features=features,
            capabilities=capabilities,
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
        # Return a copy to prevent external mutation
        board = self.boards.get(board_id)
        if board is None:
            return None
        # Return the board object (callers should treat it as read-only)
        return board
    
    def list_boards(self, only_available: bool = False) -> List[Board]:
        """List all boards, optionally filtering to available only.
        
        Note: This is eventually consistent. For strict consistency,
        use list_boards_async() which acquires the lock.
        """
        boards = list(self.boards.values())
        if only_available:
            boards = [b for b in boards if b.status == BoardState.AVAILABLE]
        return boards
    
    async def list_boards_async(self, only_available: bool = False) -> List[Board]:
        """List all boards with proper locking for consistency."""
        async with self._lock:
            boards = list(self.boards.values())
            if only_available:
                boards = [b for b in boards if b.status == BoardState.AVAILABLE]
            return boards
    
    async def reserve_board(self, board_id: str, user: str, timeout_minutes: int = 30) -> bool:
        """Reserve a board for exclusive use."""
        async with self._lock:
            board = self.boards.get(board_id)
            if not board:
                logger.warning(f"reserve_board: Board {board_id} not found")
                return False

            # CRITICAL: Board must be AVAILABLE to reserve
            # We explicitly check this rather than relying on transition validation
            # to prevent race conditions where multiple agents see AVAILABLE simultaneously
            if board.status != BoardState.AVAILABLE:
                logger.warning(f"reserve_board: Board {board_id} is not available (status: {board.status.name})")
                return False

            # Also check transition validity
            if not self._is_valid_transition(board.status, BoardState.RESERVED):
                logger.warning(f"reserve_board: Invalid transition from {board.status.name} to RESERVED for {board_id}")
                return False

            old_status = board.status
            board.status = BoardState.RESERVED
            board.reserved_by = user
            board.reserved_until = datetime.now() + timedelta(minutes=timeout_minutes)

            self._notify_state_change(board_id, old_status, board.status)
            logger.info(f"Board {board_id} reserved by {user} until {board.reserved_until}")
            return True
    
    def _is_valid_transition(self, from_state: BoardState, to_state: BoardState) -> bool:
        """Check if a state transition is valid."""
        if from_state == to_state:
            return True  # Same state is always valid
        return (from_state, to_state) in self.VALID_TRANSITIONS
    
    async def release_board(self, board_id: str, user: str) -> bool:
        """Release a reserved board."""
        async with self._lock:
            board = self.boards.get(board_id)
            if not board:
                logger.warning(f"release_board: Board {board_id} not found")
                return False
            
            if board.status != BoardState.RESERVED:
                logger.warning(f"release_board: Board {board_id} is not RESERVED (status: {board.status.name})")
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
            
            # Check queue for next waiting request (will acquire lock again, but that's OK)
            # We need to release the lock first to avoid deadlock
            pass
        
        # Outside the lock, check queue
        if self._queue:
            await self._check_queue_for_board(board_id)
        
        return True
    
    async def _check_queue_for_board(self, board_id: str):
        """Check queue and assign board to next waiting request atomically."""
        entry = None

        # Step 1: Find matching entry while holding lock
        async with self._lock:
            board = self.boards.get(board_id)
            if not board or board.status != BoardState.AVAILABLE:
                logger.debug(f"_check_queue_for_board: Board {board_id} not available (status: {board.status if board else 'not found'})")
                return

            # Use feature-based matching to find best match
            entry = self._queue.find_best_match(
                board_type=board.type,
                board_id=board_id,
                board_features=board.get_features_set(),
                board_capabilities=board.get_capabilities_dict()
            )

            if not entry:
                logger.debug(f"_check_queue_for_board: No matching queue entry for {board_id}")
                return

            # CRITICAL: Mark board as RESERVED immediately to prevent race conditions
            # We use a temporary holder until the queue confirms assignment
            old_status = board.status
            board.status = BoardState.RESERVED
            board.reserved_by = f"assigning:{entry.queue_id}"
            board.reserved_until = datetime.now() + timedelta(minutes=entry.estimated_minutes)

        # Step 2: Outside the lock, assign to queue (this may trigger callbacks)
        # We don't hold the lock here to avoid deadlock with callback
        assign_success = await self._queue.assign_board(entry.queue_id, board_id)

        if not assign_success:
            # Assignment failed - release the board back to available
            async with self._lock:
                board = self.boards.get(board_id)
                if board and board.reserved_by == f"assigning:{entry.queue_id}":
                    board.status = BoardState.AVAILABLE
                    board.reserved_by = None
                    board.reserved_until = None
            logger.warning(f"_check_queue_for_board: Failed to assign {board_id} to queue entry {entry.queue_id}, board released")
            return

        # Step 3: Update reservation to final agent
        async with self._lock:
            board = self.boards.get(board_id)
            if board and board.reserved_by == f"assigning:{entry.queue_id}":
                old_status = board.status
                board.reserved_by = entry.agent_id
                self._notify_state_change(board_id, BoardState.AVAILABLE, board.status)
                logger.info(f"Board {board_id} auto-assigned and reserved for queue entry {entry.queue_id} (agent: {entry.agent_id})")
            else:
                logger.warning(f"_check_queue_for_board: Board {board_id} state changed during assignment")
    
    async def _on_board_assigned(self, queue_id: str, board_id: str):
        """Callback when a board is assigned from the queue.
        
        Note: The board is already reserved in _check_queue_for_board() to prevent
        race conditions. This callback is for notification/logging purposes only.
        """
        entry = self._queue.get_entry(queue_id)
        if not entry:
            return
        
        # Verify the board is reserved for this entry
        async with self._lock:
            board = self.boards.get(board_id)
            if board and board.status == BoardState.RESERVED:
                if board.reserved_by == entry.agent_id:
                    logger.info(f"Verified {board_id} reserved for {entry.agent_id} from queue")
                else:
                    logger.warning(f"Board {board_id} reserved by {board.reserved_by}, expected {entry.agent_id}")
            else:
                logger.warning(f"Board {board_id} not in RESERVED state when assigned from queue")
    
    async def update_board_state(self, board_id: str, new_state: BoardState) -> bool:
        """Update a board's state (for internal use)."""
        async with self._lock:
            board = self.boards.get(board_id)
            if not board:
                return False
            
            # Validate state transition
            if not self._is_valid_transition(board.status, new_state):
                logger.warning(f"update_board_state: Invalid transition from {board.status.name} to {new_state.name} for {board_id}")
                return False
            
            old_state = board.status
            board.status = new_state
            board.last_seen = datetime.now()
            
            self._notify_state_change(board_id, old_state, new_state)
            logger.debug(f"Board {board_id} state updated: {old_state.name} -> {new_state.name}")
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
    
    async def check_expired_reservations(self) -> List[str]:
        """Check and release expired reservations. Returns list of released board IDs."""
        released = []
        now = datetime.now()
        
        async with self._lock:
            expired_boards = []
            for board_id, board in self.boards.items():
                if board.status == BoardState.RESERVED and board.reserved_until:
                    if now > board.reserved_until:
                        expired_boards.append(board_id)
                        logger.info(f"Reservation expired for {board_id}")
                        old_status = board.status
                        board.status = BoardState.AVAILABLE
                        board.reserved_by = None
                        board.reserved_until = None
                        self._notify_state_change(board_id, old_status, board.status)
                        released.append(board_id)
        
        # Check queue for expired boards (outside the lock)
        if self._queue:
            for board_id in expired_boards:
                await self._check_queue_for_board(board_id)
        
        return released