"""MCP Board Farm - AI-controllable embedded hardware board farm."""

__version__ = "0.1.0"
__author__ = "MCP Board Farm Contributors"

from .models import Board, BoardState, BuildConfig
from .board_manager import BoardManager

__all__ = [
    "Board",
    "BoardState",
    "BuildConfig",
    "BoardManager",
]
