@echo off
setlocal
cd /d "%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%STARTUP%\NEXUS AI.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%TARGET%');$s.TargetPath='%~dp0start_nexus.bat';$s.WorkingDirectory='%~dp0';$s.WindowStyle=7;$s.Save()"
if exist "%TARGET%" (echo NEXUS AI will launch when you sign in to Windows.) else (echo Could not create startup shortcut.)
pause
