import os
import sys
import json
import asyncio
import threading
import queue
import difflib
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.orchestrator import DeepGravityOrchestrator

app = FastAPI(title="DeepGravity Sovereign IDE")

# Resolve workspace config
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))
if not os.path.exists(config_path):
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json.template"))

orchestrator = DeepGravityOrchestrator(config_path)
orchestrator.initialize_session()

# Global approval queue and WebSocket reference for thread callbacks
active_approval_queue: Optional[queue.Queue] = None
active_websocket: Optional[WebSocket] = None
active_loop: Optional[asyncio.AbstractEventLoop] = None
active_log_websockets = set()

def broadcast_log(message: str):
    if not active_log_websockets or not active_loop:
        return
    for ws in list(active_log_websockets):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(message), active_loop)
        except Exception:
            pass

# Reentrant-safe stdout/stderr wrapper to capture all output for the live log stream
class ReentrantSafeStdout:
    _local = threading.local()

    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, data):
        self.original_stream.write(data)
        self.original_stream.flush()
        if getattr(self._local, "writing", False):
            return
        if data.strip():
            # Avoid infinite feedback loop from websocket connection/traffic logging
            lower_data = data.lower()
            if any(marker in lower_data for marker in ["websocket", "ws/", "connection open", "connection closed"]):
                return
            self._local.writing = True
            try:
                broadcast_log(data.strip())
            except Exception:
                pass
            finally:
                self._local.writing = False

    def flush(self):
        self.original_stream.flush()

    def __getattr__(self, name):
        return getattr(self.original_stream, name)

sys.stdout = ReentrantSafeStdout(sys.stdout)
sys.stderr = ReentrantSafeStdout(sys.stderr)

# Hook TaskManager logs to broadcast_log
def task_log_callback(task_id: str, line: str):
    broadcast_log(f"[{task_id}] {line.rstrip()}")

if hasattr(orchestrator, "task_manager"):
    orchestrator.task_manager.log_callback = task_log_callback

# Custom models
class FileWriteRequest(BaseModel):
    path: str
    content: str

class TerminalCommandRequest(BaseModel):
    command: str
    cwd: str

class TaskKillRequest(BaseModel):
    task_id: str


