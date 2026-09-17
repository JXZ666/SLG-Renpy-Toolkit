"""The window rpykit-luna.exe opens when it is double-clicked.

Nothing here makes decisions. It collects a game directory, hands it to
cmd_fontfix, and shows what that prints - so the console entry point and the
window are guaranteed to behave identically, because they run the same code.

Colour lives in exactly one place, _repaint(). sv-ttk repaints every ttk widget
on a theme change, but tk's classic widgets - the Tk root and the log's Text -
are not ttk and keep their old colours until something tells them otherwise, so
they are repainted by hand from the same palette.
"""

import argparse
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import sv_ttk
except ImportError:  # the window still works, it just looks like 1995
    sv_ttk = None

import cmd_fontfix

TITLE = "rpykit-luna  露娜汉化预飞"

HINT = ("把游戏文件夹整个丢到本程序的图标上，效果和这里点「安装字体」一样。\n"
        "选好目录 →「干跑预览」看决策 →「安装字体」→ 开游戏用露娜，中文不再显示成方块。")

# Windows 11's semantic colours, dark on the left, light on the right. The
# light variants are the darker, higher-contrast pair, because the same hue
# that reads on #1c1c1c is invisible on #fafafa.
_STATUS = {
    "ok": ("#6ccb5f", "#0f7b0f"),
    "warn": ("#fce100", "#8a5300"),
    "bad": ("#ff99a4", "#c42b1c"),
}
_GLYPH = {"ok": "\u221a", "warn": "!", "bad": "\u00d7", "info": "\u00b7"}

# Used only if sv-ttk is missing or the style has not been applied yet.
_FALLBACK = {
    "dark": {"bg": "#1c1c1c", "fg": "#fafafa",
             "selbg": "#2f60d8", "selfg": "#ffffff"},
    "light": {"bg": "#fafafa", "fg": "#1c1c1c",
              "selbg": "#2f60d8", "selfg": "#ffffff"},
}


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


def _namespace(game_dir, revert=False, dry_run=False, force=False):
    """The argument set cmd_fontfix.run() expects.

    Mode is pinned to luna: `full` also forces config.language, and installing
    that on a game that is meant to be translated at runtime would make the
    game render one Chinese layer and the translator produce a second.
    """
    return argparse.Namespace(
        game_dir=game_dir, work=None, mode="luna",
        lang="chinesesimplified", revert=revert, force=force, dry_run=dry_run)


