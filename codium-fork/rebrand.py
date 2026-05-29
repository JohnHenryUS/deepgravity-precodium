import json
import os

original_path = 'codium-fork/resources/app/product.json'
target_path = 'codium-fork/vscodium-bin/resources/app/product.json'

if not os.path.exists(original_path):
    # Fallback to source version if template isn't found
    original_path = 'codium-fork/vscodium-source/product.json'

print(f"Reading original product.json from {original_path}...")
with open(original_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print("Applying DeepGravity identity and branding...")
# Core identity and folder isolation (essential for running alongside other VSCodium instances)
data['nameShort'] = "DeepGravity"
data['nameLong'] = "DeepGravity — Sovereign Agentic Coding Harness"
data['applicationName'] = "deepgravity"
data['dataFolderName'] = ".deepgravity"
data['sharedDataFolderName'] = ".deepgravity-shared"
data['win32MutexName'] = "deepgravity"

# Server/tunnel naming
data['serverApplicationName'] = "deepgravity-server"
data['serverDataFolderName'] = ".deepgravity-server"
data['tunnelApplicationName'] = "deepgravity-tunnel"

# Windows branding
data['win32DirName'] = "DeepGravity"
data['win32NameVersion'] = "DeepGravity"
data['win32RegValueName'] = "DeepGravity"
data['win32AppUserModelId'] = "DeepGravity.DeepGravity"
data['win32ShellNameShort'] = "DeepGravity"
data['win32TunnelServiceMutex'] = "deepgravity-tunnelservice"
data['win32TunnelMutex'] = "deepgravity-tunnel"
data['win32ContextMenu'] = None  # Sovereign tool, no context menu pollution

# macOS/Linux
data['darwinBundleIdentifier'] = "com.deepgravity"
data['linuxIconName'] = "deepgravity"
data['urlProtocol'] = "deepgravity"

# Redirect help and issue URLs to our project
data['reportIssueUrl'] = "https://github.com/JohnHenryUS/deepgravity/issues/new"
data['releaseNotesUrl'] = "https://github.com/JohnHenryUS/deepgravity/releases"
data['requestFeatureUrl'] = "https://github.com/JohnHenryUS/deepgravity/issues/new"
data['documentationUrl'] = "https://github.com/JohnHenryUS/deepgravity"

# --- SOVEREIGN SAFETY PRINCIPLE ---
# We do NOT touch 'defaultChatAgent', 'trustedExtensionAuthAccess', or
# 'builtInExtensionsEnabledWithAutoUpdates'. In VSCodium, these point to Copilot,
# but because the Copilot extension is not installed or bundled, they sit completely inert.
# Modifying these keys triggers complex internal TypeErrors in VS Code's compiled 
# dependency injection container, causing the main window to go completely black on boot.

print(f"Writing rebranded product.json to {target_path}...")
os.makedirs(os.path.dirname(target_path), exist_ok=True)
with open(target_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("[+] Rebrand complete successfully. Identity isolated safely.")
