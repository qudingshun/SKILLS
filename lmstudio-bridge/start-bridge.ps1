$ErrorActionPreference = "Stop"
$bridge = Join-Path $PSScriptRoot "bridge.py"
$port = 8098

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "LM Studio bridge already running on port $port. Nothing to do."
    exit 0
}

Start-Process -FilePath "python" -ArgumentList "`"$bridge`"" -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "LM Studio bridge started on port $port."
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

Write-Error "LM Studio bridge failed to start."
exit 1