from pathlib import Path
import sys
import types
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import renpy_compat


def fixture(tmp_path):
    def write(rel, content):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    write("renpy/config.py", "label_overrides = {}\n")
    write("renpy/common/00start.rpy", 'renpy.jump("start")\n')
    write("game/screens.rpy", 'screen main_menu():\n    textbutton "NEW GAME" action Start("chapter_picker")\n')
    write("game/script.rpy", "label chapter_picker:\n    return\n")
    return write


def execute(text, labels, overrides=None):
    config = types.SimpleNamespace(label_overrides=dict(overrides or {}))
    renpy = types.SimpleNamespace(has_label=lambda name: name in labels or name in config.label_overrides)
    block = text.split("init 999 python:\n", 1)[1]
    import textwrap
    exec(compile(textwrap.dedent(block), "<runtime_compat>", "exec"), {"config": config, "renpy": renpy})
    return config.label_overrides


def test_verified_custom_entry_and_runtime_guards(tmp_path):
    fixture(tmp_path)
    assert renpy_compat.survey(tmp_path)["target"] == "chapter_picker"
    text = renpy_compat.render(tmp_path)
    assert execute(text, {"chapter_picker"}) == {"start": "chapter_picker"}
    assert execute(text, {"start", "chapter_picker"}) == {}
    assert execute(text, {"chapter_picker"}, {"start": "foreign"}) == {"start": "foreign"}
    assert execute(text, set()) == {}
    # An in-memory mutation removing the missing-start guard must be caught.
    broken = text.replace('not renpy.has_label("start") and', 'True and')
    assert execute(broken, {"start", "chapter_picker"}) != {}


@pytest.mark.parametrize("rel,content", [
    ("game/extra.rpy", "label start:\n    return\n"),
    ("game/unknown.rpyc", "opaque"),
    ("game/scripts.rpa", "opaque"),
    ("game/script.rpy", "label different:\n    return\n"),
    ("game/screens.rpy", 'screen main_menu():\n    textbutton "A" action Start(variable)\n'),
    ("game/screens.rpy", 'screen main_menu():\n    textbutton "A" action Start("chapter_picker")\n    textbutton "B" action Start("other")\n'),
    ("renpy/config.py", "other = {}\n"),
])
def test_unsafe_or_unnecessary_fallback_refused(tmp_path, rel, content):
    write = fixture(tmp_path)
    write(rel, content)
    assert not renpy_compat.survey(tmp_path)["supported"]
    with pytest.raises(ValueError):
        renpy_compat.render(tmp_path)


def test_luna_error_is_diagnosed_without_fake_remedy(tmp_path):
    write = fixture(tmp_path)
    write("game/script.rpy", "label start:\n    return\n")
    write("traceback.txt", "The displayable with id 'what' was not given the exact contents of the what variable given to the say screen.")
    found = renpy_compat.survey(tmp_path)
    assert not found["supported"]
    assert found["diagnostics"] == ["luna_text_mismatch"]
    assert "developer" not in renpy_compat.render.__code__.co_names


def test_installed_patch_does_not_change_static_result(tmp_path):
    write = fixture(tmp_path)
    before = renpy_compat.survey(tmp_path)
    write("game/" + renpy_compat.REL, renpy_compat.render(tmp_path))
    write("game/" + renpy_compat.REL + "c", "compiled")
    assert renpy_compat.survey(tmp_path) == before


def luna_engine(monkeypatch, embed_split=1):
    import re
    engine = types.ModuleType("renpy")
    state = {"slow": None, "calls": []}
    class Text:
        def __init__(self, text):
            self.text = [text]
        def render(self):
            return self.text[0]
    class DTT:
        def __init__(self, text):
            self.text = text
            parts = text.split("{w}")
            self.pause_start = [0, len(parts[0])] if len(parts) > 1 else [0]
            self.pause_end = [len(parts[0]), len(text)] if len(parts) > 1 else [len(text)]
    original_init = Text.__init__
    namespace = {"original_Text_init_hook": original_init}
    def host(text, split):
        state["calls"].append((text, split))
        return text.replace("Probe", "MuchLongerTranslatedProbe")
    namespace.update(callLunaHost=host, callLunaIsUsingEmbed=lambda split: split == embed_split)
    exec('def new_init(self, text):\n    translated = callLunaHost(text, 1) if callLunaIsUsingEmbed(1) else text\n    original_Text_init_hook(self, translated)\n', namespace)
    Text.__init__ = namespace["new_init"]
    def display_say(who, what, *args, **kwargs):
        dtt = kwargs.get("dtt") or DTT(what)
        widget = Text(dtt.text)
        if widget.text[0] != dtt.text:
            raise RuntimeError("exact contents mismatch")
        state["slow"] = (dtt.pause_start, dtt.pause_end, widget.text[0])
        assert namespace["callLunaHost"]("Unrelated UI", 1) == "Unrelated UI"
        return widget
    engine.character = types.SimpleNamespace(display_say=display_say, DialogueTextTags=DTT)
    engine.text = types.SimpleNamespace(text=types.SimpleNamespace(Text=Text))
    monkeypatch.setitem(sys.modules, "renpy", engine)
    return engine, namespace, host, state


