"""
Idle Watchdog — monitors orchestrator health during inactive periods.

Runs as a background daemon thread. On idle timeout (default 30 min),
saves a state snapshot for crash-recovery pickup and signals shutdown.

Not content monitoring — purely process-and-connection health telemetry.
"""

import os
import json
import time
import threading
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("watchtower")

# ── Default configuration ───────────────────────────────────────────

DEFAULT_CONFIG = {
    "enabled": True,
    "ping_interval": 120,         # seconds between provider pings during idle
    "max_idle_pings": 15,         # 15 pings x 120s = 30 min before idle shutdown
    "task_stuck_threshold": 600,  # 10 min — a task running this long without progress is suspect
    "mode": "auto"                # "auto" | "ondemand" | "disabled"
}


class IdleWatchdog:
    """
    Background thread that monitors orchestrator health during user inactivity.
    
    Responsibilities:
    - Tracks time since last user activity
    - Pings the active provider every `ping_interval` seconds during idle
    - Checks background tasks for stuck processes (>task_stuck_threshold)
    - After max_idle_pings with no activity and no running tasks, saves state and stops
    """

    def __init__(self, orchestrator, config: Optional[Dict] = None):
        self.orchestrator = orchestrator
        cfg = {**DEFAULT_CONFIG}
        if config:
            cfg.update(config)
        
        self.enabled = cfg["enabled"]
        self.ping_interval = cfg["ping_interval"]
        self.max_idle_pings = cfg["max_idle_pings"]
        self.task_stuck_threshold = cfg["task_stuck_threshold"]
        self.mode = cfg["mode"]

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._idle_ping_count = 0
        self._last_user_activity = time.time()
        self._last_provider_ok = True
        self._stuck_tasks_logged = set()  # track which tasks we've already warned about

        # Snapshot path — written on idle timeout, checked on restart
        log_dir = os.path.join(os.path.dirname(orchestrator.config_path), "logs")
        os.makedirs(log_dir, exist_ok=True)
        self._snapshot_path = os.path.join(log_dir, "idle_snapshot.json")
        self._heartbeat_path = getattr(orchestrator, "_heartbeat_path", 
                                       os.path.join(log_dir, "heartbeat.json"))
        
        # Inactivity flag — checked by chat worker on next message
        self.went_idle = False
        self.idle_message = ""

    # ── Public API ───────────────────────────────────────────────────

    def start(self):
        """Start the watchdog background thread."""
        if not self.enabled or self.mode == "disabled":
            return
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="idle-watchdog")
        self._thread.start()
        logger.info("[Watchtower] Started (ping=%ss, max_idle=%s pings, stuck=%ss)",
                     self.ping_interval, self.max_idle_pings, self.task_stuck_threshold)

    def stop(self):
        """Signal the watchdog to stop."""
        self._running = False
        # Also clean up snapshot if it exists — we're shutting down cleanly
        self._clear_snapshot()

    def ping_user_activity(self):
        """Called whenever the user sends a message or interacts. Resets idle counter."""
        self._last_user_activity = time.time()
        self._idle_ping_count = 0
        self.went_idle = False
        self.idle_message = ""

    def get_status(self) -> Dict:
        """Return current watchdog status for display / heartbeat."""
        idle_seconds = time.time() - self._last_user_activity
        return {
            "enabled": self.enabled,
            "running": self._running,
            "idle_seconds": round(idle_seconds, 1),
            "idle_pings": self._idle_ping_count,
            "max_idle_pings": self.max_idle_pings,
            "provider_ok": self._last_provider_ok,
            "went_idle": self.went_idle,
            "idle_message": self.idle_message,
            "mode": self.mode
        }

    def check_snapshot_on_restart(self) -> Optional[Dict]:
        """
        Called on orchestrator initialization. If an idle snapshot exists,
        returns it so the system can report what happened.
        Deletes the snapshot after reading.
        """
        if not os.path.exists(self._snapshot_path):
            return None
        try:
            with open(self._snapshot_path, "r") as f:
                snapshot = json.load(f)
            self._clear_snapshot()
            return snapshot
        except Exception:
            self._clear_snapshot()
            return None

    # ── Internal loop ────────────────────────────────────────────────

    def _run(self):
        while self._running:
            time.sleep(self.ping_interval)
            if not self._running:
                break

            idle_time = time.time() - self._last_user_activity

            # If user has been active recently, reset and skip
            if idle_time < self.ping_interval * 0.8:
                self._idle_ping_count = 0
                continue

            self._idle_ping_count += 1

            # 1. Ping the provider
            self._ping_provider()

            # 2. Check for stuck tasks
            self._check_tasks()

            # 3. Evaluate idle timeout
            if self._idle_ping_count >= self.max_idle_pings:
                self._handle_idle_timeout()

    # ── Provider Ping ────────────────────────────────────────────────

    def _ping_provider(self):
        """
        Lightweight check against the active provider's base URL.
        Not a model query — just connectivity check.
        """
        try:
            import requests as http_requests
            # Get the active provider's base URL
            routing = self.orchestrator.config.get("api", {}).get("routing", {})
            active_provider_name = routing.get("attunement_core") or routing.get("primary_orchestrator", "")
            providers = self.orchestrator.config.get("api", {}).get("providers", {})
            prov_cfg = providers.get(active_provider_name, {})
            base_url = prov_cfg.get("base_url", "").rstrip("/")
            
            if not base_url:
                self._last_provider_ok = False
                return

            # Try a lightweight GET to the base URL or /v1/models
            api_key = prov_cfg.get("api_key", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            
            for endpoint in ["/v1/models", "/api/models", ""]:
                try:
                    resp = http_requests.get(
                        f"{base_url}{endpoint}", 
                        headers=headers, 
                        timeout=10
                    )
                    if resp.status_code < 500:  # Any non-server-error is "alive"
                        self._last_provider_ok = True
                        return
                except Exception:
                    continue

            self._last_provider_ok = False
            logger.warning("[Watchtower] Provider ping failed for %s", base_url)

        except ImportError:
            self._last_provider_ok = True  # can't check, assume alive
        except Exception:
            self._last_provider_ok = False

    # ── Task Stuck Detection ─────────────────────────────────────────

    def _check_tasks(self):
        """Check running tasks for age without output."""
        if not hasattr(self.orchestrator, "task_manager"):
            return

        tasks = self.orchestrator.task_manager.list_tasks()
        now = time.time()

        for task in tasks:
            if task.get("status") != "RUNNING":
                continue

            task_id = task.get("taskId", "")
            if task_id in self._stuck_tasks_logged:
                continue

            # Check how long the task has been running
            start_time_str = task.get("startTime", "")
            try:
                # Parse start time — format is "2026-05-30 12:00:00"
                start_epoch = time.mktime(time.strptime(start_time_str, "%Y-%m-%d %H:%M:%S"))
                age = now - start_epoch

                if age > self.task_stuck_threshold:
                    # Check log file for recent output
                    log_file = task.get("logFile", "")
                    recent_output = ""
                    if log_file and os.path.exists(log_file):
                        try:
                            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                                lines = f.readlines()
                            # Last 5 lines
                            recent_output = "".join(lines[-5:]).strip()
                        except Exception:
                            pass

                    logger.warning(
                        "[Watchtower] ⚠ Task %s running for %.0fs without completion. "
                        "Recent output: %s",
                        task_id, age, recent_output[:200] if recent_output else "(no output)"
                    )
                    self._stuck_tasks_logged.add(task_id)
            except Exception:
                pass

    # ── Idle Timeout Handling ────────────────────────────────────────

    def _handle_idle_timeout(self):
        """
        Called after max_idle_pings with no user activity and no running tasks.
        Saves a state snapshot and records that we went idle.
        Does NOT stop the orchestrator — just the watchdog monitoring.
        """
        # Check for running tasks
        has_running = False
        if hasattr(self.orchestrator, "task_manager"):
            tasks = self.orchestrator.task_manager.list_tasks()
            has_running = any(t.get("status") == "RUNNING" for t in tasks)

        if has_running:
            # Don't idle-shutdown if tasks are running
            logger.info("[Watchtower] Idle timeout reached but tasks are running — staying active.")
            return

        # Save snapshot
        self._save_idle_snapshot()

        # Set the went_idle flag
        idle_minutes = int((time.time() - self._last_user_activity) / 60)
        self.idle_message = (
            f"⏸️ Watchtower: No activity detected for {idle_minutes} minutes. "
            f"Monitoring paused. State saved to logs/idle_snapshot.json. "
            f"Send a message to resume."
        )
        self.went_idle = True

        logger.info("[Watchtower] %s", self.idle_message)

        # Stop the watchdog loop — monitoring pauses
        self._running = False

    def _save_idle_snapshot(self):
        """Save current orchestrator state for pickup on restart."""
        try:
            snapshot = {
                "timestamp": time.time(),
                "reason": "idle_timeout",
                "idle_minutes": round((time.time() - self._last_user_activity) / 60, 1),
                "session_id": getattr(self.orchestrator, "current_session_id", None),
                "depth_level": getattr(self.orchestrator, "depth_level", "S"),
                "provider_ok": self._last_provider_ok,
                "history_length": len(getattr(self.orchestrator, "conversation_history", [])),
                "pid": os.getpid()
            }

            with open(self._snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            logger.info("[Watchtower] Idle snapshot saved to %s", self._snapshot_path)

        except Exception as e:
            logger.error("[Watchtower] Failed to save idle snapshot: %s", e)

    def _clear_snapshot(self):
        """Remove the idle snapshot file."""
        try:
            if os.path.exists(self._snapshot_path):
                os.remove(self._snapshot_path)
        except Exception:
            pass

    # ── Lifecycle ────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()
