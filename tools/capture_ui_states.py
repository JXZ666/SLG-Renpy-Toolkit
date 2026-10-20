"""Capture every page in both themes and report structural UI evidence.

This is a developer aid, not a release artifact.  It uses only a synthetic game
root and writes screenshots to a caller-provided folder (normally a temporary
directory).  The JSON report is the part worth keeping in review: it records the
sticky action position, focus traversal chain, and wrapped-label widths without
committing large PNGs to the repository.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile

import customtkinter as ctk
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_state  # noqa: E402
import appgui  # noqa: E402
import features  # noqa: E402
import ui_focus  # noqa: E402

PAGES = ("process", "library", "toolbox", "log", "help", "settings")


def _pump(root, rounds=5):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _focus_chain(root, widget):
    target = ui_focus.focus_target(widget)
    if target is None:
        return []
    try:
        target.focus_set()
        root.update()
        chain = []
        current = root.tk.call("focus")
        seen = set()
        for _ in range(40):
            key = str(current)
            if not key or key in seen:
                break
            seen.add(key)
            chain.append(key)
            current = root.tk.call("tk_focusNext", current)
        return chain
    except Exception:  # noqa: BLE001 - capture is best effort
        return []


def _fake_survey(game_dir):
    return {
        "game_dir": str(game_dir), "ok": True, "verdict": "warn",
        "label": "有风险", "engine": {"id": "renpy", "version": "8.3.0"},
        "renpy": {"version": "8.3.0", "name": "Sample Game"},
        "python": {"major": 3}, "arch": "both",
        "sources": {"loose_rpy": 12, "loose_rpyc": 12, "rpa": ["archive.rpa"]},
        "splash": {"found": True},
        "reasons": ["这是合成样本，仅用于界面截图。"],
    }


def _support():
    return {
        "fontfix": {"supported": True, "mechanism": "font_name_map",
                    "reasons": []},
        "intro": {"supported": True, "mechanism": "label_overrides",
                  "reasons": []},
        "runtime_compat": {
            "supported": True, "mechanism": "luna_say_bridge",
            "reasons": ["Verified say API; Real Luna session verification is still required."],
        },
        "gallery": {
            "supported": False, "mechanism": None,
            "reasons": ["Custom image/replay lock logic needs a dedicated adapter."],
        },
        "translation": {"supported": True, "mechanism": "renpy_live_bridge",
                        "reasons": ["合成界面样本，不代表当前游戏通过运行验收。"]},
    }


def capture(output, width=900, height=620):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = []
    with tempfile.TemporaryDirectory(prefix="rpykit-ui-capture-") as folder:
        temp = Path(folder)
        game = temp / "Sample Game"
        (game / "renpy").mkdir(parents=True)
        (game / "game").mkdir()
        for mode in ("light", "dark"):
            ctk.set_appearance_mode(mode)
            root = ctk.CTk()
            root.withdraw()
            state = app_state.default_state()
            state.update(
                appearance=mode,
                window={"width": width, "height": height},
                games=[{"path": str(game), "name": "合成样本",
                        "available": True}],
                active_game="",
            )
            app = appgui.App(root, state=state,
                             state_path=str(temp / (mode + "-state.json")))
            root.geometry("%dx%d+80+60" % (width, height))
            app.game_dir = str(game)
            app.var_dir.set(str(game))
            survey = _fake_survey(game)
            app._set_compat(survey)
            app._apply_feature_support({"feature_support": _support()})
            app._paint_chips({key: False for feature in features.CATALOG
                              for key in feature["state"].values()})
            app._set_state("warn", "已载入合成样本，可先模拟安装验证。")
            app._set_buttons()
            root.deiconify()
            _pump(root)
            page_reports = {}
            focus = {}
            chain = []
            for page in PAGES:
                app._show_page(page)
                _pump(root, 8)
                if page == "process":
                    app.process_scroll._parent_canvas.yview_moveto(0)
                    _pump(root)
                image = ImageGrab.grab(
                    window=ctypes.windll.user32.GetParent(root.winfo_id()))
                filename = "%s-%dx%d-%s.png" % (mode, width, height, page)
                image.save(output / filename)
                page_reports[page] = {
                    "screenshot": filename,
                    "width": image.width,
                    "height": image.height,
                    "widgets": len(list(_walk(app.pages[page]))),
                }
                if page == "process":
                    action = app.btn_go
                    root_top = root.winfo_rooty()
                    root_bottom = root_top + root.winfo_height()
                    action_bottom = action.winfo_rooty() + action.winfo_height()
                    page_reports["process"]["sticky_action"] = {
                        "mapped": bool(action.winfo_ismapped()),
                        "top": action.winfo_rooty(),
                        "bottom": action_bottom,
                        "window_top": root_top,
                        "window_bottom": root_bottom,
                        "visible": root_top <= action.winfo_rooty()
                                   and action_bottom <= root_bottom + 1,
                        "height": action.winfo_height(),
                    }
                    for name, widget in (
                            ("pick", app.btn_pick),
                            ("entry", app.entry_dir),
                            ("fontfix", app.rows["fontfix"].toggle),
                            ("simulate", app.btn_dry),
                            ("install", app.btn_go),
                            ("undo", app.btn_undo)):
                        target = ui_focus.focus_target(widget)
                        focus[name] = {
                            "takefocus": str(target.cget("takefocus")) if target else "",
                            "target": str(target) if target else "",
                        }
                    chain = _focus_chain(root, app.btn_go)
            report.append({
                "mode": mode,
                "viewport": {"width": width, "height": height},
                "feature_columns": getattr(app, "_feature_columns", 1),
                "pages": page_reports,
                "focus": focus,
                "focus_chain": chain,
                "buttons": {
                    "install_text_color": str(app.btn_go.cget("text_color")),
                    "simulate_text_color": str(app.btn_dry.cget("text_color")),
                    "theme": app._theme,
                },
            })
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, default=900)
    parser.add_argument("--height", type=int, default=620)
    args = parser.parse_args(argv)
    report = capture(args.output, args.width, args.height)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