def test_mock_luna_bad_baseline_then_bridge_preserves_slow_ranges(monkeypatch):
    engine, namespace, host, state = luna_engine(monkeypatch)
    with pytest.raises(RuntimeError, match="exact contents"):
        engine.character.display_say(None, "Probe{w}end")
    exec(compile(renpy_compat.LUNA_BODY, "<bridge>", "exec"), {})
    old_dtt = engine.character.DialogueTextTags("Probe{w}end")
    widget = engine.character.display_say(None, "Probe{w}end", dtt=old_dtt)
    assert widget.text[0] == "MuchLongerTranslatedProbe{w}end"
    assert state["slow"][0] == [0, len("MuchLongerTranslatedProbe")]
    assert state["slow"][1][-1] == len(widget.text[0])
    assert namespace["callLunaHost"] is host
    assert ("Unrelated UI", 1) in state["calls"]


def test_bridge_restores_host_on_real_exception(monkeypatch):
    engine, namespace, host, _ = luna_engine(monkeypatch)
    def failure(*args, **kwargs):
        raise RuntimeError("unrelated failure")
    engine.character.display_say = failure
    exec(compile(renpy_compat.LUNA_BODY, "<bridge>", "exec"), {})
    with pytest.raises(RuntimeError, match="unrelated failure"):
        engine.character.display_say(None, "Probe")
    assert namespace["callLunaHost"] is host


def test_render_split_moves_translation_upstream(monkeypatch):
    engine, namespace, host, state = luna_engine(monkeypatch, embed_split=2)
    exec(compile(renpy_compat.LUNA_BODY, "<bridge>", "exec"), {})
    assert engine.character.display_say(None, "Probe").text == ["MuchLongerTranslatedProbe"]
    assert ("Probe", 2) in state["calls"]
    assert namespace["callLunaHost"] is host


def test_bridge_late_attach_and_idempotency(monkeypatch):
    engine, namespace, host, _ = luna_engine(monkeypatch)
    hooked = engine.text.text.Text.__init__
    engine.text.text.Text.__init__ = namespace["original_Text_init_hook"]
    scope = {}
    exec(compile(renpy_compat.LUNA_BODY, "<bridge>", "exec"), scope)
    first = engine.character.display_say
    exec(compile(renpy_compat.LUNA_BODY, "<bridge>", "exec"), scope)
    assert engine.character.display_say is first
    assert first(None, "Probe").text == ["Probe"]
    engine.text.text.Text.__init__ = hooked
    assert first(None, "Probe").text == ["MuchLongerTranslatedProbe"]


def test_changed_control_tags_not_rewritten(monkeypatch):
    engine, namespace, _, _ = luna_engine(monkeypatch)
    namespace["callLunaHost"] = lambda text, split: "translation without pause"
    exec(compile(renpy_compat.LUNA_BODY, "<bridge>", "exec"), {})
    with pytest.raises(RuntimeError, match="exact contents"):
        engine.character.display_say(None, "Probe{w}end")


def test_bad_bridge_without_dtt_recompute_is_detected(monkeypatch):
    engine, namespace, host, _ = luna_engine(monkeypatch)
    broken = renpy_compat.LUNA_BODY.replace('kwargs["dtt"] = dtt', 'pass # mutation: stale pause schedule')
    exec(compile(broken, "<mutated-bridge>", "exec"), {})
    with pytest.raises(RuntimeError, match="exact contents"):
        engine.character.display_say(None, "Probe{w}end", dtt=engine.character.DialogueTextTags("Probe{w}end"))
    assert namespace["callLunaHost"] is host


def test_verified_luna_api_does_not_require_historical_log(tmp_path, monkeypatch):
    write = fixture(tmp_path)
    write("game/script.rpy", "label start:\n    return\n")
    write("renpy/character.py", "def display_say(\nclass DialogueTextTags\ndtt = DialogueTextTags(what)\nif what_text.text[0] == what_string:\nelif renpy.config.developer:\n")
    write("renpy/text/text.py", "def set_text(\n")
    import hashlib
    pair = tuple(hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest()
                 for rel in ("renpy/character.py", "renpy/text/text.py"))
    monkeypatch.setattr(renpy_compat, "REVIEWED_LUNA_ENGINES", {pair})
    assert renpy_compat.survey(tmp_path)["mechanism"] == "luna_say_bridge"
    assert "def bridge(" in renpy_compat.render(tmp_path)
    write("renpy/text/text.py", "def set_text(\n# unreviewed semantic change\n")
    assert not renpy_compat.survey(tmp_path)["supported"]
