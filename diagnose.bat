@echo off
rem Print what Windows allows for this keyboard, then wait.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% "%~dp0keyboard_studio.py" --diagnose
echo.
pause
