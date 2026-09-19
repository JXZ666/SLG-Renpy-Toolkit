"""Prove the pre-flight can tell the four kinds of game apart.

Every fact survey() reports comes from a different file, and the shapes are not
uniform across Ren'Py generations - which is exactly how this went wrong the
first time it was written against real games:

  * game/script_version.txt is the easy source, but Hikari ships without one;
  * Ren'Py 8 puts `version = '8.3.0.24082114'` in renpy/vc_version.py;
  * Ren'Py 7 puts `version_tuple = (7, 4, 11, vc_version)` in
    renpy/__init__.py, and indents it, so an anchored pattern misses it;
  * Ren'Py 7's vc_version.py holds only an SVN revision with no version at all;
  * lib/ is named lib/python2.7 + lib/windows-i686 on 7 and
    lib/python3.9 + lib/py3-windows-x86_64 on 8.

The trees here are synthesized so each defect has one test that names it.

Run:  python tests/test_compat.py
      python tests/test_compat.py --real       (also sweep the real games)
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import cmd_fontfix  # noqa: E402
import compat  # noqa: E402

REAL_GAMES = os.environ.get(
    "RPYKIT_GAMES_DIR", r"D:\game&novel\黄油\3D SLG游戏")


def _w(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make(root, py=3, arch=("x86_64",), script_version="(8, 3, 0)",
         vc_version=None, init_tuple=None, rpa=0, rpy=(), rpyc=(),
         renpy_dir=True):
    """A plausible Ren'Py distribution skeleton, assembled to order."""
    os.makedirs(os.path.join(root, "game"), exist_ok=True)
    if renpy_dir:
        os.makedirs(os.path.join(root, "renpy", "common"), exist_ok=True)
        _w(os.path.join(root, "renpy", "__init__.py"), "# engine\n")
    if script_version is not None:
        _w(os.path.join(root, "game", "script_version.txt"), script_version)
    if vc_version is not None:
        _w(os.path.join(root, "renpy", "vc_version.py"), vc_version)
    if init_tuple is not None:
        _w(os.path.join(root, "renpy", "__init__.py"),
           "if True:\n    version_tuple = %s\n" % init_tuple)

    libs = ["python%s" % ("3.9" if py == 3 else "2.7")]
    for a in arch:
        libs.append("py3-windows-%s" % a if py == 3 else "windows-%s" % a)
    for n in libs:
        os.makedirs(os.path.join(root, "lib", n), exist_ok=True)

    for i in range(rpa):
        with open(os.path.join(root, "game", "archive%d.rpa" % i), "wb") as f:
            f.write(b"RPA-3.0 %016x %08x\n" % (0, 0))
    for name in rpy:
        _w(os.path.join(root, "game", name), "label start:\n    return\n")
    for name in rpyc:
        with open(os.path.join(root, "game", name), "wb") as f:
            f.write(b"RENPY RPC2" + b"\x00" * 16)
    return root


def shim_text():
    """What the tool's own shim looks like on disk, marker and all."""
    return ("# %s - do not hand-edit\ninit 999 python:\n    pass\n"
            % cmd_fontfix.MARKER)


