@echo off
REM Builds GUI and CLI executables under release\<APP_VERSION> by default.
REM Pass an output directory as the first argument to choose another destination.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python not found on PATH & exit /b 1)

if not exist "assets\SLG-Renpy-Toolkit.ico" (
    echo Missing assets\SLG-Renpy-Toolkit.ico - run: python tools\make_icon.py
    exit /b 1
)

if not "%~1"=="" (
    python tools\build_exe.py "%~1"
) else (
    python tools\build_exe.py
)
if errorlevel 1 exit /b 1

echo.
echo Built GUI and CLI executables.
endlocal
