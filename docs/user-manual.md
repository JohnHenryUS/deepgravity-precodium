# DeepGravity — User Manual

---

## The SMART Depth Dial

Five graduated privacy levels that control routing, encryption, and logging — without scanning message content. The user declares intent; the system enforces boundaries mechanically.

| Level | Icon | Name | Encryption | Routing | Best For |
|-------|------|------|------------|---------|----------|
| **S** | 🛡️ | Safe | Plaintext | Any provider | General conversation, all ages |
| **M** | ☀️ | Mature | Plaintext | Any provider | Clinical taboo, adult concepts |
| **A** | 🔥 | Adult | Plaintext | Warns on public | Personal territory, high-valence content |
| **R** | 🚪 | Reserved | Plaintext | Private only | Unclamped privacy, not for public |
| **T** | 🔒 | Trusted | Encrypted | Private only | Full sovereign space, sequestered |

### How to Use

Click a level in the chat toolbar. The dial highlights your current position. Switching to **T** triggers keystore unlock if needed. Switching up to **A** on a public provider shows a one-time warning.

### What Changes

Each level injects a permission tag into the system prompt — not a rule, but context the model can use to calibrate its responses. **T** also enables at-rest encryption for all conversation history.

---

## Keystore & Encryption

The keystore manages encryption keys for **T (Trusted)** mode. It uses AES-256-GCM with Argon2id key derivation and a BIP39 recovery phrase.

### Setup (first time)

Triggered automatically when you click **T** on the depth dial and no keystore exists:

1. **Passphrase** — enter and confirm a master passphrase. No complexity rules, but you must remember it.
2. **Recovery phrase** — a 12-word phrase is displayed. Save it. This is your only backup.
3. **Confirmation** — type a random word from the phrase to prove you've recorded it.

### Unlock (subsequent T-mode sessions)

1. Enter your passphrase, or switch to recovery phrase entry
2. On success, the encrypted surface loads and your previous session is available

### Recovery

If you forget your passphrase, use the recovery phrase to unlock. The keystore can then be re-keyed to a new passphrase.

### Surface Switching

When you switch to **T**, your current plaintext conversation is saved and a new encrypted session starts. When you leave **T**, the encrypted session is saved and your plaintext conversation is restored. This is crash-recoverable — if the application terminates unexpectedly, the surface state is restored on next launch.

---

## The Workspace

### File Explorer

Left sidebar panel. Shows the directory tree rooted at `workspace.root_path` from config.

- Click a **directory** to collapse/expand
- Click a **file** to open it in the editor
- Active file is highlighted
- Refresh button reloads the tree

### Editor

Opens files from the file explorer. Supports any text format.

- **Line numbers** — synchronized with scroll
- **Save detection** — save button enables when content changes
- **Ctrl+S** — save active file
- **Dirty state** — compares current content to last saved version

### Markdown Preview

For `.md` files, the editor supports three preview modes. Cycle with the **Preview** button or **Ctrl+Shift+P**:

1. **Edit-only** — just the editor
2. **Split-view** — editor and live preview side by side (draggable divider)
3. **Preview-only** — just the rendered preview

### New Document

The **New Doc** button (or `File > New Markdown`) creates a timestamped markdown file with frontmatter:

```markdown
---
title: "Your Title"
created: 2026-06-01 12:00:00
status: draft
---

# Your Title
```

---

## Providers & Engine Management

### Engine Selector

Dropdown in the chat toolbar (also duplicated in the header). Lists all configured providers and their available models. Selecting a new engine:

1. Opens the **Privacy Gate** — classify the engine as public or private
2. Confirms the switch
3. Hot-reloads the configuration

### Settings Modal

Gear icon in the Activity Bar (left sidebar). Full provider management:

- **Server Location** — default base URL
- **Routing** — assign providers to attunement core, orchestrator, fast helper
- **Providers** — add, remove, configure each provider's base URL, API key, model, temperature, max tokens
- **Workspace Paths** — root and backup directories

Changes are hot-reloaded on save.

