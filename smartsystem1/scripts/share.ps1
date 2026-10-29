# share.ps1 — bring up the production stack and expose it on a public URL via a
# Cloudflare *quick* tunnel (no account, no card). Run from anywhere:
#
#     powershell -ExecutionPolicy Bypass -File scripts\share.ps1
#
# The quick-tunnel URL is random and CHANGES every run. This script wires the
# fresh URL into .env.prod (only photos depend on it — the frontend calls the API
# on a relative path) and recreates the API container so presigned photo URLs
# point at the public origin. Leave this window OPEN — closing it kills the
# tunnel and your friend loses access (the stack keeps running in Docker).

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$compose = @("--env-file", ".env.prod", "-f", "docker-compose.prod.yml")
$cf  = Join-Path $root ".tools\cloudflared.exe"
$log = Join-Path $root ".tools\tunnel.log"

if (-not (Test-Path $cf)) { throw "cloudflared not found at $cf — download it into .tools\ first." }

Write-Host "==> Ensuring the production stack is up..." -ForegroundColor Cyan
docker compose @compose up -d | Out-Null

Write-Host "==> Stopping any old tunnel..." -ForegroundColor Cyan
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item $log -ErrorAction SilentlyContinue

Write-Host "==> Starting Cloudflare quick tunnel..." -ForegroundColor Cyan
# cloudflared prints the assigned URL to stderr.
$proc = Start-Process -FilePath $cf `
    -ArgumentList "tunnel","--url","http://localhost:80","--no-autoupdate" `
    -RedirectStandardError $log -RedirectStandardOutput "$log.out" `
    -PassThru -WindowStyle Hidden

# Poll the log for the public URL (usually appears within ~10s).
$url = $null
foreach ($i in 1..30) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value; break }
    }
}
if (-not $url) { throw "Tunnel URL did not appear within 30s — check $log" }

Write-Host "==> Wiring $url into .env.prod..." -ForegroundColor Cyan
$envText = Get-Content .env.prod -Raw
$envText = $envText -replace "SITE_URL=.*",              "SITE_URL=$url"
$envText = $envText -replace "PUBLIC_S3_ENDPOINT_URL=.*","PUBLIC_S3_ENDPOINT_URL=$url"
$envText = $envText -replace 'CORS_ORIGINS=.*',          "CORS_ORIGINS=[`"$url`"]"
Set-Content .env.prod -Value $envText -Encoding utf8 -NoNewline

Write-Host "==> Recreating API so photo URLs use the new origin..." -ForegroundColor Cyan
docker compose @compose up -d --force-recreate api | Out-Null

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  CivicPulse AI is LIVE — share this URL with your friend:" -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Keep this window open. Press Ctrl+C to stop sharing (the Docker"
Write-Host "stack keeps running; only the public tunnel goes down)."
Write-Host ""

# Hold the window so the tunnel stays alive and tied to this session.
Wait-Process -Id $proc.Id
