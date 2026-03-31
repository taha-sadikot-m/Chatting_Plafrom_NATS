# ─────────────────────────────────────────────────────────────────
# ChatRoom - Upload files to EC2 then start the app
# Run from your Windows machine after launching EC2
# Prerequisites: AWS CLI installed, PEM key file
#
# Usage:
#   .\deploy\upload_to_ec2.ps1 -KeyFile "C:\path\to\key.pem" -Host "ec2-xx-xx-xx-xx.compute.amazonaws.com"
# ─────────────────────────────────────────────────────────────────

param(
    [Parameter(Mandatory)][string]$KeyFile,
    [Parameter(Mandatory)][string]$Host,
    [string]$User = "ubuntu"
)

$AppDir  = Split-Path $PSScriptRoot -Parent
$Remote  = "${User}@${Host}"
$SshOpts = "-i `"$KeyFile`" -o StrictHostKeyChecking=no"

Write-Host "`n📦 Uploading ChatRoom to EC2 ($Host)..." -ForegroundColor Cyan

# Files to upload (exclude local-only files)
$exclude = @("__pycache__", "*.pyc", "venv", ".env", "cloudflared.exe", "deploy\*.sh", "*.log", ".git")
$rsyncExclude = $exclude | ForEach-Object { "--exclude=$_" }

# Use scp if rsync not available
Write-Host "[1/3] Copying files..." -ForegroundColor White
scp $SshOpts.Split(" ") -r `
    "$AppDir\app.py" `
    "$AppDir\cognito_auth.py" `
    "$AppDir\requirements.txt" `
    "$AppDir\gunicorn.conf.py" `
    "$AppDir\static" `
    "$AppDir\templates" `
    "${Remote}:/home/${User}/chatroom/"

Write-Host "[2/3] Installing dependencies..." -ForegroundColor White
ssh $SshOpts.Split(" ") $Remote "cd /home/${User}/chatroom && python3 -m venv venv && source venv/bin/activate && pip install -q -r requirements.txt gunicorn eventlet"

Write-Host "[3/3] Restarting service..." -ForegroundColor White
ssh $SshOpts.Split(" ") $Remote "sudo systemctl restart chatroom"

Write-Host "`n✅  Deployed! Your app is live at:  http://$Host" -ForegroundColor Green
Write-Host "    Share this link with others." -ForegroundColor Yellow
