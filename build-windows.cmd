@echo off
setlocal
cd /d "%~dp0"
echo Preparing the Windows x64 desktop from verified binaries, without VS compilation.
echo Downloads and dependencies stay inside this project's .build folder.
echo This script does not change system configuration or GitHub billing.
echo Missing Visual C++ runtime prerequisites are reported, never installed silently.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows_local.ps1" %*
set "COMPANION_BUILD_EXIT=%ERRORLEVEL%"
if not "%COMPANION_BUILD_EXIT%"=="0" echo Build stopped. See the log path printed above. No success package is claimed.
echo.
pause
exit /b %COMPANION_BUILD_EXIT%
