# Phase 5 Bootstrap — DeepGravity Codium Fork

**Target**: Fork VSCodium, strip it to a sovereign DeepGravity shell.

---

## Prerequisites (already installed)

| Tool | Version | Status |
|---|---|---|
| Node.js | v24.12.0 | ✓ |
| Git | 2.54.0 | ✓ |
| Python | 3.14.2 | ✓ (not needed for fork, for backend) |

## Pre-flight (one-time setup)

Run these in PowerShell **as Administrator**:

```powershell
# 1. Fix npm execution policy so we can install yarn
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. Install yarn globally
npm install -g yarn

# 3. Verify
yarn --version
```

## Fork & Clone

```powershell
# 4. Navigate to the staging directory
cd D:\doraheart\Projects\DeepGravity\codium-fork\

# 5. Clone VSCodium (this will take a while — ~1.5GB)
git clone --depth 1 --branch main https://github.com/VSCodium/vscodium.git .

# 6. Install dependencies
yarn install
```

## First Build (verify it compiles clean)

```powershell
# 7. Build the editor
yarn run build

# 8. Launch
yarn run start
```

If it opens a working editor window, the base is solid. Then the stripping begins.

## What to Strip (in order)

1. **Telemetry**: Remove `src/vs/platform/telemetry/`, `src/vs/base/common/errorLogger.ts`
2. **Marketplace**: Remove gallery extensions endpoint, `extensionsGallery` from product config
3. **Accounts / Sign-in**: Remove `src/vs/platform/sign/`, authentication providers
4. **Live Share / Remote**: Remove SSH, WSL, Containers remote extensions
5. **Collaboration**: Remove all `codereview`, `comments`, `pullrequest` extensions
6. **Extension Gallery UI**: Remove the Extensions view panel, keep only the local loader

## Replacements to Build

After stripping, wire in:

- `src/deepgravity/extension-loader.ts` — scans `Sovereign_Tools/extensions/` at startup
- `src/deepgravity/themes/` — Dark, Light, Dora themes + user directory scanner
- `src/deepgravity/workspace-persistence.ts` — last-open-workspace, root variable
- `src/deepgravity/api-bridge.ts` — connects to the Python orchestrator backend

---

*Pick up here when you're back. The Python environment doesn't matter for this part.*
