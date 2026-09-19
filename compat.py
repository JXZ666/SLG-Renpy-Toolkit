"""Pre-flight survey: what kind of Ren'Py game is this, and will we cope?

The tool used to decide everything from one fact - `<game>/game` exists - and
that is not enough to answer the question a player actually has, which is "will
this work on MY game". A shipped adult game may be Ren'Py 6, 7 or 8; it may run
on Python 2.7 or 3.12; its story may be loose .rpy, loose .rpyc, or sealed in an
archive this tool cannot read. None of those are visible from the directory
name, and two of them change the right answer.

This module answers it from the folder alone. It never boots the engine, never
imports renpy, and never unpickles a script - every fact here comes from a
filename, a small text file, or an archive header. That is a deliberate ceiling:
a pre-flight that can crash on a broken game is worse than no pre-flight, since
the whole point is to look before anything is written.

`survey()` is the only entry point. It is cheap enough to call every time the
user picks a different folder.
"""

import os
import re

import rpa


def _cf():
    """cmd_fontfix, imported on first use.

    Deferred on purpose: cmd_fontfix imports this module, so importing it back
    at the top would make a cycle whose success depends on which of the two the
    interpreter happened to load first. Reaching for it inside a function keeps
    the direction one-way - cmd_fontfix knows about us, we only borrow four
    helpers from it that already exist (ownership proof, the archive listing,
    the comment stripper, the rival-override scan) rather than restating them
    here and letting the two copies drift.
    """
    import cmd_fontfix
    return cmd_fontfix

# `game/script_version.txt` is the cheapest source: a bare tuple the engine
# writes on every save-compatible build, e.g. "(7, 4, 11)". It is not always
# there (Hikari ships without one), so there are three fallbacks behind it.
#
# The two Ren'Py generations disagree about where the version lives, and both
# shapes are indented, so no pattern here may anchor on column zero:
#   Ren'Py 8  renpy/vc_version.py  -> version = '8.3.0.24082114' + version_name
#   Ren'Py 7  renpy/__init__.py    -> version_tuple = (7, 4, 11, vc_version)
#   Ren'Py 7  renpy/vc_version.py  -> vc_version = 2266   (an SVN revision)
_RE_SCRIPT_VERSION = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
_RE_VERSION_TUPLE = re.compile(r"^[ \t]*version_tuple\s*=\s*\(([^)]*)\)", re.M)
_RE_VC_VERSION_STR = re.compile(r"""^[ \t]*version\s*=\s*["']([^"']+)["']""", re.M)
_RE_VERSION_NAME = re.compile(r"""^[ \t]*version_name\s*=\s*["']([^"']+)["']""", re.M)
_RE_SVN_REVISION = re.compile(r"^[ \t]*vc_version\s*=\s*(\d+)", re.M)

# The game's own opening-logo label. find_intro_conflicts deliberately ignores
# this shape (a game defining splashscreen is normal, not a rival add-on), so
# the question "is there anything to skip at all" needs its own pattern.
_RE_SPLASH_LABEL = re.compile(r"^[ \t]*label[ \t]+splashscreen[ \t]*:", re.M)

# lib/ naming is not one convention. A Ren'Py 7 game ships lib/python2.7 and
# lib/windows-i686; a Ren'Py 8 game ships lib/python3.9 and lib/py3-windows-x86_64.
_RE_PY2 = re.compile(r"^(?:python2|py2-)", re.I)
_RE_PY3 = re.compile(r"^(?:python3|py3-)", re.I)

MAX_HEAD_BYTES = 200 * 1024


def _read_head(path, limit=MAX_HEAD_BYTES):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _version(game_dir):
    """(version, major, source, name) - from the cheapest file that has one."""
    text = _read_head(os.path.join(game_dir, "game", "script_version.txt"), 4096)
    m = _RE_SCRIPT_VERSION.search(text)
    if m:
        parts = [int(g) for g in m.groups()]
        return ".".join(str(p) for p in parts), parts[0], "game/script_version.txt", None

    vc = _read_head(os.path.join(game_dir, "renpy", "vc_version.py"), 8192)
    name = _RE_VERSION_NAME.search(vc)
    name = name.group(1) if name else None
    m = _RE_VC_VERSION_STR.search(vc)
    if m:
        # Ren'Py 8 spells it 8.3.0.24082114 - the trailing component is a build
        # stamp, so the three-part prefix is the part worth showing.
        nums = [p for p in m.group(1).split(".") if p.isdigit()]
        if len(nums) >= 3:
            major = int(nums[0])
            return ".".join(nums[:3]), major, "renpy/vc_version.py", name

    text = _read_head(os.path.join(game_dir, "renpy", "__init__.py"))
    m = _RE_VERSION_TUPLE.search(text)
    if m:
        nums = [p.strip() for p in m.group(1).split(",") if p.strip().isdigit()]
        if nums:
            if not name:
                got = _RE_VERSION_NAME.search(text)
                name = got.group(1) if got else None
            return ".".join(nums[:3]), int(nums[0]), "renpy/__init__.py", name

    m = _RE_SVN_REVISION.search(vc)
    if m:
        # An SVN revision is not a version, but it proves which tree this is,
        # and the caller can see that nothing better was found.
        return "vc%s" % m.group(1), None, "renpy/vc_version.py", name
    return None, None, None, None


