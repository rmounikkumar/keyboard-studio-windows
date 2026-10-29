@echo off
rem One-time setup: install dependencies (no admin needed).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install --upgrade pip
%PY% -m pip install -r "%~dp0requirements.txt"
echo.
echo Done. Start the app with run.bat.
echo If the light does not change, run diagnose.bat and copy its report.
pause
