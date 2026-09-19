"""What this tool can install, and which of it the user asked for.

The catalogue is deliberately dumb data. It exists so that the window can draw
one row per feature without knowing what any of them do, which is the whole
point of the split: the tool stopped being "the font installer that also skips
logos" the moment a second feature arrived, and a third must not mean editing
the layout, the argument parser and the runner again.

This module therefore imports nothing from the rest of the tool, and the
implementations live in cmd_fontfix next to the code they already share. The
direction is one-way on purpose: cmd_fontfix reads selections from here, and
nothing here reaches back - a cycle between the two would make the import order
of a frozen build matter, which is not a class of bug worth inviting.
"""

# Order is the order the window lists them in and the order run() applies them.
#
# `state` names the three booleans cmd_fontfix reports for this feature inside
# installed_state(): whether anything is there, whether it is provably this
# tool's, and whether it is the template this build writes. The window reads
# them through their names and never through a feature id, which is what lets a
# third feature appear with no edit to the layout.
CATALOG = [
    {
        "id": "fontfix",
        "title": "汉化预飞（字体）",
        # Broken by hand: Tk only wraps at a space or inside a single run that
        # overflows on its own, so a CJK sentence followed by a Latin word wraps
        # after the first word and leaves the rest of the line empty.
        "desc": "把游戏用到的每个字体名指向一个 FontGroup：拉丁字母继续用游戏自己的字体，\n"
                "中文交给随包安装的 Noto。这是给运行时注入中文（露娜等）打底的一步，\n"
                "不翻译任何文本。",
        "default_on": True,
        "state": {"installed": "shim", "ours": "ours", "current": "current"},
    },
    {
        "id": "intro",
        "title": "跳过开场 logo",
        "desc": "把游戏的 splashscreen 标签指向一个空实现，开局直接进主菜单，\n"
                "不必每次启动都看一遍厂商 logo。会先备份游戏里原有的同名覆盖文件，\n"
                "撤销时原样放回。",
        "default_on": True,
        "state": {"installed": "intro", "ours": "intro_ours",
                  "current": "intro_current"},
    },
]


def ids():
    """Every known feature id, in catalogue order."""
    return [f["id"] for f in CATALOG]


def by_id(fid):
    """The catalogue entry for `fid`, or None."""
    for f in CATALOG:
        if f["id"] == fid:
            return f
    return None


def title_of(fid):
    entry = by_id(fid)
    return entry["title"] if entry else fid


def default_selection():
    """The ids a user gets with nothing explicitly chosen."""
    return [f["id"] for f in CATALOG if f["default_on"]]


def selected(args):
    """Which features this run installs, as ids in catalogue order.

    Two spellings are accepted, and they must not fight. `features` is the
    explicit list the window sends now that there is more than one thing to
    tick. `skip_intro` is the single switch from when there was not, still
    exposed as --no-skip-intro and still asserted by the tests.

    A caller that knows only `skip_intro` gets the projection it has always
    got, which is what keeps the old command line working: fonts, plus the
    intro unless it was turned off. Unknown ids are dropped rather than
    raising - a catalogue entry that a newer window knows about must not brick
    an older exe.
    """
    chosen = getattr(args, "features", None)
    if chosen is None:
        chosen = ["fontfix"]
        if getattr(args, "skip_intro", True):
            chosen.append("intro")
    known = set(ids())
    return [fid for fid in ids() if fid in chosen and fid in known]
