#!/usr/bin/env python3
"""Script to fix sync/async duality in board_queue.py"""

import re

with open('src/mcp_boardfarm/board_queue.py', 'r') as f:
    content = f.read()

# 1. Change all 'with self._lock:' to 'async with self._lock:'
content = re.sub(r'(?<!async )with self\._lock:', 'async with self._lock:', content)

# 2. Remove assign_board_sync method entirely
pattern = r'    def assign_board_sync\(self.*?(?=\n    def |\n    async def |\n\nclass |\n# Singleton|$)'
content = re.sub(pattern, '', content, flags=re.DOTALL)

# 3. Also need to make add_request, get_entry, get_position, etc. async
# Let's make methods that use the lock async
methods_to_async = [
    'def add_request',
    'def get_entry', 
    'def get_position',
    'def find_best_match',
    'def get_next_for_board',
    'def complete_job',
    'def cancel_request',
    'def list_queue',
    'def get_queue_summary',
    'def cleanup_expired',
    'def apply_priority_boost',
    'def _save',
    'def _load',
    'def _sort_queue',
]

for method in methods_to_async:
    # Change 'def method' to 'async def method' if not already async
    pattern = f'(?<!async )\\b{method}\\b'
    content = re.sub(pattern, f'async {method}', content)

with open('src/mcp_boardfarm/board_queue.py', 'w') as f:
    f.write(content)

print("Done! Fixed sync/async duality.")
