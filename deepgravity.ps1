#!/usr/bin/env pwsh
<#
.SYNOPSIS
    DeepGravity — Sovereign Agentic Coding Harness
.DESCRIPTION
    Launches the DeepGravity editor (fork of VSCodium) with the correct
    extensions directory, workspace root, and backend configuration.

    Default workspace: D:\doraheart
    Extensions:        D:\doraheart\Sovereign_Tools\extensions\
    Config:            D:\doraheart\Projects\DeepGravity\config.json

.PARAMETER Workspace
    Path to open as the default workspace. Overrides config default.

.PARAMETER ExtensionsDir
    Path to scan for local extensions. Overrides config default.

.PARAMETER NoWorkspace
    Launch without opening any workspace folder.

.PARAMETER DisableGPU
    Launch with GPU acceleration disabled (useful for remote desktop).

.PARAMETER Version
    Print version information and exit.

.PARAMETER Help
    Show this help message.
#>

param(
    [string]$Workspace = "",
    [string]$ExtensionsDir = "",
    [switch]$NoWorkspace,
    [switch]$DisableGPU,
    [switch]$Version,
    [switch]$Help
)

$DeepGravityRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $DeepGravityRoot "config.json"

# --- Defaults ---
$DefaultWorkspace = ""
$DefaultExtensionsDir = Join-Path $DeepGravityRoot "extensions"
$EditorBinary = Join-Path $DeepGravityRoot "codium-fork\vscodium-bin\deepgravity.exe"
$BackendHost = "127.0.0.1"
$BackendPort = 19850

# --- Help ---
if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Detailed
    exit 0
}

# --- Version ---
if ($Version) {
    if (Test-Path $EditorBinary) {
        $versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($EditorBinary)
        Write-Host "DeepGravity v0.1.0-sovereign"
        Write-Host "Editor: DeepGravity $($versionInfo.ProductVersion)"
        Write-Host "Node: $(node --version)"
        Write-Host "Platform: Windows NT"
    } else {
        Write-Host "DeepGravity v0.1.0-sovereign"
        Write-Host "Editor: (not found at $EditorBinary)"
    }
    exit 0
}

# --- Load config overrides ---
if (Test-Path $ConfigPath) {
    try {
        $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($config.editor.workspaceRoot) { $DefaultWorkspace = $config.editor.workspaceRoot }
        if ($config.editor.extensionsDir) { $DefaultExtensionsDir = $config.editor.extensionsDir }
        if ($config.server.host) { $BackendHost = $config.server.host }
        if ($config.server.port) { $BackendPort = $config.server.port }
    } catch {
        Write-Warning "Could not parse config.json: $_"
    }
}


# Ensure deepgravity.exe is assembled from chunks
& "$DeepGravityRoot\codium-fork\vscodium-bin\merge-exe.ps1" 2>$null | Out-Null
# --- Resolve parameters ---
$resolvedWorkspace = if ($NoWorkspace) { $null } elseif ($Workspace) { $Workspace } else { $DefaultWorkspace }
$resolvedExtensionsDir = if ($ExtensionsDir) { $ExtensionsDir } else { $DefaultExtensionsDir }

# --- Ensure extensions directory exists ---
if (-not (Test-Path $resolvedExtensionsDir)) {
    New-Item -ItemType Directory -Path $resolvedExtensionsDir -Force | Out-Null
    Write-Host "Created extensions directory: $resolvedExtensionsDir"
}

# --- Build argument list ---
$argsList = @()

if ($resolvedWorkspace) {
    $argsList += "--folder-uri"
    $argsList += "file:///$($resolvedWorkspace.Replace('\','/'))"
}

$argsList += "--extensions-dir"
$argsList += $resolvedExtensionsDir

# ── Start Python backend ──
$BackendScript = Join-Path $DeepGravityRoot "src\ui\web_server.py"
if (Test-Path $BackendScript) {
    $backendProc = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "web_server" }
    if (-not $backendProc) {
        try {
            $pythonCmd = if (Get-Command "python" -ErrorAction SilentlyContinue) { "python" } else { "python3" }
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $pythonCmd
            $psi.Arguments = "`"$BackendScript`""
            $psi.WorkingDirectory = $DeepGravityRoot
            $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
            $psi.UseShellExecute = $true
            [System.Diagnostics.Process]::Start($psi) | Out-Null
            Write-Host "  Backend:    Starting Python orchestrator..."
            Start-Sleep 2
        } catch {
            Write-Warning "  Backend:    Could not start Python server: $_"
        }
    } else {
        Write-Host "  Backend:    Already running"
    }
}

# GPU control
if ($DisableGPU) {
    $argsList += "--disable-gpu"
}

# --- Set backend URL for chat extension ---
# Resolve the connectable host. If bound to 0.0.0.0 (all interfaces),
# connect via loopback (127.0.0.1).
$resolvedBackendHost = $BackendHost
if ($resolvedBackendHost -eq "0.0.0.0") {
    $resolvedBackendHost = "127.0.0.1"
}
$env:DEEPGRAVITY_BACKEND_URL = "http://${resolvedBackendHost}:${BackendPort}"
Write-Host "  Backend URL: $env:DEEPGRAVITY_BACKEND_URL"

# --- Write a brief log ---
$logDir = Join-Path $DeepGravityRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "deepgravity-launch-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
@"
[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] DeepGravity launch
  Binary: $EditorBinary
  Workspace: $resolvedWorkspace
  Extensions: $resolvedExtensionsDir
  Args: $($argsList -join ' ')
"@ | Out-File -FilePath $logFile -Encoding utf8

# --- Launch ---
Write-Host "    ____             __                                         "
Write-Host "   / __ \___  ____ _/ /____  _____       __                     "
Write-Host "  / / / / _ \/ __ '/ __/ _ \/ ___/______/ /_                     "
Write-Host " / /_/ /  __/ /_/ / /_/  __/ /__/_____/ __/                     "
Write-Host "/_____/\___/\__, /\__/\___/\___/      \__/                      "
Write-Host "           /____/                                                "
Write-Host "  Sovereign Agentic Coding Harness"
Write-Host ""
Write-Host "  Workspace:   $resolvedWorkspace"
Write-Host "  Extensions:  $resolvedExtensionsDir"
Write-Host ""

if (-not (Test-Path $EditorBinary)) {
    Write-Error "Editor binary not found at: $EditorBinary"
    Write-Host "Run '.\codium-fork\download-editor.ps1' to download VSCodium."
    exit 1
}

try {
    & $EditorBinary $argsList
    Write-Host "  DeepGravity is starting..."
} catch {
    Write-Error "Failed to launch editor: $_"
    exit 1
}

