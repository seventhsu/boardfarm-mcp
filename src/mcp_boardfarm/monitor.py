"""Serial monitor for capturing board output."""

import os
import re
import json
import asyncio
import logging
import serial
import serial.tools.list_ports
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from dataclasses import asdict
from collections import deque

from .models import Board, LogEntry

logger = logging.getLogger(__name__)


class SerialMonitor:
    """Monitor serial output from boards."""
    
    def __init__(self, max_buffer_lines: int = 10000):
        self.max_buffer_lines = max_buffer_lines
        self._buffers: Dict[str, deque] = {}  # board_id -> deque of LogEntry
        self._serial_ports: Dict[str, serial.Serial] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._callbacks: List[Callable[[LogEntry], None]] = []
    
    async def start_monitoring(self, board: Board, 
                               on_log: Optional[Callable[[LogEntry], None]] = None) -> bool:
        """Start monitoring serial output from a board."""
        board_id = board.board_id
        
        if board_id in self._tasks:
            logger.warning(f"Already monitoring {board_id}")
            return True
        
        if not board.serial.port:
            logger.error(f"No serial port configured for {board_id}")
            return False
        
        # Initialize buffer
        if board_id not in self._buffers:
            self._buffers[board_id] = deque(maxlen=self.max_buffer_lines)
        
        # Start monitoring task
        try:
            task = asyncio.create_task(
                self._monitor_loop(board_id, board.serial.port, board.serial.baud)
            )
            self._tasks[board_id] = task
            logger.info(f"Started monitoring {board_id} on {board.serial.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start monitoring {board_id}: {e}")
            return False
    
    async def stop_monitoring(self, board_id: str) -> bool:
        """Stop monitoring a board."""
        if board_id not in self._tasks:
            logger.warning(f"Not monitoring {board_id}")
            return False
        
        task = self._tasks.pop(board_id)
        task.cancel()
        
        # Close serial port
        if board_id in self._serial_ports:
            try:
                self._serial_ports[board_id].close()
            except Exception as e:
                logger.error(f"Error closing serial port for {board_id}: {e}")
            del self._serial_ports[board_id]
        
        logger.info(f"Stopped monitoring {board_id}")
        return True
    
    async def close_all(self):
        """Stop all monitoring."""
        board_ids = list(self._tasks.keys())
        for board_id in board_ids:
            await self.stop_monitoring(board_id)
    
    async def _monitor_loop(self, board_id: str, port: str, baud: int):
        """Main monitoring loop for a board."""
        while True:
            try:
                # Open serial port
                ser = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1  # Non-blocking reads
                )
                self._serial_ports[board_id] = ser
                
                buffer = ""
                
                while True:
                    try:
                        # Read available data
                        if ser.in_waiting > 0:
                            data = ser.read(ser.in_waiting)
                            text = data.decode('utf-8', errors='replace')
                            buffer += text
                            
                            # Process complete lines
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                line = line.rstrip('\r')
                                await self._add_log_entry(board_id, line)
                        
                        await asyncio.sleep(0.01)  # 10ms sleep
                        
                    except serial.SerialException as e:
                        logger.error(f"Serial error on {board_id}: {e}")
                        break
                        
            except serial.SerialException as e:
                logger.error(f"Could not open {port} for {board_id}: {e}")
                await asyncio.sleep(1)  # Wait before retry
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(f"Unexpected error in monitor loop for {board_id}")
                await asyncio.sleep(1)
    
    async def _add_log_entry(self, board_id: str, message: str):
        """Add a log entry to the buffer."""
        # Try to detect log level from message
        level = "INFO"
        upper_msg = message.upper()
        if any(x in upper_msg for x in ['ERROR', 'ERR', 'FAIL', 'ASSERT']):
            level = "ERROR"
        elif any(x in upper_msg for x in ['WARN', 'WARNING']):
            level = "WARN"
        elif any(x in upper_msg for x in ['DEBUG', 'DBG']):
            level = "DEBUG"
        
        entry = LogEntry(
            timestamp=datetime.now(),
            board_id=board_id,
            level=level,
            message=message
        )
        
        # Add to buffer
        if board_id not in self._buffers:
            self._buffers[board_id] = deque(maxlen=self.max_buffer_lines)
        self._buffers[board_id].append(entry)
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                logger.error(f"Log callback error: {e}")
    
    def get_logs(self, board_id: str, since: Optional[datetime] = None,
                 max_lines: int = 1000) -> List[LogEntry]:
        """Get buffered logs for a board."""
        if board_id not in self._buffers:
            return []
        
        logs = list(self._buffers[board_id])
        
        if since:
            logs = [l for l in logs if l.timestamp >= since]
        
        # Return most recent lines
        return logs[-max_lines:]
    
    def register_callback(self, callback: Callable[[LogEntry], None]):
        """Register a callback for new log entries."""
        self._callbacks.append(callback)
    
    def is_monitoring(self, board_id: str) -> bool:
        """Check if a board is being monitored."""
        return board_id in self._tasks
    
    def get_monitored_boards(self) -> List[str]:
        """Get list of currently monitored boards."""
        return list(self._tasks.keys())


