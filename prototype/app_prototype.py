"""Interface prototype for the redesigned window.

Fake data only. Every number, game name and log line below is a literal, so the
layout can be judged before any real logic is rewired. Nothing here imports the
toolkit; when the shape is agreed, the pages get wired to compat/features/
simulation and this file is deleted.
"""

import tkinter as tk

import customtkinter as ctk

PAGE_BG = ("#F5F4FB", "#131120")
SIDEBAR_BG = ("#EBE9F8", "#1A1728")
CARD_BG = ("#FFFFFF", "#201C33")
SUNKEN_BG = ("#F7F6FD", "#262238")
BORDER = ("#E3DFF3", "#302B49")
TEXT = ("#1B1733", "#EEEBFA")
MUTED = ("#6E6990", "#9B96BA")
ACCENT = ("#6D4AFF", "#8B6BFF")
ACCENT_HOVER = ("#5A38EE", "#7C5CF7")
ACCENT_SOFT = ("#E9E3FF", "#2C2450")
SEGMENT_BG = ("#EDEAF7", "#2B2643")
OK = ("#17A06B", "#43D69F")
OK_SOFT = ("#E2F7EE", "#17362C")
WARN = ("#B0740A", "#F0B845")
WARN_SOFT = ("#FDF2DF", "#3A3117")
BAD = ("#C43D2E", "#FF8072")
BAD_SOFT = ("#FDE9E6", "#3D2320")
GRAD_A = (0x6D, 0x4A, 0xFF)
GRAD_B = (0x3F, 0xA9, 0xF5)

CJK = "Microsoft YaHei UI"
MONO = "Consolas"

FEATURES = [
    ("字", "汉化预飞（字体）", "把游戏用到的每个字体名指向 FontGroup：拉丁字母继续用游戏自己的字体，中文交给随包字体。",
     True, "未安装", "ok"),
    ("开", "跳过开场 logo", "把 splashscreen 指向空实现，开局直接进主菜单。",
     True, "已安装", "ok"),
    ("裁", "字体子集化", "按游戏实际用到的字符裁剪字体，替掉现在 17.7 MB 的全量拷贝。",
     True, "待处理", "idle"),
    ("备", "整目录快照备份", "动手前把 game/ 打包，出任何事都能一键回到初始状态。",
     True, "未安装", "idle"),
    ("控", "解锁开发者控制台", "打开 shift+O 控制台，便于调试与跳转。",
     False, "未安装", "ok"),
    ("藏", "解锁画廊 / 跳过已读", "解锁 CG 回放，跳过已读文本。",
     False, "不支持", "bad"),
]

GAMES = [
    ("Game-A", "0.6.0", "Ren'Py 8.4.2 · Py3.12", "已装 2 项", "ok", "#6D4AFF"),
    ("Game-B", "0.06.06b", "Ren'Py 8.3.0 · Py3.9", "已装 2 项", "ok", "#3FA9F5"),
    ("Game-C", "0.6.23", "Ren'Py 8.2.3 · Py3.9", "已装 2 项", "ok", "#E86AA6"),
    ("Game-H", "0.9", "Ren'Py 8.5.0 · Py3.12", "未处理", "idle", "#F0A93B"),
    ("Game-F", "0.8", "Ren'Py 8.3.2 · Py3.9", "无 splashscreen", "warn", "#3FC7A8"),
    ("Game-I", "0.6.6.0", "Ren'Py 7.4.11 · Py2.7", "需降级方案", "warn", "#7A8CA8"),
    ("Game-J", "1.01", "Ren'Py 7.5.3 · Py2.7", "fontfix 被拦截", "bad", "#C4564A"),
]