def main():
    failures = []

    def check(label, cond, detail=""):
        if cond:
            print("  ok   %s" % label)
        else:
            print("  FAIL %s %s" % (label, detail))
            failures.append(label)

    tmp = tempfile.mkdtemp(prefix="rpykit_compat_test_")
    try:
        def p(*parts):
            return os.path.join(tmp, *parts)

        # --- the four shapes that matter -------------------------------------
        print("engine detection")
        g = make(p("py2"), py=2, arch=("i686", "x86_64"),
                 script_version="(7, 4, 11)", rpa=3)
        s = compat.survey(g)
        check("Ren'Py 7 + py2 reads the version off script_version.txt",
              s["renpy"]["version"] == "7.4.11", s["renpy"])
        check("py2 is detected from lib/python2.7", s["python"]["major"] == 2,
              s["python"])
        check("both architectures are seen", s["arch"] == "both", s["arch"])
        check("py2 is a warning, not a refusal", s["verdict"] == "warn",
              s["verdict"])
        check("py2 warning says the path is untested",
              any("py2" in r or "Python 2" in r for r in s["reasons"]),
              s["reasons"])

        g = make(p("py3"), script_version="(8, 3, 0)", rpy=("script.rpy",))
        s = compat.survey(g)
        check("py3 is clean", s["verdict"] == "ok", s["reasons"])
        check("py3 label is 可装", s["label"] == "可装", s["label"])
        check("loose sources are counted, not called packed",
              s["sources"]["loose_rpy"] == 1
              and not s["sources"]["packed_only"], s["sources"])

        # Hikari ships no script_version.txt at all; Ren'Py 8's vc_version.py
        # spells the version as a 4-part string.
        g = make(p("vc8"), script_version=None, rpy=("script.rpy",),
                 vc_version="branch = 'master'\nofficial = True\n"
                            "version = '8.3.0.24082114'\n"
                            "version_name = 'Second Star to the Right'\n")
        s = compat.survey(g)
        check("no script_version.txt still finds the version in vc_version.py",
              s["renpy"]["version"] == "8.3.0", s["renpy"])
        check("the 4-part build stamp is trimmed off", "." in (s["renpy"]["version"] or "")
              and s["renpy"]["version"].count(".") == 2, s["renpy"])
        check("the release name is kept", s["renpy"]["name"].startswith("Second"),
              s["renpy"]["name"])

        # Ren'Py 7 indents version_tuple inside an if-block, which an anchored
        # pattern silently misses.
        g = make(p("tuple7"), script_version=None, rpy=("script.rpy",),
                 init_tuple="(7, 4, 11, vc_version)")
        s = compat.survey(g)
        check("an indented version_tuple is still found",
              s["renpy"]["version"] == "7.4.11", s["renpy"])

        g = make(p("svn"), script_version=None, rpy=("script.rpy",),
                 vc_version="vc_version = 2266\nofficial = True\n")
        s = compat.survey(g)
        check("a bare SVN revision is reported as such, not as a version",
              s["renpy"]["version"] == "vc2266", s["renpy"])
        check("an unknown major version is not invented",
              s["renpy"]["major"] is None, s["renpy"])

        # --- packing ----------------------------------------------------------
        print("packed sources")
        g = make(p("packed"), rpa=2)
        s = compat.survey(g)
        check("no loose scripts + archives reads as packed_only",
              s["sources"]["packed_only"], s["sources"])
        check("packed sources are a warning", s["verdict"] == "warn", s["verdict"])

        g = make(p("rpa2"), rpa=1)
        with open(os.path.join(g, "game", "archive0.rpa"), "wb") as f:
            f.write(b"RPA-2.0 %016x %08x\n" % (0, 0))
        s = compat.survey(g)
        check("a non-3.0 archive is named as unreadable",
              s["sources"]["unsupported_rpa"] == ["archive0.rpa"], s["sources"])
        check("an unreadable archive warns",
              any("RPA-3.0" in r for r in s["reasons"]), s["reasons"])

        # --- the tool's own leftovers are not the game's ---------------------
        print("tool leftovers")
        g = make(p("patched"), rpy=("story.rpy",))
        _w(os.path.join(g, "game", "zz_localization.rpy"), shim_text())
        with open(os.path.join(g, "game", "zz_localization.rpyc"), "wb") as f:
            f.write(b"RENPY RPC2" + b"\x00" * 16)
        s = compat.survey(g)
        check("our own shim is not counted as game source",
              s["sources"]["loose_rpy"] == 1, s["sources"])
        check("the .rpyc Ren'Py made from our shim is not counted either",
              s["sources"]["loose_rpyc"] == 0, s["sources"])
        check("our own shim is not a collision", s["collisions"] == [],
              s["collisions"])
        check("an already-patched game is still installable ok",
              s["verdict"] == "ok", s["reasons"])

        # --- conflicts --------------------------------------------------------
        print("conflicts")
        g = make(p("foreign"), rpy=("story.rpy",))
        _w(os.path.join(g, "game", "zz_localization.rpy"), "# hand written\n")
        s = compat.survey(g)
        check("a foreign shim is reported as a collision",
              s["collisions"] == ["game/zz_localization.rpy"], s["collisions"])
        check("a foreign shim warns", s["verdict"] == "warn", s["verdict"])

        g = make(p("rival"), rpy=("story.rpy", "zzz_skip_splash.rpy"))
        _w(os.path.join(g, "game", "zzz_skip_splash.rpy"),
           'init 999 python:\n    config.label_overrides["splashscreen"] = "x"\n')
        s = compat.survey(g)
        check("a rival splash override is found",
              s["splash"]["overridden_by"] == ["zzz_skip_splash.rpy"],
              s["splash"])
        check("a rival override warns", s["verdict"] == "warn", s["verdict"])

        # --- splashscreen present --------------------------------------------
        print("splashscreen")
        g = make(p("splash"), rpy=("script.rpy",))
        _w(os.path.join(g, "game", "script.rpy"),
           "label splashscreen:\n    scene black\n    return\n")
        s = compat.survey(g)
        check("a real splashscreen label is found", s["splash"]["found"],
              s["splash"])
        check("its file is named", s["splash"]["where"] == "script.rpy",
              s["splash"])

        # A game defining splashscreen is normal and must not read as a rival
        # override - find_intro_conflicts deliberately ignores that shape.
        check("the game's own splashscreen is not called a conflict",
              s["splash"]["overridden_by"] == [] and s["verdict"] == "ok",
              (s["splash"], s["reasons"]))

        g = make(p("nosplash"), rpy=("story.rpy",))
        s = compat.survey(g)
        check("no splashscreen is only a note, not a warning",
              s["verdict"] == "ok"
              and any("splashscreen" in r for r in s["reasons"]),
              (s["verdict"], s["reasons"]))

        # --- refusals ---------------------------------------------------------
        print("refusals")
        g = p("empty")
        os.makedirs(g, exist_ok=True)
        s = compat.survey(g)
        check("no game/ is 不适用", s["label"] == "不适用", s["label"])
        check("no game/ is bad", s["verdict"] == "bad" and not s["ok"],
              s["verdict"])

        g = make(p("notrenpy"), renpy_dir=False)
        shutil.rmtree(os.path.join(g, "lib"))
        s = compat.survey(g)
        check("game/ with no renpy/ and no lib/ is 不适用",
              s["label"] == "不适用", s["label"])

        s = compat.survey(None)
        check("a None game_dir does not raise", s["verdict"] == "bad", s)

        # --- summary is printable --------------------------------------------
        s = compat.survey(make(p("summary"), rpy=("a.rpy",)))
        line = compat.summary(s)
        check("summary is a single line", "\n" not in line, line)
        check("summary names the verdict", s["label"] in line, line)

        # --- the real games, when asked --------------------------------------
        if "--real" in sys.argv:
            print("real games (%s)" % REAL_GAMES)
            if not os.path.isdir(REAL_GAMES):
                check("the real games folder exists", False, REAL_GAMES)
            else:
                seen = 0
                for name in sorted(os.listdir(REAL_GAMES)):
                    gd = os.path.join(REAL_GAMES, name)
                    if not os.path.isdir(gd):
                        continue
                    seen += 1
                    s = compat.survey(gd)
                    print("       %-38s %s" % (name[:38], compat.summary(s)))
                    for r in s["reasons"]:
                        print("           - %s" % r)
                    check("survey survives %s" % name[:30],
                          s["verdict"] in ("ok", "warn", "bad"), s["verdict"])
                    check("%s is recognised as Ren'Py" % name[:30],
                          s["verdict"] != "bad", s["reasons"])
                check("the folder held games to sweep", seen > 0, seen)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print("FAILED %d:" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
