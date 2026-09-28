@echo off
REM Builds GUI and CLI executables under release\1.0.0 by default.
REM Pass an output directory as the first argument to choose another destination.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python not found on PATH & exit /b 1)

if not exist "requirements-build.txt" (
    echo Missing requirements-build.txt.
    exit /b 1
)

REM Check every pinned build dependency. Never upgrade or install packages here.
python -c "from importlib.metadata import version; from packaging.requirements import Requirement; from pathlib import Path; reqs=[Requirement(s) for s in Path('requirements-build.txt').read_text(encoding='utf-8').splitlines() if s.strip() and not s.lstrip().startswith('#')]; actual={r.name:version(r.name) for r in reqs}; bad=[f'{r.name}: expected {r.specifier}, found {actual[r.name]}' for r in reqs if not r.specifier.contains(actual[r.name], prereleases=True)]; print('\n'.join(bad) if bad else 'Build dependencies match requirements-build.txt.'); raise SystemExit(bool(bad))" || (
    echo Build dependencies are missing or do not match requirements-build.txt.
    echo In a clean Python environment run: python -m pip install -r requirements-build.txt
    exit /b 1
)

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