LOG_LINES = [
    ("muted", "2026-09-28 11:02:14  rpykit 0.10.0-dev  python 3.13.12  win32"),
    ("muted", "2026-09-28 11:02:14  预检 Game-C 0.6.23"),
    ("ok",    "2026-09-28 11:02:14  [ok]   引擎        Ren'Py 8.2.3 / Python 3.9.10 / 64-bit"),
    ("ok",    "2026-09-28 11:02:14  [ok]   脚本        5 rpa + 9 散装 .rpyc（归档可读）"),
    ("ok",    "2026-09-28 11:02:15  [ok]   fontfix     FontGroup + config.font_name_map 均在"),
    ("ok",    "2026-09-28 11:02:15  [ok]   intro       config.label_overrides 在，splashscreen 已定义"),
    ("muted", "2026-09-28 11:02:15  扫描字体引用：DejaVuSans.ttf, DejaVuSans-Bold.ttf, PT_Serif.ttf"),
    ("muted", "2026-09-28 11:02:16  DejaVuSans.ttf 汉字覆盖 0/20902 → keep-latin"),
    ("muted", "2026-09-28 11:02:16  PT_Serif.ttf 汉字覆盖 0/20902 → keep-ascii"),
    ("ok",    "2026-09-28 11:02:17  [ok]   字符集      本次共 3 412 个唯一字符"),
    ("acc",   "2026-09-28 11:02:19  子集化 NotoSansSC-VF.ttf  17.7 MB → 486 KB（2.7%）"),
    ("ok",    "2026-09-28 11:02:19  [ok]   写入       game/localization/NotoSansSC-subset.ttf"),
    ("ok",    "2026-09-28 11:02:19  [ok]   写入       game/zz_localization.rpy"),
    ("muted", "2026-09-28 11:02:20  已记入 install_manifest.json（3 条）"),
    ("acc",   "2026-09-28 11:02:31  启动副本并观察主菜单…"),
    ("ok",    "2026-09-28 11:02:48  [ok]   冒烟测试    已进入主菜单，模拟成功"),
]

NAV = [("process", "处理"), ("library", "游戏库"), ("toolbox", "工具箱"),
       ("log", "日志"), ("settings", "设置")]

PAGE_TITLE = {
    "process": ("处理", "选一个游戏，勾要装的东西，然后跑模拟。"),
    "library": ("游戏库", "打开过的游戏都在这里，可以多选批量装或批量撤销。"),
    "toolbox": ("工具箱", "不改游戏也能用的检查工具。"),
    "log": ("日志", "全部输出都在这里，主界面不再被日志挤占。"),
    "settings": ("设置", "外观、备份与更新。"),
}


def _gradient(canvas, width, height, bg):
    canvas.configure(bg=bg)
    canvas.delete("g")
    for x in range(width):
        t = x / max(1, width - 1)
        r = int(GRAD_A[0] + (GRAD_B[0] - GRAD_A[0]) * t)
        g = int(GRAD_A[1] + (GRAD_B[1] - GRAD_A[1]) * t)
        b = int(GRAD_A[2] + (GRAD_B[2] - GRAD_A[2]) * t)
        canvas.create_line(x, 0, x, height, fill=f"#{r:02x}{g:02x}{b:02x}", tags="g")


