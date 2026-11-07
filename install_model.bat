@echo off
cd /d "%~dp0"
echo Installing local NEXUS chat model and embedding model...
where ollama >nul 2>nul
if errorlevel 1 (
 echo Ollama is not installed. Download it from https://ollama.com/download
 pause
 exit /b 1
)
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
echo.
echo Both local models are ready. No provider API keys are required.
pause
