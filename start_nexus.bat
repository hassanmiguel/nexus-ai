@echo off
setlocal
title NEXUS AI Launcher
cd /d "%~dp0"
echo ========================================
echo          NEXUS AI - LOCAL AGENT
echo ========================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from https://python.org
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing / checking dependencies...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)
echo.
echo Checking optional Ollama engine...
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama not found. This is fine: NEXUS Core works with zero models.
  echo Install Ollama later from https://ollama.com/download for generative chat.
  echo.
) else (
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=1)" >nul 2>nul
  if errorlevel 1 (
    echo Starting Ollama daemon...
    start "NEXUS Ollama" cmd /c "ollama serve"
    timeout /t 3 >nul
  ) else (
    echo Ollama daemon is already running.
  )
  ollama list
  echo.
)
echo Starting NEXUS AI at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
python run_nexus.py --host 127.0.0.1 --port 8000
pause
