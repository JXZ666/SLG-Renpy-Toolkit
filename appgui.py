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
import help_content
import renpy_compat
import renpy_gallery
import simulation
import engine_adapters
import ui_focus
import ui_text
import ui_tokens

TITLE = branding.APP_NAME

# The glyphs are semantic status markers, not emoji.  They are deliberately
# small and monochrome so the text colour carries the meaning in both themes.
_GLYPH = {"ok": "\u221a", "warn": "!", "bad": "\u00d7", "info": "\u00b7"}


def _aliases(theme):
    """Compatibility names used by the older layout code.

    ``accent`` used to mean both “accent fill” and “accent text”.  Those two
    now have different jobs: a dark purple fill with white text, and a lighter
    purple for text on a light surface.  The alias keeps old call sites working
    while new code uses the explicit names.
    """
    pal = dict(ui_tokens.PALETTES[theme])
    pal["accent"] = pal["accent_fill"]
    pal["selbg"] = pal["select"]
    pal["selfg"] = pal["fg"]
    return pal


_COLORS = {theme: _aliases(theme) for theme in ("light", "dark")}
_PAIR = {name: (_COLORS["light"][name], _COLORS["dark"][name])
         for name in _COLORS["light"]}


def _walk(widget):
    """Yield a widget and every descendant, depth first."""
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


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


