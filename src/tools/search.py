import os
import re
import fnmatch
from typing import List, Dict, Any, Optional

class SearchOperations:
    """
    Implements local search, grep, and directory traversal operations.
    Skips binary formats and standard system directories (venv, git, node_modules)
    to optimize context load.
    """

    def __init__(self):
        # Folders to completely ignore during recursive search
        self.exclude_dirs = {
            ".git", "node_modules", "venv", ".venv", "__pycache__", 
            ".idea", ".vscode", "dist", "build", "env", "bin", "obj"
        }
        # Binary or heavy file extensions to skip during content checks
        self.exclude_extensions = {
            ".exe", ".dll", ".zip", ".tar", ".gz", ".png", ".jpg", ".jpeg", 
            ".gif", ".pdf", ".mp4", ".mp3", ".wav", ".avi", ".mov", ".iso",
            ".bin", ".pyc", ".db", ".sqlite", ".ico", ".woff", ".woff2"
        }

    def list_dir(self, directory_path: str) -> List[Dict[str, Any]]:
        """
        List the contents of a directory. Returns file names, paths, sizes, and types.
        """
        norm_path = os.path.abspath(os.path.normpath(directory_path))
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Directory not found: {norm_path}")
        if not os.path.isdir(norm_path):
            raise ValueError(f"Path is not a directory: {norm_path}")

        results = []
        try:
            for entry in os.scandir(norm_path):
                stat = entry.stat()
                is_dir = entry.is_dir()
                results.append({
                    "name": entry.name,
                    "path": os.path.abspath(entry.path),
                    "is_directory": is_dir,
                    "size_bytes": stat.st_size if not is_dir else 0,
                    "modified_time": stat.st_mtime
                })
        except Exception as e:
            raise RuntimeError(f"Failed to list directory contents: {e}")

        # Sort: directories first, then alphabetically by name
        results.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))
        return results

    def grep_search(
        self, 
        search_path: str, 
        query: str, 
        case_insensitive: bool = True,
        is_regex: bool = False,
        include_globs: Optional[List[str]] = None,
        max_results: int = 20,
        truncate_content: int = 250
    ) -> Dict[str, Any]:
        """
        Recursively searches file content for a string or regex pattern.
        
        Args:
            search_path: Absolute path to search within.
            query: The search term or regex pattern.
            case_insensitive: Set to True to ignore case.
            is_regex: Set to True if query is a regex pattern.
            include_globs: Optional list of glob patterns to filter files.
            max_results: Maximum number of matches to return (default 20).
            truncate_content: Max characters per content line (default 250). 
                              Set to 0 for no truncation.
        
        Returns:
            Dict with:
              - "matches": List of match results (capped by max_results)
              - "total_found": Total matching lines found before any cap
              - "truncated": True if results were capped or content was truncated
              - "content_truncated": True if individual content lines were truncated
        """
        norm_path = os.path.abspath(os.path.normpath(search_path))
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Search path not found: {norm_path}")

        raw_matches = []
        content_truncated = False
        
        # Compile search regex/literal
        flags = re.IGNORECASE if case_insensitive else 0
        if is_regex:
            try:
                pattern = re.compile(query, flags)
            except Exception as e:
                raise ValueError(f"Invalid regex query pattern: {e}")
        else:
            # Literal string search
            pattern = re.compile(re.escape(query), flags)

        # Single file target check
        if os.path.isfile(norm_path):
            self._search_single_file(norm_path, pattern, raw_matches, truncate_content)
            capped = raw_matches[:max_results]
            total = len(raw_matches)
            if truncate_content > 0:
                for m in capped:
                    if m.get("_content_truncated"):
                        content_truncated = True
                        del m["_content_truncated"]
            return {
                "matches": capped,
                "total_found": total,
                "truncated": total > max_results or content_truncated,
                "content_truncated": content_truncated
            }

        # Recursive folder crawl
        for root, dirs, files in os.walk(norm_path):
            # Prune excluded directories in-place to avoid traversing them
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

            for file in files:
                file_path = os.path.join(root, file)
                _, ext = os.path.splitext(file.lower())

                if ext in self.exclude_extensions:
                    continue

                # Filter by file glob pattern if specified (e.g. *.py)
                if include_globs:
                    matched_glob = False
                    for glob in include_globs:
                        if fnmatch.fnmatch(file.lower(), glob.lower()):
                            matched_glob = True
                            break
                    if not matched_glob:
                        continue

                self._search_single_file(file_path, pattern, raw_matches, truncate_content)
                
                # Stop early if we already have enough matches
                if len(raw_matches) >= max_results:
                    # Keep crawling to count total, but cap at a reasonable ceiling
                    # to avoid excessive I/O
                    if len(raw_matches) >= 500:
                        break

        total = len(raw_matches)
        capped = raw_matches[:max_results]
        
        # Check for content truncation and strip internal flags
        if truncate_content > 0:
            for m in capped:
                if m.get("_content_truncated"):
                    content_truncated = True
                    del m["_content_truncated"]

        return {
            "matches": capped,
            "total_found": total,
            "truncated": total > max_results or content_truncated,
            "content_truncated": content_truncated
        }

    def _search_single_file(self, file_path: str, pattern: re.Pattern, 
                            matches: List[Dict[str, Any]], truncate_content: int = 250):
        """
        Scan a single text file line by line and append match reports.
        If truncate_content > 0, each content line is capped at that many characters.
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_idx, line in enumerate(f):
                    if pattern.search(line):
                        content = line.strip()
                        truncated = False
                        if truncate_content > 0 and len(content) > truncate_content:
                            content = content[:truncate_content] + "... [truncated]"
                            truncated = True
                        entry = {
                            "file": os.path.abspath(file_path),
                            "line_number": line_idx + 1,
                            "content": content
                        }
                        if truncated:
                            entry["_content_truncated"] = True
                        matches.append(entry)
        except Exception:
            # Silently skip file read failures (permissions/binary lockups)
            pass
