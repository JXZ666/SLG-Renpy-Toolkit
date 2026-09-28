"""Production CustomTkinter interface for the Ren'Py toolkit.

The view reads feature definitions from ``features.CATALOG`` and delegates
installation, rollback and isolated simulation to the existing back end.
Game-library entries and presentation preferences are stored outside game
directories by :mod:`app_state`.
"""

import argparse
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

import app_state
import branding
import cmd_fontfix
import compat
import features
import simulation

TITLE = branding.APP_NAME

# Windows 11's semantic colours, dark on the left, light on the right. The
# light variants are the darker, higher-contrast pair, because the same hue
# that reads on #1c1c1c is invisible on #fafafa.
_GLYPH = {"ok": "\u221a", "warn": "!", "bad": "\u00d7", "info": "\u00b7"}

# Used only if sv-ttk is missing or the style has not been applied yet.
_COLORS = {
    "light": {
        "bg": "#f4f5fb", "sidebar": "#ffffff", "panel": "#ffffff",
        "panel_alt": "#f8f8fd", "fg": "#202136", "dim": "#777a92",
        "border": "#e3e4ef", "accent": "#7057e8", "accent_hover": "#6046d3",
        "accent_soft": "#eeeaff", "ok": "#18794e", "warn": "#9a6400",
        "bad": "#bf3b4b", "input": "#ffffff", "select": "#ded8ff",
    },
    "dark": {
        "bg": "#11121a", "sidebar": "#161824", "panel": "#1a1c29",
        "panel_alt": "#222437", "fg": "#f0eff8", "dim": "#a0a3b7",
        "border": "#303349", "accent": "#9a85ff", "accent_hover": "#b2a3ff",
        "accent_soft": "#302a4a", "ok": "#79d8a4", "warn": "#ffca69",
        "bad": "#ff8797", "input": "#202232", "select": "#463b72",
    },
}
_PAIR = {name: (_COLORS["light"][name], _COLORS["dark"][name])
         for name in _COLORS["light"]}


class _Sink:
    """File-like object that pushes anything written to it onto a queue.

    cmd_fontfix reports with print(), and it has to keep doing that to stay
    usable from the console entry point. Swapping stdout for this gets the
    window the same lines without touching a single reporting call.
    """

    def __init__(self, q):
        self._q = q

    def write(self, text):
        if text:
            self._q.put(text)

    def flush(self):
        pass


def _namespace(game_dir, revert=False, dry_run=False, force=False, skip_intro=True,
               feature_ids=None):
    """The argument set cmd_fontfix.run() expects.

    Mode is pinned to luna: `full` also forces config.language, and installing
    that on a game that is meant to be translated at runtime would make the
    game render one Chinese layer and the translator produce a second.

    Both spellings of the feature selection are always filled in and always
    agree, so the worker never has to care which one is canonical. With no
    `feature_ids` the defaults decide. `skip_intro=False` subtracts the intro
    from whatever was asked for - that is the old single-switch spelling, kept
    working for callers that predate the catalogue, and honoured even beside an
    explicit list rather than quietly losing to it.
    """
    if feature_ids is None:
        feature_ids = features.default_selection()
    if not skip_intro:
        feature_ids = [f for f in feature_ids if f != "intro"]
    return argparse.Namespace(
        game_dir=game_dir, work=None, mode="luna",
        lang="chinesesimplified", revert=revert, force=force, dry_run=dry_run,
        features=list(feature_ids), skip_intro=skip_intro)


def _system_theme():
    """Which way Windows itself is set, so the window opens matching it."""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion"
                r"\Themes\Personalize") as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except Exception:  # noqa: BLE001 - a preference, never worth failing over
        return "dark"


def _palette(root, theme=None):
    """Return the concrete palette for the currently resolved appearance."""
    if theme not in ("dark", "light"):
        theme = "dark"
    pal = dict(_COLORS[theme])
    pal["selbg"] = pal["select"]
    pal["selfg"] = pal["fg"]
    pal["theme"] = theme
    return pal


def _chip(entry, state):
    """(level, text) for one feature, read through the names its entry gives.

    Nothing here is keyed on a feature id, so a feature added to features.py
    gets a chip without this module knowing what it installs.
    """
    keys = entry.get("state")
    if not state or not keys:
        return "info", "未安装"
    if not state.get(keys["installed"]):
        return "info", "未安装"
    if not state.get(keys["ours"]):
        return "warn", "外来文件"
    if not state.get(keys["current"]):
        return "warn", "旧模板"
    return "ok", "已安装"


def _describe(s):
    """One line naming what kind of game this folder holds."""
    r = s["renpy"]
    py = s["python"]["major"]
    src = s["sources"]
    bits = [s["label"], "Ren'Py %s" % (r["version"] or "版本未知")]
    if r.get("name"):
        bits.append(r["name"])
    bits.append("Python %s" % (py if py else "?"))
    bits.append("双架构" if s["arch"] == "both" else (s["arch"] or "架构未知"))
    scripts = src.get("loose_rpy", 0) + src.get("loose_rpyc", 0)
    if src.get("rpa"):
        bits.append("%d 个归档 / %d 个可读脚本" % (len(src["rpa"]), scripts))
    else:
        bits.append("%d 个可读脚本" % scripts)
    bits.append("开场 logo %s" % ("找到了" if s["splash"].get("found") else "没找到"))
    return " \u00b7 ".join(bits)


def _reasons(s):
    return "\n".join("\u2014\u2014 " + x for x in (s.get("reasons") or []))


class _FeatureRow:
    """The widgets and current support state for one catalogue entry."""

    def __init__(self, entry, card, toggle, chip_var, chip_label,
                 reason_var, reason_label):
        self.id = entry["id"]
        self.entry = entry
        self.card = card
        self.toggle = toggle
        self.chip_var = chip_var
        self.chip_label = chip_label
        self.reason_var = reason_var
        self.reason_label = reason_label
        self.supported = True


