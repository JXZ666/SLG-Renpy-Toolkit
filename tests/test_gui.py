"""Offline checks for the SLG-Renpy-Toolkit window.

The window cannot be clicked from here, so this covers what can be asserted
without eyes: that the layout builds at all, that a theme switch repaints the
widgets sv-ttk does not own, and that every branch of the status logic lands on
a colour that exists.

Run:  python tests/test_gui.py
"""

import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

import appgui  # noqa: E402

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
    check("sv_ttk is importable", appgui.sv_ttk is not None,
          "theme falls back to the default ttk look")

    root = tk.Tk()
    root.withdraw()
    try:
        app = appgui.App(root)
        root.update()

        check("window builds", app.log is not None)

        # The skip-the-logos box. Default on, and it has to reach the Namespace
        # the worker thread reads - the GUI only ever reads the Tk variable on
        # the main thread, so this is the seam worth pinning.
        check("the skip-intro box starts ticked", app.var_skip.get() is True)
        check("it is live before a game is picked",
              "disabled" not in app.chk_skip.state())
        check("it rides into the namespace",
              appgui._namespace("x", skip_intro=False).skip_intro is False
              and appgui._namespace("x").skip_intro is True)

        # The boxes are drawn from features.CATALOG rather than from a list in
        # the layout, which is the whole point of the catalogue: a third feature
        # must appear in the window without an edit to appgui.py.
        check("one card per catalogue entry",
              sorted(app.rows) == sorted(appgui.features.ids()), sorted(app.rows))
        check("every card is ticked the way its entry says",
              {fid: app.var_on[fid].get() for fid in app.rows}
              == {e["id"]: bool(e.get("default_on", True))
                  for e in appgui.features.CATALOG})
        # Both spellings of the selection travel together, or the runner would
        # have to guess which one the window meant.
        check("the two spellings agree",
              appgui._namespace("x", feature_ids=["intro"]).features == ["intro"]
              and appgui._namespace("x", feature_ids=["intro"]).skip_intro is True)
        check("unticking the intro wins over an explicit list",
              appgui._namespace("x", feature_ids=["fontfix", "intro"],
                                 skip_intro=False).features == ["fontfix"])

        # A theme switch has to reach the Text, or dark mode shows a white block.
        seen = set()
        for theme in ("dark", "light", "dark"):
            app._apply_theme(theme)
            root.update()
            p = appgui._palette(root)
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
                  level in appgui._GLYPH, got)
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
