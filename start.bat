@echo off
echo ============================================================
echo  Starting Corpus AI Services...
echo ============================================================
docker compose up -d
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to start Docker containers.
    echo Please make sure Docker Desktop is running and try again!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Waiting for services to initialize...
timeout /t 3 /nobreak >nul

echo Opening Corpus AI in your default browser...
start http://localhost:8501

echo.
echo ============================================================
echo  Corpus AI is running!
echo  - Web App:  http://localhost:8501
echo  - API Docs: http://localhost:8000/api/v1/docs
echo  To stop:    run stop.bat
echo ============================================================