def _namespace(game_dir, revert=False, dry_run=False, force=False, skip_intro=None,
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
    feature_ids = list(feature_ids)
    if skip_intro is True and "intro" not in feature_ids:
        feature_ids.append("intro")
    elif skip_intro is False:
        feature_ids = [f for f in feature_ids if f != "intro"]
    return argparse.Namespace(
        game_dir=game_dir, work=None, mode="luna",
        lang="chinesesimplified", revert=revert, force=force, dry_run=dry_run,
        features=list(feature_ids), skip_intro="intro" in feature_ids)


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
    """One compact line naming what kind of game this folder holds."""
    engine = s.get("engine", {})
    if engine.get("id") and engine["id"] != "renpy":
        name = {"rpgmaker_mv": "RPG Maker MV",
                "rpgmaker_mz": "RPG Maker MZ"}.get(engine["id"], "未知引擎")
        return "%s  ·  %s %s" % (name, engine.get("version") or "版本未知",
                                 s.get("label") or "")
    r = s.get("renpy") or {}
    py = (s.get("python") or {}).get("major")
    bits = ["Ren'Py %s" % (r.get("version") or "版本未知")]
    if r.get("name"):
        bits.append(str(r["name"]))
    bits.append("Python %s" % (py if py else "?"))
    bits.append("双架构" if s.get("arch") == "both" else (s.get("arch") or "架构未知"))
    return "  ·  ".join(b for b in bits if b)


def _reasons(s):
    reasons = ui_text.localize_reasons((s or {}).get("reasons") or [])
    return "\n".join("\u2022 " + x for x in reasons)


def _describe_details(s):
    """Labeled rows for the diagnostics page, instead of one long dot string."""
    engine = s.get("engine") or {}
    r = s.get("renpy") or {}
    py = (s.get("python") or {}).get("major")
    src = s.get("sources") or {}
    scripts = (src.get("loose_rpy") or 0) + (src.get("loose_rpyc") or 0)
    name = {"rpgmaker_mv": "RPG Maker MV",
            "rpgmaker_mz": "RPG Maker MZ"}.get(engine.get("id"), "Ren'Py")
    lines = [
        "游戏：" + str(s.get("label") or "未知"),
        "引擎：" + name + " " + str(engine.get("version") or r.get("version") or "版本未知"),
        "运行时：Python %s" % (py if py else "未识别"),
        "架构：" + ("双架构" if s.get("arch") == "both" else str(s.get("arch") or "未识别")),
        "脚本：%d 个可读脚本" % scripts,
    ]
    if src.get("rpa"):
        lines.append("归档：%d 个" % len(src["rpa"]))
    if s.get("splash"):
        lines.append("开场 logo：" + ("找到了" if s["splash"].get("found") else "没找到"))
    return lines


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
        self.support_level = "unknown"
        self.reason_items = []


class _OperationMixin:
    """Shared operation and simulation state-machine methods."""

    # --- state ------------------------------------------------------------

    _SIM_STAGE_NAMES = {
        "compat": "\u517c\u5bb9\u9884\u68c0",
        "copy": "\u590d\u5236\u6e38\u620f\u526f\u672c",
        "install": "\u6a21\u62df\u5b89\u88c5\u8865\u4e01",
        "launch": "\u542f\u52a8\u526f\u672c",
        "confirm": "\u786e\u8ba4\u4e3b\u83dc\u5355",
        "gameplay": "剧情场景验证",
    }

    _SIM_STAGE_DEFAULTS = {
        "compat": "\u5c1a\u672a\u5f00\u59cb",
        "copy": "\u7b49\u5f85\u590d\u5236",
        "install": "\u7b49\u5f85\u6a21\u62df\u5b89\u88c5",
        "launch": "\u5c1a\u672a\u542f\u52a8",
        "confirm": "\u7b49\u5f85\u542f\u52a8\u9a8c\u8bc1",
        "gameplay": "尚未验证",
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
        if not self.game_dir or engine_adapters.detect(self.game_dir)["id"] in ("unknown", "ambiguous"):
            self._set_sim_result("bad", "\u8bf7\u5148\u9009\u62e9\u6709\u6548\u7684\u6e38\u620f\u6839\u76ee\u5f55\u3002")
            return

        game_dir = self.game_dir
        self._log("\n===== 模拟运行 =====\n")
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
            survey = engine_adapters.survey(game_dir, quick=True)
            support_map = survey.get("feature_support", {}) if isinstance(survey, dict) else {}
            unsupported = []
            if isinstance(support_map, dict):
                for fid in feature_ids:
                    spec = support_map.get(fid)
                    # Fail closed: only an explicit True is usable.  A missing
                    # or null value is exactly how an unreviewed adapter used
                    # to look supported and get copied into a simulation.
                    if not isinstance(spec, dict) or spec.get("supported") is not True:
                        reasons = spec.get("reasons") if isinstance(spec, dict) else []
                        if isinstance(reasons, str):
                            reasons = [reasons]
                        if not reasons:
                            reasons = ["support status is unknown"]
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
        self._log("\n[模拟失败] %s\n" % message)
        self.sim_confirm_frame.pack_forget()
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
        self._pack_sim_confirm()
        self._set_buttons()
        if self.close_after_cleanup:
            self._cleanup_simulation(stop=True, close_after=True)
            return
        self.root.after(400, self._poll_simulation)

    def _simulation_launch_failed(self, message):
        self.busy = False
        self._set_sim_stage("launch", "failed", message)
        self._set_sim_result("bad", "\u65e0\u6cd5\u542f\u52a8\u6e38\u620f\uff1a" + str(message))
        self._log("\n[模拟启动失败] %s\n" % message)
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
        runtime_errors = getattr(session, "runtime_errors", [])
        if runtime_errors:
            self._set_sim_stage("launch", "failed", runtime_errors[-1])
            self._set_sim_result("bad", "游戏报告了新异常：" + runtime_errors[-1])
            self._show_log()
            self.sim_confirm_frame.pack_forget()
            if code is None:
                self.root.after(400, self._poll_simulation)
            else:
                self.sim_process_exited = True
                self._cleanup_simulation(stop=False)
            return
        if code is None:
            self.root.after(400, self._poll_simulation)
            return
        self.sim_process_exited = True
        if code != 0:
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
        self.btn_sim_gameplay.configure(state="normal")
        self._set_sim_stage("gameplay", "pending", "尚未确认新游戏、原报错场景和读档")
        self._set_sim_result("warn", "主菜单已确认；剧情和露娜组合尚未验证。继续在副本中测试后确认剧情结果。")
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

    def confirm_simulation_gameplay(self):
        session = self.sim_session
        if session is None or not self.sim_confirmed:
            return
        try:
            session.confirm_gameplay()
        except Exception as exc:
            self._set_sim_stage("gameplay", "failed", str(exc))
            self._set_sim_result("bad", "剧情确认失败：" + str(exc))
            self._show_log()
            return
        self._set_sim_stage("gameplay", "success", "用户确认已测试的剧情场景正常")
        self._set_sim_result("ok", "主菜单与本次测试的剧情场景已确认；关闭游戏后清理副本。")
        self.sim_gameplay_confirmed = True
        self.btn_sim_gameplay.configure(state="disabled")

    def _simulation_confirm_failed(self, message):
        self.busy = False
        self._set_sim_stage("confirm", "failed", message)
        self._set_sim_result("bad", "\u65e0\u6cd5\u786e\u8ba4\u4e3b\u83dc\u5355\uff1a" + str(message))
        self._log("\n[模拟确认失败] %s\n" % message)
        self._show_log()
        self._set_buttons()
        if self.sim_session is not None and not self.sim_confirmed:
            self._pack_sim_confirm()
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
            self.close_after_cleanup = False
            self._set_sim_result(
                "bad", "隔离副本清理遇到错误：" + "; ".join(errors) +
                "。可以点击“重试清理”，或关闭窗口后再试。")
            self._pack_sim_confirm(cleanup=True)
            self._set_buttons()
            return
        self.sim_session = None
        self.sim_preparing = False
        self.sim_launched = False
        self.sim_confirmed = False
        self.sim_gameplay_confirmed = False
        self.sim_process_exited = False
        self.sim_confirm_frame.pack_forget()
        self.btn_sim_gameplay.configure(state="disabled")
        self._set_sim_stage("copy", "success",
                            "隔离副本已清理")
        if self.sim_result_level == "ok":
            self._set_sim_result(
                "ok", self.sim_result_message + "  隔离副本已清理。")
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



    def _engine_id(self):
        try:
            return engine_adapters.detect(self.game_dir)["id"]
        except Exception:  # noqa: BLE001 - a broken path is simply unusable
            return "unknown"

    def _update_action_hint(self):
        selected = [features.title_of(fid) for fid in self._ticked()]
        if selected:
            text = "已选 %d 项：%s" % (len(selected), "、".join(selected))
        elif not self.game_dir:
            text = "先选择游戏目录，再勾选要处理的功能。"
        elif self.scan_failed:
            text = "游戏检查失败；请查看运行日志，修复路径后重新检查。"
        elif self._engine_id() in ("unknown", "ambiguous"):
            text = "该目录没有可识别的游戏引擎，请选择包含 game/ 的游戏根目录。"
        elif not any(row.supported for row in self.rows.values()):
            text = "当前游戏没有可用功能，请查看功能行中的兼容原因。"
        else:
            text = "勾选至少一个可用功能；模拟和安装都会使用当前勾选项。"
        self.var_action_hint.set(text)

    def _selection_changed(self):
        self._set_buttons()

    def _log(self, text):
        if not text:
            return
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")
        if hasattr(self, "log_empty"):
            self.log_empty.place_forget()
        self._update_log_actions()

    def _log_text(self):
        return self.log.get("1.0", "end-1c")

    def _update_log_actions(self):
        if not hasattr(self, "btn_clear_log"):
            return
        has_text = bool(self._log_text().strip())
        for button in (self.btn_clear_log, self.btn_copy_log, self.btn_export_log):
            button.configure(state="normal" if has_text else "disabled")
        if hasattr(self, "btn_view_log"):
            self.btn_view_log.configure(state="normal" if has_text else "disabled")
        if not has_text and hasattr(self, "log_empty"):
            self.log_empty.place(relx=0.5, rely=0.45, anchor="center")

    def _ticked(self):
        """Read enabled feature ids on the main thread, in catalogue order."""
        return [fid for fid in features.ids()
                if self.rows[fid].supported and self.var_on[fid].get()]


    def _apply_feature_support(self, survey):
        # Older survey data has no support matrix; keep its previous permissive
        # behavior.  A present-but-incomplete matrix is different: an unknown
        # value must not be treated as "supported", because that is how an
        # experimental adapter ends up looking finished.
        support_map = survey.get("feature_support") if isinstance(survey, dict) else None
        matrix_present = isinstance(support_map, dict) and bool(support_map)
        support_map = support_map if isinstance(support_map, dict) else {}
        for fid, row in self.rows.items():
            spec = support_map.get(fid)
            spec = spec if isinstance(spec, dict) else {}
            raw_reasons = spec.get("reasons") or []
            if isinstance(raw_reasons, str):
                raw_reasons = [raw_reasons]
            reasons = ui_text.localize_reasons(raw_reasons, fid)
            row.reason_items = [
                {"code": ui_text.reason_code(reason), "text": text}
                for reason, text in zip(raw_reasons, reasons)
            ] if reasons else []
            if not matrix_present:
                row.supported = True
                row.support_level = "unknown"
                row.reason_var.set("")
                row.reason_label.pack_forget()
                continue
            level, label, detail = ui_text.support_copy(spec, fid)
            row.support_level = level
            row.supported = level in ("supported", "experimental")
            if level == "unsupported":
                self.var_on[fid].set(False)
                row.reason_var.set(detail or "当前游戏不支持此功能。")
                row.reason_label.configure(text_color=_PAIR["bad"])
                row.reason_label.pack(fill="x", padx=14, pady=(6, 11))
            elif level == "experimental":
                row.reason_var.set(detail or "实验性功能，尚未在真实引擎完整验证。")
                row.reason_label.configure(text_color=_PAIR["warn"])
                row.reason_label.pack(fill="x", padx=14, pady=(6, 11))
            elif level == "unknown":
                self.var_on[fid].set(False)
                row.reason_var.set("尚未确认此功能是否可用；为避免误操作，已暂不勾选。")
                row.reason_label.configure(text_color=_PAIR["bad"])
                row.reason_label.pack(fill="x", padx=14, pady=(6, 11))
            else:
                row.reason_var.set(detail)
                row.reason_label.configure(text_color=_PAIR["dim"])
                if detail:
                    row.reason_label.pack(fill="x", padx=14, pady=(6, 11))
                else:
                    row.reason_label.pack_forget()
            if any(item["code"] == "unknown" for item in row.reason_items):
                # Keep technical evidence available without putting the raw
                # English sentence in the normal interface.
                raw = "；".join(str(x) for x in raw_reasons)
                if raw and hasattr(self, "log"):
                    self._log("\n[兼容性原文 %s] %s\n" % (fid, raw))
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
        selected = self._ticked()
        if not selected:
            messagebox.showinfo(TITLE, "请先勾选至少一个可用功能。")
            return
        if not self._confirm_install(selected):
            return
        if not self._confirm_overwrite():
            return
        self._spawn(self._args(force=True), "安装到游戏", notify=True)

    def _installed_titles(self, state=None):
        if state is None:
            state = self._installed
        state = state or {}
        titles = []
        for entry in features.CATALOG:
            keys = entry.get("state") or {}
            if any(state.get(key) for key in keys.values()):
                titles.append(entry["title"])
        return titles

    def _confirm_install(self, selected):
        names = "、".join(features.title_of(fid) for fid in selected)
        body = (
            "即将把以下功能写入游戏目录：\n\n  %s\n\n"
            "路径：%s\n\n"
            "工具会先备份要改动的文件，之后可以用“撤销还原”恢复。"
            "不确定游戏是否兼容时，请先取消并运行模拟。\n\n继续吗？"
            % (names, self.game_dir or "（未选择）")
        )
        return messagebox.askyesno(TITLE, body)

    def revert(self):
        # No feature selection here: undo is undo, everything this tool wrote
        # goes, whether or not it is ticked now.
        if not self.game_dir:
            messagebox.showinfo(TITLE, "请先选择一个游戏目录。")
            return
        try:
            current = engine_adapters.installed_state(self.game_dir)
        except Exception as exc:  # noqa: BLE001 - report instead of crashing
            messagebox.showerror(TITLE, "无法读取安装状态：%s\n请先重新检查游戏。" % exc)
            return
        installed = self._installed_titles(current)
        if not installed:
            messagebox.showinfo(TITLE, "没有检测到本工具写入的补丁，无需撤销。")
            return
        body = (
            "将撤销本工具写入的以下补丁：\n\n  %s\n\n"
            "游戏存档和自然取得的进度不会被回滚；只恢复本工具改过的文件。\n\n"
            "继续吗？" % "、".join(installed)
        )
        if not messagebox.askyesno(TITLE, body):
            return
        self._spawn(_namespace(self.game_dir, revert=True), "撤销还原", notify=True)

    def _foreign_targets(self, selected):
        """Return target paths that hold files this tool cannot claim.

        The addon targets are not all listed by compat.survey(); checking them
        here closes the gap that let a hand-written zz_rpykit_compat.rpy be
        overwritten after only the generic install confirmation.
        """
        try:
            state = engine_adapters.installed_state(self.game_dir)
            engine = engine_adapters.detect(self.game_dir)["id"]
        except Exception as exc:  # noqa: BLE001 - report, do not overwrite blind
            raise RuntimeError("无法读取安装状态：%s" % exc)
        relative = []
        if engine == "renpy" and state.get("shim") and not state.get("ours"):
            relative.append("game/" + cmd_fontfix.SHIM_REL)
        if "fontfix" in selected:
            relative.extend(("game/" + cmd_fontfix.SHIM_REL,
                             "game/" + cmd_fontfix.GAME_FONT_REL,
                             "game/NotoSansSC-VF.ttf"))
        if "intro" in selected:
            relative.append("game/" + cmd_fontfix.INTRO_REL)
            for name in cmd_fontfix.find_intro_conflicts(self.game_dir):
                relative.append("game/" + name)
        if "runtime_compat" in selected:
            relative.append("game/" + renpy_compat.REL)
        if "gallery" in selected:
            relative.append("game/" + renpy_gallery.REL)
        foreign = []
        for rel in relative:
            full = os.path.join(self.game_dir, *rel.replace("/", os.sep).split(os.sep))
            if not os.path.isfile(full):
                continue
            try:
                ours = cmd_fontfix._is_ours(full)
            except Exception:  # noqa: BLE001 - an unreadable file is not ours
                ours = False
            if not ours and rel not in foreign:
                foreign.append(rel)
        # These came from the scan and already denote real files.
        for rel in ((self._survey or {}).get("collisions") or []):
            rel = str(rel)
            if rel not in foreign:
                foreign.append(rel)
        return foreign

    def _confirm_overwrite(self):
        """One explicit confirmation for every foreign target path."""
        try:
            selected = set(self._ticked())
            foreign = self._foreign_targets(selected)
        except RuntimeError as exc:
            messagebox.showerror(TITLE, str(exc) + "\n请先重新检查游戏。")
            return False
        if not foreign:
            return True
        return messagebox.askyesno(
            TITLE,
            "以下位置已有非本工具写入的文件：\n\n  %s\n\n"
            "继续会先把它们备份到工作目录的 quarantine/，再写入本工具的版本；"
            "「撤销还原」会尽量放回原处。\n\n要继续吗？"
            % "\n  ".join(foreign))

    def _spawn(self, argv, title, notify):
        if self.busy:
            return
        self._log("\n===== %s =====\n" % title)
        self._show_log()
        self.busy = True
        self.notify = notify
        self.last_action = "revert" if getattr(argv, "revert", False) else "install"
        self.last_selected = list(getattr(argv, "features", None) or [])
        self._set_buttons()
        threading.Thread(target=self._work, args=(argv,), daemon=True).start()

    def _work(self, argv):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _Sink(self.queue)
        code = 0
        try:
            code = engine_adapters.run(argv) or 0
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
            if self.last_action == "revert":
                messagebox.showinfo(
                    TITLE, "已撤销本工具写入的补丁。\n\n"
                           "游戏存档和自然取得的进度没有被回滚；"
                           "如果文件被外部修改过，工具会保留可恢复的备份。")
            elif self.last_outcome == "no_changes":
                messagebox.showinfo(
                    TITLE, "没有需要改动的文件。\n\n"
                           "选中的字体已覆盖中文，本次没有写入游戏目录。")
            else:
                messagebox.showinfo(
                    TITLE, "已安装：%s。\n\n"
                           "建议先开一次游戏检查主菜单和一段剧情；"
                           "如果异常，可点击“撤销还原”。" % (names or "所选功能"))
        else:
            self._show_log()
            messagebox.showerror(
                TITLE, "处理失败，游戏目录没有完成本次操作。\n\n"
                       "详细信息已写入运行日志；如提示部分文件已改，请先撤销还原再重试。")


class App(_OperationMixin):
    """CustomTkinter production shell around the existing operation state machine."""

    PAGES = {
        "process": ("处理", "选择游戏，先模拟运行，再决定是否写入原目录。"),
        "library": ("游戏库", "只保存手动添加的位置，不扫描整个磁盘。"),
        "toolbox": ("游戏信息", "兼容性、引擎版本与已安装补丁的只读诊断。"),
        "log": ("运行日志", "查看、复制或导出最近的处理输出。"),
        "help": ("帮助", "离线查看功能说明、风险边界与撤销方式。"),
        "settings": ("设置", "调整外观；窗口大小会自动记住。"),
    }
    NAV = (("process", "处理"), ("library", "游戏库"),
           ("toolbox", "游戏信息"), ("log", "运行日志"),
           ("help", "帮助"), ("settings", "设置"))

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
        self.last_action = None
        self.rows = {}
        self.var_on = {}
        self.action_buttons = {}
        self.queue = queue.Queue()
        self.sim_session = None
        self.sim_preparing = False
        self.sim_launched = False
        self.sim_confirmed = False
        self.sim_gameplay_confirmed = False
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
        self.scan_failed = False
        self._font_cache = {}
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Configure>", self._schedule_geometry_save, add="+")
        self._apply_theme(self.state.get("appearance", "system"), persist=False)
        self._set_buttons()
        self.root.after(80, self._drain)
        active = self.state.get("active_game")
        if active and os.path.isdir(active):
            self.set_game_dir(active, remember=False)

    def _font(self, size=None, weight="normal"):
        """Return one cached CTkFont per role/size.

        CTkFont objects belong to a Tk root.  Recreating them for every label
        was both wasteful and a source of inconsistent sizes when a caller
        passed a literal.  ``size=None`` means body copy.
        """
        if size is None:
            size = ui_tokens.FONT_ROLES["body"]
        key = (int(size), str(weight))
        cached = self._font_cache.get(key)
        if cached is None:
            cached = ctk.CTkFont(family="Microsoft YaHei UI", size=int(size),
                                 weight=str(weight))
            self._font_cache[key] = cached
        return cached

    def _card(self, parent, padding=ui_tokens.SPACING[3]):
        card = ctk.CTkFrame(parent, corner_radius=ui_tokens.RADIUS["card"],
                            fg_color=_PAIR["panel"], border_width=1,
                            border_color=_PAIR["border"])
        card.pack_propagate(True)
        card.pack(fill="x", pady=(0, ui_tokens.SPACING[2]))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack_propagate(True)
        inner.pack(fill="both", expand=True, padx=padding, pady=padding)
        return card, inner

    def _build(self):
        self.root.title(TITLE)
        size = self.state.get("window") or app_state.DEFAULT_WINDOW
        width = max(900, int(size.get("width", 1180)))
        height = max(620, int(size.get("height", 780)))
        width, height = self._clamp_window_size(width, height)
        min_w, min_h, _max_w, _max_h = self._screen_bounds()
        self.root.geometry("%dx%d" % (width, height))
        self.root.minsize(min_w, min_h)
        try:
            self.root.iconbitmap(cmd_fontfix._asset(branding.ICON_NAME))
        except Exception:
            pass

        self.shell = ctk.CTkFrame(self.root, corner_radius=0, fg_color=_PAIR["bg"])
        self.shell.pack(fill="both", expand=True)
        self.shell.grid_columnconfigure(1, weight=1)
        self.shell.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self.shell, width=224, corner_radius=0,
                                    fg_color=_PAIR["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        ctk.CTkFrame(self.sidebar, width=4, corner_radius=0,
                     fg_color=_PAIR["accent_fill"]).place(x=0, y=0, relheight=1)
        ctk.CTkFrame(self.sidebar, width=1, corner_radius=0,
                     fg_color=_PAIR["border"]).place(relx=1.0, y=0, relheight=1,
                                                     anchor="ne")

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=(20, 12), pady=(24, 20))
        ctk.CTkLabel(logo, text="RPY", width=44, height=44,
                     corner_radius=ui_tokens.RADIUS["card"],
                     fg_color=_PAIR["accent_soft"], text_color=_PAIR["accent_text"],
                     font=self._font(15, "bold")).pack(side="left")
        brand = ctk.CTkFrame(logo, fg_color="transparent")
        brand.pack(side="left", padx=(11, 0))
        ctk.CTkLabel(brand, text="Ren'Py Toolkit", anchor="w",
                     text_color=_PAIR["fg"],
                     font=self._font(13, "bold")).pack(anchor="w")
        ctk.CTkLabel(brand, text="简体中文补丁工具", anchor="w",
                     text_color=_PAIR["dim"],
                     font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(
                         anchor="w", pady=(3, 0))

        self.nav_buttons = {}
        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=12)
        for page_id, title in self.NAV:
            button = ctk.CTkButton(
                nav, text=title, anchor="w", height=42,
                corner_radius=ui_tokens.RADIUS["button"],
                fg_color="transparent", hover_color=_PAIR["panel_alt"],
                text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["secondary"]),
                command=lambda target=page_id: self._show_page(target))
            button.pack(fill="x", pady=3)
            self.nav_buttons[page_id] = button
        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=15)
        self.btn_theme = ctk.CTkButton(
            bottom, text="外观：跟随系统", height=36,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["panel_alt"], hover_color=_PAIR["accent_soft"],
            text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=self._toggle_theme)
        self.btn_theme.pack(fill="x")
        self.version_label = ctk.CTkLabel(
            bottom, text="v" + branding.APP_VERSION, anchor="w",
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]))
        self.version_label.pack(anchor="w", pady=(9, 0))
        self.channel_label = ctk.CTkLabel(
            bottom, text="界面测试版", anchor="w", text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]))
        self.channel_label.pack(anchor="w", pady=(2, 0))

        self.content = ctk.CTkFrame(self.shell, fg_color=_PAIR["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 24),
                          pady=(0, 16))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)
        self.header = ctk.CTkFrame(self.content, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 12))
        self.header.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(
            self.header, text="", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["page"], "bold"))
        self.page_title.grid(row=0, column=0, sticky="w")
        self.page_subtitle = ctk.CTkLabel(
            self.header, text="", anchor="w", text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["body"]))
        self.page_subtitle.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.var_global_status = tk.StringVar(value="就绪")
        self.status_chip = ctk.CTkLabel(
            self.header, textvariable=self.var_global_status, height=28,
            corner_radius=14, fg_color=_PAIR["panel_alt"],
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]), padx=10)
        self.status_chip.grid(row=0, column=1, rowspan=2, sticky="e",
                              padx=(12, 0))
        self.bar = ctk.CTkProgressBar(
            self.content, height=3, corner_radius=0,
            progress_color=_PAIR["accent_fill"], fg_color=_PAIR["border"])
        self.bar.set(0)
        self.bar.grid(row=1, column=0, sticky="new", padx=24)
        self.bar.grid_remove()
        self.page_host = ctk.CTkFrame(self.content, fg_color="transparent")
        self.page_host.grid(row=2, column=0, sticky="nsew", padx=24,
                            pady=(12, 4))
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
        self._build_help(self.pages["help"])
        self._build_settings(self.pages["settings"])
        self._show_page("process")
        self._install_focus()
        self._bind_shortcuts()
        self.root.after_idle(self._apply_wrap)

    def _build_process(self, parent):
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=1)

        page = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        self.process_scroll = page

        _, inner = self._card(page, padding=ui_tokens.SPACING[3])
        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="游戏目录", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                side="left")
        ctk.CTkLabel(
            head, text="Ren'Py 6-8 / RPG Maker MV-MZ", anchor="e",
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(side="right")
        ctk.CTkLabel(
            inner, text="选择包含 game/ 与引擎文件的游戏根目录。扫描只读取结构，不改动游戏。",
            anchor="w", justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", pady=(5, 12))
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self.var_dir = tk.StringVar(value="")
        self.entry_dir = ctk.CTkEntry(
            row, textvariable=self.var_dir, state="readonly", height=40,
            corner_radius=ui_tokens.RADIUS["control"],
            fg_color=_PAIR["input"], border_width=1,
            border_color=_PAIR["border_strong"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"]))
        self.entry_dir.pack(side="left", fill="x", expand=True)
        self.btn_pick = ctk.CTkButton(
            row, text="浏览…", width=92, height=40,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"], border_width=2,
            border_color=_PAIR["accent_fill"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"),
            command=self.pick)
        self.btn_pick.pack(side="left", padx=(8, 0))

        self.var_compat = tk.StringVar(value="")
        self.lbl_compat = ctk.CTkLabel(
            inner, textvariable=self.var_compat, anchor="w", justify="left",
            wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"]))
        self.var_reasons = tk.StringVar(value="")
        self.lbl_reasons = ctk.CTkLabel(
            inner, textvariable=self.var_reasons, anchor="w", justify="left",
            wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]))
        self.var_state = tk.StringVar(value="先选择一个游戏目录。")
        self.lbl_state = ctk.CTkLabel(
            inner, textvariable=self.var_state, anchor="w", justify="left",
            wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"))
        self.lbl_state.pack(anchor="w", pady=(10, 0))

        heading = ctk.CTkFrame(page, fg_color="transparent")
        heading.pack(fill="x", pady=(4, 7))
        ctk.CTkLabel(
            heading, text="功能", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                side="left")
        ctk.CTkLabel(
            heading, text="默认只勾选字体预飞；其余功能先在副本验证", anchor="e",
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(side="right")
        grid = ctk.CTkFrame(page, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        self.feature_grid = grid
        self.feature_cards = []
        self._feature_columns = 1
        self.rows = {}
        self.var_on = {}
        for i, entry in enumerate(features.CATALOG):
            feature_card = ctk.CTkFrame(
                grid, corner_radius=ui_tokens.RADIUS["card"],
                fg_color=_PAIR["panel"], border_width=1,
                border_color=_PAIR["border"])
            feature_card.grid(row=i, column=0, sticky="ew", pady=(0, 8))
            self.feature_cards.append(feature_card)
            feature_card.bind(
                "<Configure>",
                lambda event: self.root.after_idle(self._apply_wrap), add="+")
            head = ctk.CTkFrame(feature_card, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(11, 0))
            var = tk.BooleanVar(value=bool(entry.get("default_on", True)))
            self.var_on[entry["id"]] = var
            toggle = ctk.CTkCheckBox(
                head, text=entry["title"], variable=var,
                command=self._selection_changed,
                checkbox_width=20, checkbox_height=20, border_width=2,
                corner_radius=ui_tokens.RADIUS["control"],
                fg_color=_PAIR["accent_fill"],
                hover_color=_PAIR["accent_hover"],
                border_color=_PAIR["border_strong"],
                checkmark_color=_PAIR["on_accent"],
                text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["body"], "bold"))
            toggle.pack(side="left")
            chip_var = tk.StringVar(value="未检查")
            chip = ctk.CTkLabel(
                head, textvariable=chip_var, height=24, corner_radius=8,
                fg_color=_PAIR["panel_alt"], text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["meta"]), padx=8)
            chip.pack(side="right")
            help_button = ctk.CTkButton(
                head, text="说明", width=48, height=24,
                corner_radius=ui_tokens.RADIUS["button"],
                fg_color="transparent", border_width=1,
                border_color=_PAIR["border_strong"],
                hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["meta"]),
                command=lambda topic=entry["id"]: self.show_help(topic))
            help_button.pack(side="right", padx=(0, 6))
            summary = entry.get("summary") or entry.get("desc", "")
            ctk.CTkLabel(
                feature_card, text=summary, anchor="w", justify="left",
                wraplength=1, text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                    fill="x", padx=14, pady=(6, 0))
            reason_var = tk.StringVar(value="")
            reason = ctk.CTkLabel(
                feature_card, textvariable=reason_var, anchor="w",
                justify="left", wraplength=1, text_color=_PAIR["bad"],
                font=self._font(ui_tokens.FONT_ROLES["meta"]))
            self.rows[entry["id"]] = _FeatureRow(
                entry, feature_card, toggle, chip_var, chip, reason_var, reason)
        if "intro" in self.rows:
            self.var_skip = self.var_on["intro"]
            self.chk_skip = self.rows["intro"].toggle

        _, body = self._card(page)
        ctk.CTkLabel(
            body, text="模拟与安装", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                anchor="w")
        ctk.CTkLabel(
            body, text="模拟只作用于隔离副本；只有“安装到游戏”会写入原目录。",
            anchor="w", justify="left", wraplength=1,
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                fill="x", pady=(4, 10))
        self.sim_result_var = tk.StringVar(value="尚未运行模拟安装。")
        self.sim_result_label = ctk.CTkLabel(
            body, textvariable=self.sim_result_var, anchor="w",
            justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["body"], "bold"))
        self.sim_result_label.pack(anchor="w", pady=(0, 8))
        log_row = ctk.CTkFrame(body, fg_color="transparent")
        log_row.pack(fill="x", pady=(0, 8))
        self.btn_view_log = ctk.CTkButton(
            log_row, text="查看运行日志", height=30, width=106,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color="transparent", border_width=1,
            border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            state="disabled", command=self._show_log)
        self.btn_view_log.pack(side="left")
        ctk.CTkLabel(
            log_row, text="原始输出只写入左侧“运行日志”，这里保留步骤状态。",
            anchor="w", justify="left", wraplength=1,
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(
                side="left", padx=(10, 0))

        self.sim_confirm_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.btn_sim_success = ctk.CTkButton(
            self.sim_confirm_frame, text="已进入主菜单", height=32,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"],
            font=self._font(ui_tokens.FONT_ROLES["meta"], "bold"),
            command=self.confirm_simulation_success)
        self.btn_sim_failure = ctk.CTkButton(
            self.sim_confirm_frame, text="启动失败", height=32,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color="transparent", border_width=1,
            border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=self.confirm_simulation_failure)
        self.btn_sim_gameplay = ctk.CTkButton(
            self.sim_confirm_frame, text="已测试剧情 / 读档", height=32,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["panel_alt"], hover_color=_PAIR["accent_soft"],
            text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            state="disabled", command=self.confirm_simulation_gameplay)
        self.btn_sim_finish = ctk.CTkButton(
            self.sim_confirm_frame, text="结束模拟并清理", height=32,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=lambda: self._cleanup_simulation(
                stop=self.sim_launched and not self.sim_process_exited))
        self.btn_sim_cleanup = ctk.CTkButton(
            self.sim_confirm_frame, text="重试清理", height=32,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["bad"], hover_color=_PAIR["bad"],
            text_color=_PAIR["on_accent"],
            font=self._font(ui_tokens.FONT_ROLES["meta"], "bold"),
            command=lambda: self._cleanup_simulation(
                stop=self.sim_launched and not self.sim_process_exited))
        self.btn_sim_success.pack(side="left")
        self.btn_sim_failure.pack(side="left", padx=(7, 0))
        self.btn_sim_gameplay.pack(side="left", padx=(7, 0))
        self.btn_sim_finish.pack(side="left", padx=(7, 0))
        self.sim_confirm_frame.pack_forget()
        self.btn_sim_cleanup.pack_forget()

        footer = ctk.CTkFrame(
            outer, corner_radius=ui_tokens.RADIUS["card"],
            fg_color=_PAIR["panel"], border_width=1,
            border_color=_PAIR["border"])
        footer.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        footer_inner = ctk.CTkFrame(footer, fg_color="transparent")
        footer_inner.pack(fill="x", padx=14, pady=11)
        self.buttons = ctk.CTkFrame(footer_inner, fg_color="transparent")
        buttons = self.buttons
        buttons.pack(fill="x")
        self.btn_dry = ctk.CTkButton(
            buttons, text="模拟安装并运行", height=38,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"], border_width=2,
            border_color=_PAIR["accent_fill"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"),
            command=self.simulate_run)
        self.btn_dry.pack(side="left")
        self.btn_go = ctk.CTkButton(
            buttons, text="安装到游戏", height=38,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["panel_alt"], hover_color=_PAIR["accent_soft"],
            text_color=_PAIR["fg"], border_width=2,
            border_color=_PAIR["panel_alt"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"]),
            command=self.install)
        self.btn_go.pack(side="left", padx=(8, 0))
        self.btn_undo = ctk.CTkButton(
            buttons, text="撤销还原", height=38,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"]),
            command=self.revert)
        self.btn_undo.pack(side="left", padx=(8, 0))
        self.action_buttons = {"simulate": self.btn_dry, "go": self.btn_go,
                               "undo": self.btn_undo}
        self.var_action_hint = tk.StringVar(value="")
        ctk.CTkLabel(
            footer_inner, textvariable=self.var_action_hint, anchor="w",
            justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(
                anchor="w", pady=(8, 0))

        self.sim_stage_vars = {}
        self.sim_stage_labels = {}
        self.sim_card = ctk.CTkFrame(body, fg_color="transparent")
        self.sim_card.pack(fill="x", pady=(12, 0))
        ctk.CTkFrame(self.sim_card, height=1, fg_color=_PAIR["border"]).pack(
            fill="x", pady=(0, 9))
        ctk.CTkLabel(
            self.sim_card, text="模拟步骤", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["card_title"], "bold")).pack(
                anchor="w")
        ctk.CTkLabel(
            self.sim_card,
            text="进程正常退出不等于进入主菜单；确认结果后清理副本，不会修改原游戏。",
            anchor="w", justify="left", wraplength=1,
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(
                anchor="w", pady=(3, 7))
        for key, name in (("compat", "兼容预检"), ("copy", "准备隔离副本"),
                          ("install", "模拟安装补丁"), ("launch", "启动副本"),
                          ("confirm", "确认主菜单"), ("gameplay", "剧情场景验证")):
            var = tk.StringVar(value=name + "：等待")
            label = ctk.CTkLabel(
                self.sim_card, textvariable=var, anchor="w",
                text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["meta"]))
            label.pack(anchor="w", pady=2)
            self.sim_stage_vars[key] = var
            self.sim_stage_labels[key] = label
        self._reset_simulation_status()

    def _build_library(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 9))
        self.btn_add_game = ctk.CTkButton(
            tools, text="添加游戏…", height=36,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"], border_width=2,
            border_color=_PAIR["accent_fill"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"),
            command=self.add_game)
        self.btn_add_game.pack(side="left")
        ctk.CTkLabel(
            tools, text="只保存手动添加的位置，不扫描整盘", text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["meta"])).pack(
                side="left", padx=12)
        self.library_scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.library_scroll.pack(fill="both", expand=True)
        self.library_action_buttons = []
        self._render_library()

    def _library_status(self, path):
        if not os.path.isdir(path):
            return "unsupported", "路径不可用"
        try:
            engine = engine_adapters.detect(path)
        except Exception:  # noqa: BLE001 - one bad bookmark must not break the page
            return "unsupported", "不可访问"
        if engine["id"] in ("unknown", "ambiguous"):
            return "unsupported", "未识别"
        name = {"rpgmaker_mv": "RPG Maker MV",
                "rpgmaker_mz": "RPG Maker MZ"}.get(engine["id"], "Ren'Py")
        version = engine.get("version")
        return "supported", name + (" " + version if version else "")

    def _render_library(self):
        if hasattr(self, "library_action_buttons"):
            self.library_action_buttons.clear()
        for widget in self.library_scroll.winfo_children():
            widget.destroy()
        if not self.state.get("games"):
            _, body = self._card(self.library_scroll, padding=ui_tokens.SPACING[4])
            ctk.CTkLabel(
                body, text="游戏库为空", text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                    anchor="w")
            ctk.CTkLabel(
                body, text="点击上方“添加游戏…”，选择一个包含 game/ 与引擎文件的根目录。",
                anchor="w", justify="left", wraplength=1, text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                    anchor="w", pady=(6, 0))
            self._install_focus()
            self._apply_wrap()
            return
        for entry in self.state["games"]:
            level, status = self._library_status(entry["path"])
            available = level == "supported"
            _, body = self._card(self.library_scroll, padding=ui_tokens.SPACING[2])
            body.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                body, text=entry["name"], anchor="w", text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["card_title"], "bold")).grid(
                    row=0, column=0, sticky="w")
            ctk.CTkLabel(
                body, text=status, text_color=_PAIR["ok"] if available else _PAIR["bad"],
                font=self._font(ui_tokens.FONT_ROLES["meta"])).grid(
                    row=0, column=1, sticky="e", padx=(8, 0))
            ctk.CTkLabel(
                body, text=entry["path"], anchor="w", justify="left",
                wraplength=1, text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["meta"])).grid(
                    row=1, column=0, columnspan=2, sticky="ew", pady=(4, 9))
            buttons = ctk.CTkFrame(body, fg_color="transparent")
            buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
            open_button = ctk.CTkButton(
                buttons, text="打开处理页", width=102, height=30,
                corner_radius=ui_tokens.RADIUS["button"],
                fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
                text_color=_PAIR["on_accent"], border_width=2,
                border_color=_PAIR["accent_fill"],
                font=self._font(ui_tokens.FONT_ROLES["meta"], "bold"),
                state="normal" if available else "disabled",
                command=lambda path=entry["path"]: self.set_game_dir(path))
            open_button.pack(side="left")
            rename_button = ctk.CTkButton(
                buttons, text="重命名", width=74, height=30,
                corner_radius=ui_tokens.RADIUS["button"],
                fg_color="transparent", border_width=1,
                border_color=_PAIR["border_strong"],
                hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["meta"]),
                command=lambda item=entry: self.rename_game(item))
            rename_button.pack(side="left", padx=(8, 0))
            remove_button = ctk.CTkButton(
                buttons, text="移出游戏库", width=88, height=30,
                corner_radius=ui_tokens.RADIUS["button"],
                fg_color="transparent", border_width=1,
                border_color=_PAIR["border_strong"],
                hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["meta"]),
                command=lambda path=entry["path"]: self.remove_game(path))
            remove_button.pack(side="right")
            open_button._rpykit_available = available
            rename_button._rpykit_available = True
            remove_button._rpykit_available = True
            self.library_action_buttons.extend(
                (open_button, rename_button, remove_button))
        self._install_focus()
        self._apply_wrap()
        # A newly created card has no measured width yet.  Run once after the
        # geometry manager has settled so a path never keeps wraplength=1.
        self.root.after(50, self._apply_wrap)

    def _build_toolbox(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        _, body = self._card(scroll, padding=ui_tokens.SPACING[4])
        ctk.CTkLabel(
            body, text="兼容性与安装诊断", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                anchor="w")
        ctk.CTkLabel(
            body, text="由兼容性预检生成，只读游戏结构，不执行游戏代码。",
            anchor="w", justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", pady=(5, 12))
        self.var_toolbox_info = tk.StringVar(value="尚未选择游戏。")
        ctk.CTkLabel(
            body, textvariable=self.var_toolbox_info, anchor="nw",
            justify="left", wraplength=1, text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(fill="x")
        self.var_toolbox_installed = tk.StringVar(value="")
        ctk.CTkLabel(
            body, textvariable=self.var_toolbox_installed, anchor="w",
            justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", pady=(10, 0))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(
            buttons, text="重新检查", height=32,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"], border_width=2,
            border_color=_PAIR["accent_fill"],
            font=self._font(ui_tokens.FONT_ROLES["meta"], "bold"),
            command=self.refresh_game).pack(side="left")
        ctk.CTkButton(
            buttons, text="打开游戏目录", height=32,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=self.open_game_folder).pack(side="left", padx=(8, 0))

    def _build_log(self, parent):
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        tools = ctk.CTkFrame(body, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 8))
        self.btn_clear_log = ctk.CTkButton(
            tools, text="清空", width=76, height=32,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=self.clear_log)
        self.btn_clear_log.pack(side="left")
        self.btn_export_log = ctk.CTkButton(
            tools, text="导出…", width=76, height=32,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=self.export_log)
        self.btn_export_log.pack(side="right", padx=(8, 0))
        self.btn_copy_log = ctk.CTkButton(
            tools, text="复制全部", width=88, height=32,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["meta"]),
            command=self.copy_log)
        self.btn_copy_log.pack(side="right")
        self.log_card = ctk.CTkFrame(
            body, corner_radius=ui_tokens.RADIUS["card"],
            fg_color=_PAIR["panel"], border_width=1,
            border_color=_PAIR["border"])
        self.log_card.pack(fill="both", expand=True)
        self.log = ctk.CTkTextbox(
            self.log_card, wrap="none",
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["panel"], text_color=_PAIR["fg"],
            font=ctk.CTkFont(family="Consolas",
                             size=ui_tokens.FONT_ROLES["mono"]),
            border_width=1, border_color=_PAIR["border"])
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        self.log.configure(state="disabled")
        self.log_empty = ctk.CTkLabel(
            self.log_card, text="暂无日志\n处理或模拟运行后，输出会显示在这里。",
            justify="center", text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["body"]))
        self.log_empty.place(relx=0.5, rely=0.45, anchor="center")
        self._update_log_actions()

    def _build_help(self, parent):
        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        _, intro = self._card(body, padding=ui_tokens.SPACING[4])
        ctk.CTkLabel(
            intro, text="离线帮助", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                anchor="w")
        ctk.CTkLabel(
            intro,
            text="这些说明随程序打包，不联网。功能能否使用以当前游戏的预检结果为准。",
            anchor="w", justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", pady=(5, 0))
        self.help_grid = ctk.CTkFrame(body, fg_color="transparent")
        self.help_grid.pack(fill="x")
        self.help_grid.grid_columnconfigure(0, weight=1)
        self.help_grid.grid_columnconfigure(1, weight=0)
        self.help_cards = {}
        self._help_columns = 1
        for index, (topic_id, topic) in enumerate(help_content.topics()):
            card = ctk.CTkFrame(
                self.help_grid, corner_radius=ui_tokens.RADIUS["card"],
                fg_color=_PAIR["panel"], border_width=1,
                border_color=_PAIR["border"])
            card.grid(row=index, column=0, sticky="nsew", pady=(0, 8))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=ui_tokens.SPACING[4],
                       pady=ui_tokens.SPACING[4])
            ctk.CTkLabel(
                inner, text=topic["title"], anchor="w", text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["card_title"], "bold")).pack(
                    anchor="w")
            ctk.CTkLabel(
                inner, text=topic["summary"], anchor="w", justify="left",
                wraplength=1, text_color=_PAIR["dim"],
                font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                    anchor="w", pady=(5, 10))
            for section in topic["sections"]:
                ctk.CTkLabel(
                    inner, text=section["heading"], anchor="w",
                    text_color=_PAIR["fg"],
                    font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold")).pack(
                        anchor="w", pady=(4, 2))
                for line in section["body"]:
                    ctk.CTkLabel(
                        inner, text="• " + line, anchor="w", justify="left",
                        wraplength=1, text_color=_PAIR["dim"],
                        font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                            anchor="w", pady=1)
            self.help_cards[topic_id] = card
        self._install_focus()
        self.root.after(50, self._apply_wrap)

    def show_help(self, topic_id):
        topic = help_content.topic_for(topic_id)
        if not topic:
            return
        existing = getattr(self, "_help_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.destroy()
        except tk.TclError:
            pass
        window = ctk.CTkToplevel(self.root)
        self._help_window = window
        window.title("说明 · " + topic["title"])
        window.geometry("660x560")
        window.transient(self.root)
        window.resizable(True, True)
        frame = ctk.CTkFrame(window, fg_color=_PAIR["bg"])
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        scroll = ctk.CTkScrollableFrame(frame, fg_color=_PAIR["bg"])
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(
            scroll, text=topic["title"], anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                anchor="w", padx=6, pady=(4, 6))
        ctk.CTkLabel(
            scroll, text=topic["summary"], anchor="w", justify="left",
            wraplength=560, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", padx=6, pady=(0, 10))
        for section in topic["sections"]:
            ctk.CTkLabel(
                scroll, text=section["heading"], anchor="w",
                text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["card_title"], "bold")).pack(
                    anchor="w", padx=6, pady=(6, 2))
            for line in section["body"]:
                ctk.CTkLabel(
                    scroll, text="• " + line, anchor="w", justify="left",
                    wraplength=560, text_color=_PAIR["dim"],
                    font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                        anchor="w", padx=6, pady=1)
        close = ctk.CTkButton(
            frame, text="关闭", height=34, width=84,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"),
            command=window.destroy)
        close.pack(anchor="e", pady=(10, 0))
        ui_focus.install(close, _PAIR["focus"], _PAIR["border"])
        window.bind("<Escape>", lambda _event: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.grab_set()
        window.after(80, lambda: ui_focus.focus_target(close).focus_set())

    def _build_settings(self, parent):
        body = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True)
        _, card = self._card(body, padding=ui_tokens.SPACING[4])
        ctk.CTkLabel(
            card, text="外观", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                anchor="w")
        ctk.CTkLabel(
            card, text="跟随系统深浅色，也可以手动指定。两种主题使用同一套对比度标准。",
            anchor="w", justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", pady=(5, 12))
        self.theme_modes = {"跟随系统": "system", "浅色": "light", "深色": "dark"}
        self.theme_focus = ctk.CTkFrame(
            card, fg_color="transparent", border_width=1,
            border_color=_PAIR["border_strong"],
            corner_radius=ui_tokens.RADIUS["button"])
        self.theme_focus.pack(fill="x")
        self.theme_segment = ctk.CTkSegmentedButton(
            self.theme_focus, values=list(self.theme_modes),
            command=self._mode_from_label,
            height=36, corner_radius=ui_tokens.RADIUS["button"],
            border_width=1,
            selected_color=_PAIR["accent_soft"],
            selected_hover_color=_PAIR["accent_soft"],
            unselected_color=_PAIR["panel_alt"],
            unselected_hover_color=_PAIR["accent_soft"],
            text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"]))
        self.theme_segment.pack(fill="x", padx=2, pady=2)
        segment_target = ui_focus.focus_target(self.theme_segment)
        if segment_target is not None:
            segment_target.bind(
                "<FocusIn>",
                lambda _event: self.theme_focus.configure(
                    border_width=2, border_color=_PAIR["focus"]), add="+")
            segment_target.bind(
                "<FocusOut>",
                lambda _event: self.theme_focus.configure(
                    border_width=1, border_color=_PAIR["border_strong"]), add="+")
        _, size_card = self._card(body, padding=ui_tokens.SPACING[4])
        ctk.CTkLabel(
            size_card, text="窗口大小", anchor="w", text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(
                anchor="w")
        size = self.state.get("window") or app_state.DEFAULT_WINDOW
        self.var_window = tk.StringVar(value="%d × %d（自动记住）" % (
            size.get("width", 1180), size.get("height", 780)))
        ctk.CTkLabel(
            size_card, textvariable=self.var_window, anchor="w",
            text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(
                anchor="w", pady=(6, 0))
        _, about = self._card(body, padding=ui_tokens.SPACING[4])
        ctk.CTkLabel(
            about, text="SLG Ren'Py Toolkit · v" + branding.APP_VERSION +
            "（界面测试版）\n提供可撤销补丁与隔离副本模拟运行。",
            anchor="w", justify="left", wraplength=1, text_color=_PAIR["dim"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(anchor="w")

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
            if selected:
                button.configure(
                    fg_color=_PAIR["accent_soft"],
                    text_color=_PAIR["accent_text"],
                    font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"))
            else:
                button.configure(
                    fg_color="transparent", text_color=_PAIR["dim"],
                    font=self._font(ui_tokens.FONT_ROLES["secondary"]))
        if page_id == "library":
            self._render_library()
        elif page_id == "settings":
            self.theme_segment.set({"system": "跟随系统", "light": "浅色",
                                    "dark": "深色"}[self._theme_mode])
        self.root.after(50, self._apply_wrap)

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
        self.root.after_idle(self._apply_wrap)

    def _toggle_theme(self):
        modes = ("system", "light", "dark")
        self._apply_theme(modes[(modes.index(self._theme_mode) + 1) % len(modes)])

    def _mode_from_label(self, label):
        self._apply_theme(self.theme_modes.get(label, "system"))

    def _bind_shortcuts(self):
        """Keyboard paths for the actions a mouse user would click."""
        self.root.bind("<Control-o>", lambda _event: self.pick())
        self.root.bind("<F5>", lambda _event: self.refresh_game())
        self.root.bind("<Control-l>", lambda _event: self._show_page("log"))
        self.root.bind("<Control-Return>", lambda _event: self.simulate_run())
        self.root.bind("<Escape>", lambda _event: self.root.focus_set())

    def _install_focus(self):
        """Give every visible control a Tab stop and a focus ring."""
        if not hasattr(self, "root"):
            return
        for widget in _walk(self.root):
            if not isinstance(widget, (
                    ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkEntry,
                    ctk.CTkSegmentedButton, ctk.CTkTextbox, ctk.CTkRadioButton)):
                continue
            if getattr(widget, "_rpykit_focus_target", None) is not None:
                continue
            parent = getattr(widget, "master", None)
            nested_in_segment = False
            while parent is not None:
                if isinstance(parent, ctk.CTkSegmentedButton):
                    nested_in_segment = True
                    break
                parent = getattr(parent, "master", None)
            if nested_in_segment:
                continue
            ui_focus.install(widget, _PAIR["focus"], _PAIR["border"])

    def _layout_help_cards(self, width):
        if not hasattr(self, "help_grid"):
            return
        columns = 2 if width >= ui_tokens.LAYOUT["feature_two_column_min"] else 1
        if columns == getattr(self, "_help_columns", 1):
            return
        self._help_columns = columns
        for index, card in enumerate(self.help_cards.values()):
            padx = ((0, 6) if index % 2 == 0 else (6, 0)) if columns == 2 else (0, 0)
            card.grid_configure(row=index // columns, column=index % columns,
                                sticky="nsew", padx=padx, pady=(0, 8))
        for column in (0, 1):
            self.help_grid.grid_columnconfigure(
                column, weight=1 if columns == 2 or column == 0 else 0,
                uniform="help" if columns == 2 else "")
        self.root.after_idle(self._apply_wrap)

    def _layout_feature_cards(self, width):
        """Switch the feature list between one and two columns.

        Re-gridding only when the column count changes avoids a layout storm
        during window resizes and keeps the cards from jumping between rows on
        every pixel.
        """
        if not hasattr(self, "feature_grid"):
            return
        columns = 2 if width >= ui_tokens.LAYOUT["feature_two_column_min"] else 1
        if columns == getattr(self, "_feature_columns", 1):
            return
        self._feature_columns = columns
        for index, card in enumerate(self.feature_cards):
            if columns == 2:
                padx = (0, 6) if index % 2 == 0 else (6, 0)
            else:
                padx = (0, 0)
            card.grid_configure(row=index // columns, column=index % columns,
                                sticky="nsew", padx=padx, pady=(0, 8))
        for column in (0, 1):
            self.feature_grid.grid_columnconfigure(
                column, weight=1 if columns == 2 or column == 0 else 0,
                uniform="feature" if columns == 2 else "")
        self.root.after_idle(self._apply_wrap)

    def _apply_responsive(self):
        """Use the available width without turning text into a wall."""
        if not hasattr(self, "content"):
            return
        try:
            width = self.content.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        max_width = ui_tokens.LAYOUT["max_content_width"]
        pad = ui_tokens.LAYOUT["page_padding"]
        if width > max_width + pad * 2:
            pad = (width - max_width) // 2
        for widget in (self.header, self.page_host, self.bar):
            try:
                widget.grid_configure(padx=(pad, pad))
            except tk.TclError:
                pass
        usable = max(1, width - pad * 2)
        self._layout_feature_cards(usable)
        self._layout_help_cards(usable)

    def _apply_wrap(self):
        # CTk reports physical widget widths but takes logical wrap lengths.
        # Let every label determine its own height from the width it actually
        # has; fixed 700/740/760-pixel wraps used to clip MV/MZ paths and long
        # support reasons on narrow windows.
        if not hasattr(self, "pages"):
            return
        self._apply_responsive()
        pending = list(self.pages.values())
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            if not isinstance(widget, ctk.CTkLabel):
                continue
            try:
                if not widget.cget("wraplength"):
                    continue
            except tk.TclError:
                continue
            parent = widget.master
            width = parent.winfo_width()
            if width <= 1:
                continue
            scaling = parent._get_widget_scaling() if hasattr(parent, "_get_widget_scaling") else 1
            wrap = max(180, int(width / scaling) - 32)
            if widget.cget("wraplength") != wrap:
                widget.configure(wraplength=wrap)

    def _pack_sim_confirm(self, cleanup=False):
        if not hasattr(self, "sim_confirm_frame"):
            return
        for button in (self.btn_sim_success, self.btn_sim_failure,
                       self.btn_sim_gameplay, self.btn_sim_finish,
                       self.btn_sim_cleanup):
            button.pack_forget()
        if cleanup:
            self.btn_sim_cleanup.pack(side="left")
        else:
            self.btn_sim_success.pack(side="left")
            self.btn_sim_failure.pack(side="left", padx=(7, 0))
            self.btn_sim_gameplay.pack(side="left", padx=(7, 0))
            self.btn_sim_finish.pack(side="left", padx=(7, 0))
            self.btn_sim_cleanup.pack_forget()
        self.sim_confirm_frame.pack(anchor="w", pady=(2, 0))

    def _reset_simulation_status(self):
        self.sim_stage_state = {}
        self.sim_gameplay_confirmed = False
        if hasattr(self, "btn_sim_gameplay"):
            self.btn_sim_gameplay.configure(state="disabled")
        for key, text in self._SIM_STAGE_DEFAULTS.items():
            self._set_sim_stage(key, "pending", text)
        self._set_sim_result("info", "尚未运行模拟安装。将在隔离副本中测试，不会修改原游戏。")
        self.sim_confirm_frame.pack_forget()
        if hasattr(self, "btn_sim_cleanup"):
            self.btn_sim_cleanup.pack_forget()

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
        details = _describe_details(survey)
        reasons = ui_text.localize_reasons(survey.get("reasons") or [])
        if reasons:
            details.append("兼容提示：\n" + "\n".join("\u2022 " + x for x in reasons))
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
            self.scan_failed = False
            self._survey = self._installed = None
            self._set_compat(None)
            self._apply_feature_support(None)
            self._paint_chips(None)
            self.var_toolbox_info.set("尚未选择游戏。")
            self.var_toolbox_installed.set("")
            return self._set_state("info", "先选择一个游戏目录。")
        if engine_adapters.detect(path)["id"] in ("unknown", "ambiguous"):
            self.scan_busy = False
            self.scan_failed = False
            self._survey = self._installed = None
            self._set_compat(None)
            self._apply_feature_support(None)
            self._paint_chips(None)
            self.var_toolbox_info.set("目录中未找到支持的游戏引擎。")
            self.var_toolbox_installed.set("")
            return self._set_state("bad", "请选择 Ren’Py 或 RPG Maker MV/MZ 游戏根目录。")
        self.scan_busy = True
        self.scan_failed = False
        self.var_global_status.set("正在检查游戏…")
        self._set_state("warn", "正在检查游戏引擎、功能支持和已安装补丁…")
        self._set_buttons()
        threading.Thread(target=self._scan_worker, args=(path, generation), daemon=True).start()
        return "warn", "正在检查游戏。"

    def _scan_worker(self, path, generation):
        try:
            survey = engine_adapters.survey(path, quick=True)
            installed = engine_adapters.installed_state(path)
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
            self.scan_failed = True
            self._survey = self._installed = None
            self.var_global_status.set("检查失败")
            self._set_compat(None)
            self._paint_chips(None)
            for row in self.rows.values():
                row.supported = False
                row.support_level = "unknown"
                self.var_on[row.id].set(False)
                row.reason_var.set("游戏检查失败：无法确认此功能是否可用。")
                row.reason_label.configure(text_color=_PAIR["bad"])
                row.reason_label.pack(fill="x", padx=14, pady=(6, 11))
            self.var_toolbox_info.set("检查失败：" + error)
            self._set_state("bad", "无法读取游戏兼容状态；请查看日志或重新检查。")
            self._log("\n[游戏检查失败] " + error + "\n")
            self._set_buttons()
            return
        installed = installed or {}
        self.scan_failed = False
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

    def _handle_event(self, item):
        if not isinstance(item, tuple):
            self._log(item)
            return
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

    def _drain(self):
        try:
            while True:
                item = self.queue.get_nowait()
                try:
                    self._handle_event(item)
                except Exception as exc:  # noqa: BLE001 - never freeze the queue
                    self._log("\n[界面事件处理失败] %s: %s\n"
                              % (type(exc).__name__, exc))
                    self.var_global_status.set("界面状态异常，详情见日志")
                    if not self.sim_preparing:
                        self.busy = False
                    self._set_buttons()
        except queue.Empty:
            pass
        try:
            self.root.after(80, self._drain)
        except tk.TclError:
            pass

    def _set_buttons(self):
        valid = False
        if self.game_dir and not self.scan_failed:
            try:
                valid = engine_adapters.detect(self.game_dir)["id"] not in (
                    "unknown", "ambiguous")
            except Exception:  # noqa: BLE001 - a bad path must not break callbacks
                valid = False
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
        for button in getattr(self, "library_action_buttons", ()):
            enabled = not locked and getattr(button, "_rpykit_available", True)
            button.configure(state="normal" if enabled else "disabled")
        confirm_ready = bool(self.sim_session and self.sim_launched and not self.busy)
        self.btn_sim_success.configure(state="normal" if confirm_ready else "disabled")
        self.btn_sim_failure.configure(state="normal" if confirm_ready else "disabled")
        self.btn_sim_gameplay.configure(
            state="normal" if (confirm_ready and self.sim_confirmed
                               and not self.sim_gameplay_confirmed) else "disabled")
        self.btn_sim_finish.configure(
            state="normal" if (self.sim_session and not self.busy) else "disabled")
        self.btn_sim_cleanup.configure(
            state="normal" if (self.sim_session and not self.busy) else "disabled")
        if self.busy:
            self.var_global_status.set("正在处理…")
            self.bar.grid()
            self.bar.start()
        else:
            self.bar.stop()
            self.bar.grid_remove()
        self._update_action_hint()

    def _show_log(self):
        self._show_page("log")
        try:
            self.log.see("end")
        except tk.TclError:
            pass

    def pick(self):
        chosen = filedialog.askdirectory(title="选择游戏根目录")
        if chosen:
            self.set_game_dir(chosen)

    def set_game_dir(self, game_dir, remember=True):
        target = os.path.abspath(os.fspath(game_dir)) if game_dir else None
        if (self.busy or self.sim_preparing or self.sim_session is not None) and \
                target and self.game_dir and \
                os.path.normcase(target) != os.path.normcase(self.game_dir):
            messagebox.showinfo(TITLE, "当前操作尚未结束，暂时不能切换游戏。")
            return
        self.game_dir = target
        self.var_dir.set(self.game_dir or "")
        if self.game_dir and remember and engine_adapters.detect(self.game_dir)["id"] not in ("unknown", "ambiguous"):
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
        chosen = filedialog.askdirectory(title="添加游戏根目录")
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
        text = self._log_text()
        if not text.strip():
            self.var_global_status.set("日志为空")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.var_global_status.set("日志已复制")

    def export_log(self):
        if not self._log_text().strip():
            self.var_global_status.set("日志为空，没有可导出的内容")
            return
        path = filedialog.asksaveasfilename(
            title="导出运行日志", defaultextension=".txt",
            filetypes=(("文本文件", "*.txt"), ("所有文件", "*.*")))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(self._log_text())
            self.var_global_status.set("日志已导出")
        except OSError as exc:
            messagebox.showerror(TITLE, "导出失败：%s" % exc)

    def clear_log(self):
        if not self._log_text().strip():
            self.var_global_status.set("日志已经为空")
            return
        if not messagebox.askyesno(
                TITLE, "清空运行日志？\n\n清空后无法从界面恢复；"
                       "需要保留时请先“导出…”。"):
            return
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._update_log_actions()
        self.var_global_status.set("日志已清空")

    def _schedule_geometry_save(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        self._apply_responsive()
        if self._geometry_job is not None:
            try:
                self.root.after_cancel(self._geometry_job)
            except tk.TclError:
                pass
        self._geometry_job = self.root.after(700, self._save_geometry)

    def _window_scaling(self):
        try:
            return max(1.0, float(self.root._get_window_scaling()))
        except Exception:  # noqa: BLE001 - cosmetic value only
            return 1.0

    def _screen_bounds(self):
        """(min_w, min_h, max_w, max_h) in logical pixels for this screen."""
        try:
            scale = self._window_scaling()
            screen_w = int(self.root.winfo_screenwidth() / scale)
            screen_h = int(self.root.winfo_screenheight() / scale)
            max_w = max(760, screen_w - 80)
            max_h = max(520, screen_h - 100)
            return min(900, max_w), min(620, max_h), max_w, max_h
        except Exception:  # noqa: BLE001 - geometry is cosmetic
            return 900, 620, 2400, 1800

    def _clamp_window_size(self, width, height):
        """Keep a remembered window inside the current screen."""
        min_w, min_h, max_w, max_h = self._screen_bounds()
        return (max(min_w, min(width, max_w)),
                max(min_h, min(height, max_h)))

    def _save_geometry(self):
        self._geometry_job = None
        try:
            # CTk geometry is expressed in logical pixels but winfo_* reports
            # physical pixels.  Saving the physical value made the window grow
            # by the DPI factor on every restart.
            scale = self._window_scaling()
            width = int(round(self.root.winfo_width() / scale))
            height = int(round(self.root.winfo_height() / scale))
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
        # Cancel the drain/wrap timers too.  A destroyed Tk interpreter that
        # still has queued after-scripts leaves noisy "invalid command name"
        # errors and can interfere with the next Tk root in the same process.
        try:
            for timer in self.root.tk.call("after", "info"):
                self.root.tk.call("after", "cancel", timer)
        except tk.TclError:
            pass
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
        frame.pack(fill="both", expand=True, padx=20, pady=18)
        ctk.CTkLabel(
            frame, text="找到多个启动程序，请选择要测试的版本：",
            anchor="w", justify="left", wraplength=420,
            text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["body"], "bold")).pack(
                anchor="w", pady=(0, 10))
        selected = tk.StringVar(value=launchers[0])
        radios = []
        for launcher in launchers:
            name = os.path.basename(str(launcher))
            radio = ctk.CTkRadioButton(
                frame, text=name, value=launcher, variable=selected,
                text_color=_PAIR["fg"],
                font=self._font(ui_tokens.FONT_ROLES["secondary"]))
            radio.pack(anchor="w", pady=3)
            radios.append(radio)
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", pady=(14, 0))
        def choose():
            result["value"] = selected.get()
            window.destroy()
        launch_button = ctk.CTkButton(
            buttons, text="启动所选项", command=choose, height=34,
            corner_radius=ui_tokens.RADIUS["button"],
            fg_color=_PAIR["accent_fill"], hover_color=_PAIR["accent_hover"],
            text_color=_PAIR["on_accent"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"], "bold"))
        launch_button.pack(side="right")
        cancel_button = ctk.CTkButton(
            buttons, text="取消", command=window.destroy, height=34,
            corner_radius=ui_tokens.RADIUS["button"], fg_color="transparent",
            border_width=1, border_color=_PAIR["border_strong"],
            hover_color=_PAIR["accent_soft"], text_color=_PAIR["fg"],
            font=self._font(ui_tokens.FONT_ROLES["secondary"]))
        cancel_button.pack(side="right", padx=(0, 8))
        for widget in radios + [launch_button, cancel_button]:
            ui_focus.install(widget, _PAIR["focus"], _PAIR["border"])
        window.bind("<Escape>", lambda _event: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.grab_set()
        if radios:
            window.after(50, lambda: ui_focus.focus_target(radios[0]).focus_set())
        self.root.wait_window(window)
        return result["value"]


def main(initial_dir=None):
    try:
        import win_platform
        win_platform.prepare_windows_process()
    except Exception:  # noqa: BLE001 - a platform detail must not block the UI
        pass
    state = app_state.load_state()
    ctk.set_default_color_theme("blue")
    ctk.set_appearance_mode(state.get("appearance", "system"))
    root = ctk.CTk()
    app = App(root, state=state)
    if initial_dir:
        app.set_game_dir(initial_dir)
    root.mainloop()
    return 0
