"""Exercise desktop integration without starting a game or a network provider."""
from unittest import mock

import app_state
import appgui
import game_launch
from test_stable_regressions import controller


def test_first_library_start_always_asks_and_cancel_does_not_launch(tmp_path):
    app = controller()
    root = tmp_path / "Game"
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    (root / "only.exe").write_bytes(b"fixture")
    entry = {"path": str(root), "name": "Game"}
    with mock.patch("translation_ui.filedialog.askopenfilename", return_value="") as choose, \
            mock.patch.object(game_launch, "launch") as launch:
        app.launch_library_game(entry)
    choose.assert_called_once()
    launch.assert_not_called()


def test_chosen_launcher_is_saved_and_reused_without_asking(tmp_path):
    app = controller()
    root = tmp_path / "Game & 中文"
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir()
    executable = root / "play.exe"
    executable.write_bytes(b"fixture")
    app.state = app_state.add_game(app.state, root)
    with mock.patch("translation_ui.filedialog.askopenfilename", return_value=str(executable)) as choose, \
            mock.patch.object(game_launch, "launch") as launch:
        app.launch_library_game(app.state["games"][0])
        saved = app.state["games"][0]
        assert saved["launcher_rel"] == "play.exe"
        app.launch_library_game(saved)
    choose.assert_called_once()
    assert launch.call_count == 2
    launch.assert_called_with(str(root), "play.exe")


def test_library_folder_is_independent_of_current_game(tmp_path):
    app = controller()
    app.game_dir = "a different selected game"
    with mock.patch.object(game_launch, "open_folder") as opened:
        app.open_library_folder({"path": str(tmp_path)})
    opened.assert_called_once_with(str(tmp_path))


def test_stale_translation_start_stops_host_and_leaves_game_running():
    app = controller()
    app._translation_id, app._translation_game = "current", "game"
    host, process = mock.Mock(), mock.Mock()
    app._handle_translation_event(("__translation_started__", "stale", "game", host, process))
    host.stop.assert_called_once()
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_stopping_original_translation_does_not_stop_game():
    app = controller()
    host, process = mock.Mock(), mock.Mock()
    app._translation_host, app._translation_process = host, process
    app._translation_id = "session"
    app.stop_translation()
    host.stop.assert_called_once()
    assert app._translation_host is None and app._translation_id is None
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_simulation_controls_live_in_log_and_process_only_links(ui_app):
    app, _root, _game = ui_app
    widget = app.btn_dry
    parents = []
    while widget is not None:
        parents.append(widget)
        widget = getattr(widget, "master", None)
    assert app.pages["log"] in parents and app.pages["process"] not in parents
    assert app.btn_open_sim.cget("command") == app._show_log


def test_help_search_finds_body_and_clears_without_network(ui_app):
    app, _root, _game = ui_app
    app.var_help_query.set("DPAPI")
    app._render_help_search()
    assert any(row["topic_id"] == "translation" for row in app._help_results)
    assert not app.help_grid.winfo_manager()
    app._clear_help_search()
    app._render_help_search()
    assert app.help_grid.winfo_manager() == "pack"


def test_translation_event_never_logs_untrusted_error_payload():
    app = controller()
    app._translation_id, app._translation_game = "active", "game"
    app._handle_translation_event(("__translation_log__", "active", "game",
                                   {"status": "provider_error", "api_key": "private", "text": "story"}))
    text = app._log.call_args.args[0]
    assert "private" not in text and "story" not in text


def test_luna_conflict_stops_original_host_without_killing_game():
    app = controller()
    host, process = mock.Mock(), mock.Mock()
    app._translation_id, app._translation_game = "active", "game"
    app._translation_host, app._translation_process = host, process
    app._handle_translation_event(("__translation_log__", "active", "game", {"status": "luna_conflict"}))
    host.stop.assert_called_once()
    process.terminate.assert_not_called()
    assert app._translation_id is None
    assert "Luna" in app.var_global_status.get()


