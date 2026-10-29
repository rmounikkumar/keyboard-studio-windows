@echo off
rem Run Keyboard Studio without a console window.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "%~dp0keyboard_studio.py" & exit /b)
where py >nul 2>nul && (start "" pyw "%~dp0keyboard_studio.py" & exit /b)
python "%~dp0keyboard_studio.py"
