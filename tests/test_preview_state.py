"""Channel configuration separation and optional launcher persistence."""

import copy
import json

import pytest

import app_state


def make_game(tmp_path):
    game = tmp_path / "Game & 中文"
    (game / "game").mkdir(parents=True)
    (game / "renpy").mkdir()
    (game / "bin").mkdir()
    (game / "bin" / "Play.exe").write_bytes(b"not executed")
    return game


def settings_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(app_state.branding, "APP_CHANNEL", "local-test")
    directory = tmp_path / "rpykit"
    directory.mkdir()
    return directory / "ui_state.json", directory / "ui_state.preview.json"


def test_launcher_is_optional_validated_and_deep_copied(tmp_path):
    game = make_game(tmp_path)
    original = app_state.add_game(app_state.default_state(), game)
    assert "launcher_rel" not in original["games"][0]
    chosen = app_state.set_launcher(original, game, game / "bin" / "Play.exe")
    assert chosen["games"][0]["launcher_rel"] == "bin/Play.exe"
    assert "launcher_rel" not in original["games"][0]
    chosen["window"]["width"] = 800
    assert original["window"]["width"] != 800
    cleared = app_state.set_launcher(chosen, game, None)
    assert "launcher_rel" not in cleared["games"][0]
    assert chosen["games"][0]["launcher_rel"] == "bin/Play.exe"
    with pytest.raises(ValueError):
        app_state.set_launcher(original, game, "../Other.exe")
    with pytest.raises(ValueError, match="游戏库"):
        app_state.set_launcher(original, tmp_path / "other", "Play.exe")


def test_missing_exe_reference_is_retained_for_explicit_reselection(tmp_path):
    game = make_game(tmp_path)
    state = app_state.set_launcher(app_state.add_game(app_state.default_state(), game),
                                   game, "bin/Play.exe")
    (game / "bin" / "Play.exe").unlink()
    filename = tmp_path / "state.json"
    app_state.save_state(state, filename)
    loaded = app_state.load_state(filename)
    assert loaded["games"][0]["launcher_rel"] == "bin/Play.exe"
    with pytest.raises(ValueError, match="重新选择"):
        app_state.game_launch.resolve_launcher(game, loaded["games"][0]["launcher_rel"])


def test_schema_two_bookmarks_migrate_without_adding_launcher(tmp_path):
    game = make_game(tmp_path)
    filename = tmp_path / "old.json"
    filename.write_text(json.dumps({"schema": 2, "appearance": "dark",
                                   "window": {"width": 1350, "height": 930},
                                   "games": [{"path": str(game), "name": "Old"}]}),
                        encoding="utf-8")
    loaded = app_state.load_state(filename)
    assert loaded["schema"] == 3
    assert loaded["window"] == {"width": 1350, "height": 930}
    assert loaded["games"] == [{"path": str(game), "name": "Old", "available": True}]


def test_preview_first_load_imports_without_writing_stable_or_creating_preview(tmp_path, monkeypatch):
    stable, preview = settings_files(tmp_path, monkeypatch)
    game = make_game(tmp_path)
    old = app_state.add_game(app_state.default_state(), game)
    old.update(schema=2, appearance="light", window={"width": 1000, "height": 700})
    stable.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    original = stable.read_bytes()
    loaded = app_state.load_state()
    assert app_state.state_path() == str(preview)
    assert loaded["appearance"] == "light"
    assert loaded["window"] == old["window"]
    assert loaded["games"][0]["path"] == str(game)
    assert stable.read_bytes() == original
    assert not preview.exists()
    loaded["appearance"] = "dark"
    assert app_state.save_state(loaded) == str(preview)
    assert stable.read_bytes() == original
    assert app_state.load_state()["appearance"] == "dark"


def test_existing_preview_wins_over_stable_and_corrupt_preview_does_not_reimport(tmp_path, monkeypatch):
    stable, preview = settings_files(tmp_path, monkeypatch)
    stable.write_text('{"schema": 2, "appearance": "light"}', encoding="utf-8")
    preview.write_text('{"schema": 3, "appearance": "dark"}', encoding="utf-8")
    assert app_state.load_state()["appearance"] == "dark"
    preview.write_text("{broken", encoding="utf-8")
    assert app_state.load_state() == app_state.default_state()


def test_explicit_missing_path_never_reads_stable_and_channels_save_independently(tmp_path, monkeypatch):
    stable, preview = settings_files(tmp_path, monkeypatch)
    stable.write_text('{"schema": 2, "appearance": "light"}', encoding="utf-8")
    assert app_state.load_state(tmp_path / "explicit-missing.json") == app_state.default_state()
    preview_state = app_state.default_state()
    preview_state["appearance"] = "dark"
    app_state.save_state(preview_state)
    preview_bytes = preview.read_bytes()
    monkeypatch.setattr(app_state.branding, "APP_CHANNEL", "stable")
    assert app_state.state_path() == str(stable)
    assert app_state.load_state()["appearance"] == "light"
    stable_state = app_state.load_state()
    stable_state["appearance"] = "system"
    app_state.save_state(stable_state)
    assert preview.read_bytes() == preview_bytes


def test_offline_rename_keeps_launcher_and_unsafe_import_is_dropped(tmp_path):
    offline = str(tmp_path / "offline")
    state = app_state.default_state()
    state["games"] = [{"path": offline, "name": "Before", "launcher_rel": "bin/Play.exe"}]
    before = copy.deepcopy(state)
    renamed = app_state.rename_game(state, offline, "After")
    assert renamed["games"] == [{"path": offline, "name": "After", "available": False,
                                  "launcher_rel": "bin/Play.exe"}]
    assert state == before
    filename = tmp_path / "offline.json"
    app_state.save_state(renamed, filename)
    assert app_state.load_state(filename)["games"][0]["launcher_rel"] == "bin/Play.exe"
    renamed["games"][0]["launcher_rel"] = "../../escape.exe"
    app_state.save_state(renamed, filename)
    assert "launcher_rel" not in app_state.load_state(filename)["games"][0]