def test_luna_conflict_before_started_releases_preparing_state():
    app = controller()
    app._translation_id, app._translation_game = "active", "game"
    app._translation_host = None
    app._translation_preparing = app.busy = True
    app.close_after_work = False
    host, process = mock.Mock(), mock.Mock()
    app._handle_translation_event(("__translation_log__", "active", "game", {"status": "luna_conflict"}))
    app._handle_translation_event(("__translation_started__", "active", "game", host, process))
    assert not app.busy and not app._translation_preparing
    assert app._translation_host is None and app._translation_id is None
    host.stop.assert_called_once()
    process.terminate.assert_not_called()


def test_translation_install_refreshes_current_game_after_start_or_failure():
    for event in ("__translation_started__", "__translation_failed__"):
        app = controller()
        app.game_dir = app._translation_game = "game"
        app._translation_id = "active"
        app._translation_conflict = False
        app._translation_host = None
        app.close_after_work = False
        app._refresh_state = mock.Mock()
        item = (event, "active", "game")
        if event == "__translation_started__":
            item += (mock.Mock(), mock.Mock())
        app._handle_translation_event(item)
        app._refresh_state.assert_called_once()


def test_scan_completion_keeps_active_translation_status():
    app = controller()
    app.game_dir = "game"
    app._translation_host = mock.Mock()
    app._scan_finished(0, "game", {}, {}, None)
    assert app.var_global_status.get() == "实时汉化运行中"


def test_translation_copy_uses_session_environment_and_cleanup_stops_host():
    app = controller()
    app._translation_game, app._translation_id = "original", "operation"
    app._sim_translation_settings = {"provider": "google"}
    app._sim_translation_requested = True
    host, session = mock.Mock(), mock.Mock()
    host.environment.return_value = {"RPYKIT_TRANSLATION_TOKEN": "synthetic"}
    app._new_translation_host = mock.Mock(return_value=host)
    app._simulation_launch_worker(session, "play.exe")
    session.launch.assert_called_once_with("play.exe", environment=host.environment())
    assert app.queue.get()[0] == "__sim_launched__"
    # Even after a failed copy cleanup, its proxy must already be disconnected.
    appgui._OperationMixin._cleanup_simulation(app)
    host.stop.assert_called_once()
    assert app._translation_host is None and app._translation_id is None


def test_successful_connector_revert_removes_version_barrier(tmp_path):
    import cmd_fontfix
    import proj
    import renpy_translation
    from test_revert_atomicity import _installed
    game, work = _installed(tmp_path)
    patch = game / "game" / renpy_translation.REL
    patch.write_text("# " + cmd_fontfix.MARKER + "\ninit 999 python:\n    pass\n", encoding="utf-8")
    proj.record_file(str(work), str(game), "game/" + renpy_translation.REL, "feature:translation")
    assert proj.load_manifest(str(work))["min_tool_version"] == "1.3.0"
    result = cmd_fontfix.revert(str(game), str(work))
    assert not result["conflicts"] and not patch.exists()
    assert "min_tool_version" not in proj.load_manifest(str(work))


def test_translation_revert_retains_font_dependency_and_version_barrier(tmp_path, monkeypatch):
    import branding
    import cmd_fontfix
    import proj
    import renpy_translation
    from test_revert_atomicity import _installed, _bytes_tree
    game, work = _installed(tmp_path)
    patch = game / "game" / renpy_translation.REL
    patch.write_text("# " + cmd_fontfix.MARKER + "\ninit 999 python:\n    pass\n", encoding="utf-8")
    proj.record_file(str(work), str(game), "game/" + renpy_translation.REL, "feature:translation")
    manifest = proj.load_manifest(str(work))
    assert manifest["min_tool_version"] == "1.3.0"
    with monkeypatch.context() as old:
        old.setattr(branding, "APP_VERSION", "1.2.0")
        import pytest
        with pytest.raises(proj.ManifestVersionError):
            cmd_fontfix.revert(str(game), str(work))
    patch.write_text(patch.read_text(encoding="utf-8") + "# external edit\n", encoding="utf-8")
    before = _bytes_tree(game)
    result = cmd_fontfix.revert(str(game), str(work))
    assert result["conflicts"] and _bytes_tree(game) == before
    assert proj.load_manifest(str(work))["min_tool_version"] == "1.3.0"
