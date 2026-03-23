@echo off
REM Voxel — Windows development launcher
REM Starts both the Python backend and React frontend
setlocal
cd /d "%~dp0"

echo Starting Voxel...
echo   Backend:  uv run server.py (WebSocket :8080)
echo   Frontend: npm run dev (http://localhost:5173)
echo.

start "Voxel Backend" cmd /c "uv run server.py"
timeout /t 2 /nobreak >nul
cd app && npm run dev
