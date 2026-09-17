@echo off
REM Builds dist\rpykit-luna.exe - one self-contained file, no Python needed.
REM ASCII only on purpose: cmd.exe runs .bat files through cp936 here and
REM non-ASCII comments come out mangled.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python not found on PATH & exit /b 1)

python -c "import PyInstaller" >nul 2>nul || (
    echo Installing PyInstaller...
    python -m pip install --upgrade pyinstaller || exit /b 1
)

REM The window's theme. Build-time only - sv_ttk is pure tcl and png, and
REM PyInstaller's own hook bundles it, so the spec needs no datas entry for it.
python -c "import sv_ttk" >nul 2>nul || (
    echo Installing sv-ttk...
    python -m pip install "sv-ttk==2.6.1" || exit /b 1
)

REM Referenced by icon= in the spec, so the build fails without it. Regenerate
REM with: python tools\make_icon.py   (that one step does need Pillow.)
if not exist "assets\rpykit-luna.ico" (
    echo Missing assets\rpykit-luna.ico - run: python tools\make_icon.py
    exit /b 1
)

REM Built from the spec, not from luna_main.py on the command line: passing the
REM script and flags here makes PyInstaller REWRITE rpykit-luna.spec, which
REM would silently discard its icon= and any future hand edit.
REM
REM The spec keeps console=True on purpose - dropping a game folder onto the exe
REM has to show its log. The GUI path hides the console itself
REM (luna_main._hide_console).
python -m PyInstaller --noconfirm --clean rpykit-luna.spec || exit /b 1

echo.
echo Built: %CD%\dist\rpykit-luna.exe
endlocal
