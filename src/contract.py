"""
contract.py — DeepGravity Graduated Autonomy Contract Layer
Phase 4.5.2

Defines the WorkContract system: a structured set of guardrails
that the user approves once, then the system executes within the
fence until a boundary condition is hit.

Components:
  - WorkContract: Dataclass holding guardrail policies
  - ContractParser: Extracts structured contracts from natural language
  - ContractMonitor: Validates every tool call against the active contract
  - SpinningDetector: Catches loop collapse before it burns tokens
"""

import re
import os
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum


# ── Policy Types ──────────────────────────────────────────────────────

class DestructiveEditPolicy(Enum):
    DENY = "deny"
    ARCHIVE_AND_FLAG = "archive_and_flag"
    ALLOW_WITH_DIFF = "allow_with_diff"


class FileDeletionPolicy(Enum):
    DENY = "deny"
    ARCHIVE_AND_FLAG = "archive_and_flag"


class HaltAction(Enum):
    """What happens when a guardrail is breached."""
    HALT_AND_REPORT = "halt_and_report"
    PAUSE_AND_SUMMARIZE = "pause_and_summarize"
    ESCALATE = "escalate"


# ── The Contract ──────────────────────────────────────────────────────

@dataclass
class WorkContract:
    """
    A structured work plan with guardrails.
    The user approves this once; the system runs inside the fence.
    """
    # Human-readable description of the work plan
    description: str = ""
    
    # ── Destructive Edit Policy ──
    destructive_edit_policy: DestructiveEditPolicy = DestructiveEditPolicy.ARCHIVE_AND_FLAG
    destructive_patterns: List[str] = field(default_factory=lambda: [
        r"rm\s+-rf",
        r"del\s+/[sfq]",
        r"format\s+",
        r"remove-item\s+-recurse",
        r"Clear-Content",
        r">\s*$null",
    ])
    
    # ── File Deletion Policy ──
    file_deletion_policy: FileDeletionPolicy = FileDeletionPolicy.ARCHIVE_AND_FLAG
    system_file_patterns: List[str] = field(default_factory=lambda: [
        r"pagefile\.sys",
        r"swapfile\.sys",
        r"hiberfil\.sys",
        r"boot\.ini",
        r"bootmgr",
        r"ntldr",
        r"config\.json$",
        r"\.git/",
        r"node_modules/",
    ])
    # Path where archived files go before deletion
    archive_base_path: str = ""
    
    # ── Search Retry Limits ──
    max_search_retries: int = 2
    on_search_exceeded: HaltAction = HaltAction.HALT_AND_REPORT
    
    # ── Spinning Detection ──
    spinning_enabled: bool = True
    consecutive_failure_threshold: int = 3
    identical_tool_call_threshold: int = 5
    context_window_stall_threshold_seconds: float = 60.0
    
    # ── Watchdog Timer ──
    watchdog_max_minutes: float = 0.0  # 0 = no watchdog
    on_watchdog_expiry: HaltAction = HaltAction.PAUSE_AND_SUMMARIZE
    
    # ── Path Restrictions ──
    allowed_paths: List[str] = field(default_factory=list)
    restricted_paths: List[str] = field(default_factory=lambda: [
        r"C:\\Windows",
        r"C:\\Program Files",
        r"C:\\Program Files \(x86\)",
    ])
    
    # ── Approval Tracking ──
    approved_at: Optional[float] = None
    approved_by: str = "user"
    expires_at: Optional[float] = None  # Optional TTL for the contract
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


# ── Spinning Detector ─────────────────────────────────────────────────

@dataclass
class SpinningRecord:
    """Tracks tool call patterns for spinning detection."""
    recent_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    consecutive_failures: int = 0
    last_error_time: float = 0.0
    last_content_hash: str = ""
    stall_start_time: Optional[float] = None
    
    MAX_HISTORY: int = 20


