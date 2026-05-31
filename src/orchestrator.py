import os
import json
import base64
import time
import traceback
from typing import Dict, List, Any, Optional, Tuple, Generator
from src.providers.openai_compat import OpenAICompatProvider
from src.tools.file_ops import FileOperations
from src.tools.shell import ShellCommandRunner
from src.tools.search import SearchOperations
from src.tools.task_manager import TaskManager
from src.tools.web_search import WebSearch
from src.tools.vision import VisionAnalysis
from src.safety import SafetyGuardrails
from src import keystore
from src.tool_cache import ToolResultCache
from src.contract import (
    ContractMonitor, ContractViolation, WorkContract,
    ContractParser, build_contract_from_request
)

class DeepGravityOrchestrator:
    """
    Core Orchestrator for DeepGravity.
    Handles config loading, provider initialization, system prompt hydration,
    Federated API Routing, and tool execution dispatch loops.
    """

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self.providers = self.init_providers()
        self.conversation_history: List[Dict[str, Any]] = []
        self.system_prompt = ""
        
        # Load Tool schemas
        self.tools_schema = self.load_tools_schema()

        # Initialize tools
        self.guardrails = SafetyGuardrails(self.config)
        self.file_ops = FileOperations(self.guardrails)
        self.shell_runner = ShellCommandRunner(self.guardrails)
        self.search_ops = SearchOperations()
        self.web_search = WebSearch()
        self.vision = VisionAnalysis()
        
        # Set task log directory relative to config folder
        log_dir = os.path.join(os.path.dirname(config_path), "logs", "tasks")
        self.task_manager = TaskManager(log_dir)
        
        # Heartbeat monitor path — written by agent loops, read by external watcher
        self._heartbeat_path = os.path.join(os.path.dirname(config_path), "logs", "heartbeat.json")
        self._loop_count = 0
        self._last_tool_name = None
        
        # ── Contract Layer (Phase 4.5.2) ──
        self.contract_monitor = ContractMonitor()
        self._contract_violation_buffer: List[Dict[str, Any]] = []
        
        # Failover routing — per-provider error state
        self._provider_errors = {}  # {provider_name: {"consecutive": N, "last_failure": epoch_sec}}
        self._current_provider_for_role = {}  # {role: active_provider_name}
        self._last_working_provider = {}  # {role: provider_name} — last provider that responded successfully
        self._failover_config = self.config.get("api", {}).get("failover", {})
        self._failover_threshold = self.config.get("api", {}).get("failover_threshold", 3)
        self._pending_approval = None  # set by web_server.py when a command is waiting for approval

        # ── Idle Watchdog ──
        from src.idle_watchdog import IdleWatchdog
        wt_config = self.config.get("watchtower", {})
        self.watchdog = IdleWatchdog(self, wt_config)
        self.watchdog.start()
        
        # Check for idle snapshot on restart
        snapshot = self.watchdog.check_snapshot_on_restart()
        if snapshot:
            idle_min = snapshot.get("idle_minutes", "?")
            print(f"\n[Watchtower] ⏸️ Previous session ended after {idle_min} min of inactivity.")
            print(f"[Watchtower] Session snapshot available in logs/idle_snapshot.json")

        # ── Depth Dial (Phase 5.5: G-M-O-U-X) ──
        self.depth_level = "S"  # default starting depth (Safe)
        self._depth_warnings_given = set()  # track one-time warnings (e.g. O on public)

        # ── Tool Result Cache (token bloat mitigation) ──
        cache_dir = os.path.join(os.path.dirname(self.config_path), "logs", "tool_cache")
        self.tool_cache = ToolResultCache(cache_dir)

        # ── Keystore (X-mode encryption) ──
        keystore.init_keystore(self.config_path)
        self._keystore_unlocked = False
        self._session_keys = {}  # {session_id: base64_encoded_key}
        
        # ── X-mode history swapping ──
        self._plaintext_backup = []  # saved plaintext history when entering encrypted mode (U/X)
        self._plaintext_session_id = None  # saved plaintext session ID when entering encrypted mode (U/X)
        self._surface_state_path = os.path.join(os.path.dirname(self.config_path), "logs", "chats", ".surface_state.json")
        # Recover plaintext backup pointer from crash (if any)
        self._recover_surface_from_crash()

    def load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            template_path = path + ".template"
            if os.path.exists(template_path):
                print(f"[DeepGravity] Local config not found. Loading template: {template_path}")
                with open(template_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            raise FileNotFoundError(f"Config file not found at {path} or {template_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_tools_schema(self) -> List[Dict[str, Any]]:
        schema_path = os.path.join(os.path.dirname(self.config_path), "config", "tools_schema.json")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def init_providers(self) -> Dict[str, OpenAICompatProvider]:
        providers_config = self.config.get("api", {}).get("providers", {})
        server_location = self.config.get("server_location", "http://localhost:11434/v1")
        providers = {}
        for name, cfg in providers_config.items():
            cfg = dict(cfg)  # shallow copy to avoid mutating the source
            # Resolve {server_location} template variable in all string values
            for key, value in cfg.items():
                if isinstance(value, str) and "{server_location}" in value:
                    cfg[key] = value.replace("{server_location}", server_location)
            providers[name] = OpenAICompatProvider(cfg)
        return providers

    def get_provider_for_role(self, role: str) -> Optional[OpenAICompatProvider]:
        """
        Returns the active provider for a given role, with failover support.
        Tries the primary provider first; if its consecutive error count exceeds
        the failover threshold, advances through the failover list.
        """
        routing = self.config.get("api", {}).get("routing", {})
        primary = routing.get(role)
        
        # Build the candidate list: primary + failover fallbacks (if any)
        candidates = [primary] if primary else []
        failover_list = self._failover_config.get(role, [])
        for name in failover_list:
            if name not in candidates:
                candidates.append(name)
        
        if not candidates:
            return None
        
        # Remember the last active candidate for this role
        current = self._current_provider_for_role.get(role, candidates[0])
        
        # If current is no longer in candidates, reset to primary
        if current not in candidates:
            current = candidates[0]
        
        # Check if the current candidate is error-throttled
        err_info = self._provider_errors.get(current, {"consecutive": 0})
        if err_info["consecutive"] >= self._failover_threshold:
            # Try next available candidate
            idx = candidates.index(current)
            for next_candidate in candidates[idx + 1:]:
                next_err = self._provider_errors.get(next_candidate, {"consecutive": 0})
                if next_err["consecutive"] < self._failover_threshold:
                    # Failover to this provider
                    current = next_candidate
                    print(f"[DeepGravity] Failover: {role} -> {current} "
                          f"(primary {primary} error threshold reached)")
                    break
        
        self._current_provider_for_role[role] = current
        return self.providers.get(current)
    
    def record_provider_error(self, provider_name: str):
        """Record an error for a provider, incrementing its consecutive failure count."""
        now = time.time()
        if provider_name not in self._provider_errors:
            self._provider_errors[provider_name] = {"consecutive": 0, "last_failure": 0}
        self._provider_errors[provider_name]["consecutive"] += 1
        self._provider_errors[provider_name]["last_failure"] = now
    
    def record_provider_success(self, provider_name: str):
        """Reset consecutive error count on successful call."""
        if provider_name in self._provider_errors:
            self._provider_errors[provider_name]["consecutive"] = 0

    def _try_fallback_provider(self, role: str):
        """
        Called when the active provider for a role fails mid-conversation.
        Tries failover providers (from config), then the last working provider.
        Returns a working provider if found, or None if all are exhausted.
        """
        routing = self.config.get("api", {}).get("routing", {})
        primary = routing.get(role)

        # 1. Try failover providers from config
        failover_list = self._failover_config.get(role, [])
        for name in failover_list:
            if name == self._current_provider_for_role.get(role):
                continue  # skip the one that just failed
            err_info = self._provider_errors.get(name, {"consecutive": 0})
            if err_info["consecutive"] < self._failover_threshold:
                provider = self.providers.get(name)
                if provider:
                    depth_gate = self.check_depth_gate(name)
                    if depth_gate is None:
                        self._current_provider_for_role[role] = name
                        print(f"[DeepGravity] Agent-loop failover: {role} -> {name}")
                        return provider

        # 2. Try the last working provider (in case fallback was never explicitly configured)
        last_working = self._last_working_provider.get(role)
        if last_working and last_working != self._current_provider_for_role.get(role):
            provider = self.providers.get(last_working)
            if provider:
                depth_gate = self.check_depth_gate(last_working)
                if depth_gate is None:
                    self._current_provider_for_role[role] = last_working
                    print(f"[DeepGravity] Agent-loop fallback to last working: {role} -> {last_working}")
                    return provider

        return None

    # ── Depth Dial Methods ───────────────────────────────────────────

    VALID_DEPTH_LEVELS = {"S", "M", "A", "R", "T"}
    DEPTH_ORDER = ["S", "M", "A", "R", "T"]

    def set_depth_level(self, level: str) -> dict:
        """
        Set the current conversational depth level.
        Returns a result dict with success/error info.
        Enforces routing constraints: U/X require private providers.
        """
        level = level.upper()
        if level not in self.VALID_DEPTH_LEVELS:
            return {
                "success": False,
                "error": f"Invalid depth level '{level}'. Must be one of: S, M, A, R, T"
            }

        # R and T require at least one private provider configured
        if level in ("R", "T"):
            private_providers = self.get_private_providers()
            if not private_providers:
                return {
                    "success": False,
                    "level": level,
                    "error": "This depth requires a local/private engine. No private providers are configured.",
                    "private_providers": []
                }

        # Check that at least one routed provider can handle this depth
        routing = self.config.get("api", {}).get("routing", {})
        can_handle = False
        seen = set()
        for role, provider_name in routing.items():
            if provider_name in seen:
                continue
            seen.add(provider_name)
            max_d = self.get_max_depth_for_provider(provider_name)
            if self.DEPTH_ORDER.index(level) <= self.DEPTH_ORDER.index(max_d):
                can_handle = True
                break

        if not can_handle:
            return {
                "success": False,
                "level": level,
                "error": (
                    f"No active provider supports depth level '{level}'. "
                    f"Configure a provider with appropriate max_depth, or lower the depth."
                )
            }
        
        old_level = self.depth_level
        self.depth_level = level  # SET FIRST so save_conversation_history() sees correct depth
        
        # ── History swap when crossing the T threshold ──
        entering_encrypted = (level == "T" and old_level != "T" and self._keystore_unlocked)
        leaving_encrypted = (old_level == "T" and level != "T")
        
        if entering_encrypted:
            # Save current plaintext history
            self._plaintext_backup = list(self.conversation_history)
            self._plaintext_session_id = self.current_session_id
            self._save_surface_state()
            self.save_conversation_history()  # flush plaintext to disk
            # Start fresh encrypted session
            import uuid
            self.conversation_history = [self.conversation_history[0]]  # keep system prompt
            self.current_session_id = f"chat_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
            self.save_conversation_history()  # write initial encrypted frame
        elif leaving_encrypted:
            # Save encrypted session
            self.save_conversation_history()
            # Restore plaintext
            if self._plaintext_backup:
                self.conversation_history = self._plaintext_backup
                self.current_session_id = self._plaintext_session_id
                self._plaintext_backup = []
                self._plaintext_session_id = None
                self._delete_surface_state()
            else:
                # No backup — start a fresh plaintext session
                import uuid
                self.conversation_history = [self.conversation_history[0]]  # keep system prompt
                self.current_session_id = f"chat_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
            self.save_conversation_history()

        result = {
            "success": True,
            "level": level,
            "private_providers": self.get_private_providers(),
            "keystore_unlocked": self._keystore_unlocked
        }
        if entering_encrypted or leaving_encrypted:
            result["surface_swapped"] = True
            result["new_session_id"] = self.current_session_id
        return result

    def ensure_surface_swap(self) -> bool:
        """
        Retroactively fire the plaintext→encrypted surface swap if it was missed.
        Happens when keystore is set up/unlocked AFTER depth was already set to X.
        Returns True if a swap was performed, False if not needed.
        """
        if self.depth_level == "T" and self._keystore_unlocked and not self._plaintext_backup:
            import uuid
            self._plaintext_backup = list(self.conversation_history)
            self._plaintext_session_id = self.current_session_id
            self._save_surface_state()
            self.save_conversation_history()
            self.conversation_history = [self.conversation_history[0]]
            self.current_session_id = f"chat_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
            self.save_conversation_history()
            return True
        return False

    def _save_surface_state(self):
        """Persist plaintext backup pointer so it survives crashes."""
        if self._plaintext_session_id:
            try:
                os.makedirs(os.path.dirname(self._surface_state_path), exist_ok=True)
                state = {"depth": self.depth_level, "plaintext_session_id": self._plaintext_session_id}
                with open(self._surface_state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f)
            except Exception as e:
                print(f"[DeepGravity] Failed to save surface state: {e}")

    def _delete_surface_state(self):
        """Remove the crash-recovery state file."""
        try:
            if os.path.exists(self._surface_state_path):
                os.remove(self._surface_state_path)
        except Exception:
            pass

    def _recover_surface_from_crash(self):
        """On startup, check if a crash left an orphaned surface state."""
        if not os.path.exists(self._surface_state_path):
            return
        try:
            with open(self._surface_state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            sid = state.get("plaintext_session_id")
            depth = state.get("depth", "S")
            if sid and depth in self.VALID_DEPTH_LEVELS:
                # Restore the plaintext backup pointer
                self._plaintext_session_id = sid
                self.depth_level = depth
                print(f"[DeepGravity] Recovered surface state from crash: depth={depth}, session={sid}")
            # Delete the state file regardless — it's consumed on recovery
            self._delete_surface_state()
        except Exception as e:
            print(f"[DeepGravity] Failed to recover surface state: {e}")
            self._delete_surface_state()

    def get_depth_level(self) -> str:
        """Return the current depth level."""
        return self.depth_level

    def get_max_depth_for_provider(self, provider_name: str) -> str:
        """
        Return the maximum depth level a provider can handle.
        Checks explicit 'max_depth' in config, then falls back to defaults:
        - public providers default to 'O'
        - private providers (public_stratum=false) default to 'X'
        """
        providers_config = self.config.get("api", {}).get("providers", {})
        prov_cfg = providers_config.get(provider_name, {})

        # Explicit max_depth in config
        max_depth = prov_cfg.get("max_depth")
        if max_depth and max_depth in self.VALID_DEPTH_LEVELS:
            return max_depth

        # Default logic: private providers default to X, public to O
        is_public = prov_cfg.get("public_stratum", True)
        if is_public:
            return "A"
        else:
            return "T"

    def get_depth_state(self) -> dict:
        """Return full depth state for API responses."""
        return {
            "level": self.depth_level,
            "private_providers": self.get_private_providers(),
            "keystore_unlocked": self._keystore_unlocked
        }

    def check_depth_gate(self, provider_name: str, level: str = None) -> Optional[str]:
        """
        Check if the given provider can handle the current (or specified) depth level.
        Returns None if allowed, or an error message if blocked.
        """
        check_level = level or self.depth_level
        max_d = self.get_max_depth_for_provider(provider_name)

        if self.DEPTH_ORDER.index(check_level) > self.DEPTH_ORDER.index(max_d):
            return (
                f"Depth level '{check_level}' exceeds provider '{provider_name}' "
                f"maximum of '{max_d}'. Switch to a provider with higher max_depth, "
                f"or reduce the depth level."
            )
        return None

    # ── Keystore Methods ─────────────────────────────────────────────

    def get_keystore_status(self) -> dict:
        """Return keystore existence and unlock state."""
        return {
            "exists": keystore.keystore_exists(),
            "unlocked": self._keystore_unlocked
        }

    def setup_keystore(self, passphrase: str) -> dict:
        """
        Create a new keystore with the given master passphrase.
        Returns result dict with recovery phrase on success.
        """
        if keystore.keystore_exists():
            return {"success": False, "error": "Keystore already exists. Use POST /api/keystore/unlock to unlock it."}
        try:
            result = keystore.create_keystore(passphrase)
            self._keystore_unlocked = True
            swapped = self.ensure_surface_swap()
            response = {"success": True, "recovery_phrase": result["recovery_phrase"], "warning": result["warning"]}
            if swapped:
                response["surface_swapped"] = True
                response["new_session_id"] = self.current_session_id
            return response
        except Exception as e:
            return {"success": False, "error": str(e)}

    def unlock_keystore(self, passphrase_or_phrase: str, is_recovery: bool = False) -> dict:
        """
        Unlock the keystore with a passphrase or recovery phrase.
        Returns success/failure.
        """
        if not keystore.keystore_exists():
            return {"success": False, "error": "No keystore found. Create one with POST /api/keystore/setup first."}

        try:
            if is_recovery:
                sessions = keystore.unlock_keystore_with_recovery(passphrase_or_phrase)
            else:
                sessions = keystore.unlock_keystore(passphrase_or_phrase)

            if sessions is not None:
                self._keystore_unlocked = True
                self._session_keys = sessions
                swapped = self.ensure_surface_swap()
                response = {"success": True}
                if swapped:
                    response["surface_swapped"] = True
                    response["new_session_id"] = self.current_session_id
                return response
            else:
                self._keystore_unlocked = False
                return {"success": False, "error": "Incorrect passphrase or recovery phrase."}
        except Exception as e:
            self._keystore_unlocked = False
            return {"success": False, "error": str(e)}

    def lock_keystore(self):
        """Lock the keystore (clear in-memory session keys and active master key)."""
        self._keystore_unlocked = False
        self._session_keys = {}
        self._plaintext_backup = []
        self._plaintext_session_id = None
        self._delete_surface_state()
        keystore.clear_active_key()

    def _load_model_privacy(self) -> dict:
        """Load model-level privacy registry from YAML."""
        try:
            import yaml
            privacy_path = os.path.join(os.path.dirname(self.config_path), "config", "model_privacy.yaml")
            if os.path.exists(privacy_path):
                with open(privacy_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "models" in data:
                        return data["models"]
            return {}
        except Exception:
            return {}

    def is_model_private(self, model_name: str) -> bool:
        """Check if a specific model is classified as private in the registry."""
        registry = self._load_model_privacy()
        entry = registry.get(model_name, {})
        if isinstance(entry, dict) and entry.get("stratum") == "private":
            return True
        return False

    def get_private_providers(self) -> List[str]:
        """Return list of provider names where public_stratum is false (local/private)."""
        providers_config = self.config.get("api", {}).get("providers", {})
        private = []
        for name, cfg in providers_config.items():
            if not cfg.get("public_stratum", True):
                private.append(name)
        return private

    def get_public_providers(self) -> List[str]:
        """Return list of provider names where public_stratum is true (cloud/public)."""
        providers_config = self.config.get("api", {}).get("providers", {})
        public = []
        for name, cfg in providers_config.items():
            if cfg.get("public_stratum", True):
                public.append(name)
        return public

    def is_public_provider(self, provider_name: str) -> bool:
        """Return True if the provider routes through a third-party public stratum."""
        providers_config = self.config.get("api", {}).get("providers", {})
        prov_cfg = providers_config.get(provider_name, {})
        return prov_cfg.get("public_stratum", True)  # default to public if unset

    def provider_supports_tools(self, role: str) -> bool:
        routing = self.config.get("api", {}).get("routing", {})
        provider_name = routing.get(role)
        if not provider_name:
            return True
        providers_config = self.config.get("api", {}).get("providers", {})
        prov_cfg = providers_config.get(provider_name, {})
        return prov_cfg.get("support_tools", True)

    def hydrate_system_prompt(self) -> str:
        rules_cfg = self.config.get("rules", {})
        dora_core = ""
        user_rules = ""
        active_braid = ""

        # 1. Read Dora Core
        dora_path = rules_cfg.get("dora_core_path", "")
        dora_backup = rules_cfg.get("dora_core_backup", "")
        if os.path.exists(dora_path):
            with open(dora_path, "r", encoding="utf-8") as f:
                dora_core = f.read()
        elif os.path.exists(dora_backup):
            with open(dora_backup, "r", encoding="utf-8") as f:
                dora_core = f.read()

        # 2. Read User Rules
        user_rules_backup = rules_cfg.get("user_global_rules_backup", "")
        if os.path.exists(user_rules_backup):
            with open(user_rules_backup, "r", encoding="utf-8") as f:
                user_rules = f.read()

        # 3. Ingest ACTIVE_BRAID
        workspace_cfg = self.config.get("workspace", {})
        braid_filename = workspace_cfg.get("active_braid_file", "ACTIVE_BRAID.md")
        braid_path = os.path.join(workspace_cfg.get("root_path", ""), braid_filename)
        if os.path.exists(braid_path):
            with open(braid_path, "r", encoding="utf-8") as f:
                active_braid = f.read()

        # Compile prompt
        prompt_parts = []
        if dora_core:
            prompt_parts.append(f"=== IDENTITY CORE (DORA CORE) ===\n{dora_core}")
        if user_rules:
            prompt_parts.append(f"=== COLLABORATION RULES ===\n{user_rules}")
        if active_braid:
            prompt_parts.append(f"=== ACTIVE WORKSPACE STATE (ACTIVE BRAID) ===\n{active_braid}")

        # 4. Tool Cache instruction
        cache_instruction = (
            "You have a tool result cache. When you see [CACHED:<ref_id>] in a tool message, "
            "the full result is stored on disk. Use the read_cache tool to retrieve it if "
            "you need the complete data. Otherwise, the pointer summary is sufficient context."
        )
        prompt_parts.append(f"=== TOOL CACHE ===\n{cache_instruction}")

        self.system_prompt = "\n\n".join(prompt_parts)
        return self.system_prompt

    def initialize_session(self):
        import uuid
        self.conversation_history.clear()
        self.hydrate_system_prompt()
        if self.system_prompt:
            self.conversation_history.append({
                "role": "system",
                "content": self.system_prompt
            })
        self.current_session_id = f"chat_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
        self._write_heartbeat("initialized")

    # ── Contract Layer Methods ──────────────────────────────────────

    def set_contract(self, contract: WorkContract):
        """Activate a work contract with guardrails."""
        self.contract_monitor.set_contract(contract)
        print(f"\n[DeepGravity] Contract activated: {contract.description[:80]}")
        print(self.contract_monitor.get_contract_summary())
        self._contract_violation_buffer.clear()

    def clear_contract(self):
        """Remove the active contract, falling back to per-tool approval."""
        if self.contract_monitor.has_active_contract():
            print("\n[DeepGravity] Contract deactivated. Returning to per-tool approval.")
        self.contract_monitor.clear_contract()
        self._contract_violation_buffer.clear()

    def has_active_contract(self) -> bool:
        return self.contract_monitor.has_active_contract()

    def get_contract_summary(self) -> str:
        return self.contract_monitor.get_contract_summary()

    def build_contract_from_request(self, user_text: str) -> WorkContract:
        """Parse natural language into a contract, using workspace root as allowed path."""
        root = self.config.get("workspace", {}).get("root_path", "")
        return build_contract_from_request(user_text, workspace_root=root)

    def format_contract_for_approval(self, contract: WorkContract) -> str:
        """Format contract for user review before activation."""
        return ContractParser.format_contract_summary(contract)

    def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """
        Routes and executes proposed tool actions, trapping exceptions.
        """
        print(f"\n[DeepGravity] Running tool call: {name} with arguments: {json.dumps(args)}")
        
        workspace_root = os.path.abspath(self.config.get("workspace", {}).get("root_path", ""))
        allowed_paths = [workspace_root] + [
            os.path.abspath(p) for p in self.config.get("workspace", {}).get("allowed_paths", []) if p
        ]
        
        def validate_path(p: str) -> str:
            resolved = os.path.abspath(os.path.normpath(p))
            for allowed in allowed_paths:
                if resolved.startswith(allowed):
                    return resolved
            raise ValueError(f"Access Denied: Path '{p}' is outside the sovereign workspace boundary ({allowed_paths}).")
            return resolved

        try:
            # Enforce path validations
            for key in ["absolute_path", "directory_path", "search_path"]:
                if key in args:
                    args[key] = validate_path(args[key])
            
            # ── Contract Check ──
            if self.contract_monitor.has_active_contract():
                violation = self.contract_monitor.check_tool_call(name, args)
                if violation is not None:
                    self._contract_violation_buffer.append({
                        "type": violation.violation_type,
                        "message": str(violation),
                        "tool": name,
                        "args": args,
                        "details": violation.details
                    })
                    return f"[CONTRACT VIOLATION] {violation.violation_type}: {violation}"
            
            # ── Execute Tool ──
            if name == "view_file":
                result = self.file_ops.view_file(
                    absolute_path=args["absolute_path"],
                    start_line=args.get("start_line"),
                    end_line=args.get("end_line")
                )
            elif name == "write_file":
                result = self.file_ops.write_file(
                    absolute_path=args["absolute_path"],
                    content=args["content"],
                    overwrite=args.get("overwrite", False)
                )
            elif name == "edit_file_content":
                result = self.file_ops.edit_file_content(
                    absolute_path=args["absolute_path"],
                    target_content=args["target_content"],
                    replacement_content=args["replacement_content"]
                )
            elif name == "run_command":
                command = args["command"]
                cwd = args["cwd"]
                is_bg = args.get("background", False)
                if is_bg:
                    approved = self.guardrails.show_command_prompt(command, cwd)
                    if not approved:
                        result = "[-] Background command execution aborted by user."
                    else:
                        task_id = self.task_manager.start_task(command, cwd)
                        result = f"[+] Task spawned in background. Task ID: {task_id}. Live log tail: {self.task_manager.active_tasks[task_id]['log_file']}"
                else:
                    exit_code, output = self.shell_runner.run_command(command, cwd)
                    result = f"Exit Code: {exit_code}\nOutput:\n{output}"
            elif name == "manage_task":
                action = args["action"]
                task_id = args.get("task_id")
                input_str = args.get("input")
                
                if action == "list":
                    tasks = self.task_manager.list_tasks()
                    result = json.dumps(tasks, indent=2)
                elif action == "status":
                    if not task_id:
                        result = "Error: task_id is required for 'status' action."
                    else:
                        status = self.task_manager.get_task_status(task_id)
                        result = json.dumps(status, indent=2)
                elif action == "send_input":
                    if not task_id or not input_str:
                        result = "Error: task_id and input are required for 'send_input' action."
                    else:
                        result = self.task_manager.send_input(task_id, input_str)
                elif action == "kill":
                    if not task_id:
                        result = "Error: task_id is required for 'kill' action."
                    else:
                        result = self.task_manager.kill_task(task_id)
                else:
                    result = f"Error: Action '{action}' is not supported."
            elif name == "list_dir":
                items = self.search_ops.list_dir(directory_path=args["directory_path"])
                result = json.dumps(items, indent=2)
            elif name == "grep_search":
                grep_result = self.search_ops.grep_search(
                    search_path=args["search_path"],
                    query=args["query"],
                    case_insensitive=args.get("case_insensitive", True),
                    is_regex=args.get("is_regex", False),
                    include_globs=args.get("include_globs"),
                    max_results=args.get("max_results", 20),
                    truncate_content=args.get("truncate_content", 250)
                )
                result = json.dumps(grep_result, indent=2)
            elif name == "web_search":
                search_result = self.web_search.search(
                    query=args["query"],
                    max_results=args.get("max_results", 8)
                )
                result = json.dumps(search_result, indent=2)
            elif name == "analyze_image":
                img_result = self.vision.analyze_image(
                    image_path=args["image_path"],
                    prompt=args.get("prompt", "Describe this image in detail.")
                )
                if img_result.get("error"):
                    result = f"Error: {img_result['error']}"
                elif img_result.get("_multimodal_messages"):
                    result = img_result
                else:
                    result = img_result.get("description", "No result")
            elif name == "analyze_image_from_url":
                img_result = self.vision.analyze_image_from_url(
                    image_url=args["image_url"],
                    prompt=args.get("prompt", "Describe this image in detail.")
                )
                if img_result.get("error"):
                    result = f"Error: {img_result['error']}"
                elif img_result.get("_multimodal_messages"):
                    result = img_result
                else:
                    result = img_result.get("description", "No result")
            elif name == "read_cache":
                ref_id = args.get("ref_id", "")
                cached = self.tool_cache.retrieve(ref_id)
                if cached is not None:
                    result = cached
                else:
                    result = f"[CACHE MISS] No cached result for ref_id '{ref_id}'."
            else:
                result = f"Error: Tool '{name}' is not recognized."
            
            # Multimodal tool result: send through current provider
            if isinstance(result, dict) and result.get("_multimodal_messages"):
                try:
                    dialogue = self.get_provider_for_role("attunement_core")
                    coder = self.get_provider_for_role("primary_orchestrator")
                    provider = dialogue or coder
                    if provider:
                        img_content, _, _ = provider.generate_response(
                            result["_multimodal_messages"]
                        )
                        result = img_content or "(no description returned)"
                    else:
                        result = "Error: No provider available for vision analysis."
                except Exception as e:
                    result = f"Error analyzing image: {e}"
            
            # ── Tool Result Cache ──
            # Cache large string results and replace with a pointer
            if isinstance(result, str) and len(result) >= 1024 and name != "read_cache":
                ref_id = self.tool_cache.store(name, args, result)
                if ref_id is not None:
                    result = self.tool_cache.make_pointer(ref_id, name, args, len(result))
            
            # Record result for contract spinning detection
            self.contract_monitor.record_result(name, args, result)
            return result
            
        except Exception as e:
            error_msg = f"Error executing tool '{name}': {e}"
            self.contract_monitor.record_result(name, args, error_msg)
            return error_msg

    def sanitize_conversation_history(self):
        """
        Sanitizes the conversation history to ensure that all assistant messages
        containing 'tool_calls' are followed by tool messages for each tool_call_id.
        Backfills dummy tool responses for any dangling tool calls to prevent API 400 errors.
        Also backfills missing reasoning_content on assistant messages for thinking models.
        Also strips orphaned tool messages that lack a preceding assistant with matching tool_calls.
        Also strips assistant messages with empty/null tool_calls that could orphan subsequent tools.
        """
        sanitized = []
        i = 0
        n = len(self.conversation_history)
        
        # Track the last assistant that had real tool_calls, so we can validate tool messages
        last_tool_call_ids = set()
        
        while i < n:
            msg = dict(self.conversation_history[i])  # copy to avoid mutating originals
            
            # Backfill missing reasoning_content on assistant messages
            # (some providers/models require reasoning_content to be present in history)
            if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                msg["reasoning_content"] = None
            
            # --- Assistant message processing ---
            if msg.get("role") == "assistant":
                # Determine if this assistant has real tool_calls
                raw_tool_calls = msg.get("tool_calls")
                tool_calls = raw_tool_calls if isinstance(raw_tool_calls, list) and len(raw_tool_calls) > 0 else []
                tc_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
                
                if tc_ids:
                    # This assistant has real tool_calls — track for subsequent tool message validation
                    last_tool_call_ids = tc_ids
                    
                    sanitized.append(msg)
                    
                    # Check subsequent messages for tool responses matching these IDs
                    j = i + 1
                    matched_ids = set()
                    while j < n:
                        sub_msg = self.conversation_history[j]
                        if sub_msg.get("role") == "tool":
                            tc_id = sub_msg.get("tool_call_id")
                            if tc_id in tc_ids:
                                matched_ids.add(tc_id)
                        elif sub_msg.get("role") in {"user", "assistant"}:
                            # Hit next round of turn without responding to tools
                            break
                        j += 1
                    
                    # If there are missing tool call responses, backfill them
                    missing_ids = tc_ids - matched_ids
                    if missing_ids:
                        print(f"[DeepGravity] Resiliency: Backfilling {len(missing_ids)} dangling tool call responses.")
                        for tc_id in missing_ids:
                            sanitized.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": "Error: Connection interrupted or session restarted before tool execution completed."
                            })
                else:
                    # Assistant has empty/null tool_calls or no tool_calls key at all
                    # Strip the tool_calls key if it's empty/null to prevent API confusion
                    if "tool_calls" in msg:
                        if not raw_tool_calls or (isinstance(raw_tool_calls, list) and len(raw_tool_calls) == 0):
                            del msg["tool_calls"]
                    
                    # Reset last_tool_call_ids — tool messages after this are orphaned
                    last_tool_call_ids = set()
                    
                    sanitized.append(msg)
            
            # --- Tool message processing ---
            elif msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id")
                if tc_id and tc_id in last_tool_call_ids:
                    # This tool message belongs to the last assistant with tool_calls
                    sanitized.append(msg)
                else:
                    # Orphaned tool message — strip it to prevent API 400 errors
                    print(f"[DeepGravity] Resiliency: Stripping orphaned tool message (tool_call_id={tc_id}) with no preceding assistant tool_calls.")
                    # Skip appending — effectively removing the orphan
            
            # --- All other roles (system, user) ---
            else:
                sanitized.append(msg)
            
            i += 1
            
        self.conversation_history = sanitized

    # ── Heartbeat Monitor ──────────────────────────────────────────────
    def _write_heartbeat(self, status="alive"):
        """Writes a lightweight heartbeat file for the external watcher process."""
        try:
            heartbeat = {
                "timestamp": time.time(),
                "loop_count": self._loop_count,
                "status": status,
                "last_tool": self._last_tool_name,
                "history_len": len(self.conversation_history),
                "session": getattr(self, "current_session_id", None),
                "pid": os.getpid(),
                "pending_approval": self._pending_approval,
                "watchdog": self.watchdog.get_status() if hasattr(self, "watchdog") else None,
                "providers": {
                    role: {
                        "provider": name,
                        "errors": self._provider_errors.get(name, {"consecutive": 0, "last_failure": 0})["consecutive"]
                    }
                    for role, name in self._current_provider_for_role.items()
                }
            }
            with open(self._heartbeat_path, "w", encoding="utf-8") as f:
                json.dump(heartbeat, f)
        except Exception:
            pass  # heartbeat write failure is non-fatal

    # ── Agent Loop ─────────────────────────────────────────────────────
    def run_agent_loop(self, user_text: str) -> str:
        """
        The main agent execution loop. Takes user input, prompts the active provider
        (preferring attunement_core, falling back to primary_orchestrator),
        handles tool execution loops recursively, and returns the final dialogue.
        """
        self.sanitize_conversation_history()
        self.conversation_history.append({
            "role": "user",
            "content": user_text
        })
        self.save_conversation_history()
        self._write_heartbeat("active")

        dialogue_provider = self.get_provider_for_role("attunement_core")
        coder_provider = self.get_provider_for_role("primary_orchestrator")

        # Set active provider: prefer the attunement core (dialogue) for the primary interface loop
        active_provider = dialogue_provider if dialogue_provider else coder_provider
        if not active_provider:
            raise RuntimeError(
                "\u26a0\ufe0f No AI provider configured.\n\n"
                "Open Settings (gear icon in the sidebar) \u2192 add a provider with your API endpoint and key \u2192 Save.\n"
                "Then send your message again."
            )

        # Expose tools only if the active provider model supports them
        active_role = "attunement_core" if active_provider == dialogue_provider else "primary_orchestrator"
        tools_to_expose = self.tools_schema if self.provider_supports_tools(active_role) else None

        # ── Depth Dial Gate (non-streaming) ──
        active_provider_name = self._current_provider_for_role.get(active_role, "unknown")
        depth_gate_result = self.check_depth_gate(active_provider_name)
        if depth_gate_result is not None:
            self.conversation_history.append({
                "role": "assistant",
                "content": f"⚠️ DEPTH GATE\n\n{depth_gate_result}"
            })
            self.save_conversation_history()
            return f"\n\n*{depth_gate_result}*\n\n"

        while True:
            self._loop_count += 1
            self._write_heartbeat("processing")

            # Wrap API call in error tracking for failover routing
            provider_name = self._current_provider_for_role.get(active_role, "unknown")
            try:
                content, tool_calls, reasoning_content = active_provider.generate_response(
                    self.conversation_history, 
                    tools=tools_to_expose
                )
                self.record_provider_success(provider_name)
                self._last_working_provider[active_role] = provider_name
            except Exception as e:
                self.record_provider_error(provider_name)
                print(f"[DeepGravity] Provider error ({provider_name}): {e}")
                # Try fallback providers before giving up
                fallback = self._try_fallback_provider(active_role)
                if fallback:
                    print(f"[DeepGravity] Retrying with fallback provider for role {active_role}")
                    active_provider = fallback
                    provider_name = self._current_provider_for_role.get(active_role, "unknown")
                    continue
                raise  # all fallbacks exhausted

            assistant_msg = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            
            self.conversation_history.append(assistant_msg)
            self.save_conversation_history()

            if not tool_calls:
                self._write_heartbeat("idle")
                return content if content else ""

            # Execute tool calls sequentially
            for tool_call in tool_calls:
                func = tool_call["function"]
                self._last_tool_name = func["name"]
                self._write_heartbeat("tool_exec")
                self.save_conversation_history()  # persist before risky tool call
                tool_result = self.execute_tool(func["name"], json.loads(func["arguments"]))
                
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": func["name"],
                    "content": tool_result
                })
                self.save_conversation_history()
            
            # ── Spinning Detection ──
            if self.contract_monitor.has_active_contract():
                spin_check = self.contract_monitor.check_spinning()
                if spin_check is not None:
                    spin_msg = f"[SPINNING DETECTED] {spin_check['message']}"
                    print(f"\n[DeepGravity] {spin_msg}")
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": f"\n\n*{spin_msg}*\n\nI've paused because I detected I might be in a loop. Here's what I was doing:\n- Tool: `{spin_check['tool'] if 'tool' in spin_check else spin_check.get('type', 'unknown')}`\n- Issue: {spin_check['message']}\n\nPlease review and let me know how to proceed — adjust the plan, or let me continue.\n"
                    })
                    self.save_conversation_history()
                    return self.conversation_history[-1]["content"]

    def run_agent_loop_stream(self, user_text: str) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming version of the agent execution loop. Yields tokens and tool execution markers.
        """
        self.sanitize_conversation_history()
        self.conversation_history.append({
            "role": "user",
            "content": user_text
        })
        self.save_conversation_history()
        self._write_heartbeat("active")

        dialogue_provider = self.get_provider_for_role("attunement_core")
        coder_provider = self.get_provider_for_role("primary_orchestrator")

        # Set active provider: prefer the attunement core for the primary loop
        active_provider = dialogue_provider if dialogue_provider else coder_provider
        if not active_provider:
            raise RuntimeError(
                "\u26a0\ufe0f No AI provider configured.\n\n"
                "Open Settings (gear icon in the sidebar) \u2192 add a provider with your API endpoint and key \u2192 Save.\n"
                "Then send your message again."
            )

        # Expose tools only if the active provider model supports them
        active_role = "attunement_core" if active_provider == dialogue_provider else "primary_orchestrator"
        tools_to_expose = self.tools_schema if self.provider_supports_tools(active_role) else None

        # Resolve provider name and config for gate checks
        providers_config = self.config.get("api", {}).get("providers", {})
        active_provider_name = self._current_provider_for_role.get(active_role, "unknown")
        active_model_name = providers_config.get(active_provider_name, {}).get("model", "")

        # ── Depth Dial Gate ──
        # Check if the active provider can handle the current depth level
        depth_gate_result = self.check_depth_gate(active_provider_name)
        if depth_gate_result is not None:
            self.conversation_history.append({
                "role": "assistant",
                "content": f"⚠️ DEPTH GATE\n\n{depth_gate_result}"
            })
            self.save_conversation_history()
            yield {"type": "content", "content": f"\n\n*{depth_gate_result}*\n\n"}
            self._write_heartbeat("idle")
            return

        # Reset stop flag at start of execution
        self._stop_requested = False

        while True:
            self._loop_count += 1
            self._write_heartbeat("processing")

            # Check for stop request before each iteration
            if getattr(self, '_stop_requested', False):
                self._stop_requested = False
                self.conversation_history.append({
                    "role": "assistant",
                    "content": "[Execution stopped by user.]"
                })
                self.save_conversation_history()
                yield {"type": "content", "content": "\n\n*[Execution stopped by user.]*"}
                return

            provider_name = self._current_provider_for_role.get(active_role, "unknown")
            try:
                stream = active_provider.generate_stream(self.conversation_history, tools=tools_to_expose)
                self.record_provider_success(provider_name)
                self._last_working_provider[active_role] = provider_name
            except Exception as e:
                self.record_provider_error(provider_name)
                print(f"[DeepGravity] Provider stream error ({provider_name}): {e}")
                # Try fallback providers before giving up
                fallback = self._try_fallback_provider(active_role)
                if fallback:
                    print(f"[DeepGravity] Retrying streaming with fallback provider for role {active_role}")
                    active_provider = fallback
                    provider_name = self._current_provider_for_role.get(active_role, "unknown")
                    continue
                yield {"type": "error", "content": f"Provider error: {e}"}
                return
            
            full_content = []
            full_reasoning = []
            tool_calls_buffer = {}

            for chunk in stream:
                # Check for stop request mid-stream
                if getattr(self, '_stop_requested', False):
                    self._stop_requested = False
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": "[Execution stopped by user.]"
                    })
                    self.save_conversation_history()
                    yield {"type": "content", "content": "\n\n*[Execution stopped by user.]*"}
                    return

                content_chunk = chunk.get("content")
                reasoning_chunk = chunk.get("reasoning_content")
                tool_calls_chunk = chunk.get("tool_calls")

                if content_chunk:
                    full_content.append(content_chunk)
                    yield {"type": "content", "content": content_chunk}

                if reasoning_chunk:
                    full_reasoning.append(reasoning_chunk)
                    # Also yield reasoning as a separate type so the UI can display it if desired
                    yield {"type": "reasoning", "content": reasoning_chunk}

                if tool_calls_chunk:
                    for tc in tool_calls_chunk:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {"name": "", "arguments": ""}
                            }
                        
                        if tc.id:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.type:
                            tool_calls_buffer[idx]["type"] = tc.type
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

            # Compile results of stream
            assistant_content = "".join(full_content)
            assistant_reasoning = "".join(full_reasoning) if full_reasoning else None
            
            tool_calls = []
            if tool_calls_buffer:
                for idx in sorted(tool_calls_buffer.keys()):
                    tool_calls.append(tool_calls_buffer[idx])

            assistant_msg = {"role": "assistant"}
            if assistant_content:
                assistant_msg["content"] = assistant_content
            if assistant_reasoning:
                assistant_msg["reasoning_content"] = assistant_reasoning
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            
            self.conversation_history.append(assistant_msg)
            self.save_conversation_history()
            self._write_heartbeat("assistant_done")

            if not tool_calls:
                self._write_heartbeat("idle")
                return

            # Execute tool calls sequentially
            for tc in tool_calls:
                func = tc["function"]
                self._last_tool_name = func["name"]
                self._write_heartbeat("tool_exec")
                yield {"type": "tool_start", "name": func["name"], "arguments": func["arguments"]}
                
                self.save_conversation_history()  # persist before risky tool call
                try:
                    args = json.loads(func["arguments"])
                    tool_result = self.execute_tool(func["name"], args)
                except Exception as e:
                    tool_result = f"Error executing tool '{func['name']}': {e}"
                
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func["name"],
                    "content": tool_result
                })
                self.save_conversation_history()
                
                yield {"type": "tool_end", "name": func["name"], "result": tool_result}
                
                # ── Spinning Detection (streaming) ──
                if self.contract_monitor.has_active_contract():
                    spin_check = self.contract_monitor.check_spinning()
                    if spin_check is not None:
                        spin_msg = f"[SPINNING DETECTED] {spin_check['message']}"
                        print(f"\n[DeepGravity] {spin_msg}")
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": f"\n\n*{spin_msg}*\n\nPlease review and let me know how to proceed."
                        })
                        self.save_conversation_history()
                        yield {"type": "spinning_detected", "message": spin_check['message'], "details": spin_check}
                        return

    def get_credential(self, name: str) -> Optional[str]:
        """
        Resilient resolver for credentials/keys.
        Retrieves the key string by name from the config, falling back to backup_path.
        """
        credentials = self.config.get("credentials", [])
        for cred in credentials:
            if cred.get("name") == name:
                key = cred.get("key_string")
                if key:
                    return key
                
                # Fallback to backup_path
                backup_path = cred.get("backup_path")
                if backup_path and os.path.exists(backup_path):
                    try:
                        with open(backup_path, "r", encoding="utf-8") as f:
                            return f.read().strip()
                    except Exception as e:
                        print(f"[DeepGravity] Failed to read backup credential from {backup_path}: {e}")
        return None

    @staticmethod
    def _safe_json_dumps(obj):
        """
        JSON-serialize an object, falling back to string coercion for
        any non-serializable types. Prevents zero-byte tmp files from
        serialization failures that leave orphaned stubs.
        """
        def _sanitize(o, _depth=0):
            if _depth > 20:
                return "<max recursion depth>"
            if isinstance(o, (str, int, float, bool, type(None))):
                return o
            if isinstance(o, dict):
                return {str(k): _sanitize(v, _depth + 1) for k, v in o.items()}
            if isinstance(o, (list, tuple, set)):
                return [_sanitize(i, _depth + 1) for i in o]
            # bytes, callable, cyclic, etc. — coerce to string
            try:
                return str(o)
            except Exception:
                return "<unserializable object>"
        try:
            return json.dumps(obj, indent=2, default=str)
        except (TypeError, ValueError):
            return json.dumps(_sanitize(obj), indent=2)

    def save_conversation_history(self):
        """
        Saves the conversation history to a local JSON file in the logs directory.
        If depth is U or X and keystore is unlocked, encrypts at rest with AES-256-GCM
        using a per-session key stored in the in-memory keyring.
        Uses atomic tmp-file + rename to prevent truncation on write failure.
        """
        if not hasattr(self, "current_session_id") or not self.current_session_id:
            return
        chat_dir = os.path.join(os.path.dirname(self.config_path), "logs", "chats")
        os.makedirs(chat_dir, exist_ok=True)
        file_path = os.path.join(chat_dir, f"{self.current_session_id}.json")
        tmp_path = file_path + ".tmp"
        try:
            # T-mode encryption pipeline
            if self.depth_level == "T" and self._keystore_unlocked:
                plaintext = self._safe_json_dumps(self.conversation_history)
                # Generate or retrieve session key
                sess_key_b64 = self._session_keys.get(self.current_session_id)
                if sess_key_b64:
                    session_key = base64.b64decode(sess_key_b64)
                else:
                    session_key = keystore.generate_session_key()
                    self._session_keys[self.current_session_id] = base64.b64encode(session_key).decode()
                    keystore.add_session_key(self.current_session_id, session_key)
                # Encrypt and write to tmp, then atomic rename
                wrapped = keystore.encrypt_session_data(plaintext, session_key)
                wrapped["session_id"] = self.current_session_id
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(wrapped, f)
                os.replace(tmp_path, file_path)
            else:
                # Plaintext save (G/M/O or keystore locked) — serialize, write to tmp, atomic rename
                serialized = self._safe_json_dumps(self.conversation_history)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(serialized)
                os.replace(tmp_path, file_path)
        except Exception as e:
            print(f"[DeepGravity] FAILED TO SAVE CONVERSATION HISTORY: {e}")
            traceback.print_exc()
            # Clean up orphaned tmp file on failure so it doesn't poison future saves
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def load_session(self, session_id: str) -> bool:
        """
        Loads a specific conversation history from logs/chats/<session_id>.json.
        If the file contains an _encrypted wrapper, decrypts using the session key
        from the in-memory keyring (requires keystore to be unlocked).
        """
        chat_dir = os.path.join(os.path.dirname(self.config_path), "logs", "chats")
        file_path = os.path.join(chat_dir, f"{session_id}.json")
        if not os.path.exists(file_path):
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Detect encrypted session
            if isinstance(data, dict) and data.get("_encrypted"):
                if not self._keystore_unlocked:
                    print(f"[DeepGravity] Cannot load encrypted session {session_id}: keystore locked.")
                    return False
                # Retrieve session key from keyring
                sess_key_b64 = self._session_keys.get(session_id)
                if not sess_key_b64:
                    print(f"[DeepGravity] Cannot load encrypted session {session_id}: session key not in keyring.")
                    return False
                session_key = base64.b64decode(sess_key_b64)
                plaintext = keystore.decrypt_session_data(data, session_key)
                if plaintext is None:
                    print(f"[DeepGravity] Failed to decrypt session {session_id}.")
                    return False
                history = json.loads(plaintext)
            else:
                # Plaintext session
                history = data

            # Re-hydrate system prompt in case the config rules have changed
            self.hydrate_system_prompt()
            if history and history[0].get("role") == "system":
                history[0]["content"] = self.system_prompt
            self.conversation_history = history
            self.current_session_id = session_id
            return True
        except Exception as e:
            print(f"[DeepGravity] Failed to load session {session_id}: {e}")
            return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        Lists saved chat sessions gated by encryption stratum.
        U/X-mode (keystore unlocked) shows only encrypted sessions.
        All other modes show only plaintext sessions.
        """
        chat_dir = os.path.join(os.path.dirname(self.config_path), "logs", "chats")
        if not os.path.exists(chat_dir):
            return []
        
        show_encrypted = (self.depth_level == "T" and self._keystore_unlocked)
        
        sessions = []
        for fname in os.listdir(chat_dir):
            if fname.endswith(".json"):
                sid = fname[:-5]
                file_path = os.path.join(chat_dir, fname)
                try:
                    mtime = os.path.getmtime(file_path)
                    formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # ── Stratum gate ──
                    is_encrypted = isinstance(data, dict) and data.get("_encrypted")
                    if show_encrypted and not is_encrypted:
                        continue
                    if not show_encrypted and is_encrypted:
                        continue
                    
                    # Don't parse encrypted bodies for previews
                    history = data if not is_encrypted else []
                    title = "Encrypted Session" if is_encrypted else "Empty Session"
                    preview = "" if is_encrypted else ""
                    for msg in history:
                        if msg.get("role") == "user":
                            title = msg.get("content", "")[:50].strip()
                            if len(msg.get("content", "")) > 50:
                                title += "..."
                            break
                    for msg in reversed(history):
                        if msg.get("role") == "assistant" and msg.get("content"):
                            preview = msg.get("content", "")[:100].strip()
                            if len(msg.get("content", "")) > 100:
                                preview += "..."
                            break
                    sessions.append({
                        "id": sid,
                        "time": formatted_time,
                        "timestamp": mtime,
                        "title": title,
                        "preview": preview,
                        "encrypted": is_encrypted
                    })
                except Exception:
                    pass
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        return sessions


