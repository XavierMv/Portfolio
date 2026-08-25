@echo off
REM ============================================================
REM  Portfolio Analyzer Discovery May 2026 - Windows launcher
REM ============================================================
echo.
echo  Portfolio Analyzer Discovery - starting...
echo.

cd /d "%~dp0"

REM --- 1. Build frontend if not already built ---
if not exist "frontend\dist\index.html" (
    echo  [1/3] Building frontend ^(first run only^)...
    cd frontend
    call npm install
    call npm run build
    cd ..
) else (
    echo  [1/3] Frontend already built - skipping.
)

REM --- 2. Install Python deps ---
echo  [2/3] Installing Python dependencies...
cd backend
pip install -r ..\requirements.txt --quiet

REM --- 3. Launch server ---
echo  [3/3] Starting server at http://localhost:8000
echo.
echo  Open http://localhost:8000 in your browser.
echo  Press Ctrl+C to stop.
echo.
python -m uvicorn server:app --host 0.0.0.0 --port 8000

pause