class SpinningDetector:
    """
    Detects when the agent has entered a loop or stalled.
    
    Detection modes:
    1. Identical tool calls — same tool, same arguments, repeated
    2. Consecutive errors — same error, same tool, no recovery
    3. Content stall — no new information entering the context
    """
    
    def __init__(self, contract: WorkContract):
        self.contract = contract
        self.record = SpinningRecord()
    
    def record_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: str):
        """Record a tool call for spinning analysis."""
        self.record.recent_tool_calls.append({
            "name": tool_name,
            "args": arguments,
            "result_preview": result[:200],
            "time": time.time(),
            "is_error": result.startswith("Error") or "Access Denied" in result
        })
        # Trim history
        if len(self.record.recent_tool_calls) > SpinningRecord.MAX_HISTORY:
            self.record.recent_tool_calls.pop(0)
    
    def check(self) -> Optional[Dict[str, Any]]:
        """
        Returns a violation report if spinning is detected, else None.
        """
        if not self.contract.spinning_enabled:
            return None
        
        recent = self.record.recent_tool_calls
        if len(recent) < 3:
            return None
        
        # 1. Check for consecutive identical tool calls
        identical_count = 0
        for i in range(len(recent) - 1, max(len(recent) - 10, 0), -1):
            if (recent[i]["name"] == recent[i-1]["name"] and 
                recent[i]["args"] == recent[i-1]["args"]):
                identical_count += 1
            else:
                break
        
        # Also check for same-tool-but-different-args pattern (search thrashing)
        same_tool_count = sum(1 for tc in recent[-10:] if tc["name"] == recent[-1]["name"])
        if same_tool_count >= self.contract.identical_tool_call_threshold:
            return {
                "type": "identical_tool_call_loop",
                "tool": recent[-1]["name"],
                "count": same_tool_count,
                "message": f"Called '{recent[-1]['name']}' {same_tool_count} times in the last {min(len(recent), 10)} turns. Possible search loop.",
                "severity": "warning"
            }
        
        if identical_count >= self.contract.identical_tool_call_threshold:
            return {
                "type": "identical_tool_call_loop",
                "tool": recent[-1]["name"],
                "count": identical_count,
                "message": f"Identical tool call '{recent[-1]['name']}' repeated {identical_count + 1} times with the same arguments.",
                "severity": "warning"
            }
        
        # 2. Check for consecutive errors
        error_count = 0
        for tc in reversed(recent[-10:]):
            if tc.get("is_error"):
                error_count += 1
            else:
                break
        
        if error_count >= self.contract.consecutive_failure_threshold:
            return {
                "type": "consecutive_failure_loop",
                "count": error_count,
                "last_error": recent[-1].get("result_preview", ""),
                "message": f"{error_count} consecutive tool execution errors. System may be spinning.",
                "severity": "error"
            }
        
        # 3. Check for content stall — same content hash across multiple turns
        if len(recent) >= 4:
            latest_args_hash = hashlib.md5(
                json.dumps(recent[-1]["args"], sort_keys=True).encode()
            ).hexdigest()
            prev_args_hash = hashlib.md5(
                json.dumps(recent[-3]["args"], sort_keys=True).encode()
            ).hexdigest()
            
            if latest_args_hash == prev_args_hash and recent[-1]["name"] == recent[-3]["name"]:
                # Same tool, same args, N turns apart — oscillation
                if self.record.stall_start_time is None:
                    self.record.stall_start_time = time.time()
                elif (time.time() - self.record.stall_start_time) > self.contract.context_window_stall_threshold_seconds:
                    return {
                        "type": "context_stall",
                        "message": f"Agent has been cycling between the same states for {self.contract.context_window_stall_threshold_seconds:.0f}s. No information gain detected.",
                        "severity": "warning"
                    }
            else:
                self.record.stall_start_time = None
        
        return None
    
    def reset(self):
        """Clear the spinning record — call when a new work phase starts."""
        self.record = SpinningRecord()


# ── Contract Monitor ──────────────────────────────────────────────────

class ContractViolation(Exception):
    """Raised when a tool call violates the active contract."""
    def __init__(self, violation_type: str, message: str, details: Optional[Dict] = None):
        self.violation_type = violation_type
        self.details = details or {}
        super().__init__(message)


