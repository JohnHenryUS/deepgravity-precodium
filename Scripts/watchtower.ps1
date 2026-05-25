<#
.SYNOPSIS
  Watchtower - standalone heartbeat monitor for DeepGravity.
  Reads logs/heartbeat.json and reports orchestrator status.
  Does not depend on the orchestrator process being responsive.
.DESCRIPTION
  Can be invoked from anywhere: Win+R, taskbar shortcut, hotkey.
  Checks heartbeat freshness and dumps diagnostics if stale.
.PARAMETER Path
  Path to DeepGravity config directory (containing logs/heartbeat.json).
  Defaults to the current working directory.
.PARAMETER Threshold
  Seconds of heartbeat staleness before reporting a stall. Default 30.
.PARAMETER Watch
  If set, loops continuously, re-checking every N seconds.
.EXAMPLE
  .\watchtower.ps1
  .\watchtower.ps1 -Watch -Threshold 15
  .\watchtower.ps1 -Path D:\google-drive-dora-bugout\Projects\DeepGravity
#>

param(
    [string]$Path = (Get-Location).Path,
    [int]$Threshold = 30,
    [switch]$Watch
)

$heartbeatFile = Join-Path (Join-Path $Path "logs") "heartbeat.json"

function Get-SecondsAgo($epoch) {
    try {
        $date = [DateTimeOffset]::FromUnixTimeSeconds($epoch).LocalDateTime
        return [math]::Round(((Get-Date) - $date).TotalSeconds)
    } catch {
        return 999999
    }
}

function Read-Heartbeat {
    if (-not (Test-Path $heartbeatFile)) {
        return $null
    }
    try {
        $raw = Get-Content $heartbeatFile -Raw -ErrorAction Stop
        return $raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Format-Heartbeat($hb) {
    if (-not $hb) {
        return "NO HEARTBEAT - orchestrator may not be running."
    }
    $ago = Get-SecondsAgo $hb.timestamp
    $status = if ($ago -gt $Threshold) { "STALLED" } else { $hb.status }
    
    $lines = @(
        "DeepGravity Watchtower",
        "-------------------",
        "Status:    $status",
        "Loop:      $($hb.loop_count)",
        "Session:   $($hb.session)",
        "History:   $($hb.history_len) messages",
        "Last tool: $($hb.last_tool)",
        "PID:       $($hb.pid)",
        "Age:       ${ago}s ago (threshold: ${Threshold}s)"
    )
    return $lines -join "`n"
}

function Show-Diagnostics {
    $logDir = Join-Path (Join-Path $Path "logs") "chats"
    if (Test-Path $logDir) {
        $latest = Get-ChildItem $logDir -Filter *.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            Write-Host "`n[!] Recent session: $($latest.Name) ($([math]::Round($latest.Length/1024)) KB)" -ForegroundColor Yellow
        }
    }
    Write-Host "`nTo restart orchestrator: cd $Path && python -m src.main" -ForegroundColor Cyan
    $dgRoot = Split-Path (Split-Path $Path -Parent) -Parent
    $staticDir = Join-Path $dgRoot "src" "ui" "static"
    if (Test-Path $staticDir) {
        $backupDir = Join-Path $staticDir "backup"
        $backupOk = (Test-Path (Join-Path $backupDir "app.js")) -and (Test-Path (Join-Path $backupDir "style.css"))
        if (-not $backupOk) { Write-Host "[!] Static backups missing - run: python -m src.ui.web_server" -ForegroundColor Yellow }
    }
}

# -- Main ------------------------------------------------
if (-not $Watch) {
    $hb = Read-Heartbeat
    $output = Format-Heartbeat $hb
    Write-Host $output

    if ($hb) {
        $ago = Get-SecondsAgo $hb.timestamp
        if ($ago -gt $Threshold) {
            Show-Diagnostics
        }
    }
    exit
}

# -- Watch mode ------------------------------------------
Write-Host "Watchtower active - checking every ${Threshold}s. Press Ctrl+C to stop." -ForegroundColor Green
while ($true) {
    Clear-Host
    $hb = Read-Heartbeat
    $output = Format-Heartbeat $hb
    Write-Host $output

    if ($hb) {
        $ago = Get-SecondsAgo $hb.timestamp
        if ($ago -gt $Threshold) {
            Show-Diagnostics
        }
    }
    Start-Sleep -Seconds $Threshold
}
