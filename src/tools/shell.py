import subprocess
import sys
from typing import Tuple
from src.safety import SafetyGuardrails

class ShellCommandRunner:
    """
    Executes Powershell commands on Windows with real-time stream output
    and mandatory approval guardrails.
    """

    def __init__(self, guardrails: SafetyGuardrails):
        self.guardrails = guardrails

    def run_command(self, command: str, cwd: str) -> Tuple[int, str]:
        """
        Executes a shell command via PowerShell after user confirmation.
        Streams stdout and stderr directly to console in real time.
        """
        # Call Safe Deployment Prompt
        approved = self.guardrails.show_command_prompt(command, cwd)
        if not approved:
            return -1, "[-] Command execution aborted by user."

        # Setup powershell process on Windows
        # Using -NoProfile to speed up activation and avoid local profiles interference
        ps_cmd = ["powershell.exe", "-NoProfile", "-Command", command]

        try:
            # Launch process with stdout and stderr combined to avoid pipe buffer deadlock
            process = subprocess.Popen(
                ps_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1, # Line buffered
                shell=False
            )

            stdout_output = []
            
            # Read combined output line by line in real time and write to local sys.stdout
            while True:
                # Read a line from stdout (which now includes stderr)
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    stdout_output.append(line)

            # Wait for exit status
            exit_code = process.wait()
            combined_output = "".join(stdout_output)

            return exit_code, combined_output

        except Exception as e:
            return 1, f"[-] Failed to execute subprocess: {e}"
