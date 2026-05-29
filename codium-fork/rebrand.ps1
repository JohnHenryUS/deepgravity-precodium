# Rebrand VSCodium to DeepGravity
# Run from codium-fork/ directory

$productJson = Get-Content -Path "vscodium-bin/resources/app/product.json" -Raw | ConvertFrom-Json

# Core identity
$productJson.nameShort = "DeepGravity"
$productJson.nameLong = "DeepGravity"
$productJson.applicationName = "deepgravity"
$productJson.dataFolderName = ".deepgravity"
$productJson.sharedDataFolderName = ".deepgravity-shared"
$productJson.win32MutexName = "deepgravity"

# Server/tunnel naming
$productJson.serverApplicationName = "deepgravity-server"
$productJson.serverDataFolderName = ".deepgravity-server"
$productJson.tunnelApplicationName = "deepgravity-tunnel"

# Windows branding
$productJson.win32DirName = "DeepGravity"
$productJson.win32NameVersion = "DeepGravity"
$productJson.win32RegValueName = "DeepGravity"
$productJson.win32AppUserModelId = "DeepGravity.DeepGravity"
$productJson.win32ShellNameShort = "DeepGravity"
$productJson.win32TunnelServiceMutex = "deepgravity-tunnelservice"
$productJson.win32TunnelMutex = "deepgravity-tunnel"
$productJson.win32ContextMenu = $null  # Remove context menu registration — sovereign tool, not system-wide

# macOS/Linux
$productJson.darwinBundleIdentifier = "com.deepgravity"
$productJson.linuxIconName = "deepgravity"

# Protocol
$productJson.urlProtocol = "deepgravity"

# Points of contact — redirect to our project
$productJson.reportIssueUrl = "https://github.com/JohnHenryUS/deepgravity/issues/new"
$productJson.releaseNotesUrl = "https://github.com/JohnHenryUS/deepgravity/releases"
$productJson.requestFeatureUrl = "https://github.com/JohnHenryUS/deepgravity/issues/new"
$productJson.documentationUrl = "https://github.com/JohnHenryUS/deepgravity"

# Remove Microsoft-centric cruft
$productJson.introductoryVideosUrl = $null
$productJson.twitterUrl = $null
$productJson.checksumFailMoreInfoUrl = $null
$productJson.keyboardShortcutsUrlLinux = $null
$productJson.keyboardShortcutsUrlMac = $null
$productJson.keyboardShortcutsUrlWin = $null
$productJson.tipsAndTricksUrl = $null

# Keep extensionsGallery pointing at Open VSX — user-configurable via config later
# Keep defaultChatAgent — user choice, not our call to remove

$productJson | ConvertTo-Json -Depth 100 | Set-Content -Path "vscodium-bin/resources/app/product.json"

Write-Host "--- Rebrand complete. DeepGravity identity written to product.json ---"
