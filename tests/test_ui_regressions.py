"""Targeted regressions for the 1.2.0 GUI bug-fix pass."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import appgui  # noqa: E402


def _pump(root, rounds=8):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def test_simulation_fails_closed_on_unknown_support(ui_app):
    app, root, game = ui_app
    app.var_on["fontfix"].set(True)
    with mock.patch.object(
            appgui.engine_adapters, "survey",
            return_value={"feature_support": {
                "fontfix": {"supported": None, "reasons": ["status unknown"]},
            }}), \
            mock.patch.object(appgui.simulation, "prepare") as prepare:
        app._simulation_prepare_worker(str(game), ["fontfix"])
        for _ in range(50):
            root.update()
            if app.sim_stage_state.get("compat", ("",))[0] == "bad":
                break
            time.sleep(0.01)
    assert not prepare.called
    assert app.sim_stage_state["compat"][0] == "bad"


def test_revert_rechecks_installed_state_instead_of_stale_cache(ui_app):
    app, _root, _game = ui_app
    app._installed = {}
    fresh = {"shim": True, "ours": True, "current": True}
    with mock.patch.object(appgui.engine_adapters, "installed_state",
                           return_value=fresh), \
            mock.patch.object(appgui.messagebox, "askyesno",
                              return_value=True), \
            mock.patch.object(app, "_spawn") as spawn:
        app.revert()
    assert spawn.called


def test_foreign_collision_is_confirmed(ui_app):
    app, _root, _game = ui_app
    app._survey = {"collisions": ["game/foreign.rpy"]}
    app.var_on["intro"].set(False)
    with mock.patch.object(appgui.engine_adapters, "installed_state",
                           return_value={}), \
            mock.patch.object(appgui.messagebox, "askyesno",
                              return_value=False) as ask:
        assert app._confirm_overwrite() is False
    assert ask.called
    assert "foreign.rpy" in ask.call_args.args[1]


def test_addon_foreign_target_is_confirmed(ui_app):
    app, _root, game = ui_app
    target = Path(game) / "game" / "zz_rpykit_compat.rpy"
    target.write_text("# hand-written foreign addon\n", encoding="utf-8")
    app.var_on["runtime_compat"].set(True)
    try:
        with mock.patch.object(appgui.messagebox, "askyesno",
                               return_value=False) as ask:
            assert app._confirm_overwrite() is False
        assert ask.called
        assert "zz_rpykit_compat.rpy" in ask.call_args.args[1]
    finally:
        target.unlink(missing_ok=True)
        app.var_on["runtime_compat"].set(False)


def test_install_stops_when_installed_state_cannot_be_read(ui_app):
    app, _root, _game = ui_app
    with mock.patch.object(appgui.engine_adapters, "installed_state",
                           side_effect=OSError("unreadable")), \
            mock.patch.object(appgui.messagebox, "askyesno",
                              return_value=True), \
            mock.patch.object(appgui.messagebox, "showerror") as error, \
            mock.patch.object(app, "_spawn") as spawn:
        app.install()
    assert error.called and not spawn.called


def test_window_size_is_clamped_to_screen(ui_app):
    app, _root, _game = ui_app
    with mock.patch.object(app, "_window_scaling", return_value=1.0), \
            mock.patch.object(app.root, "winfo_screenwidth",
                              return_value=1600), \
            mock.patch.object(app.root, "winfo_screenheight",
                              return_value=900):
        assert app._clamp_window_size(2400, 1600) == (1520, 800)
        assert app._clamp_window_size(900, 620) == (900, 620)

    with mock.patch.object(app, "_window_scaling", return_value=1.25), \
            mock.patch.object(app.root, "winfo_screenwidth",
                              return_value=1366), \
            mock.patch.object(app.root, "winfo_screenheight",
                              return_value=768):
        assert app._clamp_window_size(1200, 900) == (1012, 520)


def test_simulation_failure_is_written_to_log(ui_app):
    app, _root, _game = ui_app
    app._simulation_failed("synthetic failure", None)
    assert "synthetic failure" in app._log_text()
    assert app.active_page == "log"


def test_scan_error_changes_global_status(ui_app):
    app, _root, _game = ui_app
    app._scan_finished(app._scan_generation, app.game_dir, None, None,
                       "synthetic scan failure")
    assert app.var_global_status.get() == "检查失败"
    assert app._survey is None and app._installed is None
    assert app.btn_go.cget("state") == "disabled"


def test_set_buttons_survives_engine_detection_error(ui_app):
    app, _root, _game = ui_app
    with mock.patch.object(appgui.engine_adapters, "detect",
                           side_effect=OSError("unreadable core")):
        app._set_buttons()
    assert app.btn_go.cget("state") == "disabled"


def test_cannot_switch_game_while_busy(ui_app, tmp_path):
    app, _root, game = ui_app
    other = tmp_path / "Other Game"
    (other / "game").mkdir(parents=True)
    (other / "renpy").mkdir()
    app.busy = True
    try:
        with mock.patch.object(appgui.messagebox, "showinfo") as info:
            app.set_game_dir(str(other))
        assert app.game_dir == str(game)
        assert info.called
    finally:
        app.busy = False


def test_segmented_children_do_not_reenter_tab_chain(ui_app):
    app, _root, _game = ui_app
    app._show_page("settings")
    app._install_focus()
    outer = appgui.ui_focus.focus_target(app.theme_segment)
    assert outer is not None
    for child in app.theme_segment.winfo_children():
        target = appgui.ui_focus.focus_target(child)
        if target is not None:
            assert str(target.cget("takefocus")) == "0"


def test_theme_segment_focus_changes_wrapper_border(ui_app):
    app, root, _game = ui_app
    app._show_page("settings")
    _pump(root)
    target = appgui.ui_focus.focus_target(app.theme_segment)
    target.focus_force()
    root.update()
    assert int(app.theme_focus.cget("border_width")) == 2
    root.focus_set()
    root.update()
    assert int(app.theme_focus.cget("border_width")) == 1
