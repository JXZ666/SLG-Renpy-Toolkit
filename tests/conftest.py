"""Shared Tk window for the GUI test suites.

Tk on this Windows build can fail to load its Tcl library when a later test
creates a new interpreter after an earlier one was destroyed.  Creating one
root for the whole pytest session avoids that platform failure and also keeps
the legacy `test_gui` script and the newer UI tests on the same interpreter.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_state  # noqa: E402
import appgui  # noqa: E402

ctk = pytest.importorskip("customtkinter")

_SHARED_ROOT = None
try:
    _SHARED_ROOT = ctk.CTk()
    _SHARED_ROOT.withdraw()
    # `test_gui.main()` (and CTkFont's default-root lookup) use this root.
    tk._default_root = _SHARED_ROOT
except tk.TclError as _exc:  # pragma: no cover - environment-specific
    _SHARED_ROOT = None
    _SHARED_ROOT_ERROR = str(_exc)
else:
    _SHARED_ROOT_ERROR = ""


def shared_root():
    """The root created at collection time, or None if Tk is unavailable."""
    return _SHARED_ROOT


def _game(base):
    game = Path(base) / "Synthetic Game"
    (game / "renpy").mkdir(parents=True, exist_ok=True)
    (game / "game").mkdir(exist_ok=True)
    return game


def _support():
    return {
        fid: {"supported": True, "mechanism": "font_name_map", "reasons": []}
        for fid in appgui.features.ids()
    }


def _pump(root, rounds=8):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


@pytest.fixture(scope="session")
def ui_window(tmp_path_factory):
    root = shared_root()
    if root is None:
        pytest.skip("Tk interpreter unavailable: %s" % _SHARED_ROOT_ERROR)
    # A previous script suite may have left widgets or geometry behind.
    for child in list(root.winfo_children()):
        try:
            child.destroy()
        except tk.TclError:
            pass
    root.deiconify()
    base = tmp_path_factory.mktemp("shared-ui")
    game = _game(base)
    state = app_state.default_state()
    state.update(
        appearance="light",
        window={"width": 900, "height": 620},
        games=[{"path": str(game), "name": "Synthetic", "available": True}],
        active_game="",
    )
    app = appgui.App(root, state=state,
                     state_path=str(base / "ui_state.json"))
    root.geometry("900x620")
    root.deiconify()
    _pump(root)
    yield app, root, game


@pytest.fixture
def ui_app(ui_window):
    """Reset the shared window to the default process-page state."""
    app, root, game = ui_window
    app.state["window"] = {"width": 900, "height": 620}
    root.geometry("900x620")
    app.state["games"] = [{"path": str(game), "name": "Synthetic",
                           "available": True}]
    app.state["active_game"] = ""
    app.game_dir = str(game)
    app.var_dir.set(str(game))
    app._installed = None
    app._survey = None
    app.scan_failed = False
    app.sim_session = None
    app.sim_preparing = False
    app.sim_launched = False
    app.sim_confirmed = False
    app.sim_gameplay_confirmed = False
    app.sim_process_exited = False
    app.sim_cleanup_running = False
    app.busy = False
    app._reset_simulation_status()
    app.log.configure(state="normal")
    app.log.delete("1.0", "end")
    app.log.configure(state="disabled")
    app._update_log_actions()
    for entry in appgui.features.CATALOG:
        app.var_on[entry["id"]].set(bool(entry.get("default_on", True)))
    app._apply_feature_support({"feature_support": _support()})
    app._set_buttons()
    app._show_page("process")
    _pump(root)
    return app, root, game


def pytest_sessionfinish(session, exitstatus):
    """Destroy the one shared Tk root exactly once."""
    root = shared_root()
    if root is None:
        return
    try:
        for timer in root.tk.call("after", "info"):
            root.tk.call("after", "cancel", timer)
        root.destroy()
    except tk.TclError:
        pass
