"""Behavior regressions for the 1.2 stable pass, with isolated UI state."""

from __future__ import annotations

import copy
import queue
from unittest import mock

import pytest

import app_state
import appgui


class Value:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class Widget:
    def __init__(self):
        self.visible = False
        self.options = {}

    def configure(self, **options):
        self.options.update(options)

    def pack(self, **_options):
        self.visible = True

    def pack_forget(self):
        self.visible = False


def controller():
    """Build only the controller fields; never create a Tk root or game."""
    app = appgui.App.__new__(appgui.App)
    app.game_dir = ""
    app.state = app_state.default_state()
    app.root = mock.Mock()
    app.queue = queue.Queue()
    app._scan_generation = 0
    app._survey = app._installed = None
    app.scan_busy = app.scan_failed = False
    app.busy = app.sim_preparing = False
    app.sim_session = None
    app.sim_launched = app.sim_process_exited = False
    app.sim_confirmed = app.sim_gameplay_confirmed = False
    app.close_after_cleanup = False
    app.rows = {}
    app.library_action_buttons = []
    for name in ("var_global_status", "var_toolbox_info", "var_toolbox_installed", "var_dir"):
        setattr(app, name, Value())
    for name in ("btn_go", "btn_dry", "btn_undo", "btn_pick", "btn_add_game",
                 "btn_sim_success", "btn_sim_failure", "btn_sim_gameplay",
                 "btn_sim_finish", "btn_sim_cleanup", "sim_confirm_frame"):
        setattr(app, name, Widget())
    app.bar = mock.Mock()
    app._ticked = mock.Mock(return_value=["fontfix"])
    for name in ("_set_compat", "_apply_feature_support", "_paint_chips", "_set_state",
                 "_log", "_update_action_hint", "_persist_state", "_render_library",
                 "_show_log", "_set_sim_stage", "_set_sim_result", "_cleanup_simulation"):
        setattr(app, name, mock.Mock())
    return app


def test_library_open_selects_game_and_opens_process_page(ui_app):
    app, _root, game = ui_app
    app._render_library()
    with mock.patch.object(app, "set_game_dir") as select, \
            mock.patch.object(app, "_show_page") as show:
        app.library_action_buttons[0].invoke()
    select.assert_called_once_with(str(game))
    show.assert_called_once_with("process")


def test_release_channel_uses_shared_branding(ui_app):
    app, _root, _game = ui_app
    assert app.channel_label.cget("text") == appgui.branding.CHANNEL_LABEL


def test_offline_bookmark_can_be_renamed_without_readding(tmp_path):
    offline = str(tmp_path / "Offline Game")
    original = app_state.default_state()
    original.update(games=[{"name": "Old", "path": offline, "available": False}],
                    active_game=offline)
    app = controller()
    app.state = copy.deepcopy(original)
    with mock.patch.object(appgui.simpledialog, "askstring", return_value="New"), \
            mock.patch.object(app_state, "add_game", side_effect=AssertionError("must not add")):
        app.rename_game(app.state["games"][0])
    assert app.state["games"] == [{"name": "New", "path": offline, "available": False}]
    assert app.state["active_game"] == offline
    assert original["games"][0]["name"] == "Old"
    filename = tmp_path / "ui_state.json"
    app_state.save_state(app.state, filename)
    assert app_state.load_state(filename)["games"][0]["name"] == "New"
    assert not (tmp_path / "Offline Game").exists()


def test_rename_unknown_bookmark_does_not_add_an_entry(tmp_path):
    with pytest.raises(ValueError, match="游戏库"):
        app_state.rename_game(app_state.default_state(), tmp_path / "Missing", "New")


def test_refresh_routes_engine_read_error_into_failed_scan():
    app = controller()
    app.game_dir = "unreadable-game"
    with mock.patch.object(appgui.engine_adapters, "detect", side_effect=OSError("core unreadable")), \
            mock.patch.object(appgui.threading, "Thread") as thread:
        result = app._refresh_state()
    assert result[0] == "bad"
    assert app.scan_failed and not app.scan_busy
    assert app._survey is None and app._installed is None
    assert app.var_global_status.get() == "检查失败"
    assert "core unreadable" in app.var_toolbox_info.get()
    assert app.btn_go.options["state"] == "disabled"
    thread.assert_not_called()


def test_simulate_routes_engine_read_error_without_starting_worker():
    app = controller()
    app.game_dir = "unreadable-game"
    with mock.patch.object(appgui.engine_adapters, "detect", side_effect=OSError("core unreadable")), \
            mock.patch.object(appgui.threading, "Thread") as thread:
        app.simulate_run()
    thread.assert_not_called()
    assert app.scan_failed and not app.busy and not app.sim_preparing
    app._set_sim_result.assert_called_once()
    assert app._set_sim_result.call_args.args[0] == "bad"
    assert app.var_global_status.get() == "检查失败"
    assert "core unreadable" in app.var_toolbox_info.get()
    assert app.btn_go.options["state"] == "disabled"
    thread.assert_not_called()