class ContractMonitor:
    """
    Wraps tool execution with contract validation.
    
    Every tool call is checked against the active contract's guardrails
    before execution. If a guardrail is breached, a ContractViolation
    is raised, which the orchestrator catches to halt and report.
    """
    
    def __init__(self, contract: Optional[WorkContract] = None):
        self.contract = contract
        self.spinning_detector = SpinningDetector(contract) if contract else None
        self.search_count = 0
        self.tool_call_count = 0
        self._start_time = time.time()
    
    def set_contract(self, contract: WorkContract):
        """Set or replace the active contract."""
        self.contract = contract
        self.spinning_detector = SpinningDetector(contract)
        self.search_count = 0
        self.tool_call_count = 0
        self._start_time = time.time()
    
    def clear_contract(self):
        """Remove the active contract — falls back to per-tool y/N."""
        self.contract = None
        self.spinning_detector = None
        self.search_count = 0
        self.tool_call_count = 0
    
    def has_active_contract(self) -> bool:
        return self.contract is not None and not self.contract.is_expired()
    
    def get_contract_summary(self) -> str:
        """Return a human-readable summary of the active contract's limits."""
        if not self.contract:
            return "No active contract. Per-tool approval required."
        
        c = self.contract
        lines = [
            f"Work Plan: {c.description}",
            f"  Destructive edits: {c.destructive_edit_policy.value}",
            f"  File deletion: {c.file_deletion_policy.value}",
            f"  Max search retries: {c.max_search_retries}",
            f"  Spinning detection: {'on' if c.spinning_enabled else 'off'}",
        ]
        if c.watchdog_max_minutes > 0:
            lines.append(f"  Watchdog: {c.watchdog_max_minutes}min")
        return "\n".join(lines)
    
    def check_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[ContractViolation]:
        """
        Check a proposed tool call against the active contract.
        Returns a ContractViolation if blocked, None if allowed.
        """
        if not self.has_active_contract():
            return None
        
        contract = self.contract
        self.tool_call_count += 1
        
        # ── Check Watchdog Timer ──
        if contract.watchdog_max_minutes > 0:
            elapsed = (time.time() - self._start_time) / 60.0
            if elapsed > contract.watchdog_max_minutes:
                return ContractViolation(
                    "watchdog_expired",
                    f"Watchdog timer expired ({contract.watchdog_max_minutes:.0f} minutes elapsed). "
                    f"Pausing for user review.",
                    {"elapsed_minutes": elapsed}
                )
        
        # ── Check Path Restrictions ──
        for key in ["absolute_path", "directory_path", "search_path"]:
            if key in arguments:
                path = arguments[key]
                for restricted in contract.restricted_paths:
                    if path.lower().startswith(restricted.lower()):
                        return ContractViolation(
                            "restricted_path",
                            f"Path '{path}' is in a restricted area ({restricted}). "
                            f"This requires explicit user approval.",
                            {"path": path, "restricted": restricted}
                        )
        
        # ── Check Destructive Edit Policy ──
        if tool_name == "run_command":
            command = arguments.get("command", "")
            for pattern in contract.destructive_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    if contract.destructive_edit_policy == DestructiveEditPolicy.DENY:
                        return ContractViolation(
                            "destructive_command_denied",
                            f"Command blocked by destructive edit policy: '{pattern}'",
                            {"command": command, "pattern": pattern}
                        )
                    elif contract.destructive_edit_policy == DestructiveEditPolicy.ARCHIVE_AND_FLAG:
                        # Transform the command: wrap in archive logic? No — we halt
                        # because auto-transforming destructive commands is dangerous.
                        # Instead, flag for human review.
                        return ContractViolation(
                            "destructive_command_requires_review",
                            f"Destructive command detected (pattern: '{pattern}'). "
                            f"Policy requires human review before execution.",
                            {"command": command, "pattern": pattern}
                        )
                    # ALLOW_WITH_DIFF — falls through to the existing SDP diff
        
        # ── Check File Deletion Policy ──
        if tool_name in ("write_file", "edit_file_content", "run_command"):
            file_path = arguments.get("absolute_path", "")
            command = arguments.get("command", "")
            
            # Check if this is a deletion operation
            is_deletion = False
            if tool_name == "run_command":
                del_patterns = [
                    r"del\s+",
                    r"remove-item",
                    r"rm\s+",
                    r"Clear-Content",
                ]
                for pat in del_patterns:
                    if re.search(pat, command, re.IGNORECASE):
                        is_deletion = True
                        break
            
            if is_deletion or (tool_name == "write_file" and not arguments.get("content", "")):
                # Check against system file patterns
                for pattern in contract.system_file_patterns:
                    if re.search(pattern, file_path or command, re.IGNORECASE):
                        if contract.file_deletion_policy == FileDeletionPolicy.DENY:
                            return ContractViolation(
                                "system_file_deletion_denied",
                                f"Deletion of system file '{file_path}' blocked by policy.",
                                {"file_path": file_path}
                            )
                        elif contract.file_deletion_policy == FileDeletionPolicy.ARCHIVE_AND_FLAG:
                            return ContractViolation(
                                "system_file_deletion_requires_review",
                                f"Deletion of '{file_path}' requires review. "
                                f"Policy: archive before deletion.",
                                {"file_path": file_path}
                            )
        
        # ── Check Search Retry Limits ──
        if tool_name in ("grep_search", "list_dir", "view_file"):
            self.search_count += 1
            if self.search_count > contract.max_search_retries:
                return ContractViolation(
                    "search_retry_limit_exceeded",
                    f"Search operations exceeded limit ({contract.max_search_retries}). "
                    f"Halting for user guidance on what to search for.",
                    {"search_count": self.search_count, "limit": contract.max_search_retries}
                )
        
        return None  # All checks passed
    
    def record_result(self, tool_name: str, arguments: Dict[str, Any], result: str):
        """Record the result of a tool call for spinning detection."""
        if self.spinning_detector:
            self.spinning_detector.record_tool_call(tool_name, arguments, result)
    
    def check_spinning(self) -> Optional[Dict[str, Any]]:
        """Check if the system is in a spin loop."""
        if self.spinning_detector:
            return self.spinning_detector.check()
        return None
    
    def reset(self):
        """Reset all counters — for a new work phase within the same contract."""
        self.search_count = 0
        self.tool_call_count = 0
        if self.spinning_detector:
            self.spinning_detector.reset()


