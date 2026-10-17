"""Build this app with temp preferences, inspect widgets, capture own window."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import ctypes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import customtkinter as ctk
from PIL import ImageGrab
import appgui
import app_state
import engine_adapters
import features


def _pump(root):
    for _ in range(4):
        root.update_idletasks()
        root.update()


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    with tempfile.TemporaryDirectory(prefix="rpykit-gui-11-") as folder:
        temp = Path(folder)
        os.environ["RPYKIT_WORK"] = str(temp / "work")
        game = temp / "sample"
        (game / "renpy").mkdir(parents=True)
        (game / "game").mkdir()
        for mode in ("dark", "light"):
            ctk.set_appearance_mode(mode)
            root = ctk.CTk()
            root.withdraw()
            state = app_state.default_state()
            state.update(appearance=mode, window={"width": 900, "height": 620})
            app = appgui.App(root, state=state, state_path=str(temp / (mode + "-state.json")))
            root.geometry("900x620+100+80")
            app.game_dir = str(game)
            support = {fid: {"supported": True, "reasons": ["Only recognized built-in gallery and replay conditions are bypassed; game-specific custom achievement, inventory and scripted unlock conditions remain unsupported."]}
                       for fid in features.ids()}
            support["intro"] = {"supported": False, "reasons": ["Synthetic unsupported engine path; reason must remain readable."]}
            app._apply_feature_support({"feature_support": support})
            root.deiconify()
            _pump(root)
            rows = {}
            for fid, row in app.rows.items():
                label = row.reason_label
                rows[fid] = {"reason_visible": bool(label.winfo_ismapped()),
                             "reason_height": label.winfo_height(),
                             "reason_requested": label.winfo_reqheight(),
                             "card_height": row.card.winfo_height(),
                             "reason_bottom": label.winfo_y() + label.winfo_height(),
                             "reason_text": row.reason_var.get()}
            canvas = next(w._parent_canvas for w in _walk(app.pages["process"]) if isinstance(w, ctk.CTkScrollableFrame))
            def capture(suffix):
                _pump(root)
                # Capture this exact window, including when another app is
                # foreground; never crop unrelated desktop content.
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
                ImageGrab.grab(window=hwnd).save(output / (mode + "-" + suffix + ".png"))
            capture("top")
            canvas.yview_moveto(0.45)
            capture("actions")
            actions = {name: {"height": getattr(app, name).winfo_height(), "mapped": bool(getattr(app, name).winfo_ismapped())}
                       for name in ("btn_go", "btn_dry", "btn_undo")}
            unknown = temp / "unknown"
            unknown.mkdir(exist_ok=True)
            app.game_dir = str(unknown)
            app._apply_feature_support(engine_adapters.survey(str(unknown)))
            app._set_buttons()
            unknown_disabled = all(getattr(app, name).cget("state") == "disabled" for name in ("btn_go", "btn_dry", "btn_undo"))
            (game / "js").mkdir(exist_ok=True)
            (game / "js/rpg_core.js").write_text("Utils.RPGMAKER_VERSION='1.6.2';", encoding="utf-8")
            app.game_dir = str(game)
            app._apply_feature_support(engine_adapters.survey(str(game)))
            app._set_buttons()
            ambiguous_disabled = all(getattr(app, name).cget("state") == "disabled" for name in ("btn_go", "btn_dry", "btn_undo"))
            reports.append({"mode": mode, "rows": rows, "actions": actions,
                            "unknown_disabled": unknown_disabled, "ambiguous_disabled": ambiguous_disabled})
            app._save_geometry()
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()
            (game / "js/rpg_core.js").unlink()
        (output / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    result = verify(parser.parse_args().output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
