"""Channel configuration separation and optional launcher persistence."""

import copy
import json
import os

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
    legacy_bytes = stable.read_bytes()
    monkeypatch.setattr(app_state.branding, "APP_CHANNEL", "stable")
    destination = stable.with_name("ui_state.v3.json")
    assert app_state.state_path() == str(destination)
    assert app_state.load_state(tmp_path / "explicit-missing.json") == app_state.default_state()
    assert not destination.exists()
    stable_state = app_state.load_state()
    assert stable_state["appearance"] == "dark"
    stable_state["appearance"] = "system"
    assert app_state.save_state(stable_state) == str(destination)
    assert preview.read_bytes() == preview_bytes
    assert stable.read_bytes() == legacy_bytes


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


def stable_settings_files(tmp_path, monkeypatch):
    legacy, preview = settings_files(tmp_path, monkeypatch)
    monkeypatch.setattr(app_state.branding, "APP_CHANNEL", "stable")
    return legacy, preview, legacy.with_name("ui_state.v3.json")


def write_settings(filename, **settings):
    data = json.dumps(settings, ensure_ascii=False).encode("utf-8")
    filename.write_bytes(data)
    return data


@pytest.mark.parametrize(("source_index", "malformed_other"), [(0, False), (1, False), (1, True)])
def test_stable_migration_accepts_either_usable_source(tmp_path, monkeypatch, source_index, malformed_other):
    legacy, preview, destination = stable_settings_files(tmp_path, monkeypatch)
    sources = (legacy, preview)
    source = sources[source_index]
    if malformed_other:
        sources[1 - source_index].write_bytes(b"{broken")
    game = make_game(tmp_path)
    original = write_settings(source, schema=1, appearance="dark",
                              window={"width": 1350, "height": 930}, active_game=str(game),
                              games=[{"path": str(game), "name": "Original", "launcher_rel": "bin/Play.exe"}])

    loaded = app_state.load_state()
    assert loaded["window"] == {"width": 1180, "height": 780}
    assert loaded["appearance"] == "dark"
    assert loaded["active_game"] == str(game)
    assert loaded["games"][0]["launcher_rel"] == "bin/Play.exe"
    assert app_state.load_state(destination) == loaded
    assert source.read_bytes() == original


def test_stable_migration_merges_duplicates_and_persists_only_once(tmp_path, monkeypatch):
    legacy, preview, destination = stable_settings_files(tmp_path, monkeypatch)
    game = make_game(tmp_path)
    offline = tmp_path / "Offline bookmark"
    other = tmp_path / "New bookmark"
    original_legacy = write_settings(
        legacy, schema=2, appearance="light", window={"width": 950, "height": 650},
        games=[{"path": str(game), "name": "Old name", "launcher_rel": "bin/Play.exe"},
               {"path": str(offline), "name": "Offline", "launcher_rel": "Start.exe"}],
        active_game=str(offline),
    )
    original_preview = write_settings(
        preview, schema=3, appearance="dark", window={"width": 1230, "height": 800},
        games=[{"path": str(game / "bin" / ".."), "name": "New name", "launcher_rel": "bin/New.exe"},
               {"path": str(other), "name": "Other"}],
        active_game=str(game),
    )

    loaded = app_state.load_state()
    assert loaded["games"] == [
        {"path": str(game), "name": "New name", "launcher_rel": "bin/New.exe", "available": True},
        {"path": str(offline), "name": "Offline", "launcher_rel": "Start.exe", "available": False},
        {"path": str(other), "name": "Other", "available": False},
    ]
    assert loaded["appearance"] == "dark"
    assert loaded["window"] == {"width": 1230, "height": 800}
    assert loaded["active_game"] == str(game)
    assert legacy.read_bytes() == original_legacy
    assert preview.read_bytes() == original_preview
    imported_bytes = destination.read_bytes()
    write_settings(preview, appearance="light", games=[])
    assert app_state.load_state() == loaded
    assert destination.read_bytes() == imported_bytes


def test_missing_and_invalid_preview_fields_keep_usable_legacy_values(tmp_path, monkeypatch):
    legacy, preview, _ = stable_settings_files(tmp_path, monkeypatch)
    game = make_game(tmp_path)
    offline = tmp_path / "Offline"
    write_settings(
        legacy, schema=2, appearance="light", window={"width": 950, "height": 650},
        games=[{"path": str(game), "name": "Legacy game", "launcher_rel": "bin/Play.exe"},
               {"path": str(offline), "name": "Legacy offline", "launcher_rel": "Old.exe"}],
        active_game=str(offline),
    )
    write_settings(
        preview, schema=3, appearance=["dark"], window={"width": "large", "height": 600},
        games=[{"path": str(game), "launcher_rel": "../Outside.exe"},
               {"path": str(offline), "name": {"malformed": True}}, {"path": "\x00"}],
        active_game=str(tmp_path / "Not bookmarked"),
    )

    loaded = app_state.load_state()
    assert loaded["appearance"] == "light"
    assert loaded["window"] == {"width": 950, "height": 650}
    assert loaded["active_game"] == str(offline)
    assert loaded["games"] == [
        {"path": str(game), "name": "Legacy game", "launcher_rel": "bin/Play.exe", "available": True},
        {"path": str(offline), "name": "Legacy offline", "launcher_rel": "Old.exe", "available": False},
    ]


def test_merge_preserves_full_bookmark_union(tmp_path, monkeypatch):
    legacy, preview, _ = stable_settings_files(tmp_path, monkeypatch)
    paths = [str(tmp_path / ("Offline %d" % index)) for index in range(202)]
    write_settings(legacy, games=[{"path": path} for path in paths[:101]])
    write_settings(preview, games=[{"path": path} for path in paths[101:]])

    assert [entry["path"] for entry in app_state.load_state()["games"]] == paths
    assert [entry["path"] for entry in app_state.load_state()["games"]] == paths


def test_migration_write_failure_keeps_sources_and_retries(tmp_path, monkeypatch):
    legacy, preview, destination = stable_settings_files(tmp_path, monkeypatch)
    original_legacy = write_settings(legacy, appearance="light")
    original_preview = write_settings(preview, appearance="dark")

    def fail_flush(_fd):
        raise OSError("injected migration write failure")

    with monkeypatch.context() as failing:
        failing.setattr(os, "fsync", fail_flush)
        assert app_state.load_state()["appearance"] == "dark"
    assert not destination.exists()
    assert set(destination.parent.iterdir()) == {legacy, preview}
    assert legacy.read_bytes() == original_legacy
    assert preview.read_bytes() == original_preview
    assert app_state.load_state()["appearance"] == "dark"
    assert destination.is_file()


def test_migration_keeps_destination_created_during_import(tmp_path, monkeypatch):
    legacy, _, destination = stable_settings_files(tmp_path, monkeypatch)
    write_settings(legacy, appearance="light")
    fsync = os.fsync

    def concurrent_save(fd):
        fsync(fd)
        write_settings(destination, schema=3, appearance="dark")

    monkeypatch.setattr(os, "fsync", concurrent_save)
    assert app_state.load_state()["appearance"] == "dark"
    assert app_state.load_state(destination)["appearance"] == "dark"
