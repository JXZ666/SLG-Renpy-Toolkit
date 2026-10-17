"""Keyboard, confirmation and status checks for the desktop interface.

These tests use the session Tk window from ``conftest.py`` because focus
traversal is a Tk behaviour, not something a mock can prove.  They use only
temporary synthetic directories and never touch a real game.
"""

from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import appgui  # noqa: E402
import ui_focus  # noqa: E402
import ui_tokens  # noqa: E402


pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")


def _pump(root, rounds=6):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def test_process_controls_have_takefocus_targets(ui_app):
    instance, root, _game_dir = ui_app
    instance._show_page("process")
    _pump(root)
    widgets = {
        "browse": instance.btn_pick,
        "path": instance.entry_dir,
        "font": instance.rows["fontfix"].toggle,
        "simulate": instance.btn_dry,
        "install": instance.btn_go,
        "undo": instance.btn_undo,
    }
    for name, widget in widgets.items():
        target = ui_focus.focus_target(widget)
        assert target is not None, name
        assert str(target.cget("takefocus")) in ("1", "true", "True"), name


def test_tab_chain_reaches_feature_and_action_buttons(ui_app):
    instance, root, _game_dir = ui_app
    instance._show_page("process")
    _pump(root)
    start = ui_focus.focus_target(instance.btn_pick)
    start.focus_force()
    root.update()
    chain = []
    current = root.tk.call("focus")
    try:
        for _ in range(40):
            key = str(current)
            if not key or key in chain:
                break
            chain.append(key)
            current = root.tk.call("tk_focusNext", current)
    except tk.TclError as exc:
        pytest.skip("Tk focus traversal unavailable in this interpreter: %s" % exc)
    assert str(ui_focus.focus_target(instance.rows["fontfix"].toggle)) in chain
    assert str(ui_focus.focus_target(instance.btn_go)) in chain
    assert str(ui_focus.focus_target(instance.btn_undo)) in chain


def test_button_focus_ring_is_visible_and_restored(ui_app):
    instance, root, _game_dir = ui_app
    instance._show_page("process")
    _pump(root)
    target = ui_focus.focus_target(instance.btn_go)
    target.focus_force()
    root.update()
    assert int(target.cget("highlightthickness")) == 2
    assert str(target.cget("highlightcolor")) in (
        ui_tokens.PALETTES["light"]["focus"],
        ui_tokens.PALETTES["dark"]["focus"])
    root.focus_set()
    root.update()
    assert int(target.cget("highlightthickness")) == 0


def test_entry_focus_uses_strong_border(ui_app):
    instance, root, _game_dir = ui_app
    instance._show_page("process")
    _pump(root)
    target = ui_focus.focus_target(instance.entry_dir)
    target.focus_force()
    root.update()
    assert int(instance.entry_dir.cget("border_width")) == 2
    assert instance.entry_dir.cget("border_color") == ui_tokens.PAIRS["focus"]
    root.focus_set()
    root.update()
    assert int(instance.entry_dir.cget("border_width")) == 1


def test_install_requires_confirmation_before_spawning(ui_app):
    instance, _root, _game_dir = ui_app
    with mock.patch.object(appgui.messagebox, "askyesno", return_value=False), \
            mock.patch.object(instance, "_spawn") as spawn:
        instance.install()
    assert not spawn.called


def test_revert_requires_confirmation_and_installed_work(ui_app):
    instance, _root, _game_dir = ui_app
    instance._installed = {"shim": True, "ours": True, "current": True,
                           "intro": False, "intro_ours": False,
                           "intro_current": False}
    with mock.patch.object(appgui.messagebox, "askyesno", return_value=False), \
            mock.patch.object(instance, "_spawn") as spawn:
        instance.revert()
    assert not spawn.called

    instance._installed = {}
    with mock.patch.object(appgui.messagebox, "showinfo") as info, \
            mock.patch.object(instance, "_spawn") as spawn:
        instance.revert()
    assert info.called and not spawn.called


def test_clear_log_requires_confirmation(ui_app):
    instance, _root, _game_dir = ui_app
    instance._log("one line\n")
    with mock.patch.object(appgui.messagebox, "askyesno", return_value=False):
        instance.clear_log()
    assert "one line" in instance._log_text()
    with mock.patch.object(appgui.messagebox, "askyesno", return_value=True):
        instance.clear_log()
    assert instance._log_text() == ""


def test_unknown_support_is_not_treated_as_supported(ui_app):
    instance, _root, _game_dir = ui_app
    instance._apply_feature_support({"feature_support": {
        fid: {"supported": None, "reasons": ["test unsupported"]}
        for fid in instance.rows
    }})
    for fid, row in instance.rows.items():
        assert row.supported is False, fid
        assert instance.var_on[fid].get() is False, fid
        assert row.toggle.cget("state") == "disabled", fid
        assert "test unsupported" not in row.reason_var.get(), fid


def test_english_support_reason_is_localized(ui_app):
    instance, _root, _game_dir = ui_app
    instance._apply_feature_support({"feature_support": {
        "fontfix": {"supported": False, "mechanism": None,
                    "reasons": ["MV/MZ intro bypass is not implemented"]},
        "intro": {"supported": True, "reasons": []},
        "runtime_compat": {"supported": True, "reasons": []},
        "gallery": {"supported": True, "reasons": []},
    }})
    text = instance.rows["fontfix"].reason_var.get()
    assert "not implemented" not in text
    assert "RPG Maker" in text and "暂不支持" in text


def test_simulation_confirm_buttons_are_disabled_before_launch(ui_app):
    instance, _root, _game_dir = ui_app
    assert instance.btn_sim_success.cget("state") == "disabled"
    assert instance.btn_sim_failure.cget("state") == "disabled"
    assert instance.btn_sim_finish.cget("state") == "disabled"


def test_successful_cleanup_hides_stale_confirmation_buttons(ui_app):
    instance, _root, _game_dir = ui_app
    instance.sim_session = object()
    instance.sim_launched = True
    instance.sim_confirmed = True
    instance._pack_sim_confirm()
    instance._simulation_cleaned([])
    assert instance.sim_session is None
    assert instance.sim_confirm_frame.winfo_manager() == ""
    assert instance.btn_sim_gameplay.cget("state") == "disabled"


def test_shortcuts_are_bound(ui_app):
    instance, root, _game_dir = ui_app
    assert root.bind("<Control-o>")
    assert root.bind("<F5>")
    assert root.bind("<Control-l>")
    assert root.bind("<Control-Return>")
