# Tool Result Cache — Token Bloat Mitigation

## Problem

Tool results account for ~63% of conversation history size. A single `view_file` call returning 137KB of source code gets stored in the conversation history and shipped to the provider API on every subsequent turn, even when the content is never referenced again.

## Design

### Cache Storage

Location: `logs/tool_cache/<ref_id>.json`

Each cache entry:

```json
{
  "ref_id": "a1b2c3d4",
  "tool": "view_file",
  "tool_args": {"absolute_path": "src/orchestrator.py"},
  "content": "<full tool result text>",
  "content_size": 137000,
  "timestamp": 1780198000.0,
  "summary": "Content from view_file(src/orchestrator.py): 1: import os\n2: import json..."
}
```

`ref_id`: SHA256 of content, first 8 hex chars. Collision risk: negligible for this use case. Also provides content deduplication — identical results share one cache entry.

### Threshold

Only cache results larger than 1,024 bytes (1 KB). Smaller results pass through normally — no overhead for trivial tool returns.

### Cache Pointer Format

When a tool result exceeds threshold, the `content` field in the conversation history message is replaced with a pointer string:

```
[CACHED:a1b2c3d4] view_file(src/orchestrator.py) — 134KB
```

Format is deliberately machine-parseable:
- `[CACHED:<ref_id>]` = unique identifier
- `<tool_name>(<args_preview>)` = human-readable description
- `— <size>` = original size for diagnostics

The session file on disk stores this pointer instead of the full content. The full content lives in `logs/tool_cache/<ref_id>.json`.

### New Tool: `read_cache`

Added to `config/tools_schema.json`:

```json
{
  "name": "read_cache",
  "description": "Retrieve the full content of a cached tool result by reference ID. Use when you need the complete data behind a [CACHED:...] pointer.",
  "parameters": {
    "type": "object",
    "properties": {
      "ref_id": {
        "type": "string",
        "description": "The reference ID from a [CACHED:...] pointer (e.g., 'a1b2c3d4')"
      }
    },
    "required": ["ref_id"]
  }
}
```

Returns the full cached content string. If the ref_id is not found, returns: `[CACHE MISS] No cached result for ref_id '<id>'. It may have been evicted or never cached.`

### System Prompt Injection

A brief instruction appended to the system prompt (at the end of the ACTIVE BRAID section):

```
You have a tool result cache. When you see [CACHED:<ref_id>] in a tool message,
the full result is stored on disk. Use the read_cache tool to retrieve it if
you need the complete data. Otherwise, the pointer summary is sufficient context.
```

### Implementation Points

#### 1. `src/tool_cache.py` — New module

```python
class ToolResultCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
    
    def store(self, tool_name: str, tool_args: dict, content: str) -> str:
        """Store a tool result and return ref_id. Returns None if under threshold."""
        if len(content) < 1024:
            return None
        ref_id = hashlib.sha256(content.encode()).hexdigest()[:8]
        entry = {
            "ref_id": ref_id,
            "tool": tool_name,
            "tool_args": tool_args,
            "content": content,
            "content_size": len(content),
            "timestamp": time.time(),
            "summary": content[:200] + ("..." if len(content) > 200 else "")
        }
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(os.path.join(self.cache_dir, f"{ref_id}.json"), "w") as f:
            json.dump(entry, f)
        return ref_id
    
    def retrieve(self, ref_id: str) -> str:
        """Return cached content by ref_id, or None if missing."""
        path = os.path.join(self.cache_dir, f"{ref_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            entry = json.load(f)
        return entry["content"]
    
    def make_pointer(self, ref_id: str, tool_name: str, tool_args: dict, size: int) -> str:
        """Build a cache pointer string for the conversation history."""
        args_summary = json.dumps(tool_args)
        if len(args_summary) > 80:
            args_summary = args_summary[:80] + "..."
        size_label = f"{size:,}B" if size < 1024*1024 else f"{size/1024/1024:.1f}MB"
        return f"[CACHED:{ref_id}] {tool_name}({args_summary}) — {size_label}"
```

#### 2. Modify `orchestrator.py` — `execute_tool()` method

After executing a tool and getting the result:

```python
# After line where result is computed:
if isinstance(result, str) and len(result) > 1024:
    ref_id = self.tool_cache.store(name, args, result)
    if ref_id:
        result = self.tool_cache.make_pointer(ref_id, name, args, len(result))
```

#### 3. Modify `orchestrator.py` — Tool dispatch

Add `read_cache` to the tool dispatch in `execute_tool()`:

```python
elif name == "read_cache":
    ref_id = args.get("ref_id", "")
    cached = self.tool_cache.retrieve(ref_id)
    if cached:
        result = cached
    else:
        result = f"[CACHE MISS] No cached result for ref_id '{ref_id}'."
```

#### 4. Modify `orchestrator.py` — `__init__`

```python
from src.tool_cache import ToolResultCache
# ...
self.tool_cache = ToolResultCache(os.path.join(self.config_dir, "logs", "tool_cache"))
```

#### 5. Modify `config/tools_schema.json`

Add `read_cache` schema.

#### 6. Modify system prompt hydration

Append cache usage instruction to the system prompt in `hydrate_system_prompt()`.

## X-Mode Compatibility

When depth is X and keystore is unlocked:
- Cache entries are **plaintext** on disk (they map to specific tool calls, not conversation turns)
- The conversation history still only holds the pointer, not the content
- The pointer format doesn't reveal sensitive content — just metadata about what was cached
- If X-mode requires full encryption, the cache entry content can also be encrypted with the session key

## Session Load / Replay

When loading an old session that was saved without the cache:
- Tool results have full content, not pointers
- No change needed — old sessions work as-is

When loading a new session (with pointers):
- The cache directory is checked for each `[CACHED:...]` pointer
- If the cache entry exists, the pointer is replaced with full content on load
- If the cache entry is missing (evicted/corrupted), the pointer stays and `read_cache` will return a miss

## Graceful Degradation

If `read_cache` fails:
1. Missing ref_id → clear error message → model can ask user to re-run the operation
2. Corrupted cache file → clear error → model can ask user to re-run
3. Cache directory unwritable → `store()` silently fails, result passes through as full content (no pointer)

## Files Changed

| File | Change |
|------|--------|
| `src/tool_cache.py` | New module |
| `src/orchestrator.py` | Import + init cache, modify `execute_tool()`, add `read_cache` dispatch |
| `config/tools_schema.json` | Add `read_cache` tool definition |
| `src/orchestrator.py` — `hydrate_system_prompt()` | Append cache instruction |

## Not In Scope (for now)

- **Cache eviction policy** — disk is cheap, keep everything
- **Cross-session cache sharing** — cache is per-session for now
- **Encrypted cache files** — defer to X-mode integration phase
