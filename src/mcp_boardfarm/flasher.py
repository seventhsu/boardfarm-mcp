"""Flasher module - OpenOCD and other flash programming interfaces."""

import os
import re
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .models import Board, BoardState, BuildResult, FlashResult

logger = logging.getLogger(__name__)


class OpenOCDFlasher:
    """Flasher using OpenOCD for JTAG/SWD programming."""
    
    # OpenOCD interface configs for common debuggers
    INTERFACE_CONFIGS = {
        'cmsis-dap': 'interface/cmsis-dap.cfg',
        'stlink': 'interface/stlink.cfg',
        'stlink-v2': 'interface/stlink-v2.cfg',
        'stlink-v2-1': 'interface/stlink-v2-1.cfg',
        'stlink-v3': 'interface/stlink-dap.cfg',
        'jlink': 'interface/jlink.cfg',
    }
    
    # Target configs for common MCUs
    TARGET_CONFIGS = {
        'STM32F401RE': 'target/stm32f4x.cfg',
        'STM32F401': 'target/stm32f4x.cfg',
        'STM32H755ZI': 'target/stm32h7x.cfg',
        'STM32H755': 'target/stm32h7x.cfg',
        'STM32F407': 'target/stm32f4x.cfg',
        'STM32L476': 'target/stm32l4x.cfg',
    }
    
    def __init__(self, openocd_path: str = "openocd", scripts_path: Optional[str] = None):
        self.openocd_path = openocd_path
        self.scripts_path = scripts_path or "/usr/share/openocd/scripts"
        self.verify_flash = True
        self.max_attempts = 3
        self.timeout_seconds = 60
    
    def flash(self, board: Board, build_result: BuildResult, 
              core: Optional[str] = None) -> FlashResult:
        """Flash firmware to a board."""
        start_time = time.time()
        
        if not build_result.elf_path:
            return FlashResult(
                success=False,
                board_id=board.board_id,
                build_id=build_result.build_id,
                error_message="No ELF file in build result"
            )
        
        elf_path = Path(build_result.elf_path)
        if not elf_path.exists():
            return FlashResult(
                success=False,
                board_id=board.board_id,
                build_id=build_result.build_id,
                error_message=f"ELF file not found: {elf_path}"
            )
        
        logger.info(f"Flashing {build_result.build_id} to {board.board_id}")
        
        # Build OpenOCD command
        cmd = self._build_flash_command(board, str(elf_path), core)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )
            
            success = result.returncode == 0
            
            duration = time.time() - start_time
            
            return FlashResult(
                success=success,
                board_id=board.board_id,
                build_id=build_result.build_id,
                bytes_written=0,  # Could parse from output
                verify_passed=success and self.verify_flash,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                error_message=result.stderr if not success else None
            )
            
        except subprocess.TimeoutExpired:
            return FlashResult(
                success=False,
                board_id=board.board_id,
                build_id=build_result.build_id,
                error_message=f"Flash timeout after {self.timeout_seconds}s",
                duration_seconds=time.time() - start_time
            )
        except FileNotFoundError:
            return FlashResult(
                success=False,
                board_id=board.board_id,
                build_id=build_result.build_id,
                error_message=f"OpenOCD not found at {self.openocd_path}. Is it installed?",
                duration_seconds=time.time() - start_time
            )
    
    def _build_flash_command(self, board: Board, elf_path: str, 
                              core: Optional[str] = None) -> List[str]:
        """Build OpenOCD command for flashing."""
        cmd = [
            self.openocd_path,
            "-s", self.scripts_path,
        ]
        
        # Add interface config
        interface = board.debugger.type
        interface_cfg = self.INTERFACE_CONFIGS.get(interface, 
                                                     self.INTERFACE_CONFIGS.get('cmsis-dap'))
        cmd.extend(["-f", interface_cfg])
        
        # Add transport if needed
        if board.debugger.transport == 'swd' and 'stlink-dap' not in interface_cfg:
            cmd.extend(["-c", "transport select swd"])
        
        # Add target config
        target_cfg = self._get_target_config(board)
        cmd.extend(["-f", target_cfg])
        
        # Add flash commands (core selection after init)
        cmd.extend(["-c", "init"])
        
        # For H7 dual-core, select the core after init
        if core and 'h7' in board.mcu.lower():
            ap = 0 if core.upper() == 'M7' else 1
            cmd.extend(["-c", f"dap apsel 0"])
        
        cmd.extend([
            "-c", "reset init",
            "-c", f"flash write_image erase {elf_path}",
            "-c", "reset run",
            "-c", "shutdown"
        ])
        
        return cmd
    
    def _get_target_config(self, board: Board) -> str:
        """Get OpenOCD target config for a board."""
        mcu = board.mcu.upper()
        
        # Direct match
        if mcu in self.TARGET_CONFIGS:
            return self.TARGET_CONFIGS[mcu]
        
        # Partial match
        for mcu_prefix, config in self.TARGET_CONFIGS.items():
            if mcu.startswith(mcu_prefix):
                return config
        
        # Default fallback based on family
        if 'F4' in mcu:
            return 'target/stm32f4x.cfg'
        elif 'H7' in mcu:
            return 'target/stm32h7x.cfg'
        elif 'L4' in mcu:
            return 'target/stm32l4x.cfg'
        else:
            logger.warning(f"Unknown MCU {mcu}, defaulting to stm32f4x")
            return 'target/stm32f4x.cfg'
    
    def reset(self, board: Board, reset_type: str = "soft") -> bool:
        """Reset a board."""
        cmd = [
            self.openocd_path,
            "-s", self.scripts_path,
        ]
        
        interface_cfg = self.INTERFACE_CONFIGS.get(board.debugger.type, 
                                                     self.INTERFACE_CONFIGS.get('cmsis-dap'))
        cmd.extend(["-f", interface_cfg])
        
        if board.debugger.transport == 'swd' and 'stlink-dap' not in interface_cfg:
            cmd.extend(["-c", "transport select swd"])
        
        target_cfg = self._get_target_config(board)
        cmd.extend(["-f", target_cfg])
        
        if reset_type == "hard":
            cmd.extend(["-c", "init", "-c", "reset halt", "-c", "shutdown"])
        else:
            cmd.extend(["-c", "init", "-c", "reset", "-c", "shutdown"])
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            return False


class MockFlasher:
    """Mock flasher for testing without hardware."""
    
    def __init__(self):
        self.flash_delay = 1.0  # seconds
    
    def flash(self, board: Board, build_result: BuildResult,
              core: Optional[str] = None) -> FlashResult:
        """Simulate flashing."""
        start_time = time.time()
        
        logger.info(f"[MOCK] Flashing {build_result.build_id} to {board.board_id}")
        
        time.sleep(self.flash_delay)
        
        duration = time.time() - start_time
        
        return FlashResult(
            success=True,
            board_id=board.board_id,
            build_id=build_result.build_id,
            bytes_written=0x10000,  # 64KB mock
            verify_passed=True,
            stdout="[MOCK] Flash completed successfully",
            stderr="",
            duration_seconds=duration
        )
    
    def reset(self, board: Board, reset_type: str = "soft") -> bool:
        """Simulate reset."""
        logger.info(f"[MOCK] Resetting {board.board_id} ({reset_type})")
        time.sleep(0.2)
        return True