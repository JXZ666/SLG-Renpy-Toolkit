"""Prove the two things that only break once the tool is frozen into an exe.

Running from source, everything here passes by accident. Frozen, the package
unpacks into a temp directory that Windows deletes on exit, and two long-
standing assumptions stop holding:

  * proj.work_root() must not derive from __file__, or the manifest lands in
    that temp tree and reads back empty on the next launch;
  * cmd_fontfix.install() refuses to write a file it cannot prove it owns, so
    with no manifest it would refuse to overwrite its own output - the second
    run against the same game fails outright.

There is also one source-only convenience: a 17.8 MB font is copied on every
install. The tests swap in a tiny stand-in, since what is being checked is the
decision, not the bytes.

Run:  python tests/test_luna.py
"""

import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import cmd_fontfix  # noqa: E402
import proj  # noqa: E402


class _Attrs(object):
    """Set sys attributes for a block, restoring them exactly afterwards.

    delattr matters as much as setattr: code that probes with
    getattr(sys, "_MEIPASS", None) depends on the attribute being absent in
    source mode, not on it being None.
    """

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: (hasattr(sys, k), getattr(sys, k, None)) for k in self.kw}
        for k, v in self.kw.items():
            setattr(sys, k, v)
        return self

    def __exit__(self, *exc):
        for k, (had, val) in self.old.items():
            if had:
                setattr(sys, k, val)
            elif hasattr(sys, k):
                delattr(sys, k)
        return False


class _Env(object):
    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.kw}
        for k, v in self.kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def run_fontfix(game_dir, revert=False, dry_run=False, force=False, mode="luna"):
    ns = argparse.Namespace(game_dir=game_dir, work=None, mode=mode,
                            lang="chinesesimplified", revert=revert,
                            force=force, dry_run=dry_run)
    return cmd_fontfix.run(ns)


def make_game(root, with_script=False):
    """The minimum fontfix will accept: game/ plus a renpy/ tree."""
    os.makedirs(os.path.join(root, "game"), exist_ok=True)
    os.makedirs(os.path.join(root, "renpy", "common"), exist_ok=True)
    if with_script:
        # Any .rpyc-shaped blob is enough; the scan is a regex over payloads.
        with open(os.path.join(root, "game", "script.rpyc"), "wb") as f:
            f.write(b"RENPY RPC2" + b"\x00" * 16)
    return root


def tree(root):
    """Every path under root, relative and sorted - for before/after diffs."""
    out = []
    for base, dirs, files in os.walk(root):
        for n in dirs + files:
            out.append(os.path.relpath(os.path.join(base, n), root))
    return sorted(out)


