"""The window rpykit-luna.exe opens when it is double-clicked.

Nothing here makes decisions. It collects a game directory and the set of ticked
features, hands both to cmd_fontfix, and shows what that prints - so the console
entry point and the window are guaranteed to behave identically, because they
run the same code.

The feature cards are drawn from features.CATALOG rather than from a list
written here: a third feature appears in the window by being added to that
catalogue. The only thing this module knows about a feature is the three state
keys its entry names, which is what turns installed_state() into the chip beside
each title.

Colour lives in exactly one place, _repaint(). sv-ttk repaints every ttk widget
on a theme change, but tk's classic widgets - the Tk root and the log's Text -
are not ttk and keep their old colours until something tells them otherwise, so
they are repainted by hand from the same palette. Two styles need the same
treatment for a different reason: sv-ttk colours a checkbutton and a hint label
for the *window* background, which is wrong once they sit on a card.
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
import compat
import features

TITLE = "rpykit-luna  露娜汉化预飞"

FOOTER = "也可以把游戏文件夹整个拖到本程序的图标上，跳过这个窗口直接处理。"

HINT = ("流程：选游戏目录 →「干跑预览」看每个功能打算做什么 →「开始处理」写入 → "
        "开游戏验证。只有勾上的功能会被动，没勾的不会被碰。\n"
        "「撤销还原」不看勾选，把本工具装过的所有东西（连同 Ren'Py 编译出来的 "
        ".rpyc）一起删掉，并把安装时隔离掉的原文件放回原处。")

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


def _chip_style(level):
    return {"ok": "Ok", "warn": "Warn", "bad": "Bad"}.get(
        level, "Info") + "Chip.TLabel"


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
    """The widgets one catalogue entry owns.

    Held together so that _set_buttons, _repaint and _refresh_state can walk the
    rows instead of naming the checkboxes, which is the coupling that used to
    make a second feature expensive.
    """

    def __init__(self, entry, card, toggle, chip_var, chip_label):
        self.id = entry["id"]
        self.entry = entry
        self.card = card
        self.toggle = toggle
        self.chip_var = chip_var
        self.chip_label = chip_label


class App:
    def __init__(self, root):
        self.root = root
        self.game_dir = None
        self.busy = False
        self.notify = True
        self.last_selected = []
        self.rows = {}
        self.var_on = {}
        self.action_buttons = {}
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
        self.root.minsize(720, 600)
        try:
            self.root.iconbitmap(cmd_fontfix._asset("rpykit-luna.ico"))
        except Exception:  # noqa: BLE001 - a missing icon must not stop the window
            pass

        self.wrapped = []
        self._wrap = 0

        body = ttk.Frame(self.root, padding=(18, 16, 18, 14))
        body.pack(fill="both", expand=True)
        body.bind("<Configure>", lambda e: self._wrap_to(e.width - 46))

        # --- header ---
        head = ttk.Frame(body)
        head.pack(fill="x")
        ttk.Label(head, text="露娜汉化预飞", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="rpykit-luna", style="Sub.TLabel").pack(
            side="left", padx=(10, 0), pady=(8, 0))
        self.btn_theme = ttk.Button(head, width=6, style="Toolbutton",
                                    command=self._toggle_theme)
        self.btn_theme.pack(side="right")

        self._build_source(body)
        self._build_features(body)
        self._build_actions(body)
        self._build_log(body)

        self.footer = ttk.Label(body, text=FOOTER, style="Hint.TLabel",
                                justify="left", wraplength=660)
        self.footer.pack(anchor="w", pady=(10, 0))

        # Old names for the intro now that it is one catalogue entry among
        # others. Kept because the window is not the only thing that reads them.
        if "intro" in self.rows:
            self.var_skip = self.var_on["intro"]
            self.chk_skip = self.rows["intro"].toggle

    def _build_source(self, body):
        src = ttk.Frame(body, style="Card.TFrame")
        src.pack(fill="x", pady=(14, 0))
        ttk.Label(src, text="游戏目录", style="Cap.TLabel").pack(anchor="w")

        row = ttk.Frame(src, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.var_dir = tk.StringVar(value="")
        ttk.Entry(row, textvariable=self.var_dir, state="readonly").pack(
            side="left", fill="x", expand=True)
        self.btn_pick = ttk.Button(row, text="浏览...", command=self.pick)
        self.btn_pick.pack(side="left", padx=(8, 0))

        # What this folder *is*, from compat.survey - the question a player
        # actually has, and one the old window answered with "does game/ exist".
        # The verdict keeps its colour and the reasons underneath stay dim, so a
        # game with four things wrong does not paint the card solid yellow.
        self.var_compat = tk.StringVar(value="")
        self.lbl_compat = ttk.Label(src, textvariable=self.var_compat,
                                    style="Info.TLabel", justify="left")
        self.lbl_compat.pack(anchor="w", pady=(8, 0))
        self.var_reasons = tk.StringVar(value="")
        self.lbl_reasons = ttk.Label(src, textvariable=self.var_reasons,
                                     style="CardHint.TLabel", justify="left")
        self.lbl_reasons.pack(anchor="w", pady=(4, 0))

        # What this tool has already done to it.
        self.var_state = tk.StringVar(value="")
        self.lbl_state = ttk.Label(src, textvariable=self.var_state,
                                   style="Info.TLabel", justify="left")
        self.lbl_state.pack(anchor="w", pady=(6, 0))

        self.wrapped += [self.lbl_compat, self.lbl_reasons, self.lbl_state]

    def _build_features(self, body):
        ttk.Label(body, text="功能", style="Section.TLabel").pack(
            anchor="w", pady=(16, 6))
        box = ttk.Frame(body)
        box.pack(fill="x")

        for entry in features.CATALOG:
            card = ttk.Frame(box, style="Card.TFrame")
            card.pack(fill="x", pady=(0, 8))

            head = ttk.Frame(card, style="Card.TFrame")
            head.pack(fill="x")

            var = tk.BooleanVar(value=bool(entry.get("default_on", True)))
            self.var_on[entry["id"]] = var
            toggle = ttk.Checkbutton(head, text=entry["title"], variable=var,
                                     style="Card.TCheckbutton")
            toggle.pack(side="left")

            chip_var = tk.StringVar(value="")
            chip = ttk.Label(head, textvariable=chip_var, style="InfoChip.TLabel")
            chip.pack(side="right")

            desc = ttk.Label(card, text=entry["desc"], style="CardHint.TLabel",
                             justify="left")
            desc.pack(anchor="w", pady=(6, 0))
            self.wrapped.append(desc)

            self.rows[entry["id"]] = _FeatureRow(entry, card, toggle, chip_var, chip)

    def _build_actions(self, body):
        acts = ttk.Frame(body)
        acts.pack(fill="x", pady=(14, 0))
        # One confirm, whatever is ticked above it.
        self.btn_go = ttk.Button(acts, text="开始处理", style="Accent.TButton",
                                 padding=(20, 6), command=self.install)
        self.btn_go.pack(side="left")
        self.btn_dry = ttk.Button(acts, text="干跑预览", padding=(14, 6),
                                  command=self.dry_run)
        self.btn_dry.pack(side="left", padx=(8, 0))
        self.btn_undo = ttk.Button(acts, text="撤销还原", padding=(14, 6),
                                   command=self.revert)
        self.btn_undo.pack(side="left", padx=(8, 0))
        self.bar = ttk.Progressbar(acts, mode="indeterminate", length=150)
        self.action_buttons = {"go": self.btn_go, "dry": self.btn_dry,
                               "undo": self.btn_undo}

    def _build_log(self, body):
        self.var_log = tk.BooleanVar(value=False)
        self.chk_log = ttk.Checkbutton(body, text="显示日志", variable=self.var_log,
                                       command=self._toggle_log)
        self.chk_log.pack(anchor="w", pady=(14, 4))

        card = ttk.Frame(body, style="Card.TFrame")
        ttk.Label(card, text="日志", style="Cap.TLabel").pack(anchor="w")
        hint = ttk.Label(card, text=HINT, style="CardHint.TLabel", justify="left",
                         wraplength=600)
        hint.pack(anchor="w", pady=(6, 0))
        self.wrapped.append(hint)

        box = ttk.Frame(card, style="Card.TFrame")
        box.pack(fill="both", expand=True, pady=(8, 0))
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

        # Built always, shown on demand: the log is what made the old window
        # feel like a console with a form bolted on.
        self.log_card = card

    def _toggle_log(self):
        if self.var_log.get():
            # before= keeps the footer last however often this is toggled.
            self.log_card.pack(fill="both", expand=True, before=self.footer)
            # Revealing the card does not resize the body, so no Configure will
            # arrive to hand it a wraplength - and one label asking for its
            # unwrapped width would stretch the whole window.
            self._apply_wrap()
        else:
            self.log_card.pack_forget()

    def _apply_wrap(self):
        for lbl in self.wrapped:
            lbl.configure(wraplength=max(240, self._wrap))

    def _wrap_to(self, width):
        """Hold every wrapped label to the width of the window.

        Tk breaks a line only at a space, or inside a single run that overflows
        on its own. A fixed wraplength therefore either leaves the first line
        of a Chinese sentence half empty or runs text under the card's rounded
        edge. Following the window cannot feed back into its size: the cards
        are packed with fill="x", so their width comes from the parent and not
        from what the labels ask for.
        """
        width = max(240, width)
        if width == self._wrap:
            return
        self._wrap = width
        self._apply_wrap()

    def _show_log(self):
        if not self.var_log.get():
            self.var_log.set(True)
            self._toggle_log()

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
        style.configure("Section.TLabel", background=p["bg"], foreground=p["fg"],
                        font="SunValleyBodyStrongFont")
        style.configure("Cap.TLabel", background=p["panel"], foreground=p["dim"])
        style.configure("Info.TLabel", background=p["panel"], foreground=p["fg"])

        # On a card, not on the window: sv-ttk's own colours for these two are
        # the window background, which reads as a lighter rectangle punched into
        # the panel. The indicator sprite has transparent corners, so it is the
        # checkbutton's own background that shows through them.
        style.configure("CardHint.TLabel", background=p["panel"],
                        foreground=p["dim"])
        style.configure("Card.TCheckbutton", background=p["panel"],
                        foreground=p["fg"])
        style.map("Card.TCheckbutton",
                  background=[("disabled", p["panel"])],
                  foreground=[("disabled", p["dim"])])

        for level, (dark, light) in _STATUS.items():
            fg = dark if p["theme"] == "dark" else light
            cap = level.capitalize()
            style.configure("%s.TLabel" % cap, background=p["panel"], foreground=fg)
            style.configure("%sChip.TLabel" % cap, background=p["panel"],
                            foreground=fg, font="SunValleyCaptionFont")
        style.configure("InfoChip.TLabel", background=p["panel"],
                        foreground=p["dim"], font="SunValleyCaptionFont")

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
        for b in self.action_buttons.values():
            b.state(["!disabled"] if ready else ["disabled"])
        self.btn_pick.state(["disabled"] if self.busy else ["!disabled"])
        # Not in the loop above: a feature box is answerable before a directory
        # is picked, and only the busy state has any reason to lock it.
        for row in self.rows.values():
            row.toggle.state(["disabled"] if self.busy else ["!disabled"])
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

    def _ticked(self):
        """The ticked feature ids, in catalogue order, read on the main thread."""
        return [fid for fid in features.ids() if self.var_on[fid].get()]

    def _paint_chips(self, state):
        for row in self.rows.values():
            level, text = _chip(row.entry, state)
            row.chip_var.set("%s %s" % (_GLYPH[level], text))
            row.chip_label.configure(style=_chip_style(level))

    def _set_compat(self, survey):
        """The folder's verdict, or nothing at all when there is no folder.

        Blank rather than a placeholder: the line below this one already says
        what to do, and two sentences about the same missing directory reads
        like the window is arguing with itself.
        """
        if not survey:
            self.var_compat.set("")
            self.var_reasons.set("")
            return
        level = survey["verdict"]
        self.var_compat.set("%s  %s" % (_GLYPH[level], _describe(survey)))
        self.lbl_compat.configure(style="%s.TLabel" % level.capitalize())
        self.var_reasons.set(_reasons(survey))

    def _refresh_state(self):
        """Everything the window says about the current folder, as (level, text).

        Two separate answers, because they can disagree: compat says what the
        game is and whether this tool has any business patching it, and this
        says what the tool has already done there.
        """
        d = self.game_dir
        if not d:
            self._set_compat(None)
            self._paint_chips(None)
            return self._set_state("info", "先选一个游戏目录。")
        if not os.path.isdir(os.path.join(d, "game")):
            self._set_compat(None)
            self._paint_chips(None)
            return self._set_state(
                "bad", "这里没有 game/ 子目录 —— 请选游戏根目录"
                       "（含 game/ 和 renpy/ 的那层）。")

        self._set_compat(compat.survey(d, quick=True))
        st = cmd_fontfix.installed_state(d)
        self._paint_chips(st)

        done = [features.title_of(fid) for fid in features.ids()
                if st.get(features.by_id(fid)["state"]["installed"])]
        done_note = "已经装过：%s。" % "、".join(done) if done else ""
        if not st["shim"]:
            return self._set_state(
                "ok", (done_note + "字体还没装，可以开始。") if done_note
                else "本工具还没有在这里装过东西，可以开始。")
        if not st["ours"]:
            return self._set_state(
                "warn", "已有一个 %s，但不是本工具写的 —— 开始处理会先拦下，"
                        "确认之后才备份覆盖。" % cmd_fontfix.SHIM_REL)
        if st["current"]:
            return self._set_state(
                "ok", "字体已安装（mode %s，当前模板）。再点一次等于原地覆盖。"
                      % (st["mode"] or "?"))
        return self._set_state(
            "warn", "字体已安装，但是旧版本模板（mode %s）。建议重新装一次。"
                    % (st["mode"] or "?"))

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

    def _args(self, **kw):
        """The namespace for the boxes as they are right now.

        The Tk variables are read here, on the main thread, so the worker never
        touches them.
        """
        ids = self._ticked()
        return _namespace(self.game_dir, feature_ids=ids,
                          skip_intro=("intro" in ids), **kw)

    def dry_run(self):
        self._spawn(self._args(dry_run=True),
                    "干跑预览（不写任何文件）", notify=False)

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
            names = "、".join(features.title_of(fid) for fid in self.last_selected)
            messagebox.showinfo(
                TITLE, "完成：%s。\n\n现在开一次游戏看看效果。"
                       % (names or "没有改动"))
        else:
            self._show_log()
            messagebox.showerror(TITLE, "出错了，看下面的日志。")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