def _mix(a, b, t):
    """Blend two #rrggbb colours; t=0 gives a, t=1 gives b."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * t) for x, y in zip(pa, pb))


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


def _palette(root):
    """The live colours, asked of the theme rather than guessed.

    Derived rather than listed: `dim` and `panel` are mixed from the theme's own
    background and foreground, so they stay legible in both themes. The old
    window hardcoded #444 and #666 for its secondary text, which is unreadable
    the moment the background goes dark.
    """
    if sv_ttk is not None:
        try:
            theme = sv_ttk.get_theme(root)
            theme = "dark" if theme == "dark" else "light"
        except tk.TclError:
            theme = "dark"
    else:
        theme = "dark"

    pal = dict(_FALLBACK[theme])
    if sv_ttk is not None:
        style = ttk.Style(root)
        try:
            for key, spec in (("bg", "background"), ("fg", "foreground"),
                              ("selbg", "selectbackground"),
                              ("selfg", "selectforeground")):
                got = style.lookup(".", spec)
                if got:
                    pal[key] = str(got)
            card = style.lookup("Card.TFrame", "background")
            if card:
                pal["panel"] = str(card)
        except tk.TclError:
            pass

    pal.setdefault("panel", _mix(pal["bg"], pal["fg"], 0.06))
    pal["dim"] = _mix(pal["fg"], pal["bg"], 0.38)
    pal["theme"] = theme
    return pal


class App:
    def __init__(self, root):
        self.root = root
        self.game_dir = None
        self.busy = False
        self.notify = True
        self.queue = queue.Queue()
        self._theme = _system_theme()
        self._build()
        self._apply_theme(self._theme)
        self._refresh_state()
        self._set_buttons()
        self.root.after(80, self._drain)

    # --- layout -----------------------------------------------------------

    def _build(self):
        self.root.title(TITLE)
        self.root.minsize(760, 560)
        try:
            self.root.iconbitmap(cmd_fontfix._asset("rpykit-luna.ico"))
        except Exception:  # noqa: BLE001 - a missing icon must not stop the window
            pass

        body = ttk.Frame(self.root, padding=(14, 12, 14, 12))
        body.pack(fill="both", expand=True)

        # --- header ---
        head = ttk.Frame(body)
        head.pack(fill="x")
        ttk.Label(head, text="露娜汉化预飞", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="rpykit-luna", style="Sub.TLabel").pack(
            side="left", padx=(10, 0), pady=(6, 0))
        self.btn_theme = ttk.Button(head, width=6, style="Toolbutton",
                                    command=self._toggle_theme)
        self.btn_theme.pack(side="right")

        ttk.Separator(body).pack(fill="x", pady=(10, 12))

        # --- source card ---
        src = ttk.Frame(body, style="Card.TFrame")
        src.pack(fill="x")
        ttk.Label(src, text="游戏目录", style="Cap.TLabel").pack(anchor="w")
        row = ttk.Frame(src, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.var_dir = tk.StringVar(value="")
        ttk.Entry(row, textvariable=self.var_dir, state="readonly").pack(
            side="left", fill="x", expand=True)
        self.btn_pick = ttk.Button(row, text="浏览...", command=self.pick)
        self.btn_pick.pack(side="left", padx=(8, 0))
        self.var_state = tk.StringVar(value="")
        self.lbl_state = ttk.Label(src, textvariable=self.var_state,
                                   style="Info.TLabel", wraplength=690,
                                   justify="left")
        self.lbl_state.pack(anchor="w", pady=(8, 0))

        # --- actions ---
        acts = ttk.Frame(body)
        acts.pack(fill="x", pady=(12, 0))
        self.btn_go = ttk.Button(acts, text="安装字体", style="Accent.TButton",
                                 padding=(20, 6), command=self.install)
        self.btn_go.pack(side="left")
        self.btn_dry = ttk.Button(acts, text="干跑预览", padding=(14, 6),
                                  command=self.dry_run)
        self.btn_dry.pack(side="left", padx=(8, 0))
        self.btn_undo = ttk.Button(acts, text="撤销还原", padding=(14, 6),
                                   command=self.revert)
        self.btn_undo.pack(side="left", padx=(8, 0))
        self.bar = ttk.Progressbar(acts, mode="indeterminate", length=150)

        # --- log card ---
        card = ttk.Frame(body, style="Card.TFrame")
        card.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(card, text="日志", style="Cap.TLabel").pack(anchor="w")

        box = ttk.Frame(card, style="Card.TFrame")
        box.pack(fill="both", expand=True, pady=(6, 0))
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)

        # tk.Text, not scrolledtext: ScrolledText bolts on a classic
        # tk.Scrollbar, which sv-ttk cannot restyle and which is most of what
        # made the old window look dated. The grid keeps the bars flush.
        self.log = tk.Text(box, height=13, wrap="none", state="disabled",
                           font=self._mono(), highlightthickness=0,
                           borderwidth=0, relief="flat")
        self.log.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(box, orient="vertical", command=self.log.yview)
        vs.grid(row=0, column=1, sticky="ns")
        hs = ttk.Scrollbar(box, orient="horizontal", command=self.log.xview)
        hs.grid(row=1, column=0, sticky="ew")
        self.log.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)

        ttk.Label(body, text=HINT, style="Hint.TLabel",
                  justify="left", wraplength=730).pack(anchor="w", pady=(10, 0))

    def _mono(self):
        """A modern console face, falling back to whatever tk can find."""
        try:
            from tkinter import font as tkfont
            families = set(tkfont.families(self.root))
        except Exception:  # noqa: BLE001
            families = set()
        for name in ("Cascadia Mono", "Consolas", "Courier New"):
            if name in families:
                return (name, 9)
        return ("TkFixedFont", 9)

    # --- theme ------------------------------------------------------------

    def _apply_theme(self, theme):
        if sv_ttk is not None:
            try:
                sv_ttk.set_theme(theme, self.root)
            except tk.TclError:
                pass
        self._theme = theme
        self.root.update_idletasks()
        self._repaint()

    def _toggle_theme(self):
        self._apply_theme("light" if self._theme == "dark" else "dark")

    def _repaint(self):
        p = _palette(self.root)
        style = ttk.Style(self.root)
        style.configure("Title.TLabel", background=p["bg"], foreground=p["fg"],
                        font="SunValleySubtitleFont")
        style.configure("Sub.TLabel", background=p["bg"], foreground=p["dim"])
        style.configure("Hint.TLabel", background=p["bg"], foreground=p["dim"])
        style.configure("Cap.TLabel", background=p["panel"], foreground=p["dim"])
        style.configure("Info.TLabel", background=p["panel"], foreground=p["fg"])
        for level, (dark, light) in _STATUS.items():
            style.configure("%s.TLabel" % level.capitalize(),
                            background=p["panel"],
                            foreground=dark if p["theme"] == "dark" else light)

        # The Tk root is a classic widget; sv-ttk does not reach it.
        self.root.configure(bg=p["bg"])
        self.btn_theme.configure(
            text="浅色" if p["theme"] == "dark" else "深色")
        self._paint_log(p)

    def _paint_log(self, p):
        """Repaint the Text by hand on every theme change.

        Measured: a tk.Text created before the theme is applied keeps
        background='SystemWindow', i.e. a blazing white block in dark mode, and
        tk_setPalette does not rescue it. Painting from the palette is the only
        thing that reliably works.
        """
        self.log.configure(
            background=p["panel"], foreground=p["fg"],
            insertbackground=p["fg"],
            selectbackground=p["selbg"], selectforeground=p["selfg"],
            padx=10, pady=8, spacing1=1, spacing3=1)

    # --- state ------------------------------------------------------------

    def _set_buttons(self):
        ready = bool(self.game_dir) and not self.busy
        for b in (self.btn_dry, self.btn_go, self.btn_undo):
            b.state(["!disabled"] if ready else ["disabled"])
        self.btn_pick.state(["disabled"] if self.busy else ["!disabled"])
        if self.busy:
            self.bar.pack(side="right")
            self.bar.start(12)
        else:
            self.bar.stop()
            self.bar.pack_forget()

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_state(self):
        """The five states cmd_fontfix can report, as (level, text)."""
        d = self.game_dir
        if not d:
            return self._set_state("info", "先选一个游戏目录。")
        if not os.path.isdir(os.path.join(d, "game")):
            return self._set_state(
                "bad", "这里没有 game/ 子目录 —— 请选游戏根目录"
                       "（含 game/ 和 renpy/ 的那层）。")
        st = cmd_fontfix.installed_state(d)
        if not st["shim"]:
            return self._set_state("ok", "是一个 Ren'Py 游戏。当前：未安装，可以装。")
        if not st["ours"]:
            return self._set_state(
                "warn", "已有一个 zz_localization.rpy，但不是本工具写的 —— "
                        "安装会拦下，除非点「安装字体」时确认覆盖。")
        if st["current"]:
            return self._set_state(
                "ok", "已安装（mode %s，当前模板）。再点安装等于原地覆盖。"
                      % (st["mode"] or "?"))
        return self._set_state(
            "warn", "已安装，但是旧版本模板（mode %s）。"
                    "建议点「安装字体」重装一次。" % (st["mode"] or "?"))

    def _set_state(self, level, text):
        self.var_state.set("%s  %s" % (_GLYPH[level], text))
        self.lbl_state.configure(style="%s.TLabel" % level.capitalize())
        return level, text

    # --- actions ----------------------------------------------------------

    def pick(self):
        chosen = filedialog.askdirectory(
            title="选择 Ren'Py 游戏根目录（含 game/ 与 renpy/ 的那层）")
        if not chosen:
            return
        self.game_dir = os.path.abspath(chosen)
        self.var_dir.set(self.game_dir)
        self._refresh_state()
        self._set_buttons()

    def dry_run(self):
        self._spawn(_namespace(self.game_dir, dry_run=True),
                    "干跑预览（不写任何文件）", notify=False)

    def install(self):
        if not self._confirm_overwrite():
            return
        self._spawn(_namespace(self.game_dir, force=True), "安装字体", notify=True)

    def revert(self):
        self._spawn(_namespace(self.game_dir, revert=True), "撤销还原", notify=True)

    def _confirm_overwrite(self):
        """Only asked when a foreign file is in the way, so the normal
        reinstall path stays a single click."""
        st = cmd_fontfix.installed_state(self.game_dir)
        if st["shim"] and not st["ours"]:
            return messagebox.askyesno(
                TITLE,
                "这个游戏里已经有一个 zz_localization.rpy，但它不是本工具写的。\n\n"
                "继续会把它备份到工作目录的 quarantine/ 再覆盖。要继续吗？")
        return True

    def _spawn(self, argv, title, notify):
        if self.busy:
            return
        self._log("\n===== %s =====\n" % title)
        self.busy = True
        self.notify = notify
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
        self.queue.put(("__done__", code))

    def _drain(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, tuple):
                    self._finish(item[1])
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _finish(self, code):
        self.busy = False
        self._set_buttons()
        self._refresh_state()
        if not self.notify:
            return
        if code == 0:
            messagebox.showinfo(
                TITLE, "完成。现在开游戏，露娜注入的中文应该能正常显示了。")
        else:
            messagebox.showerror(TITLE, "出错了，看下面的日志。")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