def main():
    failures = []

    def check(label, cond, detail=""):
        if cond:
            print("  ok   %s" % label)
        else:
            print("  FAIL %s %s" % (label, detail))
            failures.append(label)

    tmp = tempfile.mkdtemp(prefix="rpykit_luna_test_")
    try:
        # --- blocker 4: the bundled asset ------------------------------------
        print("bundled asset")
        check("the real font is where _asset() looks for it",
              os.path.isfile(cmd_fontfix._asset("NotoSansSC-VF.ttf")),
              cmd_fontfix._asset("NotoSansSC-VF.ttf"))

        fake_meipass = os.path.join(tmp, "meipass")
        os.makedirs(os.path.join(fake_meipass, "assets"))
        with _Attrs(_MEIPASS=fake_meipass):
            check("a frozen build resolves assets under _MEIPASS",
                  cmd_fontfix._asset("x.ttf") == os.path.join(fake_meipass, "assets", "x.ttf"),
                  cmd_fontfix._asset("x.ttf"))

        # --- blocker 1: where the workspace lives ----------------------------
        print("work root")
        with _Env(RPYKIT_WORK=None, LOCALAPPDATA=r"C:\Users\x\AppData\Local"):
            check("workspaces land in a persistent per-user dir",
                  proj.work_root() == os.path.join(r"C:\Users\x\AppData\Local", "rpykit"),
                  proj.work_root())
        with _Env(RPYKIT_WORK=os.path.join(tmp, "custom")):
            check("RPYKIT_WORK overrides it",
                  proj.work_root() == os.path.abspath(os.path.join(tmp, "custom")),
                  proj.work_root())
        with _Env(RPYKIT_WORK=None, LOCALAPPDATA=None):
            check("with no LOCALAPPDATA it falls back to the home dir",
                  proj.work_root() == os.path.join(os.path.expanduser("~"), "rpykit"),
                  proj.work_root())

        # --- blocker 2 + 4: install, reinstall, revert -----------------------
        print("install / reinstall / revert against a stand-in font")
        work = os.path.join(tmp, "work")
        game = make_game(os.path.join(tmp, "FakeGame"), with_script=True)

        # A 3-byte font keeps the test fast; _is_ours compares against whatever
        # ASSET_FONT points at, so consistency is what is under test.
        small_font = os.path.join(tmp, "small.ttf")
        with open(small_font, "wb") as f:
            f.write(b"TTF")
        real_asset = cmd_fontfix.ASSET_FONT
        cmd_fontfix.ASSET_FONT = small_font
        try:
            before = tree(game)
            with _Env(RPYKIT_WORK=work):
                run_fontfix(game, dry_run=True)
                check("dry-run writes nothing", tree(game) == before, tree(game))

                _report, first = cmd_fontfix.analyse(game)
                run_fontfix(game)
                shim = os.path.join(game, "game", cmd_fontfix.SHIM_REL)
                font = os.path.join(game, "game", *cmd_fontfix.GAME_FONT_REL.split("/"))
                check("installs the shim", os.path.isfile(shim))
                check("installs the font", os.path.isfile(font))
                check("shim self-checks clean",
                      not cmd_fontfix.validate_shim(open(shim, encoding="utf-8").read()))

                st = cmd_fontfix.installed_state(game)
                check("reports installed", st["shim"] and st["font"], st)
                check("recognises its own shim", st["ours"], st)
                check("reports the current template", st["current"], st)
                check("records luna mode", st["mode"] == "luna", st)

                # The written shim must not read back as a font source. Its
                # header comment names every face in the game and its body
                # names the CJK font, so a scan that did not skip it would
                # alias things like "localization/NotoSansSC-VF.ttf" and grow
                # the list on every reinstall.
                _report, second = cmd_fontfix.analyse(game)
                check("re-reading the game after install decides the same thing",
                      [d["names"] for d in second] == [d["names"] for d in first],
                      [d["names"] for d in second])

                # The frozen failure this whole test exists for: manifest gone.
                shutil.rmtree(work, ignore_errors=True)
                try:
                    run_fontfix(game)
                    check("reinstalls with no manifest present", True)
                except Exception as e:  # noqa: BLE001
                    check("reinstalls with no manifest present", False, repr(e))

                # A shim from an older build must be flagged, not silently kept.
                text = open(shim, encoding="utf-8").read()
                with open(shim, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text.replace("_loc_group(", "_old_group("))
                st = cmd_fontfix.installed_state(game)
                check("flags an older template as not current",
                      st["ours"] and not st["current"], st)

                # Revert works off fixed paths, so it must survive a wiped work dir.
                shutil.rmtree(work, ignore_errors=True)
                with open(shim + "c", "wb") as f:
                    f.write(b"compiled")
                run_fontfix(game, revert=True)
                check("revert removes the shim and the font", tree(game) == before, tree(game))
                check("revert removes the compiled .rpyc",
                      not os.path.exists(shim + "c"))
                check("revert removes the emptied localization/ dir",
                      not os.path.isdir(os.path.join(game, "game", "localization")))
        finally:
            cmd_fontfix.ASSET_FONT = real_asset

        # --- a foreign file in the way is still refused ----------------------
        print("a shim this tool did not write")
        g2 = make_game(os.path.join(tmp, "Foreign"))
        foreign = os.path.join(g2, "game", cmd_fontfix.SHIM_REL)
        with open(foreign, "w", encoding="utf-8") as f:
            f.write("# the player's own font patch\n")
        check("is not claimed as ours", not cmd_fontfix._is_ours(foreign))
        with _Env(RPYKIT_WORK=os.path.join(tmp, "work2")):
            try:
                run_fontfix(g2)
                check("refuses to overwrite it", False, "no error raised")
            except cmd_fontfix.FontFixError:
                check("refuses to overwrite it", True)
            except SystemExit as e:
                check("refuses to overwrite it", False, "SystemExit: %s" % e)
            check("leaves the file untouched",
                  open(foreign, encoding="utf-8").read().startswith("# the player's"))

        # --- blocker 3: the entry point stays thin ---------------------------
        print("entry point")
        import luna_main  # noqa: E402
        check("luna_main is importable", callable(luna_main.main))
        check("no translate pipeline dragged in",
              "cmd_translate" not in sys.modules and "cmd_skeleton" not in sys.modules,
              [m for m in ("cmd_translate", "cmd_skeleton") if m in sys.modules])

        # A path argument must run headless, which is what makes dropping a game
        # folder onto the exe work. Not frozen here, so the error pause is a no-op.
        g3 = make_game(os.path.join(tmp, "ArgvGame"))
        with _Env(RPYKIT_WORK=os.path.join(tmp, "work3")):
            check("a path argument runs headless and succeeds",
                  luna_main.main([g3, "--dry-run"]) == 0)
            check("a non-Ren'Py path fails instead of opening a window",
                  luna_main.main([tmp]) != 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print("FAILED: %d" % len(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
