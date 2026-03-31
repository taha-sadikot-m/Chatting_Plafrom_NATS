#!/usr/bin/env pwsh
# ─────────────────────────────────────────────────────────────────────────────
# start.ps1  –  Start NATS server + Flask chat app together
#
# Usage:
#   .\start.ps1
#   .\start.ps1 -NatsPort 4222 -AppPort 5000
# ─────────────────────────────────────────────────────────────────────────────
param(
    [int]$NatsPort = 4222,
    [int]$AppPort  = 5000
)

# Resolve paths relative to this script
$ScriptDir  = $PSScriptRoot
$NatsScript = Join-Path $ScriptDir "start_nats.ps1"
$PythonExe  = Join-Path $ScriptDir "venv\Scripts\python.exe"
$AppScript  = Join-Path $ScriptDir "app.py"

# ── Python executable: prefer local venv, fall back to system python ──────────
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Chat Platform – Startup Script"            -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Start NATS server in a new window ─────────────────────────────────────
Write-Host "Starting NATS server (port $NatsPort) ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-File `"$NatsScript`" -Port $NatsPort" -WindowStyle Normal

# Give NATS a moment to bind the port before Flask connects
Start-Sleep -Seconds 2

# ── 2. Start Flask app ────────────────────────────────────────────────────────
Write-Host "Starting Flask app (port $AppPort) ..." -ForegroundColor Yellow
$env:PORT     = "$AppPort"
$env:NATS_URL = "nats://localhost:$NatsPort"

Write-Host ""
Write-Host "Chat app running at: http://localhost:$AppPort" -ForegroundColor Green
Write-Host "NATS running at:     nats://localhost:$NatsPort" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the Flask app." -ForegroundColor DarkGray
Write-Host "(Close the NATS window separately to stop NATS.)" -ForegroundColor DarkGray
Write-Host ""

& $PythonExe $AppScript
