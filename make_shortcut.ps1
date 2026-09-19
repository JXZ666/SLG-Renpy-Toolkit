# Put a desktop shortcut to the built exe.
#
#   powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1
#
# ASCII only, on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI unless the
# file carries a UTF-8 BOM, and this project's path contains CJK. $PSScriptRoot
# supplies that path at run time, so no non-ASCII byte has to be written here.
#
# The target is a console build deliberately (a dropped game folder has to show
# its log), so Windows allocates a console before any of our code runs and
# app_main._hide_console() can only hide it afterwards. WindowStyle 7 starts
# that console minimized, which turns a black rectangle flash into a brief
# taskbar blip. If the Tk window itself ever opens minimized, set it to 1.

[CmdletBinding()]
param(
    [string] $Exe,
    [string] $Desktop = [Environment]::GetFolderPath('Desktop'),
    [string] $Name    = 'SLG-Renpy-Toolkit'
)

$ErrorActionPreference = 'Stop'

# Resolved here rather than as a param default: $PSScriptRoot comes back empty
# when the script is named by a relative path, and the failure is a confusing
# "empty string not allowed" out of Join-Path rather than anything that points
# at the real cause.
if (-not $Exe) {
    $root = $PSScriptRoot
    if (-not $root) { $root = Split-Path -Parent $PSCommandPath }
    if (-not $root) { throw 'cannot locate the project; pass -Exe explicitly' }
    $Exe = Join-Path $root 'dist\SLG-Renpy-Toolkit.exe'
}

# Comes back empty under a redirected profile (a sandboxed shell, a service
# account), where the failure otherwise surfaces as an opaque "empty string not
# allowed" out of Test-Path.
if (-not $Desktop) {
    throw 'no desktop folder for this account; pass -Desktop explicitly'
}

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "not built yet: $Exe  (run build_exe.bat first)"
}
if (-not (Test-Path -LiteralPath $Desktop)) {
    throw "desktop not found: $Desktop"
}

$Exe     = (Resolve-Path -LiteralPath $Exe).Path
$lnkPath = Join-Path $Desktop ($Name + '.lnk')

$shell = New-Object -ComObject WScript.Shell
$lnk   = $shell.CreateShortcut($lnkPath)

$lnk.TargetPath       = $Exe
$lnk.WorkingDirectory = Split-Path -Parent $Exe
# The icon embedded in the exe, not a separate .ico: it survives the exe being
# replaced by a rebuild and cannot go stale if assets\ moves.
$lnk.IconLocation     = "$Exe,0"
$lnk.Description      = 'SLG-Renpy-Toolkit - CJK fonts and intro skip for RenPy games'
$lnk.WindowStyle      = 7
$lnk.Save()

# Read it back. A silently mis-written .lnk is worse than a loud failure.
$check = $shell.CreateShortcut($lnkPath)
"{0}`n  target {1}`n  window {2}   icon {3}" -f `
    $lnkPath, $check.TargetPath, $check.WindowStyle, $check.IconLocation
