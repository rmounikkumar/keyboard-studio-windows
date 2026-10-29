@echo off
rem Rebuild the app and copy the fresh build over the installed copy.
rem Install first: copy dist\Keyboard Studio to
rem   %LOCALAPPDATA%\Programs\Keyboard Studio
rem and point a shortcut at Keyboard Studio.exe (see README).
setlocal
cd /d "%~dp0"

set "DEST=%LOCALAPPDATA%\Programs\Keyboard Studio"

if not exist "%DEST%\Keyboard Studio.exe" (
  echo No installed copy found at:
  echo   %DEST%
  echo.
  echo Build it with build-exe.bat, copy dist\Keyboard Studio there,
  echo then make a shortcut. After that this script updates it in place.
  echo.
  pause
  exit /b 1
)

tasklist /fi "imagename eq Keyboard Studio.exe" 2>nul | findstr /i /c:"Keyboard Studio.exe" >nul
if not errorlevel 1 (
  echo Keyboard Studio is running. Close it first, then run this again.
  echo.
  pause
  exit /b 1
)

where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install --quiet pyinstaller
%PY% -m PyInstaller --noconfirm "%~dp0Keyboard Studio.spec"
if errorlevel 1 (
  echo.
  echo Build failed - the installed copy was left as it was.
  pause
  exit /b 1
)

robocopy "dist\Keyboard Studio" "%DEST%" /MIR /NFL /NDL /NJH /NJS
if errorlevel 8 (
  echo.
  echo Copy failed - see the robocopy messages above.
  pause
  exit /b 1
)

echo.
echo Updated: %DEST%
echo Launch it from your Desktop or Start Menu shortcut.
echo.
pause
