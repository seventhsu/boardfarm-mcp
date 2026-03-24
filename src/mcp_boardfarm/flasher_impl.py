"""Flasher module with auto-fallback: PyOCD -> ST-Link -> OpenOCD."""

import shutil
from .flasher_impl import PyOCDFlasher, STLinkFlasher, OpenOCDFlasher, MockFlasher

class AutoFlasher:
    """Manufacturer-agnostic flasher with automatic fallback."""
    
    def __init__(self):
        self.flashers = []
        
        # Try PyOCD first (most manufacturer-agnostic)
        if shutil.which('pyocd'):
            self.flashers.append(PyOCDFlasher())
        
        # Fallback to ST-Link (STM32 specific)
        if shutil.which('st-flash'):
            self.flashers.append(STLinkFlasher())
        
        # Fallback to OpenOCD (generic)
        if shutil.which('openocd'):
            self.flashers.append(OpenOCDFlasher())
        
        if not self.flashers:
            raise RuntimeError("No flash tools found (tried: pyocd, st-flash, openocd)")
    
    def flash(self, board, build_result, core=None):
        """Try each flasher in order until one succeeds."""
        errors = []
        
        for flasher in self.flashers:
            try:
                result = flasher.flash(board, build_result, core)
                if result.success:
                    return result
                errors.append(f"{flasher.__class__.__name__}: {result.error_message}")
            except Exception as e:
                errors.append(f"{flasher.__class__.__name__}: {e}")
        
        # All failed
        from .models import FlashResult
        return FlashResult(
            success=False,
            board_id=board.board_id,
            build_id=build_result.build_id,
            error_message="All flashers failed:\n" + "\n".join(errors)
        )
    
    def reset(self, board, reset_type="soft"):
        for flasher in self.flashers:
            try:
                if flasher.reset(board, reset_type):
                    return True
            except:
                continue
        return False
