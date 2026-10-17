"""Gallery qualification, actual lock behavior, and negative mutation checks."""
import hashlib
import os
from pathlib import Path
import sys
import textwrap
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import renpy_gallery as gallery


@pytest.fixture
def standard(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    engine = tmp_path / "renpy/common/00gallery.rpy"
    engine.parent.mkdir(parents=True)
    engine.write_text("reviewed test engine")
    monkeypatch.setattr(gallery, "_ENGINES", {hashlib.sha256(engine.read_bytes()).hexdigest()})
    replay_engine = engine.with_name("00action_other.rpy")
    replay_engine.write_text("reviewed replay test engine")
    monkeypatch.setattr(gallery, "_REVIEWED_REPLAY_ENGINE", hashlib.sha256(replay_engine.read_bytes()).hexdigest())
    (game / "one.png").write_bytes(b"fixture image")
    (game / "gallery.rpy").write_text('''image one = "one.png"
init python:
    g = Gallery()
    g.button("first")
    g.unlock_image("one")
    g.condition("persistent.flag")
    g.allprior()
screen gallery():
    add g.make_button("first", "one.png")
''')
    return tmp_path


def _exec_init(patch, store, renpy, monkeypatch):
    module = types.ModuleType("renpy")
    module.store = store
    monkeypatch.setitem(sys.modules, "renpy", module)
    monkeypatch.setitem(sys.modules, "renpy.store", store)
    namespace = {"renpy": renpy, "NullAction": lambda: None,
                 "config": types.SimpleNamespace(after_load_callbacks=[])}
    body = patch.split("init 999 python:\n", 1)[1].split("\nscreen ", 1)[0]
    exec(compile(textwrap.dedent(body), "<gallery-generated-init>", "exec"), namespace)
    return namespace


def test_standard_qualifies_and_render_is_deterministic(standard):
    report = gallery.survey(standard)
    assert report["supported"] and report["mechanism"] == "standard_gallery"
    assert report["coverage"]["gallery_images"]
    assert not report["coverage"]["replay"]
    assert gallery.render(standard) == gallery.render(standard)
    assert gallery.MARKER in gallery.render(standard)


@pytest.mark.parametrize("replacement", [
    '    g.unlock_image(variable)',
    '    g.unlock_image("missing.png")',
    '    g.buttons["first"].conditions = []',
    '    Replay("first")',
])
def test_standard_rejects_unverified_mechanisms(standard, replacement):
    source = standard / "game/gallery.rpy"
    source.write_text(source.read_text().replace('    g.unlock_image("one")', replacement))
    assert not gallery.survey(standard)["supported"]
    with pytest.raises(ValueError):
        gallery.render(standard)


def test_extra_screen_lock_is_not_mistaken_for_gallery_condition(standard):
    source = standard / "game/gallery.rpy"
    source.write_text(source.read_text().replace('    add g.make_button', '    if persistent.other:\n        add g.make_button'))
    assert not gallery.survey(standard)["supported"]


def test_unknown_compiled_source_is_never_loaded(standard):
    (standard / "game/unknown.rpyc").write_bytes(b"not a pickle")
    report = gallery.survey(standard)
    assert not report["supported"]
    assert "Compiled" in report["reasons"][0]


def test_unknown_engine_is_not_assumed_compatible(standard):
    (standard / "renpy/common/00gallery.rpy").write_text("changed engine")
    assert not gallery.survey(standard)["supported"]


def _assert_standard_qualifications(namespace, store):
    node = store.g.buttons["first"]
    assert not node.conditions
    assert all(not image.conditions for image in node.images)
    assert not namespace["renpy"].seen_image("one")


def test_all_standard_lock_types_are_cleared_locally(standard, monkeypatch):
    # All three condition types are represented at both button/image levels.
    image = types.SimpleNamespace(conditions=["seen-image", "arbitrary", "all-prior"])
    button = types.SimpleNamespace(conditions=["arbitrary"], images=[image])
    store = types.ModuleType("renpy.store")
    store.g = types.SimpleNamespace(buttons={"first": button})
    persistent = {"flag": False, "seen": set()}
    renpy = types.SimpleNamespace(seen_image=lambda image: False, persistent=persistent)
    ns = _exec_init(gallery.render(standard), store, renpy, monkeypatch)
    _assert_standard_qualifications(ns, store)
    assert persistent == {"flag": False, "seen": set()}


def test_mutation_that_only_unlocks_buttons_is_detected(standard, monkeypatch):
    store = types.ModuleType("renpy.store")
    store.g = types.SimpleNamespace(buttons={"first": types.SimpleNamespace(
        conditions=[False], images=[types.SimpleNamespace(conditions=[False])])})
    broken = gallery.render(standard).replace("image.conditions = []", "pass")
    ns = _exec_init(broken, store, types.SimpleNamespace(seen_image=lambda _: False), monkeypatch)
    with pytest.raises(AssertionError):
        _assert_standard_qualifications(ns, store)


@pytest.fixture
def sample_b(tmp_path, monkeypatch):
    # Minimal authored fixture mirrors the observed mechanism, never copies
    # commercial story text. The reviewed hash is patched for this fixture.
    game = tmp_path / "game"
    game.mkdir()
    engine = tmp_path / "renpy/common/00gallery.rpy"
    engine.parent.mkdir(parents=True)
    engine.write_text("reviewed test engine")
    monkeypatch.setattr(gallery, "_ENGINES", {hashlib.sha256(engine.read_bytes()).hexdigest()})
    replay_engine = engine.with_name("00action_other.rpy")
    replay_engine.write_text("reviewed replay test engine")
    monkeypatch.setattr(gallery, "_REVIEWED_REPLAY_ENGINE", hashlib.sha256(replay_engine.read_bytes()).hexdigest())
    (game / "replay_setup.rpy").write_text('''init python:
    Replay_items.append(ReplayItem(["thumb"], "sample", "Sample"))
image thumb = "thumb.png"
''')
    (game / "script.rpy").write_text('''default points = 0
default player = persistent.player
label sample:
    $ renpy.end_replay()
''')
    (game / "thumb.png").write_bytes(b"fixture image")
    monkeypatch.setattr(gallery, "_SAMPLE_B_FINGERPRINT", gallery._fingerprint(game))
    return tmp_path


def test_sample_b_partial_reports_missing_images_and_real_scope(sample_b):
    report = gallery.survey(sample_b)
    assert report["supported"] and report["mechanism"] == "reviewed_replay"
    assert report["coverage"]["level"] == "partial"
    assert report["coverage"]["replay_count"] == 1
    assert report["coverage"]["scope"] == ["points", "player"]
    assert not report["coverage"]["gallery_images"]
    assert "missing placeholder" in report["reasons"][0]
    patch = gallery.render(sample_b)
    assert "refresh_lock" not in patch
    assert "seen_label" not in patch and "mark_label_seen" not in patch
    assert "screen gallery_B" not in patch


@pytest.mark.parametrize("changed", ["script.rpy", "replay_setup.rpy"])
def test_sample_b_version_change_invalidates_adapter(sample_b, changed):
    source = sample_b / "game" / changed
    source.write_text(source.read_text() + "\n# changed game version\n")
    assert not gallery.survey(sample_b)["supported"]


def test_missing_sample_b_thumbnail_disables_replay(sample_b):
    (sample_b / "game/thumb.png").unlink()
    assert not gallery.survey(sample_b)["supported"]


def test_standard_load_callback_reapplies_to_replaced_objects(standard, monkeypatch):
    store = types.ModuleType("renpy.store")
    store.g = types.SimpleNamespace(buttons={})
    ns = _exec_init(gallery.render(standard), store, types.SimpleNamespace(), monkeypatch)
    restored_image = types.SimpleNamespace(conditions=[False])
    restored_button = types.SimpleNamespace(conditions=[False], images=[restored_image])
    store.g = types.SimpleNamespace(buttons={"loaded": restored_button})
    ns["config"].after_load_callbacks[0]()
    assert not restored_button.conditions and not restored_image.conditions


def test_actual_reviewed_engine_qualifications(monkeypatch):
    fixture = os.environ.get("RPYKIT_GALLERY_GAME")
    if not fixture:
        pytest.skip("Set RPYKIT_GALLERY_GAME to opt in to reviewed local engine tests")
    root = Path(fixture)
    if not root.exists():
        pytest.skip("Optional reviewed engine source fixture is not installed")
    common = root / "renpy/common"
    gallery_text = (common / "00gallery.rpy").read_text(encoding="utf-8")
    replay_text = (common / "00action_other.rpy").read_text(encoding="utf-8")
    assert hashlib.sha256((common / "00gallery.rpy").read_bytes()).hexdigest() in gallery._ENGINES
    assert hashlib.sha256((common / "00action_other.rpy").read_bytes()).hexdigest() == gallery._REVIEWED_REPLAY_ENGINE
    # Execute only reviewed engine class definitions with inert APIs. No game
    # source, assets, persistent files, or compiled scripts are executed.
    body = gallery_text.split("init -1500 python:\n", 1)[1].split("    @renpy.pure", 1)[0]
    renpy = types.SimpleNamespace(seen_image=lambda _: False, seen_label=lambda _: False,
                                 split_properties=lambda *args: [{}])
    engine_ns = {"renpy": renpy}
    exec(compile(textwrap.dedent(body), "<reviewed-gallery-engine>", "exec"), engine_ns)
    g = types.SimpleNamespace(buttons={})
    button = engine_ns["__GalleryButton"](g, 0)
    image = engine_ns["__GalleryImage"](g, ["one"])
    image.conditions = [engine_ns["__GalleryUnlockCondition"](["one"]),
                        engine_ns["__GalleryArbitraryCondition"]("False"),
                        engine_ns["__GalleryAllPriorCondition"]()]
    button.images = [image]
    button.conditions = [engine_ns["__GalleryArbitraryCondition"]("False")]
    g.buttons["one"] = button
    assert not button.check_unlock() and not image.check_unlock(False)
    store = types.ModuleType("renpy.store")
    store.g = g
    ns = _exec_init(gallery._STANDARD.replace("OBJECTS", "['g']"), store, renpy, monkeypatch)
    assert button.check_unlock() and image.check_unlock(False)
    assert not renpy.seen_image("one")
    replay_class = replay_text.split("    class Replay(Action, DictEquality):", 1)[1].split("    @renpy.pure", 1)[0]
    class BaseAction:
        pass
    class BaseEquality:
        pass
    calls = []
    engine_ns = {"renpy": types.SimpleNamespace(seen_label=lambda _: False,
                 call_replay=lambda label, scope: calls.append((label, scope))),
                 "config": types.SimpleNamespace(enter_replay_transition=None, exit_replay_transition=None),
                 "Action": BaseAction, "DictEquality": BaseEquality}
    exec(compile(textwrap.dedent("    class Replay(Action, DictEquality):" + replay_class),
                 "<reviewed-replay-engine>", "exec"), engine_ns)
    Replay = engine_ns["Replay"]
    assert not Replay("sample").get_sensitive()
    action = Replay("sample", scope={"points": 0}, locked=False)
    assert action.get_sensitive()
    action()
    assert calls == [("sample", {"points": 0})]


def _assert_replay_can_start(namespace, store):
    namespace["_rpykit_replay_action"](types.SimpleNamespace(replay="sample"))()
    assert store.started == [("sample", {"points": 0, "player": "User"})]


def test_sample_b_action_really_starts_unseen_replay_without_persistent_changes(sample_b, monkeypatch):
    store = types.ModuleType("renpy.store")
    store.points, store.player, store.started = 0, "User", []
    persistent = {"seen": set(), "player": "User"}
    class Replay:
        def __init__(self, label, scope=None, locked=None):
            self.label, self.scope, self.locked = label, scope, locked
        def __call__(self):
            if self.locked is False:
                store.started.append((self.label, self.scope))
    renpy = types.SimpleNamespace(has_label=lambda label: label == "sample", persistent=persistent)
    ns = _exec_init(gallery.render(sample_b), store, renpy, monkeypatch)
    ns["Replay"] = Replay
    _assert_replay_can_start(ns, store)
    assert persistent == {"seen": set(), "player": "User"}
    assert ns["_rpykit_replay_action"](types.SimpleNamespace(replay="absent")) is None
    # In-memory negative mutation reproduces 'button looks unlocked but action
    # still follows unseen-label qualification'.
    store.started.clear()
    broken = gallery.render(sample_b).replace("locked=False", "locked=None")
    ns = _exec_init(broken, store, renpy, monkeypatch)
    ns["Replay"] = Replay
    with pytest.raises(AssertionError):
        _assert_replay_can_start(ns, store)
