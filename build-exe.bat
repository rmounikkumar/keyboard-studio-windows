@echo off
rem Build a single-folder .exe with PyInstaller (run install.bat first).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install pyinstaller
%PY% -m PyInstaller --noconfirm "%~dp0Keyboard Studio.spec"
echo.
echo Built: dist\Keyboard Studio\Keyboard Studio.exe
pause