def run_chat_worker(msg_queue: queue.Queue, loop: asyncio.AbstractEventLoop, websocket: WebSocket, approval_queue: queue.Queue):
    """
    Worker thread that pulls user messages from the queue and runs the orchestrator agent loop sequentially.
    """
    global orchestrator

    def cmd_approval(command: str, cwd: str) -> bool:
        # Send approval request to Web Client
        asyncio.run_coroutine_threadsafe(
            websocket.send_json({
                "type": "approval_required",
                "action": "command",
                "command": command,
                "cwd": cwd
            }),
            loop
        )
        # Block waiting for client response from main thread
        approved = approval_queue.get()
        return approved

    def write_approval(file_path: str, old_content: str, new_content: str, is_new: bool = False) -> bool:
        diff = ""
        if not is_new:
            old_lines = old_content.splitlines()
            new_lines = new_content.splitlines()
            diff_lines = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm=""
            )
            diff = "\n".join(diff_lines)

        # Send approval request to Web Client
        asyncio.run_coroutine_threadsafe(
            websocket.send_json({
                "type": "approval_required",
                "action": "write",
                "file_path": file_path,
                "is_new": is_new,
                "diff": diff,
                "new_content_preview": new_content[:1500]
            }),
            loop
        )
        # Block waiting for client response from main thread
        approved = approval_queue.get()
        return approved

    # Bind callbacks to safety guardrails
    orchestrator.guardrails.command_approval_callback = cmd_approval
    orchestrator.guardrails.write_approval_callback = write_approval

    # Register callback so the orchestrator can push files to the editor
    def open_file_callback(file_path: str):
        asyncio.run_coroutine_threadsafe(
            websocket.send_json({
                "type": "open_file",
                "path": file_path
            }),
            loop
        )
    orchestrator.guardrails.open_file_callback = open_file_callback

    try:
        while True:
            user_text = msg_queue.get()
            if user_text is None:  # Sentinel to exit
                break
            
            try:
                # Run the streaming agent loop
                stream = orchestrator.run_agent_loop_stream(user_text)
                for chunk in stream:
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_json({
                            "type": "stream",
                            "data": chunk
                        }),
                        loop
                    )

                # Notify final session state
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({"type": "complete"}),
                    loop
                )
            except Exception as err:
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({"type": "error", "message": str(err)}),
                    loop
                )
            finally:
                msg_queue.task_done()
    finally:
        # Clean callbacks
        orchestrator.guardrails.command_approval_callback = None
        orchestrator.guardrails.write_approval_callback = None
        orchestrator.guardrails.open_file_callback = None

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    global active_approval_queue, active_websocket, active_loop
    await websocket.accept()
    active_websocket = websocket

    # Create thread-safe queue for this connection's approvals
    approval_queue = queue.Queue()
    active_approval_queue = approval_queue

    # Create thread-safe queue for user messages
    msg_queue = queue.Queue()

    loop = asyncio.get_running_loop()
    active_loop = loop

    # Start single background worker thread for the session
    worker_thread = threading.Thread(
        target=run_chat_worker,
        args=(msg_queue, loop, websocket, approval_queue),
        daemon=True
    )
    worker_thread.start()

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "user_message":
                content = msg.get("content", "")
                active_file = msg.get("active_file")
                
                # Context injection: if a file is open in the editor, inject its content into the user message context
                if active_file:
                    root_dir = orchestrator.config.get("workspace", {}).get("root_path", "")
                    full_path = os.path.abspath(os.path.join(root_dir, active_file))
                    if full_path.startswith(os.path.abspath(root_dir)) and os.path.exists(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                file_content = f.read()
                            context_str = f"[System Context: The user has the file '{active_file}' open in the active editor pane. Content preview:\n```\n{file_content}\n```]\n\n"
                            content = context_str + content
                        except Exception:
                            pass

                if content.strip():
                    # Check if orchestrator is currently busy processing or has queued tasks
                    if msg_queue.unfinished_tasks > 0:
                        await websocket.send_json({
                            "type": "content",
                            "data": "\n\n*[Orchestrator is busy. Your message has been queued and will be processed once the current task clears...]*\n\n"
                        })
                    
                    msg_queue.put(content)

            elif msg_type == "approval_response":
                approved = msg.get("approved", False)
                approval_queue.put(approved)

            elif msg_type == "stop_execution":
                # Signal the orchestrator to halt the current agent loop
                orchestrator._stop_requested = True
                
                # Flush all queued messages
                while not msg_queue.empty():
                    try:
                        msg_queue.get_nowait()
                        msg_queue.task_done()
                    except queue.Empty:
                        break

                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({
                        "type": "content",
                        "data": "[Stop signal sent. Queued messages cleared.]"
                    }),
                    loop
                )

    except WebSocketDisconnect:
        # Unblock thread if it was waiting for approval
        approval_queue.put(False)
        # Shutdown worker thread
        msg_queue.put(None)

        if active_approval_queue == approval_queue:
            active_approval_queue = None
        if active_websocket == websocket:
            active_websocket = None


def build_tree(path: str, root_dir: str) -> list:
    try:
        items = []
        for name in os.listdir(path):
            # Ignore binary folders or build ballast
            if name in {".git", "node_modules", ".venv", "__pycache__", ".obsidian", ".gemini", "logs"}:
                continue
            full_path = os.path.join(path, name)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
            is_dir = os.path.isdir(full_path)
            
            item = {
                "name": name,
                "path": rel_path,
                "is_dir": is_dir
            }
            if is_dir:
                item["children"] = build_tree(full_path, root_dir)
            items.append(item)
        
        # Sort: directories first, then alphabetically
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return items
    except Exception:
        return []

@app.get("/api/files/list")
def list_workspace_files():
    root_dir = orchestrator.config.get("workspace", {}).get("root_path", "")
    if not os.path.exists(root_dir):
        raise HTTPException(status_code=404, detail="Workspace root folder not found.")
    tree = build_tree(root_dir, root_dir)
    return {"workspace": os.path.basename(root_dir), "tree": tree}

