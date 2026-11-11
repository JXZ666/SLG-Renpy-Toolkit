"""Persistence contracts for appearance preferences and the manual game list."""

import json
from pathlib import Path
from unittest import mock

import pytest

import app_state
import engine_adapters
import game_launch


def make_game(parent, name="Example"):
    root = parent / name
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    return root


def test_unknown_engine_can_be_bookmarked_and_launched_without_detection(tmp_path, monkeypatch):
    game = tmp_path / "Example"
    bin_dir = game / "bin"
    bin_dir.mkdir(parents=True)
    executable = bin_dir / "Play.exe"
    executable.write_bytes(b"fixture, never executed")

    def unexpected_scan(*args, **kwargs):
        pytest.fail("Library persistence must not detect the game engine")

    monkeypatch.setattr(engine_adapters, "detect", unexpected_scan)
    state = app_state.add_game(app_state.default_state(), game)

    assert state["games"] == [{"path": str(game.resolve()), "name": "Example",
                               "available": True}]
    assert state["active_game"] == str(game.resolve())
    state = app_state.rename_game(state, game, "Ordinary game")
    state = app_state.set_launcher(state, game, executable)
    filename = tmp_path / "library.json"
    app_state.save_state(state, filename)
    entry, = app_state.load_state(filename)["games"]
    assert entry["name"] == "Ordinary game"
    assert entry["available"] is True
    assert entry["launcher_rel"] == "bin/Play.exe"

    with mock.patch.object(game_launch.subprocess, "Popen") as popen:
        game_launch.launch(entry["path"], entry["launcher_rel"])
    assert popen.call_args.args == ([str(executable)],)
    assert popen.call_args.kwargs["cwd"] == str(bin_dir)
    with mock.patch.object(game_launch.os, "startfile", create=True) as open_folder:
        game_launch.open_folder(entry["path"])
    open_folder.assert_called_once_with(str(game.resolve()))

    for invalid in (tmp_path / "missing", executable):
        with pytest.raises(ValueError, match="游戏目录"):
            app_state.add_game(state, invalid)


def test_add_game_deduplicates_paths_and_allows_renaming(tmp_path):
    game = make_game(tmp_path)
    state = app_state.add_game(app_state.default_state(), game)
    state = app_state.add_game(state, game / ".")
    assert len(state["games"]) == 1
    state = app_state.add_game(state, game, "My Game")
    assert len(state["games"]) == 1
    assert state["games"][0]["name"] == "My Game"


def test_settings_round_trip_atomically_and_sanitize_bounds(tmp_path):
    game = make_game(tmp_path)
    state = app_state.add_game(app_state.default_state(), game)
    state.update(appearance="dark", window={"width": 99999, "height": 300})
    filename = tmp_path / "config" / "ui_state.json"

    app_state.save_state(state, filename)
    loaded = app_state.load_state(filename)

    assert loaded["appearance"] == "dark"
    assert loaded["window"] == {"width": 2400, "height": 560}
    assert loaded["games"][0]["path"] == str(game.resolve())
    assert loaded["active_game"] == str(game.resolve())
    assert json.loads(filename.read_text(encoding="utf-8"))["schema"] == app_state.SCHEMA_VERSION
    assert sorted(item.name for item in filename.parent.iterdir()) == ["ui_state.json"]


def test_old_physical_window_size_is_migrated_once(tmp_path):
    filename = tmp_path / "old.json"
    filename.write_text(json.dumps({
        "schema": 1,
        "window": {"width": 1350, "height": 930},
        "appearance": "light",
    }), encoding="utf-8")
    loaded = app_state.load_state(filename)
    assert loaded["schema"] == app_state.SCHEMA_VERSION
    assert loaded["window"] == {"width": 1180, "height": 780}

    app_state.save_state(loaded, filename)
    again = app_state.load_state(filename)
    assert again["window"] == {"width": 1180, "height": 780}


def test_invalid_state_falls_back_and_removed_paths_do_not_remain_active(tmp_path):
    filename = tmp_path / "broken.json"
    filename.write_text("{broken", encoding="utf-8")
    assert app_state.load_state(filename) == app_state.default_state()

    game = make_game(tmp_path)
    state = app_state.add_game(app_state.default_state(), game)
    state = app_state.remove_game(state, game)
    assert state["games"] == []
    assert state["active_game"] == ""

    filename.write_text(json.dumps({
        "schema": 1,
        "games": [{"path": str(game), "name": "Removed"}],
        "active_game": str(game),
    }), encoding="utf-8")
    import shutil
    shutil.rmtree(game)
    loaded = app_state.load_state(filename)
    assert loaded["games"] == [{"path": str(game), "name": "Removed",
                                "available": False}]
    assert loaded["active_game"] == str(game)
