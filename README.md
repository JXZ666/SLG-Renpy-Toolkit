# SLG-Renpy神奇妙妙工具 · SLG-Renpy-Toolkit

> 原名 `rpykit-luna`（露娜汉化预飞）。因为已经不止「露娜 + 字体」这一件事，改名了。

往 Ren'Py 游戏目录里装几个**可自由勾选、互不依赖**的小补丁。

目前有两个功能，地位平等，勾谁装谁：

| 功能 | 做什么 |
|---|---|
| **汉化预飞（字体）** | 给游戏补上它自己字体缺失的中文字形，解决露娜注入中文时的豆腐块 |
| **跳过开场 logo** | 让游戏跳过 `splashscreen`，开局直接进主菜单 |

## English

`SLG-Renpy-Toolkit` installs small, independently selectable patches into a Ren'Py game
folder. Today there are two, and neither depends on the other:

- **Font pre-flight** — fixes the "tofu boxes" (`□□□`) problem when using
  LunaTranslator. Luna replaces a game's text in memory but changes fonts through the
  Windows system font APIs, which Ren'Py never uses. Ren'Py loads a `.ttf` straight out
  of the game directory and hands it to FreeType, so an English game's fonts contain no
  Hanzi and the injected Chinese cannot be drawn. This feature installs a CJK font plus a
  `FontGroup` shim that keeps each original face for Latin and draws CJK with Noto Sans SC.
- **Skip the opening logo** — points the game's `splashscreen` label at an empty
  implementation, so the game boots straight to the main menu.

Nothing is written into a game's scripts, archives, `tl/` directory or language setting;
every write is recorded and fully reversible.

