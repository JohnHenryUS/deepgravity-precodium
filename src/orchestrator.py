import os
import json
import time
from typing import Dict, List, Any, Optional, Tuple, Generator
from src.providers.openai_compat import OpenAICompatProvider
from src.tools.file_ops import FileOperations
from src.tools.shell import ShellCommandRunner
from src.tools.search import SearchOperations
from src.tools.task_manager import TaskManager
from src.safety import SafetyGuardrails
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
        self._failover_config = self.config.get("api", {}).get("failover", {})
        self._failover_threshold = self.config.get("api", {}).get("failover_threshold", 3)

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
            else:
                result = f"Error: Tool '{name}' is not recognized."
            
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
            raise RuntimeError("No LLM provider resolved for agent execution loop.")

        # Expose tools only if the active provider model supports them
        active_role = "attunement_core" if active_provider == dialogue_provider else "primary_orchestrator"
        tools_to_expose = self.tools_schema if self.provider_supports_tools(active_role) else None

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
            except Exception as e:
                self.record_provider_error(provider_name)
                print(f"[DeepGravity] Provider error ({provider_name}): {e}")
                raise  # let the outer loop handle retry/failover

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
            raise RuntimeError("No LLM provider resolved for agent execution loop.")

        # Expose tools only if the active provider model supports them
        active_role = "attunement_core" if active_provider == dialogue_provider else "primary_orchestrator"
        tools_to_expose = self.tools_schema if self.provider_supports_tools(active_role) else None

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
            except Exception as e:
                self.record_provider_error(provider_name)
                print(f"[DeepGravity] Provider stream error ({provider_name}): {e}")
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

    def save_conversation_history(self):
        """
        Saves the conversation history to a local JSON file in the logs directory.
        """
        if not hasattr(self, "current_session_id") or not self.current_session_id:
            return
        chat_dir = os.path.join(os.path.dirname(self.config_path), "logs", "chats")
        os.makedirs(chat_dir, exist_ok=True)
        file_path = os.path.join(chat_dir, f"{self.current_session_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.conversation_history, f, indent=2)
        except Exception as e:
            print(f"[DeepGravity] Failed to save conversation history: {e}")

    def load_session(self, session_id: str) -> bool:
        """
        Loads a specific conversation history from logs/chats/<session_id>.json.
        """
        chat_dir = os.path.join(os.path.dirname(self.config_path), "logs", "chats")
        file_path = os.path.join(chat_dir, f"{session_id}.json")
        if not os.path.exists(file_path):
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                history = json.load(f)
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
        Lists all saved chat sessions with titles, timestamps, and last assistant responses.
        """
        chat_dir = os.path.join(os.path.dirname(self.config_path), "logs", "chats")
        if not os.path.exists(chat_dir):
            return []
        sessions = []
        for fname in os.listdir(chat_dir):
            if fname.endswith(".json"):
                sid = fname[:-5]
                file_path = os.path.join(chat_dir, fname)
                try:
                    mtime = os.path.getmtime(file_path)
                    formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                    with open(file_path, "r", encoding="utf-8") as f:
                        history = json.load(f)
                    
                    title = "Empty Session"
                    preview = ""
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
                        "preview": preview
                    })
                except Exception:
                    pass
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        return sessions