def test_selecting_game_survives_engine_read_error(tmp_path):
    app = controller()
    with mock.patch.object(appgui.engine_adapters, "detect", side_effect=OSError("locked core")):
        app.set_game_dir(tmp_path)
    assert app.game_dir == str(tmp_path)
    assert app.scan_failed
    assert app.var_global_status.get() == "检查失败"
    app._persist_state.assert_not_called()


@pytest.mark.parametrize("support_map", [None, False, [], ["fontfix"], 42, "supported"])
def test_malformed_simulation_support_map_never_copies(support_map):
    app = controller()
    with mock.patch.object(appgui.engine_adapters, "survey", return_value={"feature_support": support_map}), \
            mock.patch.object(appgui.simulation, "prepare") as prepare:
        app._simulation_prepare_worker("game", ["fontfix"])
    prepare.assert_not_called()
    event = app.queue.get_nowait()
    assert event[0] == "__sim_failed__"
    assert event[2][0]["id"] == "compat"
    assert event[2][0]["status"] == "failed"
    assert app.queue.empty()


def test_explicit_simulation_support_still_prepares():
    app = controller()
    session = object()
    with mock.patch.object(appgui.engine_adapters, "survey", return_value={
            "feature_support": {"fontfix": {"supported": True}}}), \
            mock.patch.object(appgui.simulation, "prepare", return_value=session) as prepare:
        app._simulation_prepare_worker("game", ["fontfix"])
    prepare.assert_called_once()
    assert list(app.queue.queue)[-1] == ("__sim_prepared__", session)


def test_running_game_error_keeps_stop_cleanup_reachable():
    app = controller()
    app.sim_session = mock.Mock(runtime_errors=["synthetic runtime error"])
    app.sim_session.poll.return_value = None
    app.sim_launched = True
    app._pack_sim_confirm()
    app._poll_simulation()
    assert app.sim_confirm_frame.visible
    assert app.btn_sim_finish.visible
    assert app.btn_sim_finish.options["state"] == "normal"
    assert not app.btn_sim_success.visible
    assert app.btn_sim_success.options["state"] == "disabled"
    app._cleanup_simulation.assert_not_called()
    app.root.after.assert_called_once_with(400, app._poll_simulation)
    app._set_sim_result.assert_called_with("bad", "游戏报告了新异常：synthetic runtime error")


def test_failed_cleanup_keeps_retry_button_reachable():
    app = controller()
    app.sim_session = object()
    app._simulation_cleaned(["cleanup: files busy"])
    assert app.sim_confirm_frame.visible and app.btn_sim_cleanup.visible
    assert app.btn_sim_cleanup.options["state"] == "normal"
    assert app.sim_session is not None


def test_main_menu_confirmation_is_idempotent_after_gameplay():
    app = controller()
    app.sim_session = mock.Mock(runtime_errors=[])
    app.sim_launched = app.sim_confirmed = app.sim_gameplay_confirmed = True
    app.sim_session.poll.return_value = None
    with mock.patch.object(appgui.threading, "Thread") as thread:
        app.confirm_simulation_success()
        app._simulation_confirmed()  # a duplicate queued completion is also harmless
    assert app.sim_confirmed and app.sim_gameplay_confirmed
    app._set_sim_stage.assert_not_called()
    app._set_sim_result.assert_not_called()
    thread.assert_not_called()
    app._set_buttons()
    assert app.btn_sim_success.options["state"] == "disabled"
    assert app.btn_sim_gameplay.options["state"] == "disabled"


def test_double_main_menu_click_does_not_schedule_a_second_worker():
    app = controller()
    app.sim_session = mock.Mock(runtime_errors=[])
    app.sim_launched = True
    with mock.patch.object(appgui.threading, "Thread") as thread:
        app.confirm_simulation_success()
        app.confirm_simulation_success()
    assert app.busy
    assert thread.call_count == 1
    thread.return_value.start.assert_called_once()


def test_menu_ack_cannot_override_a_new_runtime_error():
    app = controller()
    app.sim_session = mock.Mock(runtime_errors=["error after acknowledgement"])
    app.sim_launched = app.busy = True
    app._simulation_confirmed()
    assert not app.busy and not app.sim_confirmed
    app._set_sim_stage.assert_called_once_with("confirm", "failed", "error after acknowledgement")
    app._set_sim_result.assert_called_once_with(
        "bad", "确认期间游戏报告了新异常：error after acknowledgement")
    assert app.sim_confirm_frame.visible and app.btn_sim_finish.visible
    assert app.btn_sim_finish.options["state"] == "normal"
    assert app.btn_sim_success.options["state"] == "disabled"
