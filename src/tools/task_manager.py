import os
import subprocess
import time
import uuid
import threading
from typing import Dict, Any, List, Optional

class TaskManager:
    """
    Manages non-blocking background subprocesses on Windows.
    Spawns processes, registers task IDs, writes live streams to log files,
    handles stdin input, and terminates tasks.
    """

    def __init__(self, log_dir: str):
        self.log_dir = os.path.abspath(os.path.normpath(log_dir))
        os.makedirs(self.log_dir, exist_ok=True)
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.log_callback = None

    def start_task(self, command: str, cwd: str) -> str:
        """
        Spawns a PowerShell command as a non-blocking background task.
        Returns:
            task_id (str)
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        log_file = os.path.join(self.log_dir, f"{task_id}.log")

        # Spawn Powershell process on Windows with stdin/stdout/stderr piped
        # Using CREATE_NEW_PROCESS_GROUP to allow safe interrupt signals
        ps_cmd = ["powershell.exe", "-NoProfile", "-Command", command]
        
        try:
            process = subprocess.Popen(
                ps_cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )

            task_info = {
                "id": task_id,
                "command": command,
                "cwd": cwd,
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "process": process,
                "log_file": log_file,
                "status": "RUNNING",
                "exit_code": None
            }

            self.active_tasks[task_id] = task_info

            # Start background threads to consume stdout and stderr to the log file
            threading.Thread(
                target=self._log_stream_worker,
                args=(process.stdout, log_file, task_id),
                daemon=True
            ).start()
            
            threading.Thread(
                target=self._log_stream_worker,
                args=(process.stderr, log_file, task_id),
                daemon=True
            ).start()

            return task_id

        except Exception as e:
            raise RuntimeError(f"Failed to spawn background task: {e}")

    def _log_stream_worker(self, stream, log_path: str, task_id: str):
        """
        Background worker that consumes pipe lines and writes them to a local log file.
        """
        try:
            with open(log_path, "a", encoding="utf-8") as log:
                for line in stream:
                    log.write(line)
                    log.flush()
                    if self.log_callback:
                        try:
                            self.log_callback(task_id, line)
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            # Check if process has finished and update status
            task = self.active_tasks.get(task_id)
            if task:
                proc = task["process"]
                if proc.poll() is not None:
                    task["status"] = "COMPLETED"
                    task["exit_code"] = proc.returncode

    def list_tasks(self) -> List[Dict[str, Any]]:
        """
        Returns details of all active and completed background tasks.
        """
        task_list = []
        for tid, task in list(self.active_tasks.items()):
            # Re-check status of the process
            proc = task["process"]
            poll = proc.poll()
            if poll is not None:
                task["status"] = "COMPLETED"
                task["exit_code"] = poll

            task_list.append({
                "taskId": task["id"],
                "command": task["command"],
                "cwd": task["cwd"],
                "startTime": task["start_time"],
                "status": task["status"],
                "exitCode": task["exit_code"],
                "logFile": task["log_file"]
            })
        return task_list

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get details and log summary of a specific task.
        """
        task = self.active_tasks.get(task_id)
        if not task:
            raise KeyError(f"Task ID '{task_id}' not found.")

        proc = task["process"]
        poll = proc.poll()
        if poll is not None:
            task["status"] = "COMPLETED"
            task["exit_code"] = poll

        # Read last 20 lines of log file
        log_snippet = []
        if os.path.exists(task["log_file"]):
            try:
                with open(task["log_file"], "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    log_snippet = lines[-20:]
            except Exception:
                log_snippet = ["[Error reading log file]"]

        return {
            "taskId": task["id"],
            "command": task["command"],
            "status": task["status"],
            "exitCode": task["exit_code"],
            "logFile": task["log_file"],
            "logTail": "".join(log_snippet)
        }

    def send_input(self, task_id: str, input_str: str) -> str:
        """
        Send text input to the stdin pipe of a running task.
        """
        task = self.active_tasks.get(task_id)
        if not task:
            raise KeyError(f"Task ID '{task_id}' not found.")

        if task["status"] != "RUNNING":
            return f"Error: Task '{task_id}' is not running (Status: {task['status']})."

        proc = task["process"]
        try:
            # Write input string with trailing newline to stdin
            proc.stdin.write(input_str + "\n")
            proc.stdin.flush()
            return f"[+] Successfully sent input to task: {task_id}"
        except Exception as e:
            return f"Error sending input to task '{task_id}': {e}"

    def kill_task(self, task_id: str) -> str:
        """
        Kills a running background task.
        """
        task = self.active_tasks.get(task_id)
        if not task:
            raise KeyError(f"Task ID '{task_id}' not found.")

        if task["status"] != "RUNNING":
            return f"Warning: Task '{task_id}' is already terminated (Status: {task['status']})."

        proc = task["process"]
        try:
            proc.terminate() # Request termination
            time.sleep(0.5)
            if proc.poll() is None:
                proc.kill() # Force kill if still running
            
            task["status"] = "KILLED"
            task["exit_code"] = proc.poll()
            return f"[+] Task '{task_id}' terminated successfully."
        except Exception as e:
            return f"Error terminating task '{task_id}': {e}"
