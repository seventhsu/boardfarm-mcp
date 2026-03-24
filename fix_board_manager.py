#!/usr/bin/env python3
"""Script to fix sync/async duality in board_manager.py"""

import re

with open('src/mcp_boardfarm/board_manager.py', 'r') as f:
    content = f.read()

# 1. Change all 'with self._lock:' to 'async with self._lock:'
content = re.sub(r'(?<!async )with self\._lock:', 'async with self._lock:', content)

# 2. Remove threading import if present
content = re.sub(r'from threading import Lock\n?', '', content)

# 3. Make sure _lock is initialized as asyncio.Lock
content = re.sub(
    r'self\._lock = asyncio\.Lock\(\)  # Lock for atomic board operations',
    'self._lock = asyncio.Lock()  # Lock for atomic board operations',
    content
)

with open('src/mcp_boardfarm/board_manager.py', 'w') as f:
    f.write(content)

print("Done! Fixed board_manager.py sync/async duality.")