# ── Contract Parser ───────────────────────────────────────────────────

class ContractParser:
    """
    Extracts a structured WorkContract from natural language instructions.
    
    This parses the user's work request and extracts guardrail parameters.
    The result is presented to the user for confirmation before activation.
    """
    
    # Patterns for detecting guardrail intent
    PATTERNS = {
        "no_delete": [
            r"(?i)no\s*(delet|remov|eras|trash|rm)",
            r"(?i)don'?t\s*(delet|remov|eras)",
            r"(?i)never\s*(delet|remov)",
            r"(?i)preserv.*(file|data|content)",
        ],
        "archive_instead": [
            r"(?i)archiv",
            r"(?i)backup\s*(before|first)",
            r"(?i)move\s*to\s*(archiv|backup)",
            r"(?i)safe.*(keep|store)",
        ],
        "allow_destructive": [
            r"(?i)allow\s*(destruct|rm|delet)",
            r"(?i)it'?s\s*(fine|ok|safe)\s*to\s*(delet|remov)",
            r"(?i)i\s*(know|accept).*(destruct|delet|risk)",
        ],
        "search_limit": [
            r"(?i)(search|look|find|grep).*(limit|max|stop|ask)",
            r"(?i)(more\s*than|up\s*to|max).*(search|look|try|attempt)",
            r"(?i)(stop|ask|pause).*(if|when).*(search|not\s*found)",
        ],
        "no_spinning": [
            r"(?i)(don'?t|stop|avoid|prevent).*((spin|loop|repeat|stuck|cycle))",
            r"(?i)(if|when).*(stuck|loop|repeat).*(stop|ask|halt|pause)",
        ],
        "watchdog": [
            r"(?i)(timeout|watchdog|max.*(min|time|duration))",
            r"(?i)(stop|pause).*(after|in).*(\d+)\s*(min|hour)",
        ],
        "path_restrict": [
            r"(?i)(stay|keep|only|restrict).*(in|within|to)\s*([\w\\/:]+)",
            r"(?i)(don'?t|avoid|never).*(touch|modif|go).*([\w\\/:]+)",
        ],
    }
    
    @classmethod
    def parse(cls, user_text: str, workspace_root: str = "") -> WorkContract:
        """
        Parse natural language instructions into a WorkContract.
        
        Returns a best-effort contract with sensible defaults for anything
        the user didn't explicitly specify.
        """
        contract = WorkContract()
        contract.description = user_text[:200]  # Truncate for the summary
        
        # ── Destructive Edit Policy ──
        if any(re.search(p, user_text) for p in cls.PATTERNS["no_delete"]):
            contract.destructive_edit_policy = DestructiveEditPolicy.DENY
        elif any(re.search(p, user_text) for p in cls.PATTERNS["allow_destructive"]):
            contract.destructive_edit_policy = DestructiveEditPolicy.ALLOW_WITH_DIFF
        elif any(re.search(p, user_text) for p in cls.PATTERNS["archive_instead"]):
            contract.destructive_edit_policy = DestructiveEditPolicy.ARCHIVE_AND_FLAG
        # Default stays as ARCHIVE_AND_FLAG
        
        # ── File Deletion Policy ──
        if any(re.search(p, user_text) for p in cls.PATTERNS["no_delete"]):
            contract.file_deletion_policy = FileDeletionPolicy.DENY
        # Default stays as ARCHIVE_AND_FLAG
        
        # ── Search Limit ──
        search_limit_match = re.search(r"(?i)(\d+)\s*(search|look|try|attempt)", user_text)
        if search_limit_match:
            contract.max_search_retries = int(search_limit_match.group(1))
        
        # ── Spinning Detection ──
        if any(re.search(p, user_text) for p in cls.PATTERNS["no_spinning"]):
            contract.spinning_enabled = True
        # Default is True
        
        # ── Watchdog ──
        watchdog_match = re.search(r"(?i)(\d+)\s*(min|hour|minute)", user_text)
        if watchdog_match:
            value = int(watchdog_match.group(1))
            unit = watchdog_match.group(2).lower()
            if unit.startswith("hour"):
                contract.watchdog_max_minutes = value * 60
            else:
                contract.watchdog_max_minutes = value
        
        # ── Path Restrictions (simple detection) ──
        for match in re.finditer(r"(?i)(?:in|within|to)\s+([\w\\/:]{3,})", user_text):
            path = match.group(1)
            if os.path.exists(path) or "\\" in path or path.startswith("/"):
                contract.allowed_paths.append(path)
        
        # Always include workspace root
        if workspace_root and workspace_root not in contract.allowed_paths:
            contract.allowed_paths.insert(0, workspace_root)
        
        return contract
    
    @classmethod
    def format_contract_summary(cls, contract: WorkContract) -> str:
        """Format the contract for user review before approval."""
        lines = [
            "===============================================",
            "          WORK PLAN CONTRACT",
            "===============================================",
            "",
            f"  Plan: {contract.description}",
            "",
            "  --- Guardrails ---",
            f"  Destructive edits:    {contract.destructive_edit_policy.value}",
            f"  File deletion:        {contract.file_deletion_policy.value}",
            f"  Max search retries:   {contract.max_search_retries}",
            f"  Spinning detection:   {'ON' if contract.spinning_enabled else 'OFF'}",
        ]
        if contract.watchdog_max_minutes > 0:
            lines.append(f"  Watchdog:             {contract.watchdog_max_minutes:.0f} minutes")
        if contract.archive_base_path:
            lines.append(f"  Archive path:         {contract.archive_base_path}")
        if contract.allowed_paths:
            lines.append(f"  Allowed paths:        {contract.allowed_paths[0]}")
            if len(contract.allowed_paths) > 1:
                for p in contract.allowed_paths[1:]:
                    lines.append(f"                        {p}")
        lines.extend([
            "",
            "  Type 'y' to approve this contract and begin work.",
            "  Type 'n' or anything else to reject and refine.",
            "  Type 'edit' to adjust specific guardrails.",
            "",
        ])
        return "\n".join(lines)


