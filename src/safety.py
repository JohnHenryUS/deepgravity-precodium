import re
import difflib
from typing import Dict, Any, List, Optional

class SafetyGuardrails:
    """
    Implements the Safe Deployment Protocol.
    Verifies shell commands and edits, displays diff previews, and manages user confirmations.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        safety_cfg = config.get("safety", {})
        self.require_writes = safety_cfg.get("require_confirmation_for_writes", True)
        self.require_commands = safety_cfg.get("require_confirmation_for_commands", True)
        self.blocked_patterns = safety_cfg.get("blocked_command_patterns", [])
        self.command_approval_callback = None
        self.write_approval_callback = None
        self.open_file_callback = None


    def verify_command(self, command: str) -> bool:
        """
        Scan a command against blocked execution patterns.
        Returns:
            True if allowed, False if blocked.
        """
        for pattern in self.blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                print(f"\n[SAFETY BLOCK] Command blocked by pattern rule: '{pattern}'")
                return False
        return True

    def show_command_prompt(self, command: str, cwd: str) -> bool:
        """
        Displays a CLI prompt seeking user permission to run a command.
        """
        if not self.require_commands:
            return True

        if not self.verify_command(command):
            return False

        if self.command_approval_callback:
            return self.command_approval_callback(command, cwd)

        print("\n==================================================")
        print("[PROPOSED SHELL COMMAND]")
        print("==================================================")
        print(f"CWD:     {cwd}")
        print(f"Command: {command}")
        print("--------------------------------------------------")
        
        try:
            choice = input("Approve command execution? (y/N): ").strip().lower()
            return choice == 'y'
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Command execution aborted by user.")
            return False

    def generate_diff(self, file_path: str, old_content: str, new_content: str) -> List[str]:
        """
        Generates a unified diff of proposed file modifications.
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines, 
            new_lines, 
            fromfile=f"a/{file_path}", 
            tofile=f"b/{file_path}"
        )
        return list(diff)

    def show_write_prompt(self, file_path: str, old_content: str, new_content: str, is_new: bool = False) -> bool:
        """
        Displays a CLI diff view and seeks user permission to write/edit a file.
        """
        if not self.require_writes:
            return True

        if self.write_approval_callback:
            return self.write_approval_callback(file_path, old_content, new_content, is_new)

        print("\n==================================================")
        print("[PROPOSED FILE MODIFICATION]")
        print("==================================================")
        print(f"File:   {file_path}")
        print(f"Action: {'Create New' if is_new else 'Edit Content'}")
        print("--------------------------------------------------")

        if is_new:
            # Show a preview of the new content (up to 15 lines)
            lines = new_content.splitlines()
            for line in lines[:15]:
                print(f"+ {line}")
            if len(lines) > 15:
                print(f"+ ... ({len(lines) - 15} more lines)")
        else:
            diff_lines = self.generate_diff(file_path, old_content, new_content)
            # Print diff with color markers
            for line in diff_lines[:40]:  # Cap console output at 40 lines
                if line.startswith('+') and not line.startswith('+++'):
                    print(f"\033[92m{line.rstrip()}\033[0m")  # Green
                elif line.startswith('-') and not line.startswith('---'):
                    print(f"\033[91m{line.rstrip()}\033[0m")  # Red
                else:
                    print(line.rstrip())
            if len(diff_lines) > 40:
                print(f"... ({len(diff_lines) - 40} more lines of changes)")

        print("--------------------------------------------------")
        
        try:
            choice = input(f"Approve changes to {file_path}? (y/N): ").strip().lower()
            return choice == 'y'
        except (KeyboardInterrupt, EOFError):
            print("\n[-] File modifications aborted by user.")
            return False