def _lib(game_dir):
    """(python major, runtime dir, arch) read off the lib/ directory names."""
    lib_dir = os.path.join(game_dir, "lib")
    out = {"python": None, "runtime": None, "arch": None, "names": []}
    if not os.path.isdir(lib_dir):
        return out
    try:
        names = sorted(os.listdir(lib_dir))
    except OSError:
        return out
    out["names"] = names

    arches = set()
    for name in names:
        low = name.lower()
        # Python 2 wins ties: if a distribution somehow ships both, the older
        # runtime is the one worth warning about.
        if _RE_PY2.match(name):
            out["python"], out["runtime"] = 2, name
        elif _RE_PY3.match(name) and out["python"] != 2:
            out["python"], out["runtime"] = 3, name
        if "windows" in low:
            for arch in ("i686", "x86_64"):
                if low.endswith(arch):
                    arches.add(arch)
    if len(arches) > 1:
        out["arch"] = "both"
    elif arches:
        out["arch"] = arches.pop()
    return out


def _sources(game_dir, quick):
    """What the game's code looks like on disk, and whether we can read it."""
    cf = _cf()
    gdir = os.path.join(game_dir, "game")
    out = {"loose_rpy": 0, "loose_rpyc": 0, "tool_files": [], "rpa": [],
           "unsupported_rpa": [], "packed_only": False}
    if not os.path.isdir(gdir):
        return out

    try:
        names = sorted(os.listdir(gdir))
    except OSError:
        return out

    for name in names:
        low = name.lower()
        full = os.path.join(gdir, name)
        if not os.path.isfile(full):
            continue
        if low.endswith(".rpy"):
            # The tool's own shim is a loose .rpy, and counting it would make
            # every already-patched game look like it ships readable sources.
            if cf._is_ours(full):
                out["tool_files"].append(name)
            else:
                out["loose_rpy"] += 1
        elif low.endswith(".rpyc"):
            # Same reasoning for the compiled half: Ren'Py writes a .rpyc beside
            # our shim on first launch, and that is not the game's own code.
            sibling = os.path.join(gdir, name[:-1])
            if os.path.isfile(sibling) and cf._is_ours(sibling):
                continue
            out["loose_rpyc"] += 1

    archives = cf._archive_paths(game_dir)
    out["rpa"] = [os.path.basename(p) for p in archives]
    if not quick:
        # The header alone is enough: it names the format, and a non-3.0 archive
        # is one analyse() will silently see nothing inside.
        for path in archives:
            info = rpa.describe(path)
            if info.get("magic") != rpa.SUPPORTED_MAGIC.decode("ascii"):
                out["unsupported_rpa"].append(os.path.basename(path))

    out["packed_only"] = (out["rpa"] and not out["loose_rpy"]
                          and not out["loose_rpyc"])
    return out


def _splash(game_dir):
    """Whether the game defines `label splashscreen:`, and who else overrides it."""
    cf = _cf()
    gdir = os.path.join(game_dir, "game")
    out = {"found": False, "where": None, "overridden_by": []}
    if not os.path.isdir(gdir):
        return out
    for name in sorted(os.listdir(gdir)):
        if not name.lower().endswith(".rpy"):
            continue
        full = os.path.join(gdir, name)
        if not os.path.isfile(full):
            continue
        code = cf._code_only(_read_head(full, 1024 * 1024))
        if _RE_SPLASH_LABEL.search(code):
            out["found"] = True
            out["where"] = name
            break
    out["overridden_by"] = cf.find_intro_conflicts(game_dir)
    return out


