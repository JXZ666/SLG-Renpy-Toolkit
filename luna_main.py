#!/usr/bin/env python
"""rpykit-luna - give a Ren'Py game the glyphs its own fonts are missing.

LunaTranslator can replace a Ren'Py game's text in memory, but it changes fonts
through the system font APIs, which Ren'Py does not use: the engine loads a
.ttf straight out of the game directory and hands it to FreeType. So an English
game's fonts have no Hanzi and Luna's Chinese comes out as empty boxes.

This fixes that half. It points every font name the game resolves at a
FontGroup that keeps the original face for Latin and draws CJK with an
installed CJK font. It does not touch the language, the game's tl/, or any
archive, and it is fully reversible.

While it is there it also redirects the game's splashscreen to a no-op, so the
opening logos stop being part of every launch.

  double-click the exe        -> a window
  drop a game folder onto it  -> runs headless and exits
  rpykit-luna <dir> --revert  -> puts the game back

Every change is a feature listed in features.py, and the two ways of choosing
them agree: `--features a,b` says which, and `--no-skip-intro` is the older
single switch that still works. `--revert` ignores both - undo removes
everything this tool ever wrote.

Only cmd_fontfix is imported, so a frozen build stays small and cannot be
taken down by the heavier dependencies the translate pipeline needs.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Game paths are frequently CJK; the Windows console defaults to cp936 and
# would mangle them. Under a windowless build these streams can be None.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

import argparse  # noqa: E402

import cmd_fontfix  # noqa: E402
import features  # noqa: E402


def _split(value):
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _selection(args):
    """Which features this command line asked for, as ids in catalogue order.

    Three spellings meet here and must not fight: --features says what to
    install, --no-features subtracts from that, and --no-skip-intro is the
    single switch from before there was a catalogue. Unknown ids are reported
    and dropped rather than raising - a typo should not stop the run, and the
    runner would drop them anyway.
    """
    known = features.ids()
    if args.features is None:
        chosen = features.default_selection()
    else:
        chosen = [fid for fid in known if fid in _split(args.features)]

    drop = _split(args.no_features)
    if not args.skip_intro:
        drop.append("intro")
    out = [fid for fid in chosen if fid not in drop]

    unknown = [fid for fid in _split(args.features) + drop if fid not in known]
    if unknown:
        print("!! unknown feature(s) ignored: %s (known: %s)"
              % (", ".join(sorted(set(unknown))), ", ".join(known)))
    return out


def _hide_console():
    """Drops the console window on the GUI path.

    The exe is built as a console application on purpose - that is what makes
    a dragged folder show its log. Double-clicking should not leave a stray
    black window behind, so hide it once we know we are opening the GUI.
    """
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:  # noqa: BLE001 - cosmetic only, never fatal
        pass


def _pause_on_error(code):
    """Keeps the console open long enough to read a failure.

    Explorer closes the console the moment a dragged-onto process exits, so
    without this an error would flash past unread. Successful runs exit
    immediately - the game working is the confirmation.
    """
    if code == 0 or not getattr(sys, "frozen", False):
        return
    try:
        input("\n失败（退出码 %d）。按回车关闭..." % code)
    except (EOFError, OSError, RuntimeError):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rpykit-luna",
        description="Install CJK fonts into a Ren'Py game so LunaTranslator's "
                    "text renders as Chinese instead of tofu.")
    parser.add_argument("game_dir", nargs="?", default=None,
                        help="game root, the directory holding game/ and renpy/")
    parser.add_argument("--revert", action="store_true",
                        help="remove the font, the shim and the compiled .rpyc")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the decisions and write nothing")
    parser.add_argument("--force", action="store_true",
                        help="overwrite a file rpykit did not install")
    parser.add_argument("--features", default=None, metavar="IDS",
                        help="comma-separated features to install, in catalogue "
                             "order: %s" % ", ".join(features.ids()))
    parser.add_argument("--no-features", default=None, metavar="IDS",
                        help="features to leave out, subtracted from the default "
                             "set or from --features")
    parser.add_argument("--no-skip-intro", action="store_false", dest="skip_intro",
                        default=True,
                        help="keep the opening logos; by default the splashscreen "
                             "is redirected to a no-op so the game boots straight "
                             "to the main menu")
    args = parser.parse_args(argv)

    if args.game_dir is None:
        _hide_console()
        import lunagui
        lunagui.main()
        return 0

    ns = argparse.Namespace(
        game_dir=args.game_dir, work=None, mode="luna",
        lang="chinesesimplified", revert=args.revert,
        force=args.force, dry_run=args.dry_run, skip_intro=args.skip_intro,
        features=_selection(args))
    code = 0
    try:
        code = cmd_fontfix.run(ns) or 0
    except SystemExit as e:
        print("!! %s" % e)
        code = 1
    except Exception as e:  # noqa: BLE001 - the user needs the message, not a traceback
        print("!! %s: %s" % (type(e).__name__, e))
        code = 1
    _pause_on_error(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