```
SLG-Renpy-Toolkit <game_folder>                       # install (default features)
SLG-Renpy-Toolkit <game_folder> --dry-run             # preview, write nothing
SLG-Renpy-Toolkit <game_folder> --revert              # undo everything it installed
SLG-Renpy-Toolkit <game_folder> --features intro      # only the opening-logo skip
SLG-Renpy-Toolkit <game_folder> --features fontfix,intro
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

1. 到 [Releases](../../releases) 下载 `SLG-Renpy-Toolkit.exe`。
2. 双击打开窗口 → 「浏览...」选游戏目录。窗口会立刻给出一份**兼容性预检**
   （可装 / 有风险 / 不适用 + 理由），每个功能卡片右侧还有一个状态小标签，
   告诉你它现在是「未安装」「已安装」还是遇到了外来文件。
3. 在「功能」区**勾选你这次想装什么**——两个功能各自独立，不勾就是不动。
4. 先点「**干跑预览**」看每个被勾中的功能打算做什么，确认无误后点「**开始处理**」。
5. 需要还原时点「**撤销还原**」。它**不看勾选状态**，把本工具装过的所有东西
   （连同 Ren'Py 编译出来的 `.rpyc`）一起删掉，并把安装时隔离掉的原文件放回原处。

日志默认收起，勾上窗口底部的「显示日志」才展开——控制台版本的输出原样在里面。

也可以**把游戏文件夹整个拖到 exe 的图标上**，跳过窗口直接按默认功能处理，跑完自动退出。

### 方式二：从源码运行

需要 Python 3.9 或更高（本项目在 3.13 上开发构建；Ren'Py 8.x 自带的是 3.9）。
除 GUI 主题外无第三方依赖：

```bash
git clone https://github.com/JXZ666/SLG-Renpy-Toolkit.git
cd SLG-Renpy-Toolkit
python app_main.py                    # 打开窗口
python app_main.py "D:\Games\SomeGame"  # 直接安装
```

### 命令行参数

| 参数 | 说明 |
|---|---|
| `<game_dir>` | 游戏根目录，即包含 `game/` 和 `renpy/` 的那一层。省略则打开窗口 |
| `--dry-run` | 只打印决策表，不写任何文件。**先跑这个** |
| `--revert` | 撤销：删掉装进去的所有文件，并放回被隔离的原文件 |
| `--features IDS` | 逗号分隔，勾选要装的功能。可选 `fontfix`、`intro`。默认两个都装 |
| `--no-features IDS` | 逗号分隔，明确排除某些功能。`--features` 与 `--no-features` 同时给出时后者胜 |
| `--force` | 覆盖一个不是本工具装的文件 |
| `--no-skip-intro` | `--no-features intro` 的旧写法，仍然有效 |

## 兼容性预检

选中游戏目录后（命令行则是任何动作开始前），工具会先读一遍游戏本体并给出一句话结论：

- **可装** —— 没发现已知障碍。
- **有风险** —— 能装，但有需要你知道的事。比如游戏脚本全部打包在 `.rpa` 里，
  工具看不到它引用了哪些字体；或者检测到这是 Python 2.7 的 Ren'Py 7，
  写入的文件语法上是有效的但从未在真机上验证过。
- **不适用** —— 这不是一个 Ren'Py 发行版（缺 `game/` 或 `renpy/`），**直接拒绝执行**。

预检只看文件的大小与头部，**不启动 Ren'Py、不反序列化脚本**，所以在窗口里是瞬时的。
它读的是 `game/script_version.txt`（主源）、`renpy/vc_version.py`、
`renpy/__init__.py`，外加 `lib/` 与 `game/` 的目录列表。

顺便说一句「没找到 `label splashscreen:`」只是提示，不是警告：跳过开场是靠
`config.label_overrides` 查表生效的，与游戏自己有没有写过这个 label 无关。

## 安全网

这个工具的原则是**只增不改，全程可逆**：

- 不改游戏脚本，不重打包 `.rpa`，不动 `tl/`，不改语言设置。
- 每一处写入都记在 `install_manifest.json` 里。撤销时照单删除，
  并且**只删自己装过的东西**——遇到不是它写的同名文件会直接拒绝，
  除非你明确加 `--force`。跳过开场会先隔离游戏里原有的同名覆盖文件，
  撤销时原样放回。
- 装进去的文件最多四个：
  - `game/localization/NotoSansSC-VF.ttf`（思源黑体，17.7 MB）—— 字体功能
  - `game/zz_localization.rpy`（字体垫片，会生成对应的 `.rpyc`）—— 字体功能
  - `game/zz_rpykit_intro.rpy`（跳过开场，会生成对应的 `.rpyc`）—— 跳过开场功能

想彻底还原，两条路都行：点界面上的「撤销还原」，或者直接删掉上面几个文件
（连同各自的 `.rpyc`），游戏就回到原样。

## 工作原理

窗口里每个功能卡片都是从 `features.py` 的那张表里画出来的，功能自己实现
「装什么、撤什么、怎么判断已装」，窗口一行都不需要改。命令行与窗口走的是同一条
`cmd_fontfix.run()`，所以两者的行为不会分叉。

### 汉化预飞（字体）

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

### 跳过开场 logo

生成 `zz_rpykit_intro.rpy`，用 `init 999` 把 `config.label_overrides["splashscreen"]`
指向一个空实现。`init 999` 的优先级高于普通 `init python:` 块，所以即使游戏自己
（或别的汉化补丁）也覆盖过 `splashscreen`，本工具仍然排在最前面生效。

游戏里若已有同名的 `zz*` 覆盖文件，安装时会先把它挪到隔离区并记录在案，
撤销时原样放回。**没有**加 `--force` 时，工具会把这类外来文件留在原地不动
（因为它本来就排在前面，本工具照样生效），不会悄悄动别人的东西。

### 记录

两个功能写入的每一条都记在 `install_manifest.json` 里，旁边还有一份
`fontfix_report.json`，记录了这次装了什么、以及当时的兼容性预检结论。

`zz_localization.rpy` 与 `zz_rpykit_intro.rpy` 会在启动时被 Ren'Py 自动编译，
所以你会看到它们各自多出一个 `.rpyc` 兄弟文件，这是正常的。

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

Ren'Py 8.x 的 **8.2.0 / 8.2.3 / 8.3.0 / 8.3.2 / 8.3.6 / 8.4.2 / 8.5.0** 都实测过，
见下面「兼容性实测记录」。字体扫描读的是 `.rpyc` 结构，对 7.x 未做测试——
检测到 Ren'Py 7 时预检会给出提示，其中 Python 2.7 的那类报「有风险」。

**Q：游戏打包在 `.rpa` 里，需要我先解包吗？**

不需要。`.rpa` 压缩包目前支持 **RPA-3.0** 格式（现代 Ren'Py 游戏的默认格式）。
如果脚本是散在 `game/` 目录里的 `.rpyc`，则不受此限制。

**Q：装错了怎么退回去？**

点「撤销还原」，或跑 `SLG-Renpy-Toolkit <游戏目录> --revert`。

## 已知限制

- **主要在 Windows 上验证**。核心逻辑是纯标准库、基本可移植，但 Linux / macOS
  未做测试，README 不宣称支持。
- 窗口界面依赖 tkinter（Windows 官方 Python 自带）。
  主题美化 `sv-ttk` 是**可选**的，没装也能正常用（见 `requirements.txt`）。
- 撤销依赖 `install_manifest.json`。工作目录固定在 `%LOCALAPPDATA%\rpykit`，
  你可以用环境变量 `RPYKIT_WORK` 改到别处。**别把它删了**，否则就没法自动撤销，
  但那时候手动删那几个文件同样有效。
- **跳过开场只在游戏定义了 `splashscreen` 时才有肉眼可见的效果**。没有的话装了也
  无害，只是什么都不会变。
- 字体功能对**全部脚本都打包在 `.rpa` 里**的游戏无法确认字体清单，只能照
  `analyse` 能读到的东西办。预检会为此报「有风险」。

## 从源码构建 exe

需要 Windows + Python，脚本会自己装 PyInstaller：

```bat
build_exe.bat
```

产物在 `dist\SLG-Renpy-Toolkit.exe`（约 23 MB，其中 17.7 MB 是内嵌的思源黑体），
单文件、免 Python 环境。想要桌面快捷方式，运行 `make_shortcut.ps1`。

## 运行测试

```bash
python tests/test_fontfix.py   # 垫片逻辑（不需要真的启动 Ren'Py）
python tests/test_install.py   # 冻结成 exe 后才会暴露的两个问题
python tests/test_gui.py       # 窗口布局与主题切换（需要 tkinter）
python tests/test_compat.py    # 兼容性预检的判定规则（合成目录树）
```

前三个是自包含的。`tests/test_compat.py` 的默认用例也全是自包含的合成目录树
（构造出 py2、纯打包、归档不可读、根目录同名字体冲突等情形，断言判定结果）；
再加 `--real` 才会去扫本机真实游戏目录，只断言「不抛异常」。目录可用环境变量
`RPYKIT_GAMES_DIR` 指定。

## 兼容性实测记录

下面这张表是对 `D:\game&novel\黄油\3D SLG游戏` 里全部 9 个游戏跑一遍的结果。
**先把话说在前面：我一局游戏都没有真正启动过。** 下表里「装/撤」两列验证的是
**文件层面**的事——装进去什么、撤销后是否与开始时**逐字节一致**、有没有留下残渣。
至于游戏里是否真的没有豆腐块、是否真的跳过 logo 直达主菜单，**那是需要你打开游戏
用眼睛看的，不是这张表能替你保证的。**

| 游戏 | Ren'Py | Python | 脚本 | 预检 | 本次做了什么 |
|---|---|---|---|---|---|
| Couples-Lustbound-0.6.0 | 8.4.2 | 3.12 | 5 rpa + 1 散 | 可装 | 装 + 撤 |
| Hikari1stInterlude-0.06.06b | 8.3.0 | 3.9 | 2 rpa + 50 散 `.rpyc` | 可装 | 装 + 撤 |
| ParadiseCity-0.6.23 | 8.2.3 | 3.9 | 5 rpa + 9 散 | 可装 | 装 + 撤 |
| Supower-Re0.69 | 8.3.6 | 3.9 | 1 rpa + 15 散 | 可装 | 装 + 撤 |
| RiseOfTheCrimeLordExtendedENG-0.12 | 8.3.0 | 3.9 | 1 rpa + 13 散 | 可装 | 装 + 撤 |
| TAM-Ch.3_v0.8 | 8.3.2 | 3.9 | 26 散 | 可装 | 装 + 撤 |
| Lust Theory Season 2 v2.0.0 | 8.2.0 | 3.9 | 9 rpa，**全打包** | 有风险 | 仅干跑 |
| NewNeighborhood-v0.9 | 8.5.0 | 3.12 | 1 rpa，**全打包** | 有风险 | 仅干跑 |
| Horton_Bay_Stories_Jake-v0.6.6.0 | **7.4.11** | **2.7** | 11 rpa，**全打包** | 有风险 | 仅干跑 |

六个「可装」的游戏都做了真装 + 撤销，撤销后与动手前的指纹**逐字节相同**，
`game/` 目录下的文件名列表也一个不差。三个「有风险」的只跑了 `--dry-run`，
确认决策表生成正常、且**一个字节都没写**。

### 逐条说明

- **Couples-Lustbound-0.6.0** — 动它之前它就是装过的，且 `game/` 下另有一个
  **游戏作者自己写的** `zzz_skip_splash.rpy`（同名话题的民间补丁）。工具没有
  `--force` 时会刻意把它留在原地（本工具的 `init 999` 照样排在它前面生效），
  加 `--force` 才会隔离它并在撤销时放回。两种路径都实测过，撤销后 `game/`
  顶层仍是原来的 18 项。它游戏源码是打包的，`game/` 下那几个 `.rpy` 是本工具的。
- **Hikari1stInterlude-0.06.06b** — 它读不到 `game/script_version.txt`，
  版本是从 `renpy/vc_version.py` 认出来的（作品名 "Second Star to the Right"）。
  50 个散装 `.rpyc`，字体扫描走的是散装路径而不是归档路径。
- **ParadiseCity-0.6.23** — 它自己定义 `splashscreen`（在 `script.rpy` 里），
  跳过开场有实际效果。另有一个容易误判的点：它 `game/` 根目录下有一个
  `NotoSansSC-VF.ttf`，与随包字体**字节完全相同**，所以不算冲突。
  该文件不是本工具写的，`--revert` 也就**不会**删它——这是已知的清理缺口，
  属于本工具之前的历史遗留，留着不影响游戏。
- **Supower-Re0.69 / RiseOfTheCrimeLordExtendedENG-0.12** — 都自带 `splashscreen`，
  跳过开场有实际效果。Rise 那次的 `zz_localization.rpy` 是**本工具上一次装的**
  （文件头有本工具的标记），所以直接原地重写、撤销时删掉，不算外来文件。
  真正会走「外来文件」分支的是 Couples 那个 `zzz_skip_splash.rpy`：
  内容是作者手写的，工具认得出不是自己的，因此不加 `--force` 就绝不动它。
- **TAM-Ch.3_v0.8** — 没有 `splashscreen`（提示级，非警告，跳过开场装了也不会变）。
  它 `game/font/` 下有个 `PT_Serif` 子目录，**没有**被当成目标误伤。
- **Lust Theory Season 2 v2.0.0** — 9 个归档全部打包，且脚本齐全而散装脚本为 0。
  工具看不到它引用了哪些字体，因此只干跑。
- **NewNeighborhood-v0.9** — Ren'Py 8.5.0 + Python 3.12，是目前见过最新的组合。
  4 个自带字体（`DejaVuSans` 系列保留拉丁，`TwemojiCOLRv0` 是引擎的特性字体）。
- **Horton_Bay_Stories_Jake-v0.6.6.0** — 唯一的 **Ren'Py 7.4.11 + Python 2.7**，
  且 lib 里 **32 位与 64 位架构同时存在**，11 个 rpa 全打包。
  生成的垫片脚本刻意写成 **Python 2 语法安全**（无 f-string、无 dict view、
  无 `super()`），且 `FontGroup` / `config.font_name_map` / `config.label_overrides`
  在 Ren'Py 7 中都存在——但**从未在真机上跑过**，这就是它只干跑的原因。
  如果你拿它试了，请开 issue 告诉我结果。

### 验证是怎么做的

1. 只读扫一遍 9 个游戏，记下版本 / Python / 架构 / 打包情况 / 有无 `splashscreen`。
2. 每个游戏：`--dry-run`（断言一个字节都没写）→ 真装 → 断言状态 → `--revert`
   → 与动手前的 sha1 指纹逐条对比，并单独比对 `game/` 下的文件名列表
   （指纹只认识预期的路径，**文件名列表才能抓到多出来的残渣**）。
3. 那三个动手前就装着补丁的游戏，撤销后再按原样装回去——不能因为测试就把
   玩家自己装的补丁拿掉。

工作目录都在 `%LOCALAPPDATA%\rpykit\<游戏目录名>`，测试留下的报告可以自己去看。

## 许可

- 本项目代码：[MIT](LICENSE)
- `assets/NotoSansSC-VF.ttf`：SIL Open Font License 1.1，全文见
  [`assets/OFL.txt`](assets/OFL.txt)。该字体由 Adobe 出品（保留字体名 "Source"），
  原样分发、未做子集化或改名，符合 OFL 要求。

## 免责声明

本工具**不包含任何游戏内容、不含任何翻译文本**，也不修改游戏的剧情数据。
它只在游戏目录里添加一个字体文件与两个小脚本，分别用于让游戏本身能够显示中文、
以及跳过开场 logo。

仅供个人学习与汉化技术交流使用。请支持正版游戏。
