# DeepGravity — Install Guide

## Prerequisites

- **Python 3.10+** — required for the backend orchestrator
- **PowerShell 5+** (Windows) or **bash** (Linux/Mac) — for launcher scripts
- **An OpenAI-compatible API endpoint** — local or remote. DeepGravity doesn't ship with a model; it routes to providers you configure.

---

## Installation

### From Release Archive

1. Extract the archive to a directory of your choice
2. Open a terminal in that directory
3. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

4. Initialize configuration:

```powershell
Copy-Item config.json.template config.json
```

5. Edit `config.json` with your API provider details (see [Configuration](#configuration) below)

### From Git Clone

```powershell
git clone <repo-url> DeepGravity
cd DeepGravity
pip install -r requirements.txt
Copy-Item config.json.template config.json
```

---

## Configuration

### `config.json` Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `server_location` | string | `http://localhost:11434/v1` | Default base URL for providers that use `{server_location}` |
| `server.host` | string | `0.0.0.0` | Backend bind address |
| `server.port` | integer | `19850` | Backend port |
| `brain_path` | string | `""` | Path for runtime data (chats, logs, keystore). Empty = alongside config.json |
| `workspace.root_path` | string | `""` | Root directory for the file explorer |
| `workspace.backup_path` | string | `""` | Backup directory (future use) |
| `workspace.allowed_paths` | array | `[]` | Additional directories the file API can access |

### Providers

Each provider in `api.providers` has these fields:

| Field | Type | Description |
|-------|------|-------------|
| `base_url` | string | API endpoint URL. Use `{server_location}` to inherit from the root field |
| `api_key` | string | Your API key (leave empty for local models) |
| `model` | string | Model identifier (e.g. `llama3:latest`, `gpt-4`) |
| `temperature` | float | Sampling temperature (0.0–2.0) |
| `max_tokens` | integer | Maximum response tokens (optional) |
| `max_depth` | string | Maximum SMART level this provider can handle: `S`, `M`, `A`, `R`, or `T` |
| `live_directory` | boolean | If true, query `/v1/models` for available model list |
| `public_stratum` | boolean | If true, treated as a public/cloud provider. Controls Privacy Gate behavior |
| `preserve_keys` | array | Non-standard response keys to pass through (e.g. `reasoning_content`) |

### Routing

The `api.routing` section maps roles to provider names defined in `api.providers`:

- `attunement_core` — the primary conversational model (Dora's personality)
- `primary_orchestrator` — the tool-calling / orchestration model
- `fast_helper` — lightweight model for quick operations (optional)

Both `attunement_core` and `primary_orchestrator` can point to the same provider.

### Brain Path

If `brain_path` is set, DeepGravity stores all runtime data there instead of alongside the application:

- `logs/` — tool cache, heartbeats, launch logs
- `chats/` — conversation history (JSON archives)
- `keystore.enc` — encrypted key store
- `.surface_state.json` — crash recovery pointer

This enables:
- **Cloud sync**: set `brain_path` to a OneDrive, Google Drive, or Dropbox folder
- **Portable install**: app on a USB drive, brain on the local machine
- **Multi-user**: each user points to their own brain directory

---

## Launching

### Windows

```powershell
.\deepgravity.ps1
```

Or double-click `launch-deepgravity.bat`.

The launcher:
1. Starts the Python backend (`src/ui/web_server.py`) in a hidden window
2. Opens the DeepGravity editor, wired to the backend
3. Sets the `DEEPGRAVITY_BACKEND_URL` environment variable for extensions

### Linux / Mac

```bash
python src/ui/web_server.py
```

Then open `http://127.0.0.1:19850` in a browser. The editor shell is Windows-only at this time; the web UI works on all platforms.

### Command-Line Options (PowerShell launcher)

```powershell
.\deepgravity.ps1 -Workspace "D:\my-project"   # Open specific workspace
.\deepgravity.ps1 -DisableGPU                   # Disable GPU acceleration (RDP)
.\deepgravity.ps1 -NoWorkspace                  # Launch without a workspace
```

---

## First-Time Setup

### 1. Select an Engine

Use the dropdown in the chat toolbar to select a provider and model. The first time you switch, the Privacy Gate will ask you to classify the engine as public or private.

### 2. Set Your Depth

The depth dial defaults to **S (Safe)**. Click through the levels to understand what each one permits. **T (Trusted)** requires keystore setup.

### 3. Keystore (Optional)

If you plan to use **T (Trusted)** mode for encrypted conversations:

1. Click **T** on the depth dial
2. Follow the keystore setup wizard: passphrase → save recovery phrase → confirm
3. Your encrypted sessions are now crash-recoverable

---

## Updating

When a new version is released:

```powershell
# Pull the latest code
git pull

# Re-install dependencies if they changed
pip install -r requirements.txt

# Re-sync config template if new fields were added
# (your existing config.json is NOT overwritten)
```

If you cloned fresh, copy your old `brain_path` directory to the new installation and point the new config at it.

---

## Troubleshooting

### Backend won't start
- Check Python is installed: `python --version`
- Check dependencies: `pip install -r requirements.txt`
- Check the logs tab in the bottom console pane
- Try starting manually: `python src/ui/web_server.py`

### "No provider available" error
- Check `config.json` has at least one provider configured with a valid `base_url` and `api_key`
- Check the provider is set in `api.routing.attunement_core`
- If using depth R or T, ensure the provider has `public_stratum: false`

### Editor launches but chat pane is blank
- Wait 2–3 seconds for the backend to finish starting
- Check the backend URL: `http://127.0.0.1:19850` in a browser should show the web UI
- Restart the launcher — it kills and restarts the backend

### Keystore says "locked" but I know my passphrase
- Use the "recovery phrase" option in the unlock modal
- If you've lost both, T-mode sessions are unrecoverable — delete `keystore.enc` and re-setup
