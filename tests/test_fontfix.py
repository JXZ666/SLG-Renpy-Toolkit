"""Exercise the generated zz_localization.rpy logic without booting Ren'Py.

The shim's two-pass build exists for one reason: FontGroup.add() raises
"FontGroup do not accept font aliases." when the face it is handed is already
registered in config.font_name_map. Getting the order wrong only shows up as a
game that will not start, which is an expensive way to find out, so the stub
below copies that refusal verbatim from renpy/text/font.py:870 along with the
required `end` positional at :835.

Run:  python tests/test_fontfix.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import cmd_fontfix  # noqa: E402


class StubConfig(object):
    def __init__(self):
        self.font_name_map = {}
        self.language = None


class StubFontGroup(object):
    """Mirrors renpy.text.font.FontGroup closely enough to catch ordering bugs."""

    def __init__(self):
        self.map = {}

    def add(self, font, start, end, target=None, target_increment=False):
        if font in _CONFIG.font_name_map:
            raise Exception("FontGroup do not accept font aliases.")
        if start is None:
            if None not in self.map:
                self.map[None] = font
            return self
        if end is None:
            raise TypeError("add() missing 1 required positional argument: 'end'")
        for i in range(start, end + 1):
            if i not in self.map:
                self.map[i] = font
        return self


_CONFIG = StubConfig()


def run_shim(text):
    """Exec the `init 999 python:` body under the stubs."""
    body = []
    inside = False
    for line in text.splitlines():
        if line.startswith("init 999 python:"):
            inside = True
            continue
        if inside:
            if not line.strip():
                body.append("")
            elif line.startswith("    "):
                body.append(line[4:])
            else:
                break
    ns = {"FontGroup": StubFontGroup, "config": _CONFIG}
    exec(compile("\n".join(body), "<shim>", "exec"), ns)
    return ns


def resolve(group, ch):
    """How FontGroup.segment() picks a face for one character.

    An explicit range wins; anything unclaimed falls to the default entry
    registered by add(font, None, None). Asserting on map[n] directly would
    miss that, since Latin is only in the map when a range was delegated.
    """
    return group.map.get(ord(ch)) or group.map.get(None)


def build(decisions, mode="luna", lang="chinesesimplified"):
    lang_block = ""
    if mode == "full":
        import string
        lang_block = string.Template(cmd_fontfix.LANGUAGE_BLOCK).substitute(lang=lang)
    return cmd_fontfix.SHIM.substitute(
        stamp="test", game_dir="<test>", mode=mode,
        cjk_path=cmd_fontfix.GAME_FONT_REL,
        faces=cmd_fontfix._faces_block(decisions),
        language_block=lang_block,
        table_comment=cmd_fontfix._table_comment(decisions))


def main():
    failures = []

    def check(label, cond, detail=""):
        if cond:
            print("  ok   %s" % label)
        else:
            print("  FAIL %s %s" % (label, detail))
            failures.append(label)

    decisions = [
        {"names": ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"], "action": "keep-latin",
         "cjk": 0, "latin": "DejaVuSans.ttf", "lo": 0x0000, "hi": 0x2E7F,
         "why": "Latin complete", "where": "renpy-common"},
        {"names": ["tycho.ttf", "tycho"], "action": "noto-only", "cjk": 0,
         "why": "Latin coverage incomplete", "where": "loose"},
        {"names": ["SourceHanSansSC-Bold.otf"], "action": "skip", "cjk": 20976,
         "why": "already covers Hanzi", "where": "loose"},
    ]

    print("luna mode")
    _CONFIG.font_name_map.clear()
    text = build(decisions)
    check("self-check clean", not cmd_fontfix.validate_shim(text),
          cmd_fontfix.validate_shim(text))
    run_shim(text)
    fmap = _CONFIG.font_name_map
    check("aliases DejaVuSans.ttf", "DejaVuSans.ttf" in fmap)
    check("aliases the extension-less stem", "tycho" in fmap)
    check("skips a face that already covers Hanzi", "SourceHanSansSC-Bold.otf" not in fmap)
    check("does not force a language", _CONFIG.language is None, _CONFIG.language)

    # The whole point of the two-pass build: two names delegating to one face.
    g = fmap["DejaVuSans.ttf"]
    check("shares one group between the two DejaVu names",
          fmap["DejaVuSans-Bold.ttf"] is g)
    check("delegates Latin to the original face", resolve(g, "A") == "DejaVuSans.ttf",
          resolve(g, "A"))
    check("routes Hanzi to the CJK font", resolve(g, "你") == cmd_fontfix.GAME_FONT_REL,
          resolve(g, "你"))
    check("has a default for unclaimed codepoints",
          g.map.get(None) == cmd_fontfix.GAME_FONT_REL, g.map.get(None))

    t = fmap["tycho.ttf"]
    check("tycho gets no Latin delegation", resolve(t, "A") == cmd_fontfix.GAME_FONT_REL,
          resolve(t, "A"))
    check("the stem and the full name share one group", fmap["tycho"] is t)
    check("only one group per distinct delegation config",
          len({id(v) for v in fmap.values()}) == 2,
          len({id(v) for v in fmap.values()}))

    print("full mode")
    _CONFIG.font_name_map.clear()
    run_shim(build(decisions, mode="full", lang="chinesesimplified"))
    check("forces the language", _CONFIG.language == "chinesesimplified", _CONFIG.language)

    print("a game that already aliased a name we alias")
    _CONFIG.font_name_map.clear()
    _CONFIG.font_name_map["DejaVuSans.ttf"] = "already-here"
    text = build(decisions)
    run_shim(text)
    fmap = _CONFIG.font_name_map
    check("does not crash on the pre-aliased name", "DejaVuSans-Bold.ttf" in fmap)
    check("falls back to Noto-only for it",
          resolve(fmap["DejaVuSans-Bold.ttf"], "A") == cmd_fontfix.GAME_FONT_REL,
          resolve(fmap["DejaVuSans-Bold.ttf"], "A"))
    check("still routes Hanzi correctly",
          resolve(fmap["tycho.ttf"], "你") == cmd_fontfix.GAME_FONT_REL)

    print("a two-argument add would be rejected")
    bad = text.replace("group.add(_loc_cjk, None, None)", "group.add(_loc_cjk, None)")
    check("validate_shim catches it",
          any("2 argument" in p for p in cmd_fontfix.validate_shim(bad)),
          cmd_fontfix.validate_shim(bad))

    print()
    if failures:
        print("FAILED: %d" % len(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
