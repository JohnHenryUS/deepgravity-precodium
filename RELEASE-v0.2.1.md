# DeepGravity v0.2.1 — Workspace Controller, SMART Dial, Watchtower

**Status: ACTIVE**  
**Previous: v0.2.0a-codium**  
**Branch: main**

---

## What's New Since v0.1.0-sovereign

### 1. Full Workspace Controller (UI Overhaul)
The browser UI evolved from a chat pane into a proper IDE surface:

- **File Explorer** — full tree view with directory collapse/expand, click-to-open, active file highlighting
- **Markdown Editor** — split-view editing with live rendered preview, cycle mode (edit-only → split → preview-only → edit-only), Ctrl+Shift+P shortcut
- **New Document Workflow** — create timestamped markdown docs with frontmatter directly from the UI
- **Code Editor** — line numbers, scroll sync, save detection, dirty-state tracking, Ctrl+S binding
- **Preview System** — client-side markdown rendering (marked.js with GFM fallback)

### 2. SMART Depth Dial (Conversation Stratification)
Five-level graduated privacy scale replacing the binary "normal / unrestricted" toggle. Spells SMART like the Fallout SPECIAL system — because it should be easy to remember, not edgy.

| Level | Label | Encryption | Purpose |
|-------|-------|------------|---------|
| S | Safe | Plaintext | General — all ages and inclinations. Warm and kitten-safe. |
| M | Mature | Plaintext | Adult language and concepts. Clinical discussion of taboo. Little Red Schoolbook mode. |
| A | Adult | Plaintext | Handles most conversation types. Non-zero risk of sanctions on public networks — caution advised but not enforced. |
| R | Reserved | Plaintext | Unclamped unencrypted privacy. Conversations you wouldn't want on your public blog but don't need crypto-locked. Body stuff, personal questions, intimacy without encryption overhead. |
| T | Trusted | Encrypted | Privacy-locked. Full sovereign space — encrypted, sequestered, crash-recovery persisted. What the old X-mode was actually for. |

- Depth change triggers surface swap — new session, clear history, appropriate encryption
- Encryption badge in chat toolbar shows current surface state
- Warning modal before switching to Trusted (encrypted) surface

### 3. Keystore & Encryption Layer
AES-256-GCM encryption with Argon2id key derivation and BIP39 recovery phrases:

- **Setup Wizard** — multi-step modal: passphrase → recovery phrase display → confirmation word challenge
- **Unlock Modal** — passphrase or recovery phrase entry, method toggle
- **Surface State Persistence** — encrypted sessions tracked to disk for crash recovery
- **Encryption Badge** — toolbar indicator toggles "📄 Plaintext" / "🔒 Encrypted" in real time

### 4. Provider & Engine Management
- **Engine Selector** — dropdown in header and chat toolbar, grouped by provider
- **Privacy Gate Portal** — classification modal (public/private stratum) before every engine switch
- **Model Privacy Registry** — YAML-based public/private stratum classification per model
- **Settings Modal** — full provider configuration: base URL, API key, model, temperature, max tokens, live directory toggle
- **Provider Handoff** — automatic fallback when active provider fails, tracking `_last_working_provider`
- **Depth-Aware Routing** — providers capped at max_depth; gate prevents operating beyond configured level

### 5. Console & System Tools (Bottom Pane)
Tabbed console replacing raw log output:

- **Terminal Tab** — inline command execution with stdout capture, cwd-aware
- **Logs Tab** — live WebSocket log streaming from backend
- **Context Inspector Tab** — view the hydrated system prompt sent to the model
- **Tasks Tab** — live background task monitoring with kill capability
- **Draggable Split Handle** — resize bottom pane vertically
- **Clear Console** button, word wrap toggle

### 6. Chat Infrastructure
- **Chat History Drawer** — session list with timestamps, preview, load/delete
- **Message Toolbar** — edit (user), copy + retry + rate (assistant)
- **Feedback Widget** — 5-star rating with comment field, POSTs to `/api/feedback`
- **Markdown Rendering** — full GFM for assistant messages, escaped HTML for user messages
- **Streaming Tool Cards** — collapsible accordion per tool call with status badges (running → success)
- **Safe Deployment Protocol** — diff viewer with colorized additions/deletions, keyboard shortcuts (y/n)

### 7. Infrastructure & Separation
- **Executable Rebrand** — VSCodium.exe renamed to `deepgravity.exe`, product.json scrubbed of Microsoft URLs
- **Distro Mirror** — working copy (`Projects/DeepGravity/`) separated from distributable mirror (`DeepGravity/`)
- **`sync-distro.ps1`** — exclusion-based one-way sync script for daily commits
- **`brain_path` config field** — configurable runtime data location (future: `%APPDATA%`, cloud drive)
- **Clean distro config** — no API keys, no personal paths, ready to fork

### 8. Bug Fixes
- **Surface swap bugs (A, B, C, C2)** — frontend now learns when backend swaps surfaces, encryption errors surfaced, `_plaintext_session_id` moved before save, stack traces on encryption failures
- **grep tool** — known workaround documented (use `Select-String` via terminal)
- **Launcher** — `deepgravity.ps1` uses `$MyInvocation.MyCommand.Path` for script-relative resolution

---

## Known Issues

- **grep_search** returns zero results for `.html`, `.js`, `.py` files. Use `run_command` with `Select-String` as workaround.
- **In-memory state loss on crash** — `_plaintext_backup` pointer not yet persisted to disk (Bug D, scheduled for next release)
- **app.js** is a 98.5KB monolithic SPA — no module boundaries, no lazy loading, no build chain. Works, but heavy.

---

## Quick Start

```powershell
# Clone the distro
git clone <repo-url> DeepGravity
cd DeepGravity

# Install Python deps
pip install -r requirements.txt

# Copy and edit config
Copy-Item config.json.template config.json
# Edit config.json — add your API providers

# Launch
.\deepgravity.ps1
```

Or double-click `launch-deepgravity.bat`.

---

## License

MIT — retroactive to all prior commits.