class Shell(ctk.CTk):
    def __init__(self, page="process", mode="system"):
        super().__init__()
        self._mode = mode
        ctk.set_appearance_mode(self._mode)
        self.title("SLG-Renpy神奇妙妙工具 — 界面原型")
        self._want = (1120, 750)
        self._place()
        self.minsize(960, 620)
        self.configure(fg_color=PAGE_BG)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.nav = {}
        self.gradients = []
        self._build_sidebar()
        self._build_main()
        self.show(page)
        self.after(120, self._sync_theme)
        self.after(200, self._fit_window)

    def _place(self):
        width, height = self._want
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2 - 24)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _fit_window(self):
        """Shrink to the screen: scaled DPI can push the asked-for size past it."""
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        if not width or not height:
            return
        factor = min(1.0, (screen_w * 0.94) / width, (screen_h * 0.90) / height)
        if factor < 1.0:
            self._want = (int(self._want[0] * factor), int(self._want[1] * factor))
            self._place()

    # --- chrome -----------------------------------------------------------

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=218, corner_radius=0, fg_color=SIDEBAR_BG)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(98, weight=1)

        wrap = ctk.CTkFrame(bar, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="ew", padx=16, pady=(20, 18))
        strip = tk.Canvas(wrap, width=186, height=4, highlightthickness=0, bd=0)
        strip.pack(fill="x")
        self.gradients.append((strip, 186, 4))
        ctk.CTkLabel(wrap, text="SLG Ren'Py", anchor="w",
                     font=ctk.CTkFont(CJK, 19, "bold"), text_color=TEXT).pack(
            fill="x", pady=(11, 0))
        ctk.CTkLabel(wrap, text="神奇妙妙工具", anchor="w",
                     font=ctk.CTkFont(CJK, 12), text_color=MUTED).pack(fill="x")

        for idx, (key, label) in enumerate(NAV, start=1):
            btn = ctk.CTkButton(
                bar, text=label, anchor="w", height=40, corner_radius=10,
                fg_color="transparent", hover_color=ACCENT_SOFT, text_color=TEXT,
                font=ctk.CTkFont(CJK, 14),
                command=lambda k=key: self.show(k))
            btn.grid(row=idx, column=0, sticky="ew", padx=12, pady=2)
            self.nav[key] = btn

        foot = ctk.CTkFrame(bar, fg_color="transparent")
        foot.grid(row=100, column=0, sticky="ew", padx=12, pady=(0, 16))
        self.mode_btn = ctk.CTkButton(
            foot, text="外观：跟随系统", height=32, corner_radius=9,
            fg_color="transparent", hover_color=ACCENT_SOFT, text_color=MUTED,
            font=ctk.CTkFont(CJK, 12), anchor="w", command=self.cycle_mode)
        self.mode_btn.pack(fill="x")
        ctk.CTkLabel(foot, text="v0.10.0-dev", anchor="w",
                     font=ctk.CTkFont(CJK, 11), text_color=MUTED).pack(
            fill="x", padx=10, pady=(6, 0))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 4))
        top.grid_columnconfigure(0, weight=1)
        self.title_lbl = ctk.CTkLabel(top, text="", anchor="w", text_color=TEXT,
                                      font=ctk.CTkFont(CJK, 21, "bold"))
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.sub_lbl = ctk.CTkLabel(top, text="", anchor="w", text_color=MUTED,
                                    font=ctk.CTkFont(CJK, 12))
        self.sub_lbl.grid(row=1, column=0, sticky="w", pady=(3, 0))

        bar_row = ctk.CTkFrame(top, fg_color="transparent")
        bar_row.grid(row=2, column=0, sticky="ew", pady=(13, 0))
        bar_row.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(bar_row, height=6, corner_radius=3,
                                           progress_color=ACCENT, fg_color=BORDER)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.progress.set(0.42)
        self.stage_lbl = ctk.CTkLabel(
            bar_row, text="预检 42%  ·  正在读取 5 个 .rpa 归档的脚本索引",
            anchor="w", text_color=MUTED, font=ctk.CTkFont(CJK, 11))
        self.stage_lbl.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.body = ctk.CTkFrame(main, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(12, 20))
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        for key, _ in NAV:
            page = ctk.CTkFrame(self.body, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_columnconfigure(0, weight=1)
            page.grid_rowconfigure(0, weight=1)
            getattr(self, "_page_" + key)(page)
            self.pages[key] = page

    def show(self, key):
        title, sub = PAGE_TITLE[key]
        self.title_lbl.configure(text=title)
        self.sub_lbl.configure(text=sub)
        for k, btn in self.nav.items():
            active = k == key
            btn.configure(fg_color=ACCENT if active else "transparent",
                          text_color=("#FFFFFF", "#FFFFFF") if active else TEXT,
                          hover_color=ACCENT_HOVER if active else ACCENT_SOFT)
        self.pages[key].tkraise()

    def cycle_mode(self):
        order = ["system", "light", "dark"]
        label = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
        self._mode = order[(order.index(self._mode) + 1) % 3]
        ctk.set_appearance_mode(self._mode)
        self.mode_btn.configure(text="外观：" + label[self._mode])
        self.after(60, self._sync_theme)

    def set_mode(self, mode):
        self._mode = mode
        ctk.set_appearance_mode(mode)
        label = {"system": "跟随系统", "light": "浅色", "dark": "深色"}[mode]
        self.mode_btn.configure(text="外观：" + label)
        self.after(60, self._sync_theme)

    def _sync_theme(self):
        bg = SIDEBAR_BG[1] if ctk.get_appearance_mode() == "Dark" else SIDEBAR_BG[0]
        for canvas, w, h in self.gradients:
            _gradient(canvas, w, h, bg)

    # --- pages ------------------------------------------------------------

    def _page_process(self, parent):
        p = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        p.grid(row=0, column=0, sticky="nsew")
        p.grid_columnconfigure((0, 1), weight=1)

        card = self._card(p, row=0, column=0, columnspan=2)
        ctk.CTkLabel(card, text="游戏目录", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(row, height=36, corner_radius=9, fg_color=SUNKEN_BG,
                     border_color=BORDER, border_width=1, text_color=TEXT,
                     font=ctk.CTkFont(CJK, 12),
                     placeholder_text="把游戏文件夹拖进来，或点右侧浏览").grid(
            row=0, column=0, sticky="ew")
        ctk.CTkButton(row, text="浏览…", width=88, height=36, corner_radius=9,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).grid(
            row=0, column=1, padx=(8, 0))
        ctk.CTkButton(row, text="游戏库", width=88, height=36, corner_radius=9,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12),
                      command=lambda: self.show("library")).grid(
            row=0, column=2, padx=(8, 0))

        chips = ctk.CTkFrame(card, fg_color="transparent")
        chips.pack(fill="x", pady=(12, 0))
        self._chip(chips, "Ren'Py 8.2.3", "ok").pack(side="left")
        self._chip(chips, "Python 3.9", "ok").pack(side="left", padx=(6, 0))
        self._chip(chips, "5 rpa + 9 散装", "ok").pack(side="left", padx=(6, 0))
        self._chip(chips, "splashscreen 已定义", "ok").pack(side="left", padx=(6, 0))
        self._chip(chips, "fontfix 可用", "ok").pack(side="left", padx=(6, 0))

        head = ctk.CTkFrame(p, fg_color="transparent")
        head.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(20, 8))
        ctk.CTkLabel(head, text="选择功能", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 15, "bold")).pack(side="left")
        ctk.CTkLabel(head, text="每项独立检查兼容性，可分别启用", anchor="w",
                     text_color=MUTED, font=ctk.CTkFont(CJK, 11)).pack(
            side="left", padx=(10, 0))

        for idx, feature in enumerate(FEATURES):
            self._feature_card(p, idx // 2 + 2, idx % 2, feature)

        acts = ctk.CTkFrame(p, fg_color="transparent")
        acts.grid(row=99, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ctk.CTkButton(acts, text="模拟安装并运行", height=40, corner_radius=10,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(CJK, 13, "bold"),
                      command=lambda: None).pack(side="left")
        ctk.CTkButton(acts, text="开始处理", height=40, width=110, corner_radius=10,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 13), command=lambda: None).pack(
            side="left", padx=(8, 0))
        ctk.CTkButton(acts, text="撤销还原", height=40, width=110, corner_radius=10,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 13), command=lambda: None).pack(
            side="left", padx=(8, 0))

        stages = self._card(p, row=100, column=0, columnspan=2)
        ctk.CTkLabel(stages, text="本次模拟", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        for text, level in (
                ("兼容预检 · 5 项 API 全部可用", "ok"),
                ("复制游戏副本 · 2.1 GB → %LOCALAPPDATA%\\rpykit\\sim", "ok"),
                ("模拟安装补丁 · 字体子集 486 KB + 2 个脚本", "ok"),
                ("启动副本 · Game-C.exe", "acc"),
                ("确认主菜单 · 等待你在副本里点一下", "warn")):
            self._stage(stages, text, level)

    def _page_library(self, parent):
        p = ctk.CTkFrame(parent, fg_color="transparent")
        p.grid(row=0, column=0, sticky="nsew")
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)

        tools = ctk.CTkFrame(p, fg_color="transparent")
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkButton(tools, text="添加游戏…", width=110, height=34,
                      corner_radius=9, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(side="left")
        ctk.CTkButton(tools, text="扫描整个目录", width=120, height=34,
                      corner_radius=9, fg_color="transparent", border_width=1,
                      border_color=BORDER, hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="left", padx=(8, 0))
        ctk.CTkLabel(tools, text="已选 2 个游戏", anchor="e", text_color=MUTED,
                     font=ctk.CTkFont(CJK, 12)).pack(side="right")

        wall = ctk.CTkScrollableFrame(p, fg_color="transparent")
        wall.grid(row=1, column=0, sticky="nsew")
        wall.grid_columnconfigure((0, 1, 2), weight=1)
        for idx, game in enumerate(GAMES):
            self._game_card(wall, idx // 3, idx % 3, game)

        bar = ctk.CTkFrame(p, corner_radius=12, fg_color=CARD_BG, border_width=1,
                           border_color=BORDER)
        bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(bar, text="批量：装补丁到 2 个游戏", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 12)).pack(side="left", padx=14, pady=12)
        ctk.CTkButton(bar, text="批量撤销", width=110, height=34, corner_radius=9,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="right", padx=(8, 14), pady=12)
        ctk.CTkButton(bar, text="批量安装", width=110, height=34, corner_radius=9,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="right", pady=12)

    def _page_toolbox(self, parent):
        p = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        p.grid(row=0, column=0, sticky="nsew")
        p.grid_columnconfigure((0, 1), weight=1)

        font_card = self._card(p, row=0, column=0)
        ctk.CTkLabel(font_card, text="字体检查", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        drop = ctk.CTkFrame(font_card, height=88, corner_radius=10,
                            fg_color=SUNKEN_BG, border_width=1, border_color=BORDER)
        drop.pack(fill="x", pady=(10, 0))
        drop.pack_propagate(False)
        ctk.CTkLabel(drop, text="把 .ttf / .otf 拖到这里", text_color=MUTED,
                     font=ctk.CTkFont(CJK, 12)).pack(expand=True)
        ctk.CTkLabel(font_card, text="DejaVuSans.ttf", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 12, "bold")).pack(fill="x", pady=(12, 0))
        cov = ctk.CTkFrame(font_card, fg_color="transparent")
        cov.pack(fill="x", pady=(8, 0))
        cov.grid_columnconfigure(0, weight=1)
        ctk.CTkProgressBar(cov, height=6, corner_radius=3, progress_color=WARN,
                           fg_color=BORDER).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(cov, text="通用汉字 0 / 20 902（0%）· 缺 20 902", anchor="w",
                     text_color=MUTED, font=ctk.CTkFont(CJK, 11)).grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        ctk.CTkLabel(font_card, text="样例缺字：汉字 你好 世界 露娜 汉化", anchor="w",
                     text_color=WARN, font=ctk.CTkFont(CJK, 12)).pack(
            fill="x", pady=(8, 0))
        ctk.CTkButton(font_card, text="导出子集（按字符表裁剪）", height=34,
                      corner_radius=9, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            fill="x", pady=(12, 0))

        info = self._card(p, row=0, column=1)
        ctk.CTkLabel(info, text="游戏信息", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        for key, value in (
                ("引擎", "Ren'Py 8.2.3"),
                ("Python", "3.9.10"),
                ("架构", "64-bit"),
                ("脚本", "5 rpa（可读）+ 9 散装 .rpyc"),
                ("字体引用", "3 个（DejaVuSans, DejaVuSans-Bold, PT_Serif）"),
                ("已装补丁", "fontfix, intro"),
                ("工作目录", "%LOCALAPPDATA%\\rpykit\\Game-C 0.6.23")):
            self._kv(info, key, value)
        ctk.CTkButton(info, text="导出诊断报告", height=34, corner_radius=9,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            fill="x", pady=(14, 0))

    def _page_log(self, parent):
        p = ctk.CTkFrame(parent, fg_color="transparent")
        p.grid(row=0, column=0, sticky="nsew")
        p.grid_columnconfigure(0, weight=1)
        p.grid_rowconfigure(1, weight=1)

        tools = ctk.CTkFrame(p, fg_color="transparent")
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkSegmentedButton(
            tools, values=["全部", "只看错误", "只看写入"],
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SEGMENT_BG, unselected_hover_color=ACCENT_SOFT,
            text_color=TEXT, font=ctk.CTkFont(CJK, 12)).pack(side="left")
        ctk.CTkButton(tools, text="复制", width=76, height=32, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="right")
        ctk.CTkButton(tools, text="导出", width=76, height=32, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="right", padx=(0, 8))

        box = ctk.CTkTextbox(p, corner_radius=12, border_width=1,
                             border_color=BORDER, fg_color=CARD_BG,
                             text_color=TEXT, font=ctk.CTkFont(MONO, 12),
                             wrap="none")
        box.grid(row=1, column=0, sticky="nsew")
        box.tag_config("ok", foreground=OK[0])
        box.tag_config("warn", foreground=WARN[0])
        box.tag_config("bad", foreground=BAD[0])
        box.tag_config("acc", foreground=ACCENT[0])
        box.tag_config("muted", foreground=MUTED[0])
        for level, line in LOG_LINES:
            box.insert("end", line + "\n", level)
        box.configure(state="disabled")

    def _page_settings(self, parent):
        p = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        p.grid(row=0, column=0, sticky="nsew")
        p.grid_columnconfigure((0, 1), weight=1)

        look = self._card(p, row=0, column=0)
        ctk.CTkLabel(look, text="外观", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        seg = ctk.CTkSegmentedButton(
            look, values=["跟随系统", "浅色", "深色"], command=self._mode_from_label,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SEGMENT_BG, unselected_hover_color=ACCENT_SOFT,
            text_color=TEXT, font=ctk.CTkFont(CJK, 12))
        seg.pack(fill="x", pady=(12, 0))
        seg.set("跟随系统")
        self._kv(look, "窗口尺寸", "1120 × 750（记忆上次）")
        self._kv(look, "界面语言", "简体中文")

        safety = self._card(p, row=0, column=1)
        ctk.CTkLabel(safety, text="安全与更新", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        self._switch(safety, "安装前自动快照 game/ 目录", True)
        self._switch(safety, "安装后保留模拟副本（便于对比）", False)
        self._switch(safety, "启动时静默检查新版本", True)
        row = ctk.CTkFrame(safety, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(row, text="立即检查更新", height=34, corner_radius=9,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="left")
        ctk.CTkButton(row, text="打开工作目录", height=34, corner_radius=9,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12), command=lambda: None).pack(
            side="left", padx=(8, 0))
        ctk.CTkLabel(safety, text="当前 0.10.0-dev  ·  最新 0.10.0（3 天前发布）",
                     anchor="w", text_color=OK, font=ctk.CTkFont(CJK, 11)).pack(
            fill="x", pady=(10, 0))

        about = self._card(p, row=1, column=0, columnspan=2)
        ctk.CTkLabel(about, text="关于", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 14, "bold")).pack(fill="x")
        ctk.CTkLabel(
            about, anchor="w", justify="left", text_color=MUTED,
            font=ctk.CTkFont(CJK, 12),
            text="只往游戏目录里加文件，不改脚本、不重打包 .rpa、不动 tl/。\n"
                 "每处写入都记在 install_manifest.json，撤销只删自己装过的东西。\n"
                 "本工具不含任何游戏内容与翻译文本。仅供个人学习与汉化技术交流，请支持正版。").pack(
            fill="x", pady=(8, 0))
        chips = ctk.CTkFrame(about, fg_color="transparent")
        chips.pack(fill="x", pady=(12, 0))
        self._chip(chips, "MIT 许可", "idle").pack(side="left")
        self._chip(chips, "内置字体 SIL OFL 1.1", "idle").pack(side="left", padx=(6, 0))
        self._chip(chips, "仅 Windows", "idle").pack(side="left", padx=(6, 0))

    # --- widgets ----------------------------------------------------------

    def _card(self, parent, row, column, columnspan=1):
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD_BG,
                            border_width=1, border_color=BORDER)
        card.grid(row=row, column=column, columnspan=columnspan, sticky="nsew",
                  padx=(0, 8) if column == 0 and columnspan == 1 else (8, 0) if columnspan == 1 else 0,
                  pady=8)
        return card

    def _feature_card(self, parent, row, column, feature):
        badge, title, desc, on, state, level = feature
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD_BG,
                            border_width=1,
                            border_color=ACCENT if on else BORDER)
        card.grid(row=row, column=column, sticky="nsew",
                  padx=(0, 6) if column == 0 else (6, 0), pady=6)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text=badge, width=38, height=38, corner_radius=11,
                     fg_color=ACCENT_SOFT, text_color=ACCENT,
                     font=ctk.CTkFont(CJK, 16, "bold")).grid(
            row=0, column=0, rowspan=2, padx=(14, 12), pady=(14, 0), sticky="n")

        ctk.CTkLabel(card, text=title, anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 13, "bold")).grid(
            row=0, column=1, sticky="w", pady=(14, 0))
        var = tk.BooleanVar(value=on)
        ctk.CTkSwitch(card, text="", variable=var, width=42,
                      progress_color=ACCENT, button_color=("#FFFFFF", "#FFFFFF"),
                      button_hover_color=("#FFFFFF", "#FFFFFF"),
                      command=lambda c=card, v=var: c.configure(
                          border_color=ACCENT if v.get() else BORDER)).grid(
            row=0, column=2, padx=(8, 14), pady=(14, 0))

        ctk.CTkLabel(card, text=desc, anchor="w", justify="left", wraplength=330,
                     text_color=MUTED, font=ctk.CTkFont(CJK, 11)).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))

        chips = ctk.CTkFrame(card, fg_color="transparent")
        chips.grid(row=2, column=1, columnspan=2, sticky="w", pady=(10, 14))
        self._chip(chips, state, level).pack(side="left")
        if not on and level == "bad":
            ctk.CTkLabel(chips, text="缺少 config.label_overrides 之外的所需 API",
                         anchor="w", text_color=MUTED,
                         font=ctk.CTkFont(CJK, 10)).pack(side="left", padx=(8, 0))

    def _game_card(self, parent, row, column, game):
        name, version, engine, status, level, tint = game
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD_BG,
                            border_width=1, border_color=BORDER)
        card.grid(row=row, column=column, sticky="nsew",
                  padx=(0, 5) if column == 0 else (5, 0), pady=6)
        card.grid_columnconfigure(0, weight=1)

        cover = ctk.CTkFrame(card, height=104, corner_radius=11, fg_color=tint)
        cover.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 0))
        cover.pack_propagate(False)
        ctk.CTkLabel(cover, text=name[:1], text_color="#FFFFFF",
                     font=ctk.CTkFont(CJK, 34, "bold")).pack(expand=True)

        ctk.CTkLabel(card, text=name, anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 13, "bold")).grid(
            row=1, column=0, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(card, text="v" + version + "  ·  " + engine, anchor="w",
                     justify="left", wraplength=200, text_color=MUTED,
                     font=ctk.CTkFont(CJK, 11)).grid(
            row=2, column=0, sticky="w", padx=12, pady=(3, 0))
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=(9, 12))
        self._chip(bottom, status, level).pack(side="left")
        ctk.CTkCheckBox(bottom, text="", width=20, checkbox_width=18,
                        checkbox_height=18, corner_radius=5, border_width=1,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        border_color=BORDER).pack(side="right", padx=(6, 0))
        ctk.CTkButton(bottom, text="处理", width=58, height=26, corner_radius=7,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      hover_color=ACCENT_SOFT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 11),
                      command=lambda: self.show("process")).pack(side="right")

    def _chip(self, parent, text, level):
        colors = {"ok": (OK_SOFT, OK), "warn": (WARN_SOFT, WARN),
                  "bad": (BAD_SOFT, BAD), "idle": (SUNKEN_BG, MUTED)}
        bg, fg = colors[level]
        return ctk.CTkLabel(parent, text=text, height=24, corner_radius=8,
                            fg_color=bg, text_color=fg,
                            font=ctk.CTkFont(CJK, 11), padx=10)

    def _stage(self, parent, text, level):
        colors = {"ok": OK, "warn": WARN, "bad": BAD, "acc": ACCENT}
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(9, 0))
        ctk.CTkLabel(row, text="●", text_color=colors[level], width=14,
                     font=ctk.CTkFont(CJK, 12)).pack(side="left")
        ctk.CTkLabel(row, text=text, anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(CJK, 12)).pack(side="left", padx=(6, 0))

    def _kv(self, parent, key, value):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(9, 0))
        ctk.CTkLabel(row, text=key, anchor="w", width=74, text_color=MUTED,
                     font=ctk.CTkFont(CJK, 12)).pack(side="left")
        ctk.CTkLabel(row, text=value, anchor="w", justify="left", wraplength=205,
                     text_color=TEXT, font=ctk.CTkFont(CJK, 12)).pack(
            side="left", padx=(8, 0))

    def _switch(self, parent, text, value):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        ctk.CTkSwitch(row, text=text, variable=tk.BooleanVar(value=value),
                      progress_color=ACCENT, text_color=TEXT,
                      font=ctk.CTkFont(CJK, 12)).pack(side="left")

    def _mode_from_label(self, label):
        self.set_mode({"跟随系统": "system", "浅色": "light", "深色": "dark"}[label])


if __name__ == "__main__":
    import sys

    ctk.set_widget_scaling(1.0)
    page = sys.argv[1] if len(sys.argv) > 1 else "process"
    mode = sys.argv[2] if len(sys.argv) > 2 else "system"
    Shell(page=page, mode=mode).mainloop()