def _collisions(game_dir):
    """Files on the tool's own target paths that the tool did not put there.

    These are the ones that make an install stop and ask for --force. The last
    entry is not a path the tool writes at all: a game can ship its own font
    named NotoSansSC-VF.ttf in game/ root, and overwriting it with a
    byte-different file of the same name is exactly the kind of surprise worth
    naming in advance.
    """
    cf = _cf()
    gdir = os.path.join(game_dir, "game")
    targets = [
        "zz_localization.rpy",
        "zz_rpykit_intro.rpy",
        "NotoSansSC-VF.ttf",
        os.path.join("localization", "NotoSansSC-VF.ttf"),
    ]
    out = []
    for rel in targets:
        full = os.path.join(gdir, rel)
        if os.path.isfile(full) and not cf._is_ours(full):
            out.append("game/" + rel.replace(os.sep, "/"))
    return out


def survey(game_dir, quick=False):
    """Everything the tool knows about a game before it writes anything.

    `verdict` is the whole point: "ok" to install, "warn" to install while
    telling the player what may not work, "bad" to refuse. A warning is never
    fatal - the user can still proceed - so the reasons are written to be read,
    not just counted.
    """
    game_dir = os.path.abspath(game_dir) if game_dir else ""
    gdir = os.path.join(game_dir, "game")
    out = {
        "game_dir": game_dir,
        "ok": False,
        "verdict": "bad",
        "label": "不适用",
        "reasons": [],
        "renpy": {"version": None, "major": None, "source": None, "name": None},
        "python": {"major": None, "runtime": None},
        "arch": None,
        "sources": {},
        "splash": {},
        "collisions": [],
    }
    if not os.path.isdir(gdir):
        out["reasons"].append("没有 game/ 子目录，这不是一个 Ren'Py 游戏根目录。")
        return out

    version, major, source, vname = _version(game_dir)
    out["renpy"] = {"version": version, "major": major, "source": source,
                    "name": vname}
    lib = _lib(game_dir)
    out["python"] = {"major": lib["python"], "runtime": lib["runtime"]}
    out["arch"] = lib["arch"]
    out["sources"] = _sources(game_dir, quick)
    out["splash"] = _splash(game_dir)
    out["collisions"] = _collisions(game_dir)

    if not os.path.isdir(os.path.join(game_dir, "renpy")) and not lib["names"]:
        out["reasons"].append("既没有 renpy/ 也没有 lib/，不像是一个 Ren'Py 发行版。")
        return out

    warns = []
    if lib["python"] == 2:
        warns.append("这是 Python 2.7 的 Ren'Py %s，本工具从未在 py2 上实测过；"
                     "写入的文件应当有效，但无人验证。"
                     % (version or "7"))
    if out["sources"]["unsupported_rpa"]:
        warns.append("归档 %s 不是 RPA-3.0，工具读不到里面的脚本，"
                     "字体别名只能靠猜。"
                     % ", ".join(out["sources"]["unsupported_rpa"]))
    if out["sources"]["packed_only"]:
        # Deliberately says 开场 logo rather than the literal label name: the
        # window wraps these at the current width, and a trailing Latin word
        # gets pushed onto a line of its own by Tk's line-breaking rules.
        warns.append("脚本全部打包在 .rpa 里，工具看不到游戏引用了哪些字体，"
                     "也无法确认游戏是否真的定义了开场 logo。")
    if out["splash"]["overridden_by"]:
        warns.append("已有别的文件在覆盖 splashscreen：%s。"
                     "安装会把它（连同 .rpyc）隔离到工作目录，撤销时放回。"
                     % ", ".join(out["splash"]["overridden_by"]))
    if out["collisions"]:
        warns.append("目标路径上已有非本工具的文件：%s，安装时需要确认覆盖。"
                     % ", ".join(out["collisions"]))

    if warns:
        out["verdict"], out["label"] = "warn", "有风险"
        out["reasons"] = warns
    else:
        out["verdict"], out["label"] = "ok", "可装"
        out["ok"] = True

    # Not a warning: config.label_overrides is consulted by Script.lookup, so
    # the redirect lands whether or not the game defines the label itself. It is
    # still worth saying, because "nothing happened" is the expected outcome.
    if not out["splash"]["found"]:
        out["reasons"].append("在可读的脚本里没找到 `label splashscreen:`——"
                              "跳过开场仍然会被安装，但可能本来就没有 logo 可跳。")
    return out


def summary(s):
    """One console line for a survey, the way run() prints it."""
    v = s["renpy"]["version"] or "unknown"
    py = s["python"]["major"]
    py = "py%s" % py if py else "py?"
    arch = s["arch"] or "?"
    src = s["sources"]
    return ("%s - Ren'Py %s, %s %s, %d rpa / %d loose .rpy / %d loose .rpyc, "
            "splash %s" % (
                s["label"], v, py, arch,
                len(src.get("rpa", [])), src.get("loose_rpy", 0),
                src.get("loose_rpyc", 0),
                "yes" if s["splash"].get("found") else "no"))
