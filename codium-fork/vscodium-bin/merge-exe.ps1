# Reassemble deepgravity.exe from chunks
$partsDir = Join-Path $PSScriptRoot "deepgravity-parts"
$exePath = Join-Path $PSScriptRoot "deepgravity.exe"
$parts = Get-ChildItem -Path $partsDir -Filter "deepgravity.exe.part*" | Sort-Object Name

if (-not (Test-Path $exePath)) {
    Write-Host "Reassembling deepgravity.exe from $($parts.Count) parts..."
    $stream = [System.IO.File]::Create($exePath)
    foreach ($part in $parts) {
        $data = [System.IO.File]::ReadAllBytes($part.FullName)
        $stream.Write($data, 0, $data.Length)
    }
    $stream.Close()
    $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "Done. deepgravity.exe reassembled ($size MB)."
} else {
    Write-Host "deepgravity.exe already exists."
}