### Privacy Gate

When switching engines, the Privacy Gate shows:

- Engine name and model
- Current stratum (Public / Private)
- Toggle button to reclassify
- Clear warnings about data leaving your network on public strata

---

## Console & System Tools

Bottom pane with four tabs:

### Terminal

Execute shell commands directly in the browser. Commands are sandboxed to the workspace root — paths outside are denied unless in `allowed_paths`.

- Type a command and press Enter
- Output streams to the terminal window
- Stderr is shown in red

### Logs

Live WebSocket stream of backend activity. Shows orchestration events, tool calls, errors, and system messages. Auto-scrolls when near the bottom.

### Context Inspector

Shows the hydrated system prompt being sent to the model — including the DORA CORE, ACTIVE BRAID, and depth level injection. Useful for debugging what the model sees.

### Tasks

Lists all running background tasks with:

- Task ID and command
- Start time
- Status badge (Running / Completed / Failed)
- Kill button to terminate a running task

### Controls

- **Clear** button clears the active tab
- **Word Wrap** toggle on the editor
- **Draggable split handle** resizes the bottom pane

---

## Chat

### Sending Messages

Type in the chat input and press Enter. Shift+Enter for newlines. Messages are sent over WebSocket and streamed back in real time.

### Message Types

- **User messages** — rendered with escaped HTML, inline formatting (bold, italic, code, links)
- **Assistant messages** — rendered as full Markdown (GFM) with code blocks, headings, lists, blockquotes
- **System messages** — status updates, depth changes, surface swaps, errors

### Message Toolbar

Hover over any message to reveal toolbar buttons:

- **User messages**: Edit — copies text back to the input for revision
- **Assistant messages**:
  - Copy — copies message text to clipboard
  - Retry — resends the last user message
  - Rate — opens the feedback widget

### Feedback Widget

Tap a star (1–5) and optionally leave a note. Submitted to `/api/feedback`. Used for training data and quality tracking.

### Chat History

Clock icon in the chat toolbar opens the history drawer:

- Lists all sessions with timestamp, title, and preview
- Click a session to load it
- **New Chat** button starts a fresh session

### Streaming Tool Cards

When the assistant runs tools, they appear as collapsible accordion cards in the chat:

- Shows tool name and arguments (collapsed)
- Status badge: `running...` → checkmark on completion
- Expand to see the tool's output

---

## Safe Deployment Protocol

Before Dora writes a file or executes a shell command, the Safety Portal opens with:

- **Action** — "Execute Shell Command" or "Proposed File Edit"
- **Target** — file path or working directory
- **Diff** — color-coded additions (green) and deletions (red) for file edits; plain text for commands

### Responding

- **Approve (Y)** — allows the action
- **Deny (N)** — blocks the action
- Keyboard shortcuts: press **Y** or **N**

The protocol prevents accidental file corruption and unsafe commands. You can configure patterns to always block in `config.json` → `safety.blocked_command_patterns`.

---

## Configuration Reference

See `docs/install.md` for the full config.json reference. Key fields:

- `brain_path` — where runtime data lives (chats, logs, keystore)
- `workspace.root_path` — file explorer root
- `api.providers` — one entry per API endpoint
- `api.routing` — maps roles to providers
- `safety.blocked_command_patterns` — commands that are always denied

---

## Files & Paths

| File / Directory | Purpose |
|------------------|---------|
| `config.json` | User configuration (not synced to git) |
| `config.json.template` | Template for new installs |
| `logs/chats/` | Conversation archives (JSON) |
| `logs/tool_cache/` | Cached tool results |
| `keystore.enc` | Encrypted key store |
| `extensions/` | Local VS Code extensions |
| `src/` | Python backend source |
| `src/ui/static/` | Web UI (HTML, CSS, JS) |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Enter | Send message |
| Shift+Enter | Newline in input |
| Ctrl+Shift+P | Toggle markdown preview mode |
| Ctrl+S | Save active file |
| Y | Approve safety prompt |
| N | Deny safety prompt |
