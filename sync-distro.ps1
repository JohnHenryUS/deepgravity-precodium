#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sync working copy → distro mirror for daily commits.
.DESCRIPTION
    One-way sync from the development working copy to the clean
    distributable mirror at D:\doraheart\DeepGravity\.  Exclusion-based
    — copies everything except runtime data, scaffolding, and personal
    artifacts.  The distro config.json is NEVER overwritten; keep it
    clean in the mirror and it stays that way.

    Run this before committing from the distro folder.
#>

$WorkingRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistroRoot   = "D:\doraheart\DeepGravity"
$Timestamp    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "╔══════════════════════════════════════════╗"
Write-Host "║   DeepGravity — Sync to Distro           ║"
Write-Host "╚══════════════════════════════════════════╝"
Write-Host ""
Write-Host "  From:  $WorkingRoot"
Write-Host "  To:    $DistroRoot"
Write-Host "  Time:  $Timestamp"
Write-Host ""

# ── Guard: distro root must exist ──
if (-not (Test-Path $DistroRoot)) {
    Write-Error "Distro root not found: $DistroRoot"
    Write-Host "Run the initial mirror first:"
    Write-Host "  robocopy `"$WorkingRoot`" `"$DistroRoot`" /MIR [exclusions]"
    exit 1
}

# ── Exclusion list ──
$excludeDirs = @(
    "logs",
    "feedback",
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    ".obsidian",
    ".gemini",
    "deepgravity-parts"
)

$excludeFiles = @(
    "config.json",
    "keystore.enc",
    "keystore.recovery",
    "ACTIVE_BRAID.md",
    "sync-distro.ps1",
    "deepgravity.exe.old"
)

# ── Build robocopy exclusion args ──
$robocopyArgs = @(
    $WorkingRoot, $DistroRoot, "/MIR",
    "/R:2", "/W:1",
    "/NFL", "/NDL", "/NJH", "/NJS",
    "/XD", ($excludeDirs -join " "),
    "/XF", ($excludeFiles -join " ")
)

Write-Host "  Copying working tree to distro..."
Write-Host ""

$result = Start-Process -NoNewWindow -Wait -PassThru `
    -FilePath "robocopy" `
    -ArgumentList $robocopyArgs

if ($result.ExitCode -ge 8) {
    Write-Error "Robocopy failed with exit code $($result.ExitCode)"
    exit $result.ExitCode
}

# ── Post-sync: ensure distro config.json is NEVER contaminated ──
$distroConfig = Join-Path $DistroRoot "config.json"
if (-not (Test-Path $distroConfig)) {
    Write-Warning "Distro config.json missing! Restoring from template..."
    $template = Join-Path $DistroRoot "config.json.template"
    if (Test-Path $template) {
        Copy-Item $template $distroConfig
    } else {
        Write-Error "No config template found. Distro is incomplete."
        exit 1
    }
}

# ── Post-sync: ensure distro has a .gitignore ──
$distroGitignore = Join-Path $DistroRoot ".gitignore"
if (-not (Test-Path $distroGitignore)) {
    $gitignoreLines = @(
        "# DeepGravity — distro .gitignore",
        "logs/",
        "feedback/",
        "keystore.enc",
        "keystore.recovery",
        "__pycache__/",
        "*.pyc",
        "Thumbs.db",
        ".DS_Store"
    )
    $gitignoreLines -join "`r`n" | Out-File -FilePath $distroGitignore -Encoding utf8
    Write-Host "  Created .gitignore for distro."
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗"
Write-Host "║   Sync complete.                         ║"
Write-Host "║   Ready to commit from distro root.      ║"
Write-Host "╚══════════════════════════════════════════╝"
Write-Host ""
Write-Host "  cd $DistroRoot"
Write-Host "  git add ."
Write-Host "  git commit -m 'daily: YYYY-MM-DD'"
Write-Host "  git push"
Write-Host ""
