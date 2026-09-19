"""What this tool calls itself.

The name used to be spelled out wherever it was needed - the window title, the
argument parser, the spec, the build script - which is why renaming the tool
was a dozen separate edits and one of them was always going to be missed. The
Python side reads it from here now.

The spec, build_exe.bat and make_shortcut.ps1 still spell it out by hand and
have to be kept in step, because neither can import this: PyInstaller executes
a spec before any of the tool is importable, and cmd.exe reads a .bat through
cp936, which mangles anything non-ASCII. That is the whole reason there are two
names. APP_NAME is what a person reads; APP_SLUG is the ASCII spelling that a
filename, a repository or a command line has to use instead.
"""

APP_NAME = "SLG-Renpy神奇妙妙工具"
APP_SLUG = "SLG-Renpy-Toolkit"
ICON_NAME = APP_SLUG + ".ico"
