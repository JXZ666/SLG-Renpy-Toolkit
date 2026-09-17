"""Offline checks for the rpykit-luna window.

The window cannot be clicked from here, so this covers what can be asserted
without eyes: that the layout builds at all, that a theme switch repaints the
widgets sv-ttk does not own, and that every branch of the status logic lands on
a colour that exists.

Run:  python tests/test_lunagui.py
"""

import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

import lunagui  # noqa: E402

# The "this is already a Ren'Py game" status branch is the only one that needs a
# real game, and nobody cloning this repo has one. Point RPYKIT_TEST_GAME at any
# Ren'Py game directory to exercise it; otherwise that one case is skipped.
GAME = os.environ.get("RPYKIT_TEST_GAME") or None

failures = []


def check(name, ok, detail=""):
    print("%-52s %s%s" % (name, "ok" if ok else "FAIL",
                          "" if ok else "  <- " + str(detail)))
    if not ok:
        failures.append(name)


def is_hex(value):
    return (isinstance(value, str) and len(value) == 7 and value.startswith("#")
            and all(c in "0123456789abcdefABCDEF" for c in value[1:]))


def main():
    check("sv_ttk is importable", lunagui.sv_ttk is not None,
          "theme falls back to the default ttk look")

    root = tk.Tk()
    root.withdraw()
    try:
        app = lunagui.App(root)
        root.update()

        check("window builds", app.log is not None)

        # A theme switch has to reach the Text, or dark mode shows a white block.
        seen = set()
        for theme in ("dark", "light", "dark"):
            app._apply_theme(theme)
            root.update()
            p = lunagui._palette(root)
            seen.add(p["theme"])
            check("%s: palette is all hex" % theme,
                  all(is_hex(p[k]) for k in
                      ("bg", "fg", "dim", "panel", "selbg", "selfg")), p)
            bg = str(app.log.cget("background"))
            check("%s: log repainted off the system colour" % theme,
                  bg != "SystemWindow", bg)
            check("%s: log follows the palette" % theme,
                  bg.lower() == p["panel"].lower(), "%s vs %s" % (bg, p["panel"]))
            check("%s: root repainted" % theme,
                  str(root.cget("bg")).lower() == p["bg"].lower())
        check("toggling actually changes theme", seen == {"dark", "light"}, seen)

        # Every branch of the status logic, through the real code path.
        cases = [
            (None, "info"),
            (os.path.join(HERE, "no-such-game"), "bad"),
        ]
        if GAME:
            cases.append((GAME, None))
        else:
            print("%-52s SKIP" % "real-game status branch",
                  "  <- set RPYKIT_TEST_GAME=<game dir> to enable")
        for game, want in cases:
            app.game_dir = game
            got = app._refresh_state()
            level = got[0] if isinstance(got, tuple) else None
            check("state %s" % (want or "real game"),
                  level in lunagui._GLYPH, got)
            if want and level != want:
                check("state %s is %s" % (want, level), False, got)

        # No stale Markdown emphasis should survive into a Label.
        check("no asterisk emphasis in status text",
              "**" not in app.var_state.get(), app.var_state.get())

        check("buttons disable without a directory",
              "disabled" in app.btn_go.state(), app.btn_go.state())
    finally:
        root.destroy()

    print()
    if failures:
        print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