@app.get("/api/files/read")
def read_workspace_file(path: str):
    root_dir = orchestrator.config.get("workspace", {}).get("root_path", "")
    full_path = os.path.abspath(os.path.join(root_dir, path))
    
    if not full_path.startswith(os.path.abspath(root_dir)):
        raise HTTPException(status_code=403, detail="Path traversal blocked. Access restricted to workspace.")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

@app.post("/api/files/write")
def write_workspace_file(req: FileWriteRequest):
    root_dir = orchestrator.config.get("workspace", {}).get("root_path", "")
    full_path = os.path.abspath(os.path.join(root_dir, req.path))
    
    if not full_path.startswith(os.path.abspath(root_dir)):
        raise HTTPException(status_code=403, detail="Path traversal blocked. Access restricted to workspace.")

    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"success": True, "path": req.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")

@app.get("/api/config")
def get_current_config():
    return orchestrator.config

@app.post("/api/config")
def update_current_config(new_config: Dict[str, Any]):
    global orchestrator
    try:
        with open(orchestrator.config_path, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=2)
        # Hot-reload configuration and providers
        orchestrator.config = new_config
        orchestrator.providers = orchestrator.init_providers()
        orchestrator.hydrate_system_prompt()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")

@app.post("/api/terminal")
def execute_terminal_command(req: TerminalCommandRequest):
    global orchestrator, active_websocket, active_approval_queue, active_loop
    
    if not active_websocket or not active_approval_queue or not active_loop:
        raise HTTPException(
            status_code=400,
            detail="Chat WebSocket session is not active. Please connect the chat pane first to authorize commands."
        )

    aborted = False

    def cmd_approval(command: str, cwd: str) -> bool:
        nonlocal aborted
        asyncio.run_coroutine_threadsafe(
            active_websocket.send_json({
                "type": "approval_required",
                "action": "command",
                "command": command,
                "cwd": cwd
            }),
            active_loop
        )
        approved = active_approval_queue.get()
        if not approved:
            aborted = True
        return approved

    # Temporarily bind the safety callback to intercept terminal commands
    old_callback = orchestrator.guardrails.command_approval_callback
    orchestrator.guardrails.command_approval_callback = cmd_approval

    try:
        workspace_root = os.path.abspath(orchestrator.config.get("workspace", {}).get("root_path", ""))
        resolved_cwd = os.path.abspath(os.path.normpath(req.cwd))
        if not resolved_cwd.startswith(workspace_root):
            return {
                "success": False,
                "aborted": False,
                "output": f"Access Denied: Path '{req.cwd}' is outside the sovereign workspace boundary ({workspace_root})."
            }

        # Run command synchronously
        exit_code, output = orchestrator.shell_runner.run_command(req.command, resolved_cwd)
        
        if aborted or exit_code == -1:
            return {
                "success": False,
                "aborted": True,
                "output": "[-] Command execution denied by user."
            }
            
        if exit_code == 0:
            return {
                "success": True,
                "aborted": False,
                "output": output
            }
        else:
            return {
                "success": False,
                "aborted": False,
                "output": output,
                "detail": f"Command exited with code {exit_code}"
            }
    except Exception as err:
        return {
            "success": False,
            "aborted": False,
            "output": str(err)
        }
    finally:
        # Restore old callback
        orchestrator.guardrails.command_approval_callback = old_callback

@app.get("/api/config/context")
def get_system_context():
    global orchestrator
    orchestrator.hydrate_system_prompt()
    return {"context": orchestrator.system_prompt}

# ── Contract Layer API (Phase 4.5.2) ──

class ContractRequest(BaseModel):
    description: str

@app.post("/api/contract/parse")
def parse_contract(req: ContractRequest):
    """
    Parse a natural language work request into a contract for user review.
    Returns the formatted contract summary for display.
    """
    global orchestrator
    contract = orchestrator.build_contract_from_request(req.description)
    return {
        "contract_summary": orchestrator.format_contract_for_approval(contract),
        "description": contract.description,
        "guardrails": {
            "destructive_edits": contract.destructive_edit_policy.value,
            "file_deletion": contract.file_deletion_policy.value,
            "max_search_retries": contract.max_search_retries,
            "spinning_detection": contract.spinning_enabled,
            "watchdog_minutes": contract.watchdog_max_minutes,
        }
    }

