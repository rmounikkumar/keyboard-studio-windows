@echo off
rem Build a single-folder .exe with PyInstaller (run install.bat first).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install pyinstaller
%PY% -m PyInstaller --noconfirm --windowed --name "Keyboard Studio" --hidden-import psutil keyboard_studio.py
echo.
echo Built: dist\Keyboard Studio\Keyboard Studio.exe
pause