class _OperationMixin:
    """Shared operation and simulation state-machine methods."""

    # --- state ------------------------------------------------------------

    _SIM_STAGE_NAMES = {
        "compat": "\u517c\u5bb9\u9884\u68c0",
        "copy": "\u590d\u5236\u6e38\u620f\u526f\u672c",
        "install": "\u6a21\u62df\u5b89\u88c5\u8865\u4e01",
        "launch": "\u542f\u52a8\u526f\u672c",
        "confirm": "\u786e\u8ba4\u4e3b\u83dc\u5355",
    }

    _SIM_STAGE_DEFAULTS = {
        "compat": "\u5c1a\u672a\u5f00\u59cb",
        "copy": "\u7b49\u5f85\u590d\u5236",
        "install": "\u7b49\u5f85\u6a21\u62df\u5b89\u88c5",
        "launch": "\u5c1a\u672a\u542f\u52a8",
        "confirm": "\u7b49\u5f85\u542f\u52a8\u9a8c\u8bc1",
    }




    def _apply_simulation_steps(self, steps):
        if not isinstance(steps, (list, tuple)):
            return
        for step in steps:
            if not isinstance(step, dict):
                continue
            stage_id = step.get("id")
            if stage_id not in self._SIM_STAGE_NAMES:
                continue
            self._set_sim_stage(stage_id, step.get("status"), step.get("message"))

    def simulate_run(self):
        if self.busy or self.sim_session is not None:
            return
        feature_ids = self._ticked()
        if not feature_ids:
            messagebox.showinfo(
                TITLE, "\u8bf7\u5148\u52fe\u9009\u81f3\u5c11\u4e00\u4e2a\u53ef\u7528\u529f\u80fd\u3002")
            return
        if not self.game_dir or not os.path.isdir(os.path.join(self.game_dir, "game")):
            self._set_sim_result("bad", "\u8bf7\u5148\u9009\u62e9\u6709\u6548\u7684\u6e38\u620f\u6839\u76ee\u5f55\u3002")
            return

        game_dir = self.game_dir
        self._reset_simulation_status()
        self.sim_preparing = True
        self.busy = True
        self._set_sim_stage("compat", "running",
                            "\u6b63\u5728\u68c0\u67e5\u6240\u9009\u529f\u80fd\u9700\u8981\u7684 Ren'Py API")
        self._set_sim_result("warn", "\u6b63\u5728\u8fdb\u884c\u517c\u5bb9\u9884\u68c0\u2026")
        self._set_buttons()
        threading.Thread(target=self._simulation_prepare_worker,
                         args=(game_dir, list(feature_ids)), daemon=True).start()

    def _simulation_prepare_worker(self, game_dir, feature_ids):
        try:
            survey = compat.survey(game_dir, quick=True)
            support_map = survey.get("feature_support", {}) if isinstance(survey, dict) else {}
            unsupported = []
            if isinstance(support_map, dict):
                for fid in feature_ids:
                    spec = support_map.get(fid)
                    if isinstance(spec, dict) and spec.get("supported") is False:
                        reasons = spec.get("reasons") or []
                        if isinstance(reasons, str):
                            reasons = [reasons]
                        unsupported.append("%s: %s" % (
                            features.title_of(fid), "; ".join(map(str, reasons))))
            if unsupported:
                steps = [{"id": "compat", "status": "failed",
                          "message": "; ".join(unsupported)}]
                self.queue.put(("__sim_failed__",
                                "\u6240\u9009\u529f\u80fd\u4e0d\u517c\u5bb9\uff0c\u5df2\u505c\u6b62\uff0c\u672a\u590d\u5236\u6216\u4fee\u6539\u6e38\u620f\u3002",
                                steps))
                return
            self.queue.put(("__sim_stage__", "compat", "success",
                            "\u6240\u9009\u529f\u80fd\u7684 API \u68c0\u67e5\u901a\u8fc7"))
            self.queue.put(("__sim_stage__", "copy", "running",
                            "\u6b63\u5728\u590d\u5236\u5230\u9694\u79bb\u76ee\u5f55"))
            def on_log(line):
                self.queue.put(("__sim_log__", line))
                lowered = str(line).lower()
                if "installing patches" in lowered:
                    self.queue.put(("__sim_stage__", "copy", "success",
                                    "\u9694\u79bb\u526f\u672c\u590d\u5236\u5b8c\u6210"))
                    self.queue.put(("__sim_stage__", "install", "running",
                                    "\u6b63\u5728\u5728\u526f\u672c\u4e2d\u5b89\u88c5\u8865\u4e01"))
            session = simulation.prepare(
                game_dir, feature_ids,
                log_callback=on_log)
            self.queue.put(("__sim_prepared__", session))
        except Exception as exc:  # noqa: BLE001 - display every simulation failure
            steps = getattr(exc, "steps", None)
            self.queue.put(("__sim_failed__",
                            "%s: %s" % (type(exc).__name__, exc), steps))

    def _simulation_failed(self, message, steps=None):
        self.sim_preparing = False
        self.busy = False
        self._apply_simulation_steps(steps)
        if not any(level == "bad" for level, _status, _msg
                   in self.sim_stage_state.values()):
            self._set_sim_stage("install", "failed", message)
        self._set_sim_result("bad", "\u6a21\u62df\u5931\u8d25\uff1a" + str(message))
        self._show_log()
        self._set_buttons()
        if self.close_after_prepare:
            self._destroy_root()

    def _simulation_prepared(self, session):
        self.sim_preparing = False
        self.busy = False
        self.sim_session = session
        self._apply_simulation_steps(getattr(session, "steps", None))
        self._set_buttons()
        if self.close_after_prepare:
            self._cleanup_simulation(stop=False, close_after=True)
            return
        launchers = list(getattr(session, "launchers", None) or [])
        if not launchers:
            self._set_sim_stage("launch", "failed",
                                "\u6ca1\u6709\u627e\u5230\u53ef\u7528\u7684 .exe \u542f\u52a8\u5668")
            self._set_sim_result(
                "bad", "\u6a21\u62df\u5b89\u88c5\u6210\u529f\uff0c\u4f46\u6e38\u620f\u76ee\u5f55\u4e2d\u6ca1\u6709 .exe\uff0c\u65e0\u6cd5\u542f\u52a8\u9a8c\u8bc1\u3002")
            self._cleanup_simulation(stop=False)
            return
        rel_launcher = self._choose_launcher(launchers)
        if not rel_launcher:
            self._set_sim_stage("launch", "cancelled",
                                "\u7528\u6237\u53d6\u6d88\u4e86\u542f\u52a8\u5668\u9009\u62e9")
            self._set_sim_result("warn", "\u6a21\u62df\u5b89\u88c5\u6210\u529f\uff0c\u542f\u52a8\u5df2\u53d6\u6d88\uff0c\u526f\u672c\u5c06\u88ab\u6e05\u7406\u3002")
            self._cleanup_simulation(stop=False)
            return
        self._set_sim_stage("launch", "running",
                            "\u51c6\u5907\u542f\u52a8 " + str(rel_launcher))
        self.busy = True
        self._set_buttons()
        threading.Thread(target=self._simulation_launch_worker,
                         args=(session, rel_launcher), daemon=True).start()


    def _simulation_launch_worker(self, session, rel_launcher):
        try:
            process = session.launch(rel_launcher)
            if process is None:
                raise RuntimeError("\u542f\u52a8\u5668\u672a\u521b\u5efa\u8fdb\u7a0b")
            self.queue.put(("__sim_launched__", process))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("__sim_launch_failed__", "%s: %s" % (type(exc).__name__, exc)))

    def _simulation_launched(self, _process):
        self.busy = False
        self.sim_launched = True
        self.sim_process_exited = False
        self._set_sim_stage("launch", "running",
                            "\u8fdb\u7a0b\u5df2\u542f\u52a8\uff1b\u8bf7\u68c0\u67e5\u6e38\u620f\u7a97\u53e3")
        self._set_sim_stage("confirm", "waiting",
                            "\u8bf7\u5728\u6e38\u620f\u4e2d\u786e\u8ba4\u662f\u5426\u8fdb\u5165\u4e3b\u83dc\u5355")
        self._set_sim_result(
            "warn", "\u7b49\u5f85\u786e\u8ba4\uff1a\u6e38\u620f\u8fdb\u7a0b\u5df2\u542f\u52a8\uff0c\u4f46\u8fd9\u4e0d\u7b49\u4e8e\u8fd0\u884c\u6210\u529f\u3002")
        self.sim_confirm_frame.pack(anchor="w", pady=(9, 0))
        self._set_buttons()
        if self.close_after_cleanup:
            self._cleanup_simulation(stop=True, close_after=True)
            return
        self.root.after(400, self._poll_simulation)

    def _simulation_launch_failed(self, message):
        self.busy = False
        self._set_sim_stage("launch", "failed", message)
        self._set_sim_result("bad", "\u65e0\u6cd5\u542f\u52a8\u6e38\u620f\uff1a" + str(message))
        self.sim_confirm_frame.pack_forget()
        self._show_log()
        self._set_buttons()
        self._cleanup_simulation(stop=False, close_after=self.close_after_cleanup)

    def _poll_simulation(self):
        session = self.sim_session
        if session is None or not self.sim_launched or self.sim_process_exited:
            return
        try:
            code = session.poll()
        except Exception as exc:  # noqa: BLE001
            self._simulation_launch_failed("%s: %s" % (type(exc).__name__, exc))
            return
        if code is None:
            self.root.after(400, self._poll_simulation)
            return
        self.sim_process_exited = True
        if code != 0 and not self.sim_confirmed:
            message = "\u6e38\u620f\u8fdb\u7a0b\u5f02\u5e38\u9000\u51fa\uff0c\u9000\u51fa\u7801 %s" % code
            self._set_sim_stage("launch", "failed", message)
            self._set_sim_result("bad", "\u542f\u52a8\u5931\u8d25\uff1a" + message)
            self.sim_confirm_frame.pack_forget()
            self._show_log()
            self._cleanup_simulation(stop=False)
            return
        if code == 0 and not self.sim_confirmed:
            self._set_sim_stage(
                "launch", "pending_confirmation",
                "进程已正常退出；是否进入主菜单仍需你确认")
            self._set_sim_result(
                "warn", "\u8fdb\u7a0b\u5df2\u9000\u51fa\uff08\u9000\u51fa\u7801 0\uff09\uff0c\u4ecd\u9700\u4f60\u786e\u8ba4\u662f\u5426\u8fdb\u5165\u4e3b\u83dc\u5355\u3002")
            return
        if code == 0 and self.sim_confirmed:
            self._set_sim_stage(
                "launch", "success",
                "进程已正常退出，且你已确认看到主菜单")
        self._cleanup_simulation(stop=False)

    def confirm_simulation_success(self):
        if self.sim_session is None or not self.sim_launched:
            return
        self.busy = True
        self._set_sim_stage("confirm", "running",
                            "\u6b63\u5728\u8bb0\u5f55\u4f60\u7684\u4e3b\u83dc\u5355\u786e\u8ba4")
        self._set_sim_result("warn", "\u6b63\u5728\u9a8c\u8bc1\u4e3b\u83dc\u5355\u786e\u8ba4\u2026")
        self._set_buttons()
        threading.Thread(target=self._simulation_confirm_worker,
                         args=(self.sim_session,), daemon=True).start()

    def _simulation_confirm_worker(self, session):
        try:
            session.confirm_main_menu()
            self.queue.put(("__sim_confirmed__", None))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("__sim_confirm_failed__", "%s: %s" % (type(exc).__name__, exc)))

    def _simulation_confirmed(self):
        self.busy = False
        self.sim_confirmed = True
        self._set_sim_stage("confirm", "success",
                            "\u7528\u6237\u5df2\u786e\u8ba4\u770b\u5230\u4e3b\u83dc\u5355")
        self._set_sim_result(
            "ok", "\u8fd0\u884c\u9a8c\u8bc1\u6210\u529f\uff1a\u4f60\u5df2\u786e\u8ba4\u8fdb\u5165\u4e3b\u83dc\u5355\u3002\u5173\u95ed\u6e38\u620f\u540e\u4f1a\u81ea\u52a8\u6e05\u7406\u9694\u79bb\u526f\u672c\u3002")
        self.sim_confirm_frame.pack_forget()
        self._set_buttons()
        if self.close_after_cleanup:
            self._cleanup_simulation(stop=True, close_after=True)
            return
        if self.sim_process_exited:
            self._set_sim_stage(
                "launch", "success",
                "进程已正常退出，且你已确认看到主菜单")
            self._cleanup_simulation(stop=False)
        else:
            self._poll_simulation()

    def _simulation_confirm_failed(self, message):
        self.busy = False
        self._set_sim_stage("confirm", "failed", message)
        self._set_sim_result("bad", "\u65e0\u6cd5\u786e\u8ba4\u4e3b\u83dc\u5355\uff1a" + str(message))
        self._show_log()
        self._set_buttons()
        if self.sim_session is not None and not self.sim_confirmed:
            self.sim_confirm_frame.pack(anchor="w", pady=(9, 0))
        if self.close_after_cleanup:
            self._cleanup_simulation(stop=True, close_after=True)

    def confirm_simulation_failure(self):
        if self.sim_session is None or not self.sim_launched:
            return
        self._set_sim_stage("confirm", "failed",
                            "\u7528\u6237\u786e\u8ba4\u672a\u6210\u529f\u8fdb\u5165\u4e3b\u83dc\u5355")
        self._set_sim_result(
            "bad", "\u542f\u52a8\u5931\u8d25\uff1a\u4f60\u786e\u8ba4\u6e38\u620f\u6ca1\u6709\u6210\u529f\u8fdb\u5165\u4e3b\u83dc\u5355\u3002")
        self.sim_confirm_frame.pack_forget()
        self._cleanup_simulation(stop=not self.sim_process_exited)

    def _cleanup_simulation(self, stop=False, close_after=False):
        session = self.sim_session
        if session is None:
            if close_after:
                self._destroy_root()
            return
        if self.sim_cleanup_running:
            if close_after:
                self.close_after_cleanup = True
            return
        self.close_after_cleanup = self.close_after_cleanup or close_after
        self.sim_cleanup_running = True
        self.busy = True
        self._set_sim_stage("copy", "running",
                            "\u6b63\u5728\u6e05\u7406\u9694\u79bb\u526f\u672c")
        self._set_buttons()
        threading.Thread(target=self._simulation_cleanup_worker,
                         args=(session, stop), daemon=True).start()

    def _simulation_cleanup_worker(self, session, stop):
        errors = []
        try:
            if stop:
                session.stop()
        except Exception as exc:  # noqa: BLE001
            errors.append("stop: %s" % exc)
        try:
            session.cleanup()
        except Exception as exc:  # noqa: BLE001
            errors.append("cleanup: %s" % exc)
        self.queue.put(("__sim_cleaned__", errors))

    def _simulation_cleaned(self, errors):
        self.sim_cleanup_running = False
        self.busy = False
        if errors:
            self._set_sim_stage("copy", "failed", "; ".join(errors))
            self._set_sim_result(
                "bad", self.sim_result_message + "  \u9694\u79bb\u526f\u672c\u6e05\u7406\u9047\u5230\u9519\u8bef\uff1a" + "; ".join(errors))
            self.close_after_cleanup = False
            self._set_sim_result(
                "bad", self.sim_result_message + "  \u53ef\u518d\u6b21\u9000\u51fa\u4ee5\u91cd\u8bd5\u505c\u6b62\u548c\u6e05\u7406\u3002")
            self._set_buttons()
            return
        self.sim_session = None
        self.sim_preparing = False
        self.sim_launched = False
        self.sim_confirmed = False
        self._set_sim_stage("copy", "success",
                            "\u9694\u79bb\u526f\u672c\u5df2\u6e05\u7406")
        if self.sim_result_level == "ok":
            self._set_sim_result(
                "ok", self.sim_result_message + "  \u9694\u79bb\u526f\u672c\u5df2\u6e05\u7406\u3002")
        self._set_buttons()
        if self.close_after_cleanup:
            self._destroy_root()

    def close(self):
        if self.sim_preparing and self.sim_session is None:
            if messagebox.askyesno(
                    TITLE, "\u526f\u672c\u6b63\u5728\u51c6\u5907\u4e2d\u3002\u786e\u5b9a\u9000\u51fa\uff1f\u7a0b\u5e8f\u4f1a\u7b49\u5f53\u524d\u6b65\u9aa4\u7ed3\u675f\u540e\u6e05\u7406\u526f\u672c\u3002"):
                self.close_after_prepare = True
                self._set_sim_result(
                    "warn", "\u7b49\u5f85\u5f53\u524d\u526f\u672c\u64cd\u4f5c\u5b8c\u6210\uff0c\u5b8c\u6210\u540e\u6e05\u7406\u5e76\u5173\u95ed\u3002")
            return
        if self.sim_session is not None:
            if messagebox.askyesno(
                    TITLE, "\u9000\u51fa\u5c06\u505c\u6b62\u6a21\u62df\u6e38\u620f\u5e76\u6e05\u7406\u9694\u79bb\u526f\u672c\u3002\u539f\u6e38\u620f\u4e0d\u4f1a\u53d7\u5f71\u54cd\u3002\n\n\u786e\u5b9a\u9000\u51fa\u5417\uff1f"):
                if self.busy:
                    self.close_after_cleanup = True
                    self._set_sim_result(
                        "warn", "\u7b49\u5f53\u524d\u6b65\u9aa4\u7ed3\u675f\uff0c\u968f\u540e\u505c\u6b62\u8fdb\u7a0b\u3001\u6e05\u7406\u526f\u672c\u5e76\u5173\u95ed\u7a97\u53e3\u3002")
                else:
                    self._cleanup_simulation(
                        stop=self.sim_launched and not self.sim_process_exited,
                        close_after=True)
            return
        if self.busy:
            if messagebox.askyesno(
                    TITLE, "\u64cd\u4f5c\u6b63\u5728\u6267\u884c\u3002\u662f\u5426\u5728\u64cd\u4f5c\u7ed3\u675f\u540e\u5173\u95ed\u7a97\u53e3\uff1f"):
                self.close_after_work = True
            return
        self._destroy_root()



    def _update_action_hint(self):
        selected = [features.title_of(fid) for fid in self._ticked()]
        if selected:
            text = "\u6267\u884c\u8303\u56f4\uff1a" + "\u3001".join(selected)
        elif not self.game_dir:
            text = "\u5148\u9009\u62e9\u6e38\u620f\u76ee\u5f55\uff0c\u518d\u52fe\u9009\u8981\u5904\u7406\u7684\u529f\u80fd\u3002"
        elif not os.path.isdir(os.path.join(self.game_dir, "game")):
            text = "\u6240\u9009\u76ee\u5f55\u6ca1\u6709 game/\uff0c\u8bf7\u9009\u6709\u6548\u7684\u6e38\u620f\u6839\u76ee\u5f55\u3002"
        elif not any(row.supported for row in self.rows.values()):
            text = "\u5f53\u524d\u6e38\u620f\u6ca1\u6709\u53ef\u7528\u529f\u80fd\uff0c\u8bf7\u67e5\u770b\u529f\u80fd\u5361\u7247\u4e2d\u7684\u517c\u5bb9\u539f\u56e0\u3002"
        else:
            text = "\u8bf7\u52fe\u9009\u81f3\u5c11\u4e00\u4e2a\u53ef\u7528\u529f\u80fd\uff1b\u9884\u89c8\u548c\u5904\u7406\u5c06\u4f7f\u7528\u5f53\u524d\u52fe\u9009\u9879\u3002"
        self.var_action_hint.set(text)

    def _selection_changed(self):
        self._set_buttons()

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _ticked(self):
        """Read enabled feature ids on the main thread, in catalogue order."""
        return [fid for fid in features.ids()
                if self.rows[fid].supported and self.var_on[fid].get()]


    def _apply_feature_support(self, survey):
        # Older survey data has no support matrix; keep its previous behavior.
        support_map = survey.get("feature_support") if isinstance(survey, dict) else None
        support_map = support_map if isinstance(support_map, dict) else {}
        for fid, row in self.rows.items():
            spec = support_map.get(fid)
            spec = spec if isinstance(spec, dict) else {}
            row.supported = spec.get("supported") is not False
            reasons = spec.get("reasons") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            detail = "\uff1b".join(str(reason) for reason in reasons if reason)
            if row.supported:
                row.reason_var.set("")
                row.reason_label.pack_forget()
            else:
                self.var_on[fid].set(False)
                reason = "\u5f53\u524d\u6e38\u620f\u4e0d\u652f\u6301\u6b64\u529f\u80fd"
                if detail:
                    reason += "\uff1a" + detail
                row.reason_var.set(reason)
                row.reason_label.pack(anchor="w", pady=(7, 0))
        self._apply_wrap()
        if self.action_buttons:
            self._set_buttons()




    # --- actions ----------------------------------------------------------



    def _args(self, **kw):
        """The namespace for the boxes as they are right now.

        The Tk variables are read here, on the main thread, so the worker never
        touches them.
        """
        ids = self._ticked()
        return _namespace(self.game_dir, feature_ids=ids,
                          skip_intro=("intro" in ids), **kw)

    def install(self):
        if not self._ticked():
            messagebox.showinfo(TITLE, "一个功能都没有勾选，没什么要装的。")
            return
        if not self._confirm_overwrite():
            return
        self._spawn(self._args(force=True), "开始处理", notify=True)

    def revert(self):
        # No feature selection here: undo is undo, everything this tool wrote
        # goes, whether or not it is ticked now.
        self._spawn(_namespace(self.game_dir, revert=True), "撤销还原", notify=True)

    def _confirm_overwrite(self):
        """Only asked when a foreign file is in the way, so the normal
        reinstall path stays a single click."""
        st = cmd_fontfix.installed_state(self.game_dir)
        if st["shim"] and not st["ours"]:
            return messagebox.askyesno(
                TITLE,
                "这个游戏里已经有一个 %s，但它不是本工具写的。\n\n"
                "继续会把它备份到工作目录的 quarantine/ 再覆盖。要继续吗？"
                % cmd_fontfix.SHIM_REL)
        if "intro" in self.rows and self.var_on["intro"].get():
            # find_intro_conflicts already ignores this tool's own file, so a
            # plain reinstall asks nothing.
            conflicts = cmd_fontfix.find_intro_conflicts(self.game_dir)
            if conflicts:
                return messagebox.askyesno(
                    TITLE,
                    "这个游戏里已经有别的文件在跳过开场 logo：\n\n  %s\n\n"
                    "继续会把它（连同同名的 .rpyc）备份到工作目录的 quarantine/，"
                    "换成 rpykit 自己的版本。「撤销还原」会把它们放回原处。\n\n"
                    "要继续吗？" % "\n  ".join(conflicts))
        return True

    def _spawn(self, argv, title, notify):
        if self.busy:
            return
        self._log("\n===== %s =====\n" % title)
        self._show_log()
        self.busy = True
        self.notify = notify
        self.last_selected = list(getattr(argv, "features", None) or [])
        self._set_buttons()
        threading.Thread(target=self._work, args=(argv,), daemon=True).start()

    def _work(self, argv):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _Sink(self.queue)
        code = 0
        try:
            code = cmd_fontfix.run(argv) or 0
        except SystemExit as e:
            print("!! %s" % e)
            code = 1
        except Exception as e:  # noqa: BLE001 - the window must survive anything
            print("!! %s: %s" % (type(e).__name__, e))
            code = 1
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.last_outcome = getattr(argv, "outcome", None)
        self.queue.put(("__done__", code))

    def _finish(self, code):
        self.busy = False
        self._set_buttons()
        self._refresh_state()
        if self.close_after_work:
            self._destroy_root()
            return
        if not self.notify:
            return
        if code == 0:
            names = "、".join(features.title_of(fid) for fid in self.last_selected)
            if self.last_outcome == "no_changes":
                messagebox.showinfo(
                    TITLE, "完成：%s。\n\n选中的字体已全部覆盖中文，本次没有需要改动的文件。"
                           % (names or "没有改动"))
            else:
                messagebox.showinfo(
                    TITLE, "完成：%s。\n\n现在开一次游戏看看效果。"
                           % (names or "没有改动"))
        else:
            self._show_log()
            messagebox.showerror(TITLE, "出错了，看下面的日志。")


