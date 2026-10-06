@echo off
chcp 65001 >nul
title ZhiYue Campus - Frontend (Vue3 + Vite)
cd /d "%~dp0web-pc"

if not exist "node_modules" (
  echo [setup] installing frontend dependencies ...
  call npm install --no-audit --no-fund
)

echo.
echo ============================================
echo  Frontend  http://127.0.0.1:5173
echo  Press Ctrl+C to stop
echo ============================================
echo.
call npm run dev
pause
