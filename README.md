# rpykit-luna · 露娜汉化预飞

给 Ren'Py 游戏补上它自己字体缺失的中文字形。

## English

`rpykit-luna` fixes the "tofu boxes" (`□□□`) problem when using LunaTranslator with
Ren'Py games. LunaTranslator replaces a game's text in memory, but it changes fonts
through the Windows system font APIs — which Ren'Py never uses. Ren'Py loads a `.ttf`
straight out of the game directory and hands it to FreeType, so an English game's fonts
contain no Hanzi and the injected Chinese cannot be drawn.

This tool installs a CJK font into the game plus a small `FontGroup` shim that keeps each
original face for Latin and draws CJK with Noto Sans SC. It does not touch the game's
language, its `tl/` directory, or any archive, and it is fully reversible.

```
rpykit-luna <game_folder>            # install
rpykit-luna <game_folder> --dry-run  # preview, write nothing
rpykit-luna <game_folder> --revert   # undo
```

Windows binaries are attached to [Releases](../../releases). The tool itself is pure
standard library, so running from source needs no `pip install`.

---

## 这是什么问题

用 LunaTranslator 玩 Ren'Py 英文游戏时，文本是替换成功了，汉字却全变成框框（豆腐块）。

原因不在翻译，而在字体：

- LunaTranslator 的「修改游戏字体」功能改的是 **Windows 系统字体 API**
  （`CreateFontIndirectW`）。这套做法对 KiriKiri、RPGMaker、TyranoScript 有效。
- **Ren'Py 不走系统 API**。它用 `renpy.loader.load()` 直接读游戏目录里的 `.ttf` 文件，
  交给 FreeType 渲染。

所以露娜的钩子挂上了、文本也换掉了，字形却不会变——游戏的字体里根本没有汉字，
于是每个汉字都画成一个空框。

**本工具只修这一半。** 装好之后，游戏自己的字体能画汉字了，露娜注入的中文自然就显示正常。

## 快速开始

### 方式一：直接用 exe（推荐，不需要装 Python）

1. 到 [Releases](../../releases) 下载 `rpykit-luna.exe`。
2. 双击打开窗口 → 「浏览...」选游戏目录 → 先点「**干跑预览**」看它打算做什么 →
   确认无误后点「**安装字体**」。
3. 启动游戏，用露娜正常注入中文。

也可以**把游戏文件夹整个拖到 exe 的图标上**，效果等同于点「安装字体」，跑完自动退出。

### 方式二：从源码运行

需要 Python 3.9 或更高（本项目在 3.13 上开发构建；Ren'Py 8.x 自带的是 3.9）。
除 GUI 主题外无第三方依赖：

```bash
git clone https://github.com/<你的用户名>/rpykit-luna.git
cd rpykit-luna
python luna_main.py                    # 打开窗口
python luna_main.py "D:\Games\SomeGame"  # 直接安装
```

### 命令行参数

| 参数 | 说明 |
|---|---|
| `<game_dir>` | 游戏根目录，即包含 `game/` 和 `renpy/` 的那一层。省略则打开窗口 |
| `--dry-run` | 只打印决策表，不写任何文件。**先跑这个** |
| `--revert` | 撤销：删掉装进去的字体、垫片和编译产物 |
| `--force` | 覆盖一个不是本工具装的文件 |

## 安全网

这个工具的原则是**只增不改，全程可逆**：

- 不改游戏脚本，不重打包 `.rpa`，不动 `tl/`，不改语言设置。
- 每一处写入都记在 `install_manifest.json` 里。撤销时照单删除，
  并且**只删自己装过的东西**——遇到不是它写的同名文件会直接拒绝，
  除非你明确加 `--force`。
- 装进去的文件只有两个：
  - `game/localization/NotoSansSC-VF.ttf`（思源黑体，17.7 MB）
  - `game/zz_localization.rpy`（字体垫片，会生成对应的 `.rpyc`）

想彻底还原，两条路都行：点界面上的「撤销还原」，或者直接删掉上面两个文件
（外加 `game/zz_localization.rpyc`），游戏就回到原样。

## 工作原理

1. **扫描字体引用**：直接从 `.rpyc`（Ren'Py 编译后的脚本）里读出所有字体名。
   **不需要先解包游戏**——它也能读 `.rpa` 压缩包里的脚本。
