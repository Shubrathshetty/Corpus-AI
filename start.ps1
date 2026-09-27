# Corpus AI - One-command Launcher
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Starting Corpus AI Services..." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] Failed to start Docker containers." -ForegroundColor Red
    Write-Host "Please ensure Docker Desktop is running and try again." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "`nWaiting for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host "Opening Corpus AI in your default browser..." -ForegroundColor Green
Start-Process "http://localhost:8501"

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " Corpus AI is running!" -ForegroundColor Green
Write-Host " - Web App:  http://localhost:8501" -ForegroundColor White
Write-Host " - API Docs: http://localhost:8000/api/v1/docs" -ForegroundColor White
Write-Host " To stop:    run .\stop.bat or docker compose down" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
