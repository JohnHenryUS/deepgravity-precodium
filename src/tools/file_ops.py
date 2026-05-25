import os
from typing import Optional, Tuple
from src.safety import SafetyGuardrails

class FileOperations:
    """
    Handles Windows-native file operations with built-in diff safety audits.
    """

    def __init__(self, guardrails: SafetyGuardrails):
        self.guardrails = guardrails

    def normalize_path(self, path: str) -> str:
        """
        Normalize file path to Windows syntax (backslashes, clean drive roots).
        """
        return os.path.abspath(os.path.normpath(path))

    def view_file(
        self, 
        absolute_path: str, 
        start_line: Optional[int] = None, 
        end_line: Optional[int] = None
    ) -> str:
        """
        Read file contents. Supports range constraints and protects against binary loads.
        """
        norm_path = self.normalize_path(absolute_path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"File not found: {norm_path}")

        # Check size constraints or binary attributes
        try:
            with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            raise RuntimeError(f"Failed to read file: {e}")

        total_lines = len(lines)
        start = (start_line - 1) if start_line else 0
        end = end_line if end_line else total_lines

        # Clamp boundaries
        start = max(0, min(start, total_lines))
        end = max(0, min(end, total_lines))

        if start > end:
            start, end = end, start

        # Cap output at 800 lines to prevent context overloading
        if (end - start) > 800:
            end = start + 800
            truncated_marker = f"\n... [Output capped at 800 lines. Total lines: {total_lines}]"
        else:
            truncated_marker = ""

        selected_lines = lines[start:end]
        output_lines = [f"{start + i + 1}: {line}" for i, line in enumerate(selected_lines)]
        
        return "".join(output_lines) + truncated_marker

    def write_file(
        self, 
        absolute_path: str, 
        content: str, 
        overwrite: bool = False
    ) -> str:
        """
        Create a new file or completely overwrite an existing file.
        Invokes diff validation.
        """
        norm_path = self.normalize_path(absolute_path)
        is_new = not os.path.exists(norm_path)

        if not is_new and not overwrite:
            raise FileExistsError(f"File already exists: {norm_path}. Set overwrite=True to force write.")

        old_content = ""
        if not is_new:
            with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                old_content = f.read()

        # Call Safe Deployment Prompt
        approved = self.guardrails.show_write_prompt(norm_path, old_content, content, is_new=is_new)
        if not approved:
            return f"[-] Write operation rejected by user for file: {norm_path}"

        # Write to disk
        os.makedirs(os.path.dirname(norm_path), exist_ok=True)
        with open(norm_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Notify the editor to open this file
        if self.guardrails.open_file_callback:
            self.guardrails.open_file_callback(norm_path)

        return f"[+] Successfully written file: {norm_path}"

    def edit_file_content(
        self, 
        absolute_path: str, 
        target_content: str, 
        replacement_content: str
    ) -> str:
        """
        Locates target_content in a file and replaces it with replacement_content.
        Invokes diff validation.
        """
        norm_path = self.normalize_path(absolute_path)
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"File not found: {norm_path}")

        with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
            old_content = f.read()

        if target_content not in old_content:
            raise ValueError("Target content was not found in the file. Replacements must be exact matches.")

        # Compute count of occurrences
        occurrences = old_content.count(target_content)
        if occurrences > 1:
            raise ValueError(f"Target content was found {occurrences} times. Must be a unique target range.")

        # Perform replacement in memory
        new_content = old_content.replace(target_content, replacement_content, 1)

        # Call Safe Deployment Prompt
        approved = self.guardrails.show_write_prompt(norm_path, old_content, new_content, is_new=False)
        if not approved:
            return f"[-] Edit operation rejected by user for file: {norm_path}"

        with open(norm_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Notify the editor to open this file
        if self.guardrails.open_file_callback:
            self.guardrails.open_file_callback(norm_path)

        return f"[+] Successfully updated file: {norm_path}"
