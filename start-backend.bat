@echo off
chcp 65001 >nul
title ZhiYue Campus - Backend (FastAPI)
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] creating virtual environment and installing dependencies ...
  python -m venv .venv && ".venv\Scripts\python.exe" -m pip install -r requirements.txt && ".venv\Scripts\python.exe" scripts\seed.py
)

echo.
echo ============================================
echo  Backend   http://127.0.0.1:8000/docs
echo  Press Ctrl+C to stop
echo ============================================
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
