# ─────────────────────────────────────────────────────────────────
# ChatRoom - Cloudflare Quick Tunnel (no account needed)
# Run this script to get a free public HTTPS link for your app
# Usage:  Right-click > Run with PowerShell  (or: .\start_tunnel.ps1)
# ─────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

# Uses localhost.run — free SSH tunnel, no downloads, built into Windows 10+
# Alternative: serveo.net (same command, different host)

# ── 2. Start Flask if not running ─────────────────────────────────
$flaskUp = $false
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:5000" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    $flaskUp = $true
} catch {}

if ($flaskUp) {
    Write-Host "[1/2] Flask is already running on :5000" -ForegroundColor Green
} else {
    Write-Host "[1/2] Starting Flask server..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; python app.py" -WindowStyle Minimized
    Start-Sleep 3
    Write-Host "      Flask started" -ForegroundColor Green
}

# ── 3. Open SSH Tunnel via localhost.run ──────────────────────────
Write-Host "`n[2/2] Opening public tunnel via localhost.run..." -ForegroundColor Cyan
Write-Host "      Your public HTTPS URL will appear below in ~5 seconds." -ForegroundColor White
Write-Host "      Look for a line containing: https://....lhr.life" -ForegroundColor Yellow
Write-Host "" 
Write-Host "  *** IMPORTANT: Copy the https://....lhr.life URL, then:" -ForegroundColor Magenta
Write-Host "  1. Go to AWS Cognito > User Pool > App Client > Hosted UI" -ForegroundColor White
Write-Host "  2. Add  https://....lhr.life/auth/callback  to Allowed Callback URLs" -ForegroundColor White
Write-Host "  3. Add  https://....lhr.life/  to Allowed Sign-out URLs" -ForegroundColor White
Write-Host "  4. Save changes, then share the https://....lhr.life link" -ForegroundColor White
Write-Host ""
Write-Host "      Press Ctrl+C to stop the tunnel.`n" -ForegroundColor Gray

ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:5000 localhost.run
