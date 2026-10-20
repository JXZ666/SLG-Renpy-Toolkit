"""Desktop controls for explicit, session-scoped live translation."""
import os
import threading
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import branding
import ui_tokens


class TranslationUIMixin:
    def _init_translation(self):
        from translation_config import load_settings
        self._translation_config_path = os.path.join(os.path.dirname(self.state_path), "translation", "settings.json")
        self._translation_settings = load_settings(path=self._translation_config_path)
        self._translation_host = None
        self._translation_process = None
        self._translation_id = None
        self._translation_game = None
        self._translation_preparing = False
        self._translation_conflict = False
        self._sim_translation_settings = None
        self._sim_translation_requested = False

    def _build_translation_settings(self, parent, palette):
        _, body = self._card(parent, padding=ui_tokens.SPACING[4])
        ctk.CTkLabel(body, text="实时汉化（试验）", anchor="w", text_color=palette["fg"],
                     font=self._font(ui_tokens.FONT_ROLES["section"], "bold")).pack(anchor="w")
        ctk.CTkLabel(body, text="默认免费机翻；只翻译当前对白与支持的剧情选项。免费服务失败会保留原文，不会自动调用 AI。",
                     wraplength=1, justify="left", text_color=palette["dim"],
                     font=self._font()).pack(anchor="w", pady=(6, 10))
        settings = self._translation_settings
        self.translation_vars = {}
        fields = (("provider", "翻译来源", "免费机翻" if settings.get("provider") == "google" else "自填 AI"),
                  ("source_lang", "原文语言（auto 自动识别）", settings.get("source_lang", "auto")),
                  ("target_lang", "目标语言", settings.get("target_lang", "zh-CN")),
                  ("wait_seconds", "最长等待秒数（默认 2，0 暂停，最多 30）", str(settings.get("wait_seconds", 2))),
                  ("ai_endpoint", "AI 接口地址（兼容 Chat Completions）", settings.get("ai_endpoint", "")),
                  ("ai_model", "AI 模型", settings.get("ai_model", "")),
                  ("api_key", "AI Key（只在本机运行时使用）", settings.get("api_key", "")))
        self.translation_inputs = []
        for key, title, value in fields:
            ctk.CTkLabel(body, text=title, anchor="w", text_color=palette["dim"],
                         font=self._font(ui_tokens.FONT_ROLES["secondary"])).pack(anchor="w", pady=(6, 3))
            var = tk.StringVar(value=value)
            self.translation_vars[key] = var
            if key == "provider":
                widget = ctk.CTkSegmentedButton(body, values=["免费机翻", "自填 AI"], variable=var,
                                               selected_color=palette["accent_soft"],
                                               selected_hover_color=palette["accent_soft"],
                                               unselected_color=palette["panel_alt"],
                                               unselected_hover_color=palette["accent_soft"],
                                               text_color=palette["fg"], height=36, font=self._font())
            else:
                widget = ctk.CTkEntry(body, textvariable=var, height=36,
                                     show="*" if key == "api_key" else "",
                                     fg_color=palette["input"], text_color=palette["fg"],
                                     border_color=palette["border_strong"], font=self._font())
            widget.pack(fill="x")
            self.translation_inputs.append(widget)
        self.var_remember_translation_key = tk.BooleanVar(value=bool(settings.get("api_key")))
        ctk.CTkCheckBox(body, text="记住 AI Key（Windows 加密保存）", variable=self.var_remember_translation_key,
                        text_color=palette["fg"], font=self._font()).pack(anchor="w", pady=12)
        ctk.CTkLabel(body, text="当前文本会发送给所选服务。超时保留原文，迟到译文供下次使用；不会预先翻译整部游戏。",
                     wraplength=1, justify="left", text_color=palette["dim"], font=self._font()).pack(anchor="w")
        ctk.CTkButton(body, text="保存翻译设置", height=36,
                      fg_color=palette["accent_fill"], text_color=palette["on_accent"],
                      command=self.save_translation_settings).pack(anchor="w", pady=(12, 0))

    def _read_translation_settings(self):
        from translation_config import default_settings
        result = default_settings()
        for key, var in self.translation_vars.items():
            result[key] = var.get().strip()
        result["provider"] = "google" if result["provider"] == "免费机翻" else "ai"
        try:
            result["wait_seconds"] = float(result["wait_seconds"])
        except ValueError as exc:
            raise ValueError("最长等待时间必须是 0 到 30 的数字。") from exc
        if not 0 <= result["wait_seconds"] <= 30:
            raise ValueError("最长等待时间必须在 0 到 30 秒之间。")
        if result["provider"] == "ai":
            from translation_service import AIProvider
            AIProvider(result)
        return result

    def save_translation_settings(self):
        from translation_config import save_settings
        try:
            settings = self._read_translation_settings()
            save_settings(settings, remember_key=self.var_remember_translation_key.get(),
                          path=self._translation_config_path)
            self._translation_settings = settings
        except Exception:
            messagebox.showerror(branding.APP_NAME, "翻译设置未保存。请检查语言、接口、模型及等待时间；密钥不会写入日志。")
            return
        self.var_global_status.set("翻译设置已保存，下次会话生效")

    def _library_launcher(self, entry, replace=False):
        import app_state
        import game_launch
        root = entry["path"]
        rel = entry.get("launcher_rel")
        if rel and not replace:
            try:
                game_launch.resolve_launcher(root, rel)
                return rel
            except (ValueError, OSError):
                pass
        chosen = filedialog.askopenfilename(parent=self.root, title="选择这个游戏的启动 exe",
                                            initialdir=root, filetypes=[("游戏程序", "*.exe")])
        if not chosen:
            return None
        try:
            rel = game_launch.validate_launcher(root, chosen)
            self.state = app_state.set_launcher(self.state, root, rel)
            self._persist_state()
            self._render_library()
            return rel
        except (ValueError, OSError) as exc:
            messagebox.showerror(branding.APP_NAME, str(exc))
            return None

    def launch_library_game(self, entry):
        import game_launch
        rel = self._library_launcher(entry)
        if not rel:
            return
        try:
            game_launch.launch(entry["path"], rel)
        except (OSError, ValueError) as exc:
            messagebox.showerror(branding.APP_NAME, "无法启动：%s" % exc)
            return
        self.var_global_status.set("已发送游戏启动请求")

    def change_library_launcher(self, entry):
        self._library_launcher(entry, replace=True)

    def open_library_folder(self, entry):
        import game_launch
        try:
            game_launch.open_folder(entry["path"])
        except (ValueError, OSError) as exc:
            messagebox.showerror(branding.APP_NAME, "无法打开游戏文件夹：%s" % exc)

    def _new_translation_host(self, settings, game, operation_id):
        from translation_service import TranslationHost
        import proj
        cache = os.path.join(os.path.dirname(self._translation_config_path), "cache.sqlite3")
        return TranslationHost(settings, proj.game_identity(game), cache_path=cache,
                               event_callback=lambda event: self.queue.put(
                                   ("__translation_log__", operation_id, game, event))).start()

    def start_translation(self, entry):
        import cmd_fontfix
        import renpy_translation
        if self.busy or self.sim_session is not None or self._translation_host is not None:
            return
        game = entry["path"]
        try:
            support = renpy_translation.survey(game)
            if not support.get("supported"):
                self._log("实时汉化预检：" + "; ".join(support.get("reasons", [])) + "\n")
                self._show_log()
                messagebox.showinfo(branding.APP_NAME, "此游戏尚未通过内置汉化预检，详细范围见运行日志。")
                return
            settings = self._read_translation_settings()
            if settings["provider"] == "ai" and not all(settings.get(k) for k in ("ai_endpoint", "ai_model")):
                raise ValueError("请先填写 AI 接口地址和模型。")
            rel = self._library_launcher(entry)
            if not rel:
                return
            installed = cmd_fontfix.installed_state(game)
            needs_install = not (installed.get("translation_current") and installed.get("ours") and installed.get("current"))
            if needs_install and not messagebox.askyesno(
                    branding.APP_NAME, "实时汉化需要安装可撤销的字体与连接补丁。\n\n建议先在副本试用。现在安装到这个游戏并启动汉化？"):
                return
        except Exception as exc:
            messagebox.showerror(branding.APP_NAME, "无法准备汉化：%s" % exc)
            return
        self.set_game_dir(game, remember=False)
        self._translation_id = uuid.uuid4().hex
        self._translation_game = game
        self._translation_preparing = True
        self._translation_conflict = False
        self.busy = True
        self._show_log()
        self._log("\n===== 实时汉化：准备连接 =====\n")
        self._set_buttons()
        operation_id = self._translation_id
        def worker():
            host = None
            try:
                import engine_adapters
                import game_launch
                from appgui import _namespace
                if needs_install:
                    args = _namespace(game, feature_ids=["fontfix", "translation"])
                    import contextlib
                    from appgui import _Sink
                    sink = _Sink(self.queue)
                    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                        code = engine_adapters.run(args)
                    if code:
                        raise RuntimeError("连接补丁安装失败，请在处理页检查冲突。")
                if self.close_after_work:
                    raise RuntimeError("已取消汉化启动。")
                host = self._new_translation_host(settings, game, operation_id)
                process = game_launch.launch(game, rel, env=host.environment())
                self.queue.put(("__translation_started__", operation_id, game, host, process))
            except Exception:
                if host:
                    host.stop()
                self.queue.put(("__translation_failed__", operation_id, game))
        threading.Thread(target=worker, daemon=True).start()

    def start_translation_copy(self):
        if self._translation_host is not None:
            return
        for fid in ("fontfix", "translation"):
            if fid in self.var_on:
                self.var_on[fid].set(True)
        self.simulate_run()

    def _handle_translation_event(self, item):
        event, operation_id, game = item[:3]
        if operation_id != self._translation_id or game != self._translation_game:
            if event == "__translation_started__":
                item[3].stop()
            return
        if event == "__translation_started__":
            self.busy = self._translation_preparing = False
            self._translation_host, self._translation_process = item[3:5]
            if self.game_dir == game:
                self._refresh_state()
            if self._translation_conflict:
                self.stop_translation()
                self.var_global_status.set("外部 Luna 冲突，内置汉化已停止")
                if self.close_after_work:
                    self._destroy_root()
                return
            self.var_global_status.set("实时汉化运行中")
            self._log("汉化会话已启动；超时会显示原文，停止后游戏可继续运行。\n")
            self._set_buttons()
            if self.close_after_work:
                self._destroy_root()
            else:
                self.root.after(500, self._poll_translation)
        elif event == "__translation_failed__":
            self.busy = self._translation_preparing = False
            self._translation_id = None
            if self.game_dir == game:
                self._refresh_state()
            self._log("汉化启动失败：请检查连接补丁、启动程序或翻译设置。密钥不会写入日志。\n")
            self.var_global_status.set("汉化启动失败，详见日志")
            self._set_buttons()
            if self.close_after_work:
                self._destroy_root()
        elif event == "__translation_log__":
            data = item[3]
            # Never render arbitrary backend strings: provider errors can echo
            # text, request URLs, authorization headers or private credentials.
            status = data.get("status", data.get("event", "update")) if isinstance(data, dict) else "update"
            if status == "luna_conflict":
                self._log("检测到外部 Luna 内嵌，内置汉化已停止，避免重复修改文本。\n")
                # A fast launcher can report before its started event reaches
                # Tk. Keep the operation identity until that event releases
                # the preparing state and hands over the host for shutdown.
                if getattr(self, "_translation_preparing", False):
                    self._translation_conflict = True
                    return
                self.stop_translation()
                self.var_global_status.set("外部 Luna 冲突，内置汉化已停止")
                return
            words = {"ok": "译文就绪", "translated": "译文就绪", "success": "译文就绪",
                     "cache": "使用缓存", "cached": "使用缓存",
                     "timeout": "等待超时，保留原文", "error": "服务失败，保留原文",
                     "provider_error": "翻译服务不可用，保留原文", "network_error": "连接失败，保留原文",
                     "rate_limited": "翻译服务请求限流，保留原文",
                     "http_error": "翻译接口返回错误，请检查地址或授权；保留原文",
                     "unsafe": "译文格式校验未通过，保留原文", "busy": "翻译队列繁忙，保留原文",
                     "invalid_response": "翻译结果无效，保留原文",
                     "stopped": "会话已停止", "started": "本机连接已就绪"}
            self._log("[实时汉化] " + words.get(status, "未取得有效译文，保留原文") + "\n")

    def _poll_translation(self):
        process = self._translation_process
        if self._translation_host is None or process is None:
            return
        if process.poll() is not None:
            self.stop_translation()
            self._log("游戏启动进程已退出，汉化连接已关闭。\n")
        else:
            self.root.after(500, self._poll_translation)

    def stop_translation(self):
        host = getattr(self, "_translation_host", None)
        self._translation_host = self._translation_process = None
        self._translation_id = None
        if host is not None:
            host.stop()
            self._log("实时汉化已停止；正在运行的游戏保留并回退原文。\n")
            self.var_global_status.set("实时汉化已停止，游戏可继续运行")
        self._set_buttons()

    def _translation_buttons(self):
        if hasattr(self, "btn_translation_stop"):
            self.btn_translation_stop.configure(state="normal" if self._translation_host is not None else "disabled")
        if hasattr(self, "btn_translation_copy"):
            enabled = bool(self.game_dir and not self.busy and self.sim_session is None and self._translation_host is None)
            self.btn_translation_copy.configure(state="normal" if enabled else "disabled")
