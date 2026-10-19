"""Layout and typography regressions for the 900x620 desktop window."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import appgui  # noqa: E402


pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")


def _pump(root, rounds=8):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def test_sticky_actions_are_visible_at_minimum_size(ui_app):
    app, root, _game = ui_app
    root.geometry("900x620")
    _pump(root)
    app._show_page("process")
    _pump(root)
    action = app.btn_go
    assert action.winfo_ismapped()
    top = root.winfo_rooty()
    bottom = top + root.winfo_height()
    assert action.winfo_rooty() >= top
    assert action.winfo_rooty() + action.winfo_height() <= bottom + 1
    assert app.btn_dry.cget("state") == "normal"


def test_wide_window_uses_two_feature_columns(ui_app):
    app, root, _game = ui_app
    root.geometry("1600x900")
    app._show_page("process")
    _pump(root)
    assert app._feature_columns == 2
    assert len(app.feature_cards) == 4
    assert app.feature_cards[1].grid_info()["column"] == 1
    assert app.feature_cards[2].grid_info()["row"] == 1
    assert app.page_host.winfo_width() >= 1200


def test_narrow_window_keeps_one_feature_column(ui_app):
    app, root, _game = ui_app
    root.geometry("900x620")
    app._show_page("process")
    _pump(root)
    assert app._feature_columns == 1
    assert all(card.grid_info()["column"] == 0
               for card in app.feature_cards)


def test_help_page_lists_every_feature(ui_app):
    app, root, _game = ui_app
    app._show_page("help")
    _pump(root)
    assert app.active_page == "help"
    for fid in appgui.features.ids():
        assert fid in app.help_cards
    assert "fontfix" in app.help_cards

    root.geometry("1600x900")
    _pump(root)
    app._apply_responsive()
    _pump(root)
    assert app._help_columns == 2
    assert list(app.help_cards.values())[1].grid_info()["column"] == 1


def test_dynamic_wrap_replaces_fixed_card_widths(ui_app):
    app, root, _game = ui_app
    app._show_page("library")
    app._render_library()
    _pump(root, 12)
    path_labels = [
        widget for widget in _walk(app.library_scroll)
        if isinstance(widget, ctk.CTkLabel)
        and str(widget.cget("text")).startswith(str(_game))
    ]
    assert path_labels
    assert all(int(label.cget("wraplength")) > 100 for label in path_labels)
    assert all(label.winfo_width() > 100 for label in path_labels)


def test_no_body_font_below_ten_points(ui_app):
    app, root, _game = ui_app
    for page in app.pages:
        app._show_page(page)
        _pump(root, 2)
        for widget in _walk(app.pages[page]):
            if not isinstance(widget, (ctk.CTkLabel, ctk.CTkButton,
                                       ctk.CTkCheckBox, ctk.CTkEntry)):
                continue
            font = widget.cget("font")
            if hasattr(font, "cget"):
                assert int(font.cget("size")) >= 10, widget


def test_window_geometry_is_saved_in_logical_pixels(ui_app):
    app, root, _game = ui_app
    root.geometry("900x620")
    _pump(root)
    app._save_geometry()
    saved = app.state["window"]
    assert 880 <= saved["width"] <= 940, saved
    assert 600 <= saved["height"] <= 660, saved
    if hasattr(app, "var_window"):
        assert "900" in app.var_window.get()


def test_library_recognises_rpgmaker_without_fake_unavailable(ui_app, tmp_path):
    app, root, _game = ui_app
    mv = tmp_path / "MV Game"
    (mv / "www" / "js").mkdir(parents=True)
    (mv / "www" / "js" / "rpg_core.js").write_text(
        "Utils.RPGMAKER_VERSION = '1.6.2';", encoding="utf-8")
    level, status = app._library_status(str(mv))
    assert level == "supported"
    assert "RPG Maker MV" in status


def test_offline_library_entry_stays_visible_unavailable(ui_app, tmp_path):
    app, root, _game = ui_app
    missing = tmp_path / "Moved Game"
    app.state["games"] = [{"path": str(missing), "name": "Moved",
                           "available": False}]
    app._render_library()
    _pump(root)
    texts = [str(widget.cget("text")) for widget in _walk(app.library_scroll)
             if isinstance(widget, ctk.CTkLabel)]
    assert "Moved" in texts
    assert "路径不可用" in texts
