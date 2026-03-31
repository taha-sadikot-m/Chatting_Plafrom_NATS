#!/usr/bin/env pwsh
# ─────────────────────────────────────────────────────────────────────────────
# start_nats.ps1  –  Download (if needed) and run the NATS server
#
# Usage:
#   .\start_nats.ps1              # default: localhost:4222
#   .\start_nats.ps1 -Port 4223  # custom port
# ─────────────────────────────────────────────────────────────────────────────
param(
    [int]$Port = 4222
)

$NATS_VERSION   = "v2.10.24"
$NATS_DIR       = Join-Path $PSScriptRoot "nats-server"
$NATS_EXE       = Join-Path $NATS_DIR "nats-server.exe"
$NATS_ZIP_URL   = "https://github.com/nats-io/nats-server/releases/download/$NATS_VERSION/nats-server-$NATS_VERSION-windows-amd64.zip"
$NATS_ZIP_PATH  = Join-Path $NATS_DIR "nats-server.zip"

# ── 1. Create nats-server/ folder if missing ─────────────────────────────────
if (-not (Test-Path $NATS_DIR)) {
    New-Item -ItemType Directory -Path $NATS_DIR | Out-Null
}

# ── 2. Download binary if not already present ────────────────────────────────
if (-not (Test-Path $NATS_EXE)) {
    Write-Host "NATS server binary not found. Downloading $NATS_VERSION ..." -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $NATS_ZIP_URL -OutFile $NATS_ZIP_PATH -UseBasicParsing
        Write-Host "Extracting..." -ForegroundColor Cyan
        Expand-Archive -Path $NATS_ZIP_PATH -DestinationPath $NATS_DIR -Force

        # The archive extracts to a versioned sub-folder; move exe to $NATS_DIR
        $extracted = Get-ChildItem -Path $NATS_DIR -Recurse -Filter "nats-server.exe" |
                     Select-Object -First 1
        if ($extracted -and $extracted.FullName -ne $NATS_EXE) {
            Move-Item -Path $extracted.FullName -Destination $NATS_EXE -Force
        }

        Remove-Item -Path $NATS_ZIP_PATH -Force
        # Remove now-empty versioned sub-folder
        Get-ChildItem -Path $NATS_DIR -Directory | Remove-Item -Recurse -Force

        Write-Host "NATS server downloaded to $NATS_EXE" -ForegroundColor Green
    } catch {
        Write-Error "Failed to download NATS server: $_"
        Write-Host ""
        Write-Host "Please download it manually from:" -ForegroundColor Yellow
        Write-Host "  $NATS_ZIP_URL" -ForegroundColor Yellow
        Write-Host "Extract nats-server.exe into:  $NATS_DIR" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "NATS server binary found: $NATS_EXE" -ForegroundColor Green
}

# ── 3. Start the NATS server ─────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting NATS server on nats://localhost:$Port ..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $NATS_EXE --port $Port