@app.post("/api/contract/activate")
def activate_contract(req: ContractRequest):
    """
    Parse and activate a work contract from a natural language request.
    """
    global orchestrator
    contract = orchestrator.build_contract_from_request(req.description)
    orchestrator.set_contract(contract)
    return {
        "success": True,
        "message": f"Contract activated. {orchestrator.get_contract_summary()}",
        "contract": contract.description[:200]
    }

@app.post("/api/contract/clear")
def clear_contract():
    """Deactivate the current work contract."""
    global orchestrator
    orchestrator.clear_contract()
    return {"success": True, "message": "Contract deactivated. Per-tool approval restored."}

@app.get("/api/contract/status")
def contract_status():
    """Get the status of the current contract."""
    global orchestrator
    return {
        "active": orchestrator.has_active_contract(),
        "summary": orchestrator.get_contract_summary(),
        "violations": orchestrator._contract_violation_buffer[-5:] if orchestrator._contract_violation_buffer else []
    }

@app.get("/api/contract/violations")
def contract_violations():
    """Get recent contract violations."""
    global orchestrator
    return {"violations": orchestrator._contract_violation_buffer[-20:]}

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    global active_log_websockets
    await websocket.accept()
    active_log_websockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        active_log_websockets.discard(websocket)

@app.get("/api/tasks")
def list_running_tasks():
    return orchestrator.task_manager.list_tasks()

@app.post("/api/tasks/kill")
def kill_task_api(req: TaskKillRequest):
    try:
        result = orchestrator.task_manager.kill_task(req.task_id)
        return {"success": True, "result": result}
    except KeyError:
        raise HTTPException(status_code=404, detail="Task ID not found.")

@app.get("/api/chats/list")
def list_chats():
    return orchestrator.list_sessions()

@app.get("/api/chats/load")
def load_chat(id: str):
    success = orchestrator.load_session(id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return {"success": True, "history": orchestrator.conversation_history}

@app.post("/api/chats/new")
def start_new_chat():
    orchestrator.initialize_session()
    orchestrator.save_conversation_history()
    return {"success": True, "session_id": orchestrator.current_session_id}

# Serves static files or index.html fallback
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))

@app.get("/")
def get_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>DeepGravity Web Interface Staged</h1><p>Please populate static files in src/ui/static/</p>")

