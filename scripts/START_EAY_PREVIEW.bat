@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 goto use_py

where python >nul 2>nul
if %errorlevel%==0 goto use_python

echo.
echo EAY Preview requires Python to start the local static server.
echo Python was not found on PATH.
echo Alternative: install Node.js and run: npx serve -s . -l 4173
echo Then open: http://localhost:4173/
echo.
pause
exit /b 1

:use_py
start "EAY Preview Server" cmd /k "cd /d ""%~dp0"" && py -m http.server 4173"
goto open_browser

:use_python
start "EAY Preview Server" cmd /k "cd /d ""%~dp0"" && python -m http.server 4173"

:open_browser
timeout /t 2 /nobreak >nul
start "" "http://localhost:4173/"
exit /b 0
