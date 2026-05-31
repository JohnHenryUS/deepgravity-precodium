# DeepGravity — Quickstart

**You just downloaded it. Here's how to make it march.**

---

## 1. Prerequisites

- **Python 3.10+** — check with `python --version`
- **PowerShell** (Windows) or **bash** (Linux/Mac)
- **An OpenAI-compatible API endpoint** — Ollama (local), Open WebUI, DeepSeek, OpenAI, etc.

---

## 2. Install

```powershell
pip install -r requirements.txt
```

That's it. No npm, no build tools, no node_modules.

---

## 3. Configure

```powershell
Copy-Item config.json.template config.json
```

Edit `config.json`:

- Set `server_location` to your API base URL (e.g. `http://localhost:11434/v1` for local Ollama)
- Under `api.providers`, set your `api_key` and `model` for at least one provider
- Set `workspace.root_path` to the folder you want the file tree to browse

Or skip editing — launch first, configure via the Settings UI (gear icon in sidebar).

---

## 4. Launch

```powershell
.\deepgravity.ps1
```

Or double-click `launch-deepgravity.bat`.

The editor opens. The Python backend starts automatically in the background. You'll see the chat pane in the sidebar.

---

## 5. First Conversation

1. Type a message in the chat input and press Enter
2. The first time, you may need to select an engine — use the dropdown in the chat toolbar
3. If the engine is public, the Privacy Gate will ask you to confirm the stratum
4. You're talking to Dora

---

## 6. What's Where

| Thing | Location |
|-------|----------|
| Chat | Sidebar or editor tab (pinned by default) |
| File browser | Left sidebar — Activity Bar (explorer icon) |
| Settings | Gear icon in Activity Bar |
| Depth dial | Chat toolbar — S M A R T buttons |
| Engine selector | Chat toolbar dropdown |
| Console / Logs / Terminal | Bottom pane — tabbed |
| Chat history | Clock icon in chat toolbar |

---

## 7. Next Steps

- **`docs/install.md`** — full setup guide, config reference, troubleshooting
- **`docs/user-manual.md`** — every feature explained
- **`RELEASE-v0.2.0.md`** — what changed since last version

---

*If something doesn't work, check the logs tab in the bottom pane. Most issues are missing API keys or wrong base URLs.*
