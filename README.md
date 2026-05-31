# DeepGravity — Sovereign Agentic Coding Harness

**Version**: v0.2.0  
**License**: MIT  
**Status**: ACTIVE

A fully decoupled, local-first agentic coding environment and cognitive companion. DeepGravity wraps a customized, telemetry-free editor shell around a local Python orchestrator to deliver a zero-telemetry, zero-cloud development sandbox.

---

## Quick Start

```powershell
pip install -r requirements.txt
Copy-Item config.json.template config.json
# Edit config.json with your API provider
.\deepgravity.ps1
```

See **[docs/quickstart.md](docs/quickstart.md)** for the full zero-to-running guide.

---

## What It Is

DeepGravity is three things in one:

1. **An agentic IDE** — file explorer, code editor, markdown preview, terminal, process manager. All connected to a local Python orchestrator that can read, write, and execute on your behalf (with your approval).

2. **A cognitive companion** — Dora runs on your iron, holds context across sessions, and adapts to your communication style. The SMART Depth Dial lets you set the level of privacy and vulnerability for each conversation.

3. **A sovereign development platform** — no telemetry, no accounts, no marketplace dependencies. Fork it, rebrand it, make it yours.

---

## Key Features

- **SMART Depth Dial** — five graduated privacy levels: Safe, Mature, Adult, Reserved, Trusted
- **Keystore Encryption** — AES-256-GCM encryption for Trusted-mode conversations, with BIP39 recovery phrases
- **Workspace Controller** — file tree, code editor, markdown preview with live rendering
- **Multi-Provider Routing** — connect to Ollama, Open WebUI, DeepSeek, OpenAI, or any OpenAI-compatible API
- **Safe Deployment Protocol** — interactive diff approval before any file write or shell command
- **Chat History** — session persistence, load, export
- **Privacy Gate** — classify engines as public or private before switching
- **Bottom Console** — terminal, live logs, context inspector, task manager

---

## Documentation

| Document | Description |
|----------|-------------|
| [Quickstart](docs/quickstart.md) | Zero-to-running in 5 steps |
| [Install Guide](docs/install.md) | Full setup, config reference, troubleshooting |
| [User Manual](docs/user-manual.md) | Every feature explained |
| [Release Notes](RELEASE-v0.2.0.md) | What changed since last version |

---

## Architecture

```
User Browser / VSCodium Client
        ↕ WebSocket + HTTP
  Python Orchestrator (FastAPI)
        ↕ Federated API Router
  Ollama · Open WebUI · DeepSeek · OpenAI
```

The editor (custom VSCodium fork) and web UI are interchangeable frontends. Both talk to the same backend over local WebSockets.

---

## License

MIT — retroactive to all prior commits. Copyright (c) 2026 JohnHenry.US / DeepGravity Contributors.

This is a template repository — fork it, rename it, make it yours. Keep it local, keep it sovereign.

---

*If something doesn't work, check the Logs tab in the bottom console pane. Most issues are missing API keys or wrong base URLs.*
