# DeepGravity v0.1.0-precodium

**Phase 4.5 baseline — pre-Codium prototype.**

This is the final release before the VS Codium fork. Everything from here forward builds toward a sovereign, stripped editor shell.

---

## What's included

- **Federated API Router** — simultaneous multi-provider connections (DeepSeek, Ollama, OpenAI, Open WebUI)
- **Role-based routing** — assign distinct LLMs to distinct roles (primary coder, fast helper, attunement core)
- **Windows-native tool system** — file ops, shell execution, grep search with backslash path normalization
- **Safe Deployment Protocol** — interactive diff verification before any write or shell command
- **WebSocket-based approval modals** — browser UI for approving/rejecting tool executions
- **Resilient reconnection** — approval callbacks wait for WebSocket reconnection instead of falling through to CLI
- **Contract layer** — graduated autonomy via WorkContracts, ContractMonitor, SpinningDetector
- **Split-view editor** — draggable resize handle, preview toggle, file tree sidebar
- **Live log streaming** — stdout/stderr piped to browser log pane
- **Session persistence** — chat history save/load per session
- **Local feedback signals** — rating/comment endpoint for training data collection
- **Static file self-healing** — automatic backup and rollback of frontend assets
- **Configurable provider system** — add/modify API endpoints via config.json without code changes

---

## Quick start

```bash
git clone https://github.com/JohnHenryUS/deepgravity.git
cd deepgravity
pip install -r requirements.txt
python src/ui/web_server.py
```

Then open `http://127.0.0.1:8000` in a browser.

---

## License

MIT — retroactive to all prior commits.

---

## What's next (Phase 5)

v0.1.0-precodium is the last release before the VS Codium fork. Phase 5 will:

1. Fork VSCodium and strip marketplace, telemetry, accounts, collaboration surfaces
2. Replace extension gallery with local directory scan
3. Ship three built-in themes (Dark, Light, Dora)
4. Add user theme directory (drop .json files, they appear in the switcher)
5. Wire workspace root variable + last-open persistence
6. Integrate local Stable Diffusion endpoint