class MockMonitor:
    """Mock monitor for testing without hardware."""
    
    def __init__(self):
        self._buffers: Dict[str, deque] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._callbacks: List[Callable[[LogEntry], None]] = []
    
    async def start_monitoring(self, board: Board,
                               on_log: Optional[Callable[[LogEntry], None]] = None) -> bool:
        """Start mock monitoring."""
        board_id = board.board_id
        
        if board_id in self._tasks:
            return True
        
        self._buffers[board_id] = deque(maxlen=10000)
        
        task = asyncio.create_task(self._mock_generator(board_id))
        self._tasks[board_id] = task
        
        logger.info(f"[MOCK] Started monitoring {board_id}")
        return True
    
    async def stop_monitoring(self, board_id: str) -> bool:
        """Stop mock monitoring."""
        if board_id not in self._tasks:
            return False
        
        task = self._tasks.pop(board_id)
        task.cancel()
        
        logger.info(f"[MOCK] Stopped monitoring {board_id}")
        return True
    
    async def close_all(self):
        """Stop all monitoring."""
        board_ids = list(self._tasks.keys())
        for board_id in board_ids:
            await self.stop_monitoring(board_id)
    
    async def _mock_generator(self, board_id: str):
        """Generate mock log output."""
        import random
        
        messages = [
            "Booting Zephyr RTOS...",
            "*** Booting Zephyr OS...",
            "Hello World from Zephyr!",
            "Running on STM32F401RE",
            "System clock: 84 MHz",
            "UART initialized",
            "Main thread started",
            "LED toggling...",
            "Heartbeat: tick",
            "Heartbeat: tock",
        ]
        
        counter = 0
        while True:
            try:
                if counter < len(messages):
                    msg = messages[counter]
                else:
                    msg = f"Loop iteration {counter - len(messages)}"
                
                entry = LogEntry(
                    timestamp=datetime.now(),
                    board_id=board_id,
                    level="INFO",
                    message=msg
                )
                
                if board_id not in self._buffers:
                    self._buffers[board_id] = deque(maxlen=10000)
                self._buffers[board_id].append(entry)
                
                for callback in self._callbacks:
                    try:
                        callback(entry)
                    except Exception as e:
                        logger.error(f"Mock callback error: {e}")
                
                counter += 1
                await asyncio.sleep(1.0)  # 1 second between messages
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Mock generator error: {e}")
                await asyncio.sleep(1)
    
    def get_logs(self, board_id: str, since: Optional[datetime] = None,
                 max_lines: int = 1000) -> List[LogEntry]:
        """Get mock logs."""
        if board_id not in self._buffers:
            return []
        
        logs = list(self._buffers[board_id])
        
        if since:
            logs = [l for l in logs if l.timestamp >= since]
        
        return logs[-max_lines:]
    
    def register_callback(self, callback: Callable[[LogEntry], None]):
        """Register callback."""
        self._callbacks.append(callback)
    
    def is_monitoring(self, board_id: str) -> bool:
        """Check if monitoring."""
        return board_id in self._tasks
    
    def get_monitored_boards(self) -> List[str]:
        """Get monitored boards."""
        return list(self._tasks.keys())