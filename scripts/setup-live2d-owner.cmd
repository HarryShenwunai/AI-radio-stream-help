@echo off
setlocal DisableDelayedExpansion
set "APP_TARGET=%~1"
if not defined APP_TARGET set /p "APP_TARGET=Fully extracted application folder: "
if not defined APP_TARGET exit /b 1
set "APP_TARGET=%APP_TARGET:"=%"
for %%I in ("%APP_TARGET%") do if /i "%%~nxI"=="companion-desktop.exe" set "APP_TARGET=%%~dpI"
if not exist "%APP_TARGET%\resources\backend\python\python.exe" (echo Embedded Python was not found. Apply the current small update first.& pause& exit /b 1)
echo Optional OWNER-LOCAL Live2D development evaluation setup.
echo Read BOTH agreements before downloading, installing or using:
echo https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html
echo https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html
echo This does not authorize redistribution or commercial publication.
echo About 29 MB of fixed npm archives plus official Core will be downloaded.
echo No Node installation, npm scripts, models, accounts or character data are changed.
echo Close the companion application before continuing.
set /p "OWNER_ACK=Type LOCAL-EVALUATION to accept both agreements and trust the locked local build: "
set "OWNER_ACK=%OWNER_ACK:"=%"
if not "%OWNER_ACK%"=="LOCAL-EVALUATION" (echo Setup cancelled.& exit /b 2)
"%APP_TARGET%\resources\backend\python\python.exe" -I -X utf8 "%~dp0setup_live2d_owner.py" install --application-root "%APP_TARGET%" --accept-official-license --trust-locked-build
set "OWNER_RESULT=%ERRORLEVEL%"
pause
exit /b %OWNER_RESULT%