2. **测量中文覆盖**：用纯标准库解析每个字体文件的 `cmap` 表，数它到底有多少汉字。
3. **逐个字体决定策略**：
   - `skip` —— 这个字体已经有足够汉字（≥3000），不用管
   - `keep-latin` —— 保留原字体画拉丁字符，中文交给思源黑体
   - `keep-ascii` —— 同上，但只保留 ASCII 范围
   - `noto-only` —— 整个换成思源黑体
4. **安装**：把思源黑体复制进游戏，并生成 `zz_localization.rpy`，把游戏里每个字体名
   映射到一个 `FontGroup`——拉丁字符仍用游戏原本的字体（视觉风格不变），
   汉字交给思源黑体。
5. **记录**：写入 `install_manifest.json`，为撤销留下凭据。

`zz_localization.rpy` 会在启动时被 Ren'Py 自动编译，所以你会看到它多出一个
`.rpyc` 兄弟文件，这是正常的。

## 常见问题

**Q：装完了，为什么主菜单还是英文？**

因为本工具**不翻译**，它只解决字形问题。翻译是 LunaTranslator 的工作。
本工具负责让游戏「画得出」汉字，露娜负责「给出」中文。两者配合才完整。

**Q：为什么个别符号（比如快进三角 ▸）还是框？**

因为那个字符既不在游戏原字体里，也不在思源黑体里，所以仍然是空框。
本工具只补中文字形，不负责符号表。

另外说明一点：Ren'Py 自带引擎字体（`renpy/common/` 下的 Twemoji、OpenDyslexic 等）
本工具不会去动。但**游戏目录里自带的**字体名会被统一映射到思源黑体 + 原字体的
FontGroup。如果你发现游戏里的表情符号显示异常，欢迎开 issue。

**Q：支持哪些版本的 Ren'Py？**

在 **Ren'Py 8.3.3** 上完整验证过。字体扫描读的是 `.rpyc` 结构，对 7.x 未做测试。

**Q：游戏打包在 `.rpa` 里，需要我先解包吗？**

不需要。`.rpa` 压缩包目前支持 **RPA-3.0** 格式（现代 Ren'Py 游戏的默认格式）。
如果脚本是散在 `game/` 目录里的 `.rpyc`，则不受此限制。

**Q：装错了怎么退回去？**

点「撤销还原」，或跑 `rpykit-luna <游戏目录> --revert`。

## 已知限制

- **主要在 Windows 上验证**。核心逻辑是纯标准库、基本可移植，但 Linux / macOS
  未做测试，README 不宣称支持。
- 窗口界面依赖 tkinter（Windows 官方 Python 自带）。
  主题美化 `sv-ttk` 是**可选**的，没装也能正常用（见 `requirements.txt`）。
- 撤销依赖 `install_manifest.json`。工作目录固定在 `%LOCALAPPDATA%\rpykit`，
  你可以用环境变量 `RPYKIT_WORK` 改到别处。**别把它删了**，否则就没法自动撤销，
  但那时候手动删那两个文件同样有效。

## 从源码构建 exe

需要 Windows + Python，脚本会自己装 PyInstaller：

```bat
build_exe.bat
```

产物在 `dist\rpykit-luna.exe`（约 23 MB，其中 17.7 MB 是内嵌的思源黑体），
单文件、免 Python 环境。想要桌面快捷方式，运行 `make_shortcut.ps1`。

## 运行测试

```bash
python tests/test_fontfix.py   # 垫片逻辑（不需要真的启动 Ren'Py）
python tests/test_luna.py      # 冻结成 exe 后才会暴露的两个问题
python tests/test_lunagui.py   # 窗口布局与主题切换（需要 tkinter）
```

## 许可

- 本项目代码：[MIT](LICENSE)
- `assets/NotoSansSC-VF.ttf`：SIL Open Font License 1.1，全文见
  [`assets/OFL.txt`](assets/OFL.txt)。该字体由 Adobe 出品（保留字体名 "Source"），
  原样分发、未做子集化或改名，符合 OFL 要求。

## 免责声明

本工具**不包含任何游戏内容、不含任何翻译文本**，也不修改游戏的剧情数据。
它只在游戏目录里添加一个字体文件和一个字体映射脚本，用于让游戏本身能够显示中文。

仅供个人学习与汉化技术交流使用。请支持正版游戏。
