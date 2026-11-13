@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-and-assemble.ps1"
set "COMPANION_DOWNLOAD_EXIT=%ERRORLEVEL%"
if not "%COMPANION_DOWNLOAD_EXIT%"=="0" echo Download or verification failed. See the error above.
pause
exit /b %COMPANION_DOWNLOAD_EXIT%