# ── Convenience: Build Contract from User Input ──────────────────────

def build_contract_from_request(
    user_text: str,
    workspace_root: str = "",
    existing_contract: Optional[WorkContract] = None
) -> WorkContract:
    """
    Build a contract from a user request, optionally starting from
    an existing contract as a base.
    """
    parsed = ContractParser.parse(user_text, workspace_root)
    
    if existing_contract:
        # Merge: use existing contract as base, override with any
        # explicitly detected intents from the new request
        merged = existing_contract
        
        # Only override if the user explicitly mentioned the policy
        if any(re.search(p, user_text) for p in ContractParser.PATTERNS["no_delete"]):
            merged.destructive_edit_policy = parsed.destructive_edit_policy
            merged.file_deletion_policy = parsed.file_deletion_policy
        if any(re.search(p, user_text) for p in ContractParser.PATTERNS["archive_instead"]):
            merged.destructive_edit_policy = parsed.destructive_edit_policy
        if any(re.search(p, user_text) for p in ContractParser.PATTERNS["allow_destructive"]):
            merged.destructive_edit_policy = parsed.destructive_edit_policy
        
        merged.description = user_text[:200]
        if parsed.max_search_retries != 2:  # Non-default
            merged.max_search_retries = parsed.max_search_retries
        if parsed.watchdog_max_minutes > 0:
            merged.watchdog_max_minutes = parsed.watchdog_max_minutes
        
        return merged
    
    return parsed
