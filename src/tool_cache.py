"""
Tool Result Cache — stores large tool outputs on disk and replaces them
with lightweight pointers in conversation history to reduce token bloat.

Cache entries are stored in a flat directory as JSON files keyed by
a content-hash ref_id. Identical tool results deduplicate automatically.
"""

import os
import hashlib
import json
import time
from typing import Optional

# Results smaller than this pass through without caching
CACHE_THRESHOLD = 1024  # 1 KB


class ToolResultCache:
    """Manages on-disk caching of large tool execution results."""

    def __init__(self, cache_dir: str):
        """
        Args:
            cache_dir: Absolute path to the cache directory (e.g. logs/tool_cache/).
        """
        self.cache_dir = cache_dir

    def store(self, tool_name: str, tool_args: dict, content: str) -> Optional[str]:
        """
        Store a tool result in the cache.

        Returns a ref_id string if the result was cached, or None if the
        result was under the threshold and passed through unchanged.
        Returns None if the cache directory is unwritable (graceful degradation).
        """
        if len(content) < CACHE_THRESHOLD:
            return None

        ref_id = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]

        entry = {
            "ref_id": ref_id,
            "tool": tool_name,
            "tool_args": tool_args,
            "content": content,
            "content_size": len(content),
            "timestamp": time.time(),
            "summary": content[:200] + ("..." if len(content) > 200 else ""),
        }

        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            path = os.path.join(self.cache_dir, f"{ref_id}.json")
            # Only write if not already cached (deduplication)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(entry, f, indent=2)
            return ref_id
        except (OSError, PermissionError):
            return None  # cache unwritable — graceful fallback to full content

    def retrieve(self, ref_id: str) -> Optional[str]:
        """
        Retrieve cached content by ref_id.

        Returns the full content string, or None if the ref_id is not found
        or the cache file is corrupted.
        """
        path = os.path.join(self.cache_dir, f"{ref_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            return entry.get("content")
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def make_pointer(self, ref_id: str, tool_name: str,
                     tool_args: dict, size: int) -> str:
        """
        Build a human- and machine-readable cache pointer string.

        Format: [CACHED:<ref_id>] <tool>(<args>) -- <size>
        Example: [CACHED:a1b2c3d4] view_file(src/orchestrator.py) -- 134KB
        """
        args_summary = json.dumps(tool_args, ensure_ascii=False)
        if len(args_summary) > 80:
            args_summary = args_summary[:80] + "..."

        if size < 1024:
            size_label = f"{size}B"
        elif size < 1024 * 1024:
            size_label = f"{size // 1024}KB"
        else:
            size_label = f"{size / 1024 / 1024:.1f}MB"

        return f"[CACHED:{ref_id}] {tool_name}({args_summary}) -- {size_label}"
