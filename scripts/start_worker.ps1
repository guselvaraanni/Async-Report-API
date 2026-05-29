# Start Celery worker for Windows + Memurai (REQUIRED: --pool=solo)
# Run from repo root: .\scripts\start_worker.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$env:FLASK_ENV = "development"

Write-Host "Starting Celery worker (Windows solo pool)..." -ForegroundColor Cyan
Write-Host "Ensure Memurai is running on localhost:6379" -ForegroundColor Yellow

celery -A worker.celery worker --loglevel=info -Q reports --pool=solo --concurrency=1