class App(_OperationMixin):
    """CustomTkinter production shell around the existing operation state machine."""

    PAGES = {
        "process": ("处理", "选择游戏，先模拟运行，再应用补丁。"),
        "library": ("游戏库", "只保存手动添加的游戏位置，不扫描整个磁盘。"),
        "toolbox": ("游戏信息", "查看当前游戏的兼容性和补丁状态。"),
        "log": ("运行日志", "查看、复制或导出最近的处理输出。"),
        "settings": ("设置", "调整外观；窗口大小会自动记住。"),
    }
    NAV = (("process", "处理"), ("library", "游戏库"),
           ("toolbox", "游戏信息"), ("log", "运行日志"),
           ("settings", "设置"))

    def __init__(self, root, state=None, state_path=None):
        self.root = root
        self.state_path = state_path or app_state.state_path()
        self.state = state if isinstance(state, dict) else app_state.load_state(self.state_path)
        self.state.setdefault("appearance", "system")
        self.state.setdefault("window", dict(app_state.DEFAULT_WINDOW))
        self.state.setdefault("games", [])
        self.state.setdefault("active_game", "")
        self.game_dir = None
        self.busy = False
        self.notify = True
        self.last_selected = []
        self.last_outcome = None
        self.rows = {}
        self.var_on = {}
        self.action_buttons = {}
        self.queue = queue.Queue()
        self.sim_session = None
        self.sim_preparing = False
        self.sim_launched = False
        self.sim_confirmed = False
        self.sim_process_exited = False
        self.sim_cleanup_running = False
        self.close_after_prepare = False
        self.close_after_work = False
        self.close_after_cleanup = False
        self.sim_result_level = "info"
        self.sim_result_message = ""
        self.sim_stage_state = {}
        self.scan_busy = False
        self._scan_generation = 0
        self._geometry_job = None
        self._theme_mode = "system"
        self._theme = _system_theme()
        self._survey = None
        self._installed = None
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Configure>", self._schedule_geometry_save, add="+")
        self._apply_theme(self.state.get("appearance", "system"), persist=False)
        self._set_buttons()
        self.root.after(80, self._drain)
        active = self.state.get("active_game")
        if active and os.path.isdir(active):
            self.set_game_dir(active, remember=False)

    def _font(self, size=11, weight="normal"):
        return ctk.CTkFont(family="Microsoft YaHei UI", size=size, weight=weight)

    def _card(self, parent, padding=16):
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=_PAIR["panel"],
                            border_width=1, border_color=_PAIR["border"])
        card.pack_propagate(True)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack_propagate(True)
        inner.pack(fill="both", expand=True, padx=padding, pady=padding)
        return card, inner

    def _build(self):
        self.root.title(TITLE)
        size = self.state.get("window") or app_state.DEFAULT_WINDOW
        width = max(900, int(size.get("width", 1180)))
        height = max(620, int(size.get("height", 780)))
        self.root.geometry("%dx%d" % (width, height))
        self.root.minsize(900, 620)
        try:
            self.root.iconbitmap(cmd_fontfix._asset(branding.ICON_NAME))
        except Exception:
            pass

        self.shell = ctk.CTkFrame(self.root, corner_radius=0, fg_color=_PAIR["bg"])
        self.shell.pack(fill="both", expand=True)
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self.shell, width=216, corner_radius=0,
                                    fg_color=_PAIR["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        ctk.CTkFrame(self.sidebar, width=4, corner_radius=0,
                     fg_color=_PAIR["accent"]).place(x=0, y=0, relheight=1)

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=(20, 12), pady=(24, 24))
        ctk.CTkLabel(logo, text="RPY", width=42, height=42, corner_radius=12,
                     fg_color=_PAIR["accent_soft"], text_color=_PAIR["accent"],
                     font=self._font(14, "bold")).pack(side="left")
        brand = ctk.CTkFrame(logo, fg_color="transparent")
        brand.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(brand, text="Ren'Py Toolkit", anchor="w",
                     text_color=_PAIR["fg"], font=self._font(12, "bold")).pack(anchor="w")
        ctk.CTkLabel(brand, text="简体中文补丁工具", anchor="w",
                     text_color=_PAIR["dim"], font=self._font(9)).pack(anchor="w", pady=(3, 0))

        self.nav_buttons = {}
        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=12)
        for page_id, title in self.NAV:
            button = ctk.CTkButton(
                nav, text=title, anchor="w", height=40, corner_radius=10,
                fg_color="transparent", hover_color=_PAIR["panel_alt"],
                text_color=_PAIR["dim"], font=self._font(11),
                command=lambda target=page_id: self._show_page(target))
            button.pack(fill="x", pady=3)
            self.nav_buttons[page_id] = button
        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=15)
        self.btn_theme = ctk.CTkButton(
            bottom, text="外观：跟随系统", height=34, corner_radius=9,
            fg_color=_PAIR["panel_alt"], hover_color=_PAIR["accent_soft"],
            text_color=_PAIR["fg"], font=self._font(10), command=self._toggle_theme)
        self.btn_theme.pack(fill="x")
        self.version_label = ctk.CTkLabel(bottom, text="v" + branding.APP_VERSION,
                                          anchor="w", text_color=_PAIR["dim"],
                                          font=self._font(9))
        self.version_label.pack(anchor="w", pady=(9, 0))

        self.content = ctk.CTkFrame(self.shell, fg_color=_PAIR["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=(0, 12))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 11))
        header.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(header, text="", anchor="w",
                                       text_color=_PAIR["fg"], font=self._font(21, "bold"))
        self.page_title.grid(row=0, column=0, sticky="w")
        self.page_subtitle = ctk.CTkLabel(header, text="", anchor="w",
                                          text_color=_PAIR["dim"], font=self._font(10))
        self.page_subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_global_status = tk.StringVar(value="就绪")
        ctk.CTkLabel(header, textvariable=self.var_global_status,
                     text_color=_PAIR["dim"], font=self._font(9)).grid(
                         row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        self.bar = ctk.CTkProgressBar(self.content, height=3, corner_radius=0,
                                      progress_color=_PAIR["accent"],
                                      fg_color=_PAIR["border"])
        self.bar.set(0)
        self.bar.grid(row=1, column=0, sticky="new", padx=22)
        self.bar.grid_remove()
        self.page_host = ctk.CTkFrame(self.content, fg_color="transparent")
        self.page_host.grid(row=2, column=0, sticky="nsew", padx=22, pady=(13, 4))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)
        self.pages = {}
        for page_id in self.PAGES:
            frame = ctk.CTkFrame(self.page_host, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_remove()
            self.pages[page_id] = frame
        self._build_process(self.pages["process"])
        self._build_library(self.pages["library"])
        self._build_toolbox(self.pages["toolbox"])
        self._build_log(self.pages["log"])
        self._build_settings(self.pages["settings"])
        self._show_page("process")

    def _build_process(self, parent):
        page = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        page.pack(fill="both", expand=True)
        card, inner = self._card(page)
        ctk.CTkLabel(inner, text="选择游戏", anchor="w", text_color=_PAIR["fg"],
                     font=self._font(13, "bold")).pack(anchor="w")
        ctk.CTkLabel(inner, text="请选择包含 game/ 子目录的 Ren'Py 游戏根目录。",
                     anchor="w", text_color=_PAIR["dim"], font=self._font(10)).pack(
                         anchor="w", pady=(4, 9))
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self.var_dir = tk.StringVar(value="")
        self.entry_dir = ctk.CTkEntry(row, textvariable=self.var_dir, state="readonly",
                                      height=36, fg_color=_PAIR["input"],
                                      border_color=_PAIR["border"], text_color=_PAIR["fg"],
                                      font=self._font(10))
        self.entry_dir.pack(side="left", fill="x", expand=True)
        self.btn_pick = ctk.CTkButton(row, text="浏览…", width=88, height=36,
                                      corner_radius=9, fg_color=_PAIR["accent"],
                                      hover_color=_PAIR["accent_hover"],
                                      font=self._font(10), command=self.pick)
        self.btn_pick.pack(side="left", padx=(8, 0))
        self.var_compat = tk.StringVar(value="未选择游戏")
        self.lbl_compat = ctk.CTkLabel(inner, textvariable=self.var_compat,
                                       anchor="w", justify="left", wraplength=760,
                                       text_color=_PAIR["dim"], font=self._font(10))
        self.lbl_compat.pack(anchor="w", pady=(9, 0))
        self.var_reasons = tk.StringVar(value="")
        self.lbl_reasons = ctk.CTkLabel(inner, textvariable=self.var_reasons,
                                        anchor="w", justify="left", wraplength=760,
                                        text_color=_PAIR["dim"], font=self._font(9))
        self.lbl_reasons.pack(anchor="w", pady=(4, 0))
        self.var_state = tk.StringVar(value="先选择一个游戏目录。")
        self.lbl_state = ctk.CTkLabel(inner, textvariable=self.var_state, anchor="w",
                                      justify="left", wraplength=760,
                                      text_color=_PAIR["dim"], font=self._font(10, "bold"))
        self.lbl_state.pack(anchor="w", pady=(8, 0))
        self.var_compat.set("")
        self.lbl_compat.pack_forget()
        self.lbl_reasons.pack_forget()

        heading = ctk.CTkFrame(page, fg_color="transparent")
        heading.pack(fill="x", pady=(2, 7))
        ctk.CTkLabel(heading, text="可用功能", anchor="w", text_color=_PAIR["fg"],
                     font=self._font(13, "bold")).pack(side="left")
        ctk.CTkLabel(heading, text="来自当前功能目录", anchor="e",
                     text_color=_PAIR["dim"], font=self._font(9)).pack(side="right")
        grid = ctk.CTkFrame(page, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)
        self.rows = {}
        self.var_on = {}
        for i, entry in enumerate(features.CATALOG):
            feature_card = ctk.CTkFrame(grid, corner_radius=13, fg_color=_PAIR["panel"],
                                        border_width=1, border_color=_PAIR["border"])
            desc = entry.get("desc", "")
            desc_lines = sum(max(1, (len(line) + 46) // 47)
                             for line in desc.splitlines()) or 1
            feature_card.configure(height=max(116, 62 + 16 * desc_lines))
            feature_card.pack_propagate(False)
            feature_card.grid(row=i // 2, column=i % 2, sticky="nsew",
                              padx=(0, 6) if i % 2 == 0 else (6, 0), pady=6)
            head = ctk.CTkFrame(feature_card, fg_color="transparent")
            head.pack(fill="x", padx=12, pady=(11, 0))
            var = tk.BooleanVar(value=bool(entry.get("default_on", True)))
            self.var_on[entry["id"]] = var
            toggle = ctk.CTkCheckBox(head, text=entry["title"], variable=var,
                                     command=self._selection_changed,
                                     checkbox_width=18, checkbox_height=18,
                                     fg_color=_PAIR["accent"], hover_color=_PAIR["accent_hover"],
                                     text_color=_PAIR["fg"], font=self._font(10, "bold"))
            toggle.pack(side="left")
            chip_var = tk.StringVar(value="未检查")
            chip = ctk.CTkLabel(head, textvariable=chip_var, height=22, corner_radius=7,
                                fg_color=_PAIR["panel_alt"], text_color=_PAIR["dim"],
                                font=self._font(8), padx=7)
            chip.pack(side="right")
            ctk.CTkLabel(feature_card, text=desc, anchor="w", justify="left",
                         wraplength=410, text_color=_PAIR["dim"], font=self._font(9)).pack(
                             fill="x", padx=12, pady=(7, 0))
            reason_var = tk.StringVar(value="")
            reason = ctk.CTkLabel(feature_card, textvariable=reason_var, anchor="w",
                                  justify="left", wraplength=410,
                                  text_color=_PAIR["bad"], font=self._font(9))
            self.rows[entry["id"]] = _FeatureRow(
                entry, feature_card, toggle, chip_var, chip, reason_var, reason)
        if "intro" in self.rows:
            self.var_skip = self.var_on["intro"]
            self.chk_skip = self.rows["intro"].toggle

        actions, body = self._card(page)
        ctk.CTkLabel(body, text="执行", anchor="w", text_color=_PAIR["fg"],
                     font=self._font(13, "bold")).pack(anchor="w")
        ctk.CTkLabel(body, text="模拟过程和结果确认都只作用于隔离副本，不会写入原游戏。只有单独点击“开始处理”才会修改原游戏。",
                     anchor="w", text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(4, 9))
        self.sim_result_var = tk.StringVar(value="尚未运行模拟安装。")
        self.sim_result_label = ctk.CTkLabel(
            body, textvariable=self.sim_result_var, anchor="w", justify="left",
            wraplength=730, text_color=_PAIR["dim"], font=self._font(10, "bold"))
        self.sim_result_label.pack(anchor="w", pady=(0, 8))
        self.sim_confirm_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.btn_sim_success = ctk.CTkButton(
            self.sim_confirm_frame, text="已进入主菜单", height=30,
            fg_color=_PAIR["accent"], hover_color=_PAIR["accent_hover"],
            font=self._font(9), command=self.confirm_simulation_success)
        self.btn_sim_failure = ctk.CTkButton(
            self.sim_confirm_frame, text="启动失败", height=30,
            fg_color="transparent", border_width=1, border_color=_PAIR["border"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(9), command=self.confirm_simulation_failure)
        self.btn_sim_success.pack(side="left")
        self.btn_sim_failure.pack(side="left", padx=(7, 0))
        self.sim_confirm_frame.pack_forget()
        self.buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons = self.buttons
        buttons.pack(fill="x")
        self.btn_dry = ctk.CTkButton(buttons, text="模拟安装并运行", height=37,
                                     corner_radius=9, fg_color=_PAIR["accent"],
                                     hover_color=_PAIR["accent_hover"],
                                     font=self._font(10, "bold"), command=self.simulate_run)
        self.btn_dry.pack(side="left")
        self.btn_go = ctk.CTkButton(buttons, text="开始处理", height=37,
                                    corner_radius=9, fg_color=_PAIR["panel_alt"],
                                    hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
                                    font=self._font(10), command=self.install)
        self.btn_go.pack(side="left", padx=(7, 0))
        self.btn_undo = ctk.CTkButton(buttons, text="撤销还原", height=37,
                                      corner_radius=9, fg_color="transparent",
                                      border_width=1, border_color=_PAIR["border"],
                                      hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
                                      font=self._font(10), command=self.revert)
        self.btn_undo.pack(side="left", padx=(7, 0))
        self.action_buttons = {"simulate": self.btn_dry, "go": self.btn_go,
                               "undo": self.btn_undo}
        self.var_action_hint = tk.StringVar(value="")
        ctk.CTkLabel(body, textvariable=self.var_action_hint, anchor="w",
                     text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(7, 0))
        self.sim_stage_vars = {}
        self.sim_stage_labels = {}
        self.sim_card = ctk.CTkFrame(body, corner_radius=11,
                                     fg_color=_PAIR["panel_alt"],
                                     border_width=1, border_color=_PAIR["border"])
        self.sim_card.pack(fill="x", pady=(11, 0))
        sim_body = ctk.CTkFrame(self.sim_card, fg_color="transparent")
        sim_body.pack(fill="x", padx=12, pady=11)
        ctk.CTkLabel(sim_body, text="本次模拟步骤", anchor="w",
                     text_color=_PAIR["fg"], font=self._font(12, "bold")).pack(anchor="w")
        ctk.CTkLabel(sim_body, text="正常退出不代表已进入主菜单；确认结果后清理副本，不会修改原游戏。",
                     anchor="w", text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(3, 7))
        for key, name in (("compat", "兼容预检"), ("copy", "准备隔离副本"),
                          ("install", "模拟安装补丁"), ("launch", "启动副本"),
                          ("confirm", "确认主菜单")):
            var = tk.StringVar(value=name + "：等待")
            label = ctk.CTkLabel(sim_body, textvariable=var, anchor="w",
                                 text_color=_PAIR["dim"], font=self._font(9))
            label.pack(anchor="w", pady=2)
            self.sim_stage_vars[key] = var
            self.sim_stage_labels[key] = label
        self._reset_simulation_status()

    def _build_library(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 9))
        self.btn_add_game = ctk.CTkButton(tools, text="添加游戏…", height=34,
                                          corner_radius=9, fg_color=_PAIR["accent"],
                                          hover_color=_PAIR["accent_hover"],
                                          font=self._font(10), command=self.add_game)
        self.btn_add_game.pack(side="left")
        ctk.CTkLabel(tools, text="手动添加 · 不会扫描整盘", text_color=_PAIR["dim"],
                     font=self._font(9)).pack(side="left", padx=10)
        self.library_scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.library_scroll.pack(fill="both", expand=True)
        self._render_library()

    def _render_library(self):
        for widget in self.library_scroll.winfo_children():
            widget.destroy()
        if not self.state.get("games"):
            _, body = self._card(self.library_scroll)
            ctk.CTkLabel(body, text="游戏库为空", text_color=_PAIR["fg"],
                         font=self._font(12, "bold")).pack(anchor="w")
            ctk.CTkLabel(body, text="添加包含 game/ 子目录的游戏根目录。",
                         text_color=_PAIR["dim"], font=self._font(9)).pack(
                             anchor="w", pady=(5, 0))
            return
        for entry in self.state["games"]:
            _, body = self._card(self.library_scroll, padding=13)
            body.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(body, text=entry["name"], anchor="w", text_color=_PAIR["fg"],
                         font=self._font(11, "bold")).grid(row=0, column=0, sticky="w")
            exists = os.path.isdir(os.path.join(entry["path"], "game"))
            ctk.CTkLabel(body, text="可访问" if exists else "路径不可用",
                         text_color=_PAIR["ok"] if exists else _PAIR["bad"],
                         font=self._font(8)).grid(row=0, column=1, sticky="e")
            ctk.CTkLabel(body, text=entry["path"], anchor="w", wraplength=700,
                         text_color=_PAIR["dim"], font=self._font(8)).grid(
                             row=1, column=0, columnspan=2, sticky="ew", pady=(4, 8))
            buttons = ctk.CTkFrame(body, fg_color="transparent")
            buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
            ctk.CTkButton(buttons, text="打开处理页", width=92, height=28,
                          corner_radius=8, fg_color=_PAIR["accent"],
                          hover_color=_PAIR["accent_hover"], font=self._font(8),
                          command=lambda path=entry["path"]: self.set_game_dir(path)).pack(side="left")
            ctk.CTkButton(buttons, text="重命名", width=68, height=28,
                          corner_radius=8, fg_color="transparent", border_width=1,
                          border_color=_PAIR["border"], hover_color=_PAIR["accent_soft"],
                          text_color=_PAIR["fg"], font=self._font(8),
                          command=lambda item=entry: self.rename_game(item)).pack(
                              side="left", padx=(7, 0))
            ctk.CTkButton(buttons, text="移出游戏库", width=80, height=28,
                          corner_radius=8, fg_color="transparent", border_width=1,
                          border_color=_PAIR["border"], hover_color=_PAIR["accent_soft"],
                          text_color=_PAIR["fg"], font=self._font(8),
                          command=lambda path=entry["path"]: self.remove_game(path)).pack(side="right")

    def _build_toolbox(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        _, body = self._card(scroll)
        ctk.CTkLabel(body, text="当前游戏诊断", anchor="w", text_color=_PAIR["fg"],
                     font=self._font(12, "bold")).pack(anchor="w")
        ctk.CTkLabel(body, text="由兼容性预检生成，只读游戏信息。",
                     anchor="w", text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(4, 8))
        self.var_toolbox_info = tk.StringVar(value="尚未选择游戏。")
        ctk.CTkLabel(body, textvariable=self.var_toolbox_info, anchor="nw",
                     justify="left", wraplength=740, text_color=_PAIR["fg"],
                     font=self._font(9)).pack(fill="x")
        self.var_toolbox_installed = tk.StringVar(value="")
        ctk.CTkLabel(body, textvariable=self.var_toolbox_installed, anchor="w",
                     text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(8, 0))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(12, 0))
        ctk.CTkButton(buttons, text="重新检查", height=30, corner_radius=8,
                      fg_color=_PAIR["accent"], hover_color=_PAIR["accent_hover"],
                      font=self._font(9), command=self.refresh_game).pack(side="left")
        ctk.CTkButton(buttons, text="打开游戏目录", height=30, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=_PAIR["border"],
                      hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
                      font=self._font(9), command=self.open_game_folder).pack(
                          side="left", padx=(7, 0))

    def _build_log(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 8))
        for text, command, side in (("清空", self.clear_log, "left"),
                                    ("导出…", self.export_log, "right"),
                                    ("复制全部", self.copy_log, "right")):
            ctk.CTkButton(tools, text=text, width=75, height=30, corner_radius=8,
                          fg_color="transparent", border_width=1,
                          border_color=_PAIR["border"], hover_color=_PAIR["accent_soft"],
                          text_color=_PAIR["fg"], font=self._font(9),
                          command=command).pack(side=side, padx=(6, 0) if side == "right" else 0)
        self.log_card = ctk.CTkFrame(body, corner_radius=13, fg_color=_PAIR["panel"],
                                     border_width=1, border_color=_PAIR["border"])
        self.log_card.pack(fill="both", expand=True)
        self.log = ctk.CTkTextbox(self.log_card, wrap="none", corner_radius=10,
                                  fg_color=_PAIR["panel"], text_color=_PAIR["fg"],
                                  font=ctk.CTkFont(family="Consolas", size=10),
                                  border_width=0)
        self.log.pack(fill="both", expand=True, padx=9, pady=9)
        self.log.configure(state="disabled")
        self.var_log = tk.BooleanVar(value=False)

    def _build_settings(self, parent):
        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        _, card = self._card(body)
        ctk.CTkLabel(card, text="外观", anchor="w", text_color=_PAIR["fg"],
                     font=self._font(12, "bold")).pack(anchor="w")
        ctk.CTkLabel(card, text="跟随系统深浅色，也可以手动指定。",
                     anchor="w", text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(4, 9))
        self.theme_modes = {"跟随系统": "system", "浅色": "light", "深色": "dark"}
        self.theme_segment = ctk.CTkSegmentedButton(
            card, values=list(self.theme_modes), command=self._mode_from_label,
            selected_color=_PAIR["accent"], selected_hover_color=_PAIR["accent_hover"],
            unselected_color=_PAIR["panel_alt"], unselected_hover_color=_PAIR["accent_soft"],
            text_color=_PAIR["fg"], font=self._font(9))
        self.theme_segment.pack(fill="x")
        _, size_card = self._card(body)
        ctk.CTkLabel(size_card, text="窗口大小", anchor="w", text_color=_PAIR["fg"],
                     font=self._font(12, "bold")).pack(anchor="w")
        size = self.state.get("window") or app_state.DEFAULT_WINDOW
        self.var_window = tk.StringVar(value="%d × %d（自动记住）" % (
            size.get("width", 1180), size.get("height", 780)))
        ctk.CTkLabel(size_card, textvariable=self.var_window, anchor="w",
                     text_color=_PAIR["dim"], font=self._font(9)).pack(
                         anchor="w", pady=(6, 0))
        _, about = self._card(body)
        ctk.CTkLabel(about, text="SLG Ren'Py Toolkit · v" + branding.APP_VERSION +
                     "\n提供可撤销补丁与隔离副本模拟运行。",
                     anchor="w", justify="left", text_color=_PAIR["dim"],
                     font=self._font(9)).pack(anchor="w")

    def _show_page(self, page_id):
        if page_id not in self.pages:
            return
        self.active_page = page_id
        for key, page in self.pages.items():
            page.grid() if key == page_id else page.grid_remove()
        title, subtitle = self.PAGES[page_id]
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        for key, button in self.nav_buttons.items():
            selected = key == page_id
            button.configure(fg_color=_PAIR["accent_soft"] if selected else "transparent",
                             text_color=_PAIR["accent"] if selected else _PAIR["dim"],
                             font=self._font(11, "bold" if selected else "normal"))
        if page_id == "library":
            self._render_library()

    def _apply_theme(self, theme, persist=True):
        mode = theme if theme in ("system", "light", "dark") else "system"
        self._theme_mode = mode
        self._theme = _system_theme() if mode == "system" else mode
        ctk.set_appearance_mode(mode)
        try:
            self.root.configure(fg_color=_PAIR["bg"])
        except tk.TclError:
            pass
        self.btn_theme.configure(text="外观：" + {"system": "跟随系统", "light": "浅色",
                                                 "dark": "深色"}[mode])
        if hasattr(self, "theme_segment"):
            self.theme_segment.set({"system": "跟随系统", "light": "浅色",
                                    "dark": "深色"}[mode])
        if persist:
            self.state["appearance"] = mode
            self._persist_state()

    def _toggle_theme(self):
        modes = ("system", "light", "dark")
        self._apply_theme(modes[(modes.index(self._theme_mode) + 1) % len(modes)])

    def _mode_from_label(self, label):
        self._apply_theme(self.theme_modes.get(label, "system"))

    def _apply_wrap(self):
        return None

    def _reset_simulation_status(self):
        self.sim_stage_state = {}
        for key, text in self._SIM_STAGE_DEFAULTS.items():
            self._set_sim_stage(key, "pending", text)
        self._set_sim_result("info", "尚未运行模拟安装。将在隔离副本中测试，不会修改原游戏。")
        self.sim_confirm_frame.pack_forget()

    def _set_sim_stage(self, stage_id, status, message=None):
        colors = {"success": "ok", "ok": "ok", "done": "ok", "passed": "ok",
                  "failed": "bad", "failure": "bad", "error": "bad",
                  "running": "warn", "active": "warn", "waiting": "warn",
                  "pending": "info", "skipped": "info", "cancelled": "info"}
        key = str(status or "pending").lower()
        level = colors.get(key, "info")
        word = {"ok": "成功", "bad": "失败", "warn": "进行中", "info": "等待"}[level]
        detail = "：" + str(message) if message else ""
        label = self._SIM_STAGE_NAMES.get(stage_id, stage_id) + "：" + word + detail
        self.sim_stage_state[stage_id] = (level, str(status), message)
        if stage_id in self.sim_stage_vars:
            self.sim_stage_vars[stage_id].set(label)
            self.sim_stage_labels[stage_id].configure(text_color=_PAIR.get(level, _PAIR["dim"]))

    def _set_sim_result(self, level, message):
        self.sim_result_level = level
        self.sim_result_message = str(message)
        self.sim_result_var.set(self.sim_result_message)
        self.sim_result_label.configure(text_color=_PAIR.get(level, _PAIR["dim"]))

    def _set_state(self, level, text):
        self.var_state.set("%s  %s" % (_GLYPH.get(level, _GLYPH["info"]), text))
        self.lbl_state.configure(text_color=_PAIR.get(level, _PAIR["dim"]))
        return level, text

    def _set_compat(self, survey):
        if not survey:
            self.var_compat.set("")
            self.var_reasons.set("")
            self.lbl_compat.pack_forget()
            self.lbl_reasons.pack_forget()
            return
        level = survey.get("verdict", "info")
        self.var_compat.set("%s  %s" % (_GLYPH.get(level, "·"), _describe(survey)))
        if not self.lbl_compat.winfo_manager():
            self.lbl_compat.pack(anchor="w", before=self.lbl_state, pady=(9, 0))
        self.lbl_compat.configure(text_color=_PAIR.get(level, _PAIR["dim"]))
        reason_text = _reasons(survey)
        self.var_reasons.set(reason_text)
        if reason_text:
            if not self.lbl_reasons.winfo_manager():
                self.lbl_reasons.pack(anchor="w", before=self.lbl_state, pady=(4, 0))
        else:
            self.lbl_reasons.pack_forget()
        details = ["游戏：" + str(survey.get("label", "未知")),
                   _describe(survey)]
        reasons = survey.get("reasons") or []
        if reasons:
            details.append("兼容提示：\n" + "\n".join("• " + str(x) for x in reasons))
        self.var_toolbox_info.set("\n".join(details))

    def _paint_chips(self, state):
        for row in self.rows.values():
            level, text = _chip(row.entry, state)
            row.chip_var.set("%s %s" % (_GLYPH[level], text))
            row.chip_label.configure(text_color=_PAIR.get(level, _PAIR["dim"]))

    def _refresh_state(self):
        path = self.game_dir
        self._scan_generation += 1
        generation = self._scan_generation
        if not path:
            self.scan_busy = False
            self._survey = self._installed = None
            self._set_compat(None)
            self._apply_feature_support(None)
            self._paint_chips(None)
            self.var_toolbox_info.set("尚未选择游戏。")
            self.var_toolbox_installed.set("")
            return self._set_state("info", "先选择一个游戏目录。")
        if not os.path.isdir(os.path.join(path, "game")):
            self.scan_busy = False
            self._survey = self._installed = None
            self._set_compat(None)
            self._apply_feature_support(None)
            self._paint_chips(None)
            self.var_toolbox_info.set("目录中没有 game/ 子目录。")
            self.var_toolbox_installed.set("")
            return self._set_state("bad", "所选目录没有 game/ 子目录，请选择 Ren'Py 游戏根目录。")
        self.scan_busy = True
        self.var_global_status.set("正在检查游戏…")
        self._set_state("warn", "正在检查 Ren'Py 版本、功能 API 和已安装补丁…")
        self._set_buttons()
        threading.Thread(target=self._scan_worker, args=(path, generation), daemon=True).start()
        return "warn", "正在检查游戏。"

    def _scan_worker(self, path, generation):
        try:
            survey = compat.survey(path, quick=True)
            installed = cmd_fontfix.installed_state(path)
            self.queue.put(("__scan_done__", generation, path, survey, installed, None))
        except Exception as exc:
            self.queue.put(("__scan_done__", generation, path, None, None,
                            "%s: %s" % (type(exc).__name__, exc)))

    def _scan_finished(self, generation, path, survey, installed, error):
        if generation != self._scan_generation or path != self.game_dir:
            return
        self.scan_busy = False
        self.var_global_status.set("就绪")
        if error:
            self._set_compat(None)
            self._paint_chips(None)
            self.var_toolbox_info.set("检查失败：" + error)
            self._set_state("bad", "无法读取游戏兼容状态；请查看日志或重新检查。")
            self._log("\n[游戏检查失败] " + error + "\n")
            self._set_buttons()
            return
        self._survey, self._installed = survey, installed
        self._set_compat(survey)
        self._apply_feature_support(survey)
        self._paint_chips(installed)
        installed_ids = [features.title_of(fid) for fid in features.ids()
                         if installed.get(features.by_id(fid)["state"]["installed"])]
        self.var_toolbox_installed.set("已安装：" + ("、".join(installed_ids) if installed_ids else "无"))
        if not installed.get("shim"):
            self._set_state("ok", "尚未安装本工具的补丁，可以开始。")
        elif not installed.get("ours"):
            self._set_state("warn", "发现同名但不属于本工具的文件；覆盖前会先询问并备份。")
        elif installed.get("current"):
            self._set_state("ok", "补丁已安装且模板为当前版本。")
        else:
            self._set_state("warn", "检测到旧版补丁模板；可以重新处理更新。")
        self._set_buttons()

    def _drain(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, tuple):
                    event = item[0]
                    if event == "__scan_done__":
                        self._scan_finished(*item[1:])
                    elif event == "__done__":
                        self._finish(item[1])
                    elif event == "__sim_log__":
                        self._log(str(item[1]))
                    elif event == "__sim_stage__":
                        self._set_sim_stage(item[1], item[2], item[3])
                    elif event == "__sim_failed__":
                        self._simulation_failed(item[1], item[2])
                    elif event == "__sim_prepared__":
                        self._simulation_prepared(item[1])
                    elif event == "__sim_launched__":
                        self._simulation_launched(item[1])
                    elif event == "__sim_launch_failed__":
                        self._simulation_launch_failed(item[1])
                    elif event == "__sim_confirmed__":
                        self._simulation_confirmed()
                    elif event == "__sim_confirm_failed__":
                        self._simulation_confirm_failed(item[1])
                    elif event == "__sim_cleaned__":
                        self._simulation_cleaned(item[1])
                else:
                    self._log(item)
        except queue.Empty:
            pass
        try:
            self.root.after(80, self._drain)
        except tk.TclError:
            pass

    def _set_buttons(self):
        valid = bool(self.game_dir and os.path.isdir(os.path.join(self.game_dir, "game")))
        locked = self.busy or self.sim_preparing or self.sim_session is not None
        selected = bool(self._ticked())
        can_work = valid and selected and not locked and not self.scan_busy
        for button, enabled in ((self.btn_go, can_work), (self.btn_dry, can_work),
                                (self.btn_undo, valid and not locked and not self.scan_busy),
                                (self.btn_pick, not locked),
                                (self.btn_add_game, not locked)):
            button.configure(state="normal" if enabled else "disabled")
        for row in self.rows.values():
            row.toggle.configure(state="normal" if not locked and row.supported else "disabled")
        if self.busy:
            self.var_global_status.set("正在处理…")
            self.bar.grid()
            self.bar.start()
        else:
            self.bar.stop()
            self.bar.grid_remove()
        if self.sim_confirm_frame.winfo_manager() == "pack":
            self.sim_confirm_frame.pack_configure(before=self.buttons)
        self._update_action_hint()

    def _show_log(self):
        self.var_log.set(True)
        self._show_page("log")

    def pick(self):
        chosen = filedialog.askdirectory(title="选择 Ren'Py 游戏根目录")
        if chosen:
            self.set_game_dir(chosen)

    def set_game_dir(self, game_dir, remember=True):
        self.game_dir = os.path.abspath(os.fspath(game_dir)) if game_dir else None
        self.var_dir.set(self.game_dir or "")
        if self.game_dir and remember and os.path.isdir(os.path.join(self.game_dir, "game")):
            try:
                self.state = app_state.add_game(self.state, self.game_dir)
                self._persist_state()
                self._render_library()
            except (OSError, TypeError, ValueError) as exc:
                self.var_global_status.set("游戏未能加入游戏库：%s" % exc)
        elif self.game_dir and not remember:
            self.state["active_game"] = self.game_dir
        self._refresh_state()
        self._set_buttons()

    def add_game(self):
        chosen = filedialog.askdirectory(title="添加 Ren'Py 游戏根目录")
        if not chosen:
            return
        try:
            self.state = app_state.add_game(self.state, chosen)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror(TITLE, str(exc))
            return
        self._persist_state()
        self._render_library()
        self.set_game_dir(chosen, remember=False)
        self._show_page("process")

    def rename_game(self, entry):
        name = simpledialog.askstring("重命名游戏", "显示名称：", initialvalue=entry["name"],
                                      parent=self.root)
        if name is None:
            return
        active_game = self.state.get("active_game", "")
        try:
            self.state = app_state.add_game(self.state, entry["path"], name)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror(TITLE, str(exc))
            return
        self.state["active_game"] = active_game
        self._persist_state()
        self._render_library()

    def remove_game(self, path):
        self.state = app_state.remove_game(self.state, path)
        self._persist_state()
        self._render_library()
        if self.game_dir and os.path.normcase(os.path.realpath(self.game_dir)) == \
                os.path.normcase(os.path.realpath(path)):
            self.game_dir = None
            self.var_dir.set("")
            self._refresh_state()
            self._set_buttons()

    def refresh_game(self):
        self._refresh_state()

    def open_game_folder(self):
        if not self.game_dir or not os.path.isdir(self.game_dir):
            messagebox.showinfo(TITLE, "请先选择有效的游戏目录。")
            return
        try:
            os.startfile(self.game_dir)
        except (AttributeError, OSError) as exc:
            messagebox.showerror(TITLE, "无法打开目录：%s" % exc)

    def copy_log(self):
        text = self.log.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.var_global_status.set("日志已复制")

    def export_log(self):
        path = filedialog.asksaveasfilename(
            title="导出运行日志", defaultextension=".txt",
            filetypes=(("文本文件", "*.txt"), ("所有文件", "*.*")))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(self.log.get("1.0", "end-1c"))
            self.var_global_status.set("日志已导出")
        except OSError as exc:
            messagebox.showerror(TITLE, "导出失败：%s" % exc)

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _schedule_geometry_save(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        if self._geometry_job is not None:
            try:
                self.root.after_cancel(self._geometry_job)
            except tk.TclError:
                pass
        self._geometry_job = self.root.after(700, self._save_geometry)

    def _save_geometry(self):
        self._geometry_job = None
        try:
            width, height = self.root.winfo_width(), self.root.winfo_height()
            if width >= 900 and height >= 620:
                self.state["window"] = {"width": width, "height": height}
                if hasattr(self, "var_window"):
                    self.var_window.set("%d × %d（自动记住）" % (width, height))
                self._persist_state()
        except (tk.TclError, OSError):
            pass

    def _persist_state(self):
        try:
            app_state.save_state(self.state, self.state_path)
        except (OSError, TypeError, ValueError) as exc:
            self.var_global_status.set("设置未能保存：%s" % exc)

    def _destroy_root(self):
        if self._geometry_job is not None:
            try:
                self.root.after_cancel(self._geometry_job)
            except tk.TclError:
                pass
            self._geometry_job = None
        self._save_geometry()
        self.root.destroy()

    def _choose_launcher(self, launchers):
        if len(launchers) == 1:
            return launchers[0]
        result = {"value": None}
        window = ctk.CTkToplevel(self.root)
        window.title("选择游戏启动器")
        window.transient(self.root)
        window.resizable(False, False)
        frame = ctk.CTkFrame(window, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=18, pady=16)
        ctk.CTkLabel(frame, text="找到多个启动程序，请选择要测试的版本：",
                     anchor="w", wraplength=400, font=self._font(10)).pack(
                         anchor="w", pady=(0, 8))
        selected = tk.StringVar(value=launchers[0])
        for launcher in launchers:
            name = os.path.basename(str(launcher))
            ctk.CTkRadioButton(frame, text=name, value=launcher, variable=selected,
                               font=self._font(9)).pack(anchor="w", pady=2)
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", pady=(12, 0))
        def choose():
            result["value"] = selected.get()
            window.destroy()
        ctk.CTkButton(buttons, text="启动所选项", command=choose,
                      fg_color=_PAIR["accent"], font=self._font(9)).pack(side="right")
        ctk.CTkButton(buttons, text="取消", command=window.destroy,
                      fg_color="transparent", border_width=1,
                      border_color=_PAIR["border"], text_color=_PAIR["fg"],
                      font=self._font(9)).pack(side="right", padx=(0, 7))
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.grab_set()
        self.root.wait_window(window)
        return result["value"]


def main(initial_dir=None):
    state = app_state.load_state()
    ctk.set_default_color_theme("blue")
    ctk.set_appearance_mode(state.get("appearance", "system"))
    root = ctk.CTk()
    app = App(root, state=state)
    if initial_dir:
        app.set_game_dir(initial_dir)
    root.mainloop()
    return 0