@app.get("/api/providers/models")
def list_available_models():
    """
    Queries each configured provider for its available models.
    Returns a merged list of provider name -> model list.
    """
    global orchestrator
    providers_cfg = orchestrator.config.get("api", {}).get("providers", {})
    results = {}
    
    import requests as http_requests
    
    for prov_name, prov_cfg in providers_cfg.items():
        base_url = prov_cfg.get("base_url", "").rstrip("/")
        api_key = prov_cfg.get("api_key", "")
        models = []
        configured_model = prov_cfg.get("model", "")
        
        # Fetch live list if marked as live_directory or if named openwebui-live
        is_live = prov_cfg.get("live_directory", False) or prov_name == "openwebui-live"
        
        if configured_model and str(configured_model).strip() and not is_live:
            models = [str(configured_model).strip()]
        else:
            # Try OpenAI-compatible /v1/models endpoint first
            for endpoint in ["/v1/models", "/api/models", "/models"]:
                try:
                    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                    resp = http_requests.get(f"{base_url}{endpoint}", headers=headers, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        # Handle both OpenAI format { data: [{ id: ... }] } and flat lists
                        if "data" in data and isinstance(data["data"], list):
                            models = [m.get("id") or m.get("name") or str(m) for m in data["data"]]
                        elif isinstance(data, list):
                            models = [m.get("id") or m.get("name") or str(m) for m in data]
                        break
                except Exception:
                    continue
        
        # Fall back to the single model configured in config if we couldn't query
        if not models and configured_model:
            models = [configured_model]
        
        results[prov_name] = {
            "base_url": base_url,
            "models": models,
            "active_model": prov_cfg.get("model", "")
        }
    
    return {"providers": results}

@app.get("/api/extensions/list")
def list_installed_extensions():
    import os
    extensions_dir = os.path.expanduser("~/.antigravity-ide/extensions")
    if not os.path.exists(extensions_dir):
        return {"extensions": []}
    
    extensions = []
    try:
        for name in os.listdir(extensions_dir):
            full_path = os.path.join(extensions_dir, name)
            if os.path.isdir(full_path) and not name.startswith("."):
                manifest_path = os.path.join(full_path, "package.json")
                details = {"id": name, "name": name, "version": "", "description": ""}
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            pkg = json.load(f)
                            details["name"] = pkg.get("displayName") or pkg.get("name") or name
                            details["version"] = pkg.get("version") or ""
                            details["description"] = pkg.get("description") or ""
                    except Exception:
                        pass
                extensions.append(details)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read extensions: {e}")
        
    return {"extensions": extensions}

# ── Static File Self-Healing ──────────────────────────────────────────
BACKUP_DIR = os.path.join(static_dir, "backup")
STATIC_FILES = ["app.js", "style.css", "index.html"]

def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def _backup_static_files():
    """Create last-known-good backups if they don't exist yet."""
    _ensure_backup_dir()
    for fname in STATIC_FILES:
        src = os.path.join(static_dir, fname)
        dst = os.path.join(BACKUP_DIR, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                with open(src, "rb") as sf:
                    with open(dst, "wb") as df:
                        df.write(sf.read())
                print(f"[DeepGravity] Backed up {fname}")
            except Exception as e:
                print(f"[DeepGravity] Failed to backup {fname}: {e}")

def _validate_js_braces(filepath: str) -> tuple:
    """Quick brace/token balance check. Returns (ok: bool, msg: str)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return False, f"Cannot read: {e}"
    
    balance = 0
    for i, ch in enumerate(text):
        if ch in '{([':
            balance += 1
        elif ch in '})]':
            balance -= 1
        if balance < 0:
            lineno = text[:i].count('\n') + 1
            return False, f"Unmatched closing brace at line {lineno}"
    if balance != 0:
        return False, f"Unbalanced braces: {balance} unclosed"
    return True, "OK"

def _static_health() -> dict:
    """Check all static files and report status."""
    results = {}
    all_ok = True
    for fname in STATIC_FILES:
        path = os.path.join(static_dir, fname)
        backup = os.path.join(BACKUP_DIR, fname)
        entry = {"exists": os.path.exists(path), "backup": os.path.exists(backup)}
        if entry["exists"] and fname.endswith(".js"):
            ok, msg = _validate_js_braces(path)
            entry["valid"] = ok
            entry["detail"] = msg
            if not ok:
                all_ok = False
        elif entry["exists"]:
            entry["valid"] = True
            entry["detail"] = "OK"
        results[fname] = entry
    results["all_ok"] = all_ok
    return results

@app.get("/api/static/health")
def static_health():
    """Returns validation status of all static files."""
    return _static_health()

@app.post("/api/static/rollback")
def static_rollback():
    """Restore all static files from last-known-good backups."""
    _ensure_backup_dir()
    restored = []
    errors = []
    for fname in STATIC_FILES:
        backup = os.path.join(BACKUP_DIR, fname)
        target = os.path.join(static_dir, fname)
        if os.path.exists(backup):
            try:
                with open(backup, "rb") as bf:
                    with open(target, "wb") as tf:
                        tf.write(bf.read())
                restored.append(fname)
            except Exception as e:
                errors.append(f"{fname}: {e}")
        else:
            errors.append(f"{fname}: no backup found")
    
    result = {"restored": restored}
    if errors:
        result["errors"] = errors
    result["health"] = _static_health()
    return result

# Initialize backups on startup
if os.path.exists(static_dir):
    _backup_static_files()
    health = _static_health()
    if not health["all_ok"]:
        print(f"[DeepGravity] Static file validation: ISSUES DETECTED")
        for name, info in health.items():
            if name != "all_ok" and isinstance(info, dict):
                if not info.get("valid", True):
                    print(f"  {name}: {info.get('detail', 'invalid')}")
    else:
        print("[DeepGravity] Static files validated OK")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    # Serves on port 8000 by default
    uvicorn.run(app, host="127.0.0.1", port=8000)
