# DeepGravity v0.1.0-sovereign

**Phase 5 baseline — Telemetry-free VSCodium Integration and Embedded App Stack.**

This release marks the completion of the editor fork, transitioning DeepGravity from a browser-tab prototype into an integrated desktop cognitive workspace.

---

## What's New in v0.1.0-sovereign

### 1. Rebranded VSCodium Shell
* **Decoupled Editor Client**: Utilizes VSCodium as the default front-end, rebranded to isolate settings under the `.deepgravity` sandbox directory.
* **Telemetry Scrubbing**: Removed all Microsoft accounts, auto-update URLs, Copilot linkages, and upstream tracking URLs from `product.json`.
* **Air-Gapped Operation**: Configured to run with zero remote network calls on startup.

### 2. Local Extension Stack
* **`deepgravity-core`**: A local layout extension providing layout commands (`IDE Mode`, `CCE Mode`, `Doc Mode`) and registration of views container sidebar and tabs.
* **`deepgravity-chat`**: Pinned VS Code Chat participant extension that routes prompts directly to the local backend WebSocket.
* **Local Loader**: Configured to load packed and unpacked extensions from a local directory path, bypassing the Microsoft VS Code Extension Marketplace completely.

### 3. Unified Embedded Webviews
* **Dual Chat Surfaces**: Modified the chat panels (`DoraChatPanel` for editor tabs and `DoraChatViewProvider` for the Activity Bar sidebar) to load the local FastAPI server directly via secure loopback iframes (`http://127.0.0.1:19850/?embed=chat`).
* **Embed Mode Layout**: Added query string parsing and HSL glassmorphism styles that hide workspace frames (explorer, editor, console) when embedded, scaling the chat panel full-screen to fit the panel layouts perfectly.
* **Full Feature Synchronization**: Both VSCodium panels are fully connected to the same WebSocket server, sharing the active session, history logs, model selector, and safety diff verification.

### 4. Launcher & Port Upgrades
* **Port Allocation**: Swapped default port from `8000` to `19850` across the codebase ([config.json](config.json.template), launchers, web views, backend) to prevent port collisions.
* **Background Process Management**: Standardized `deepgravity.ps1` to detect existing backend servers, clean up zombie editor processes, and launch the server headlessly before opening the VSCodium window.
* **Process Spawning**: Resolved Powershell detached window bugs by utilizing direct call execution for GUI editor binaries.

---

## Quick Start

1. Initialize your configuration:
   ```powershell
   Copy-Item config.json.template config.json
   ```
2. Start the harness:
   ```powershell
   .\deepgravity.ps1
   ```

---

## License

MIT — retroactive to all prior commits.
