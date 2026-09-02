# DiStyle Photo Pipeline — lokalaus diegimo skriptas
# Paleisti: .\setup_local_digroup.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host "=== DiStyle Photo Pipeline — setup ===" -ForegroundColor Cyan

# Server venv
Write-Host ""
Write-Host "[1/4] Server venv..." -ForegroundColor Yellow
Set-Location "$Root\server"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  Sukurtas server/.env" -ForegroundColor Green
}

# Client venv
Write-Host ""
Write-Host "[2/4] Client venv..." -ForegroundColor Yellow
Set-Location "$Root\client"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# Project .env
Write-Host ""
Write-Host "[3/4] .env failai..." -ForegroundColor Yellow
Set-Location $Root
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  Sukurtas .env — UZPILDYK WC + WP laukus!" -ForegroundColor Red
} else {
    Write-Host "  .env jau egzistuoja" -ForegroundColor Green
}

# Output dirs
New-Item -ItemType Directory -Force -Path "$Root\client\output" | Out-Null
New-Item -ItemType Directory -Force -Path "$Root\client\backups" | Out-Null

Write-Host ""
Write-Host "[4/4] Ollama modelis..." -ForegroundColor Yellow
Write-Host "  Paleisk: ollama pull moondream" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== Setup baigtas ===" -ForegroundColor Green
Write-Host "Kitas zingsnis:"
Write-Host "  Langas 1: ollama serve"
Write-Host "  Langas 2: cd server; .venv\Scripts\activate; python main.py"
Write-Host "  Langas 3: cd client; .venv\Scripts\activate; python -m distyle_photo health"

Set-Location $Root
