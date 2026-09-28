"""Persistence contracts for appearance preferences and the manual game list."""

import json
from pathlib import Path

import pytest

import app_state


def make_game(parent, name="Example"):
    root = parent / name
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    return root


def test_add_game_requires_a_game_directory_and_never_scans_it(tmp_path):
    game = make_game(tmp_path)
    state = app_state.add_game(app_state.default_state(), game)

    assert state["games"] == [{"path": str(game.resolve()), "name": "Example"}]
    assert state["active_game"] == str(game.resolve())
    assert {child.name for child in game.iterdir()} == {"game", "renpy"}
    with pytest.raises(ValueError, match="game/"):
        app_state.add_game(state, tmp_path)


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
    assert json.loads(filename.read_text(encoding="utf-8"))["schema"] == 1
    assert sorted(item.name for item in filename.parent.iterdir()) == ["ui_state.json"]


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
    assert loaded["games"] == []
    assert loaded["active_game"] == ""
