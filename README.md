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
  shim that keeps each original face for Latin and draws CJK with Noto Sans SC. On Ren'Py
  7.6 and later that shim is a `FontGroup`; on older engines, which have no
  `config.font_name_map`, the Hanzi is merged into the game's own font files at install
  time and routed through `config.font_replacement_map` instead.
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

Windows binaries are attached to [Releases](../../releases). The GUI uses
CustomTkinter; running from source requires `python -m pip install -r requirements.txt`.

## Version 1.0.0 and Windows executables

The release version is `1.0.0`. It ships as single-file executables, which need
no installation or unpacking, and as onedir bundles. An onedir executable must
be kept beside its `_internal` directory, so retain the complete application
folder when copying or distributing it. Download both entry points when you
need both interfaces:

This release adds a five-page CustomTkinter interface, a manually managed game
library, and saved theme/window preferences. “Simulate install and run” works
on an isolated temporary copy; confirming the main menu only records the test
result. Applying patches to the original game is a separate, reversible action.
RPA-3.0 indexes are parsed with bounded, data-only pickle handling; RPA-1.0/2.0
remain unsupported.

- `SLG-Renpy-Toolkit.exe` opens the GUI and does not create a console window.
  Dropping a game folder onto it opens the GUI with that folder selected.
- `SLG-Renpy-Toolkit-CLI.exe` is the console version. It accepts a game folder,
  `--dry-run`, `--revert`, `--force`, feature switches, and `--version`.

Examples:

```powershell
SLG-Renpy-Toolkit-CLI.exe --version
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --dry-run
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --revert
```

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

1. 到 [Releases](../../releases) 下载 `SLG-Renpy-Toolkit.exe`（图形界面）；需要终端操作时另下 `SLG-Renpy-Toolkit-CLI.exe`。这两个是**单文件版**，双击即可，不用解压。若需要 onedir 版本，另下对应的 `.zip`，解压后把 exe 和同目录的 `_internal` 文件夹一起保留。
2. 双击打开窗口 → 「浏览...」选游戏目录。窗口会立刻给出**兼容性预检**，
   分别说明字体补丁和跳过开场是否具备所需 API，以及每项判断的理由；
   每个功能卡片右侧还有一个状态小标签，告诉你它现在是「未安装」「已安装」还是遇到了外来文件。
3. 在「功能」区**勾选你这次想装什么**——两个功能各自独立，不勾就是不动。
4. 先点「**模拟安装并运行**」。工具会把游戏复制到临时目录，在副本上安装所选补丁；
   原游戏目录保持不变。兼容预检、复制、安装、启动和主菜单确认会分别显示状态。
   如果找到多个启动器，先选择要运行的 exe；看到主菜单后点确认，只有这样才显示模拟成功。
   退出码为 0 但未确认主菜单时只会显示「待确认」，不会误报成功。
5. 需要还原时点「**撤销还原**」。它**不看勾选状态**，把本工具装过的所有东西
   （连同 Ren'Py 编译出来的 `.rpyc`）一起删掉，并把安装时隔离掉的原文件放回原处。

日志默认收起，勾上窗口底部的「查看处理日志」才展开；模拟和实际安装的详细输出都在这里。

也可以**把游戏文件夹拖到 `SLG-Renpy-Toolkit.exe` 图标上**，在窗口中预选该游戏；拖到 `SLG-Renpy-Toolkit-CLI.exe` 则按命令行默认功能直接处理。

### 方式二：从源码运行

需要 Python 3.9 或更高（本项目的当前 Windows 构建环境为 3.13.12；Ren'Py 8.x 自带的是 3.9）。
GUI 依赖 CustomTkinter。安装运行依赖后再启动：

```bash
git clone https://github.com/JXZ666/SLG-Renpy-Toolkit.git
cd SLG-Renpy-Toolkit
python -m pip install -r requirements.txt  # 安装 GUI 运行依赖
python app_window.py                  # 打开窗口
python app_window.py "D:\Games\SomeGame"  # 打开窗口并选中游戏
python app_main.py --version          # 显示 CLI 版本
python app_main.py "D:\Games\SomeGame" --dry-run  # 命令行预览
```

### 命令行参数

| 参数 | 说明 |
|---|---|
| `<game_dir>` | 游戏根目录，即包含 `game/` 和 `renpy/` 的那一层。CLI 省略时显示帮助 |
| `--dry-run` | 只打印静态决策，不写文件，也不启动游戏；需要验证启动时请用 GUI 的「模拟安装并运行」 |
| `--revert` | 撤销：删掉装进去的所有文件，并放回被隔离的原文件 |
| `--features IDS` | 逗号分隔，勾选要装的功能。可选 `fontfix`、`intro`。默认两个都装 |
| `--no-features IDS` | 逗号分隔，明确排除某些功能。`--features` 与 `--no-features` 同时给出时后者胜 |
| `--force` | 覆盖一个不是本工具装的文件 |
| `--no-skip-intro` | `--no-features intro` 的旧写法，仍然有效 |

## 兼容性预检

选中游戏目录后（命令行则是任何动作开始前），工具会先检查发行版信息，并**分别判断每个功能需要的引擎 API**：

- `fontfix` 按引擎提供的 API 选路线，两条路只要有一条走得通就算支持：
  - `config.font_name_map` + `FontGroup.add(font, start, end)` 都存在时，走运行时别名（Ren'Py 7.6 及以后）；
  - 只有 `config.font_replacement_map` 时，走合并字体路线（Ren'Py 7.5 及更早）。这条路要把汉字合并进游戏自己的字体文件，需要 `fontTools`；没装时该功能标为不支持，理由里会给出 `python -m pip install fonttools`。
  - 两条都没有时，字体功能标为不支持并阻止安装，理由里会同时点名两条路线。
- `intro` 单独检查 `config.label_overrides`。字体功能不支持，不代表跳过开场也不支持；反过来也一样。
- 每个功能都有独立的支持状态和理由。`.rpa` 中脚本不可读、架构或 Python 运行时等其他情况也会单独提示。

Ren'Py **7.5.3 走的是合并字体路线**：它没有 `config.font_name_map`，装 FontGroup 垫片会让游戏启动时报错，所以改用 `config.font_replacement_map`，把汉字合并进游戏自己的字体文件。合并后的文件保留游戏原有的全部拉丁字形，等宽问题只影响新增的汉字。Python 2.7 不是判断依据；必须看目标发行版实际提供的 API。

兼容扫描不启动 Ren'Py，也不执行补丁。它只能确认扫描到的文件/API 线索，**不能替代引擎启动验证**，更不能保证菜单、存档或字体渲染在游戏中正常。`config.label_overrides` 存在只说明跳过开场补丁具备所需 API；游戏还需实际定义 `splashscreen` 才会有可见效果。

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
「装什么、撤什么、怎么判断已装」，窗口一行都不需要改。CLI 和 GUI 的实际安装、撤销
共用 `cmd_fontfix.run()`；GUI 的模拟流程由 `simulation.py` 把同一安装逻辑运行在临时副本中，
并单独管理启动器、运行状态和清理。

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
   都变成「拉丁字符仍用游戏原本的字体、汉字交给思源黑体」。Ren'Py 7.6 及以后用一个
   `FontGroup` 分流；更老的引擎没有 `config.font_name_map`，就改用
   `config.font_replacement_map`，并在安装时把汉字**合并进游戏自己的字体文件**，
   因此每个用到的字体名都会在 `game/localization/` 下多出一份合并结果。

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
本工具不会去动。但**游戏目录里自带的**字体名会被统一映射到思源黑体 + 原字体的组合
（7.6 及以后是 FontGroup，更老是合并字体）。如果你发现游戏里的表情符号显示异常，
欢迎开 issue。

**Q：支持哪些版本的 Ren'Py？**

不能只按 Ren'Py 主版本或 Python 版本承诺支持。预检会对 `fontfix` 和 `intro` 分别检查必需 API，并在界面或命令行报告每个功能的支持状态与原因；缺少对应 API 的功能会被拦截。`fontfix` 有两条路：Ren'Py 7.6 及以后用 `config.font_name_map` + `FontGroup`，7.5 及更早用 `config.font_replacement_map` + 合并字体（需要 `fontTools`）；两条都不具备才会被判定不支持。`intro` 独立按 `config.label_overrides` 判断。预检不启动游戏，API 检查通过也不等于游戏已完成运行验证。

**Q：游戏打包在 `.rpa` 里，需要我先解包吗？**

不需要。`.rpa` 压缩包目前支持 **RPA-3.0** 格式（现代 Ren'Py 游戏的默认格式）。
如果脚本是散在 `game/` 目录里的 `.rpyc`，则不受此限制。

**Q：装错了怎么退回去？**

点「撤销还原」，或跑 `SLG-Renpy-Toolkit <游戏目录> --revert`。

## 已知限制

- **主要在 Windows 上验证**。安装、预检与归档逻辑主要使用 Python 标准库；Linux / macOS
  未做测试，README 不宣称支持。
- 窗口界面依赖 tkinter 和 CustomTkinter。运行源码前请安装 `requirements.txt` 中的固定版本。
- 兼容预检不运行目标引擎或补丁。静态 API 检查可阻止已知不兼容功能，但不能代替在游戏副本中启动并检查菜单、字体和存档。
- 撤销依赖 `install_manifest.json`。工作目录固定在 `%LOCALAPPDATA%\rpykit`，
  你可以用环境变量 `RPYKIT_WORK` 改到别处。**别把它删了**，否则就没法自动撤销，
  但那时候手动删那几个文件同样有效。
- **跳过开场只在游戏定义了 `splashscreen` 时才有肉眼可见的效果**。没有的话装了也
  无害，只是什么都不会变。
- 字体功能对**全部脚本都打包在 `.rpa` 里**的游戏无法确认字体清单，只能照
  `analyse` 能读到的东西办。预检会为此报「有风险」。

## 从源码构建 exe

需要 Windows + Python 3.9 或更高版本。构建依赖单独固定在 `requirements-build.txt`，不要装进只用于运行源码的环境：

```bat
python -m venv .venv-build
.venv-build\Scripts\activate
python -m pip install -r requirements-build.txt
python -m pip check
build_exe.bat
```

构建清单固定 CustomTkinter **6.0.0**、PyInstaller **6.22.3** 及构建依赖，版本取自 2026-09-28 本机 Windows / Python 3.13.12 构建环境的已安装包元数据。`build_exe.bat` 会校验当前环境与清单一致，不会自行安装或升级依赖。CustomTkinter 的主题和字体资源经 `collect_data_files` 收集，两种打包方式都会带上；重生成图标才需要 Pillow：`python -m pip install Pillow`。

构建产物默认放在 `release\1.0.0\`。`build_exe.bat` 一次构建两种形态：
GUI 的 onedir 在 `SLG-Renpy-Toolkit\` 文件夹内，CLI 在 `SLG-Renpy-Toolkit-CLI\` 文件夹内，
这两个文件夹须完整保留 `_internal` 运行时文件；单文件版在 `onefile\` 子目录下
（`onefile\SLG-Renpy-Toolkit.exe`、`onefile\SLG-Renpy-Toolkit-CLI.exe`），自带解压运行时，
可以单独复制。所有 exe 都带 Windows 版本资源 `1.0.0`。只想构建其中一种形态时用
`python tools\build_exe.py --mode onedir`（或 `--mode onefile`）。也可运行
`build_exe.bat D:\temp\rpykit-build` 指定另一个输出目录。构建脚本使用临时
工作目录，不覆盖仓库中的 `dist\` 或 `build\`。想要桌面快捷方式，运行
`make_shortcut.ps1` 并选择 GUI 可执行文件。

## 运行测试

```bash
python tests/test_fontfix.py   # 垫片逻辑（不需要真的启动 Ren'Py）
python tests/test_install.py   # 冻结成 exe 后才会暴露的两个问题
python tests/test_gui.py       # 窗口布局与主题切换（需要 tkinter）
python tests/test_compat.py    # 兼容性预检的判定规则（合成目录树）
python tests/test_simulation.py # 临时副本、清理、启动状态和存档隔离
python -m pytest tests/test_release.py tests/test_app_state.py tests/test_rpa.py
```

pytest 命令覆盖发布身份、GUI 状态存取与 RPA 安全解析；没有安装可选 `fontTools` 时，字体生成用例会跳过。其余测试使用合成目录、模拟会话或静态入口检查，不启动真实游戏。`tests/test_compat.py` 的默认用例全是自包含的合成目录树
（构造出 py2、纯打包、归档不可读、根目录同名字体冲突等情形，断言判定结果）；
再加 `--real` 才会去扫本机真实游戏目录，只断言「不抛异常」。目录可用环境变量
`RPYKIT_GAMES_DIR` 指定。

## 兼容性验证记录

下表保留了早期版本对 `<本地测试游戏目录>` 中 9 个游戏的文件层面记录。它们是在按功能增加 API 门禁之前完成的，旧版「可装 / 有风险」不能当作当前某项功能的支持承诺。当前是否允许安装，应以新版预检中 `fontfix` 与 `intro` 各自的 API 状态和理由为准。

这些记录验证的是扫描、静态干跑、安装和撤销，不等同于引擎启动验证。此前这些样本都没有成功启动到主菜单；Game-J 曾实际尝试启动，旧字体补丁因缺少 `config.font_name_map` 报错，那次的报错正是「7.6 以前没有运行时别名」这条结论的来源，也是后来加合并字体路线的起因。新模拟流程会使用临时副本。

| 游戏 | Ren'Py | Python | 脚本 | 旧版预检 | 已做的文件检查 | 启动状态 |
|---|---|---|---|---|---|---|
| Game-A 0.6.0 | 8.4.2 | 3.12 | 5 rpa + 1 散 | 可装 | 装 + 撤 | 未验证 |
| Game-B 0.06.06b | 8.3.0 | 3.9 | 2 rpa + 50 散 `.rpyc` | 可装 | 装 + 撤 | 未验证 |
| Game-C 0.6.23 | 8.2.3 | 3.9 | 5 rpa + 9 散 | 可装 | 装 + 撤 | 未验证 |
| Game-D 0.69 | 8.3.6 | 3.9 | 1 rpa + 15 散 | 可装 | 装 + 撤 | 未验证 |
| Game-E 0.12 | 8.3.0 | 3.9 | 1 rpa + 13 散 | 可装 | 装 + 撤 | 未验证 |
| Game-F 0.8 | 8.3.2 | 3.9 | 26 散 | 可装 | 装 + 撤 | 未验证 |
| Game-G 2.0.0 | 8.2.0 | 3.9 | 9 rpa，**全打包** | 有风险 | 仅干跑 | 未验证 |
| Game-H 0.9 | 8.5.0 | 3.12 | 1 rpa，**全打包** | 有风险 | 仅干跑 | 未验证 |
| Game-I 0.6.6.0 | **7.4.11** | **2.7** | 11 rpa，**全打包** | 有风险 | 仅干跑 | 未验证 |
| Game-J 1.01 | **7.5.3** | **2.7** | 2 rpa + 18 散 | 旧版未拦截 fontfix | 装 + 撤 + 重装 | 未验证 |

六个「可装」的游戏都做了真装 + 撤销，撤销后与动手前的指纹**逐字节相同**，
`game/` 目录下的文件名列表也一个不差。三个「有风险」的只跑了 `--dry-run`，
确认决策表生成正常、且**一个字节都没写**。这些都只是旧版本的文件操作记录，
不能据此声称功能 API 已逐款确认，更没有任何一款成功启动到主菜单。

### 逐条说明

- **Game-A 0.6.0** — 动它之前它就是装过的，且 `game/` 下另有一个
  **游戏作者自己写的** `zzz_skip_splash.rpy`（同名话题的民间补丁）。工具没有
  `--force` 时会刻意把它留在原地（本工具的 `init 999` 照样排在它前面生效），
  加 `--force` 才会隔离它并在撤销时放回。两种路径都实测过，撤销后 `game/`
  顶层仍是原来的 18 项。它游戏源码是打包的，`game/` 下那几个 `.rpy` 是本工具的。
- **Game-B 0.06.06b** — 它读不到 `game/script_version.txt`，
  版本是从 `renpy/vc_version.py` 认出来的（作品名）。
  50 个散装 `.rpyc`，字体扫描走的是散装路径而不是归档路径。
- **Game-C 0.6.23** — 它自己定义 `splashscreen`（在 `script.rpy` 里），
  跳过开场有实际效果。另有一个容易误判的点：它 `game/` 根目录下有一个
  `NotoSansSC-VF.ttf`，与随包字体**字节完全相同**，所以不算冲突。
  该文件不是本工具写的，`--revert` 也就**不会**删它——这是已知的清理缺口，
  属于本工具之前的历史遗留，留着不影响游戏。
- **Game-D 0.69 / Game-E 0.12** — 都自带 `splashscreen`，
  跳过开场有实际效果。Game-E 那次的 `zz_localization.rpy` 是**本工具上一次装的**
  （文件头有本工具的标记），所以直接原地重写、撤销时删掉，不算外来文件。
  真正会走「外来文件」分支的是 Game-A 那个 `zzz_skip_splash.rpy`：
  内容是作者手写的，工具认得出不是自己的，因此不加 `--force` 就绝不动它。
- **Game-F 0.8** — 没有 `splashscreen`（提示级，非警告，跳过开场装了也不会变）。
  它 `game/font/` 下有个 `PT_Serif` 子目录，**没有**被当成目标误伤。
- **Game-G 2.0.0** — 9 个归档全部打包，且脚本齐全而散装脚本为 0。
  工具看不到它引用了哪些字体，因此只干跑。
- **Game-H 0.9** — Ren'Py 8.5.0 + Python 3.12，是目前见过最新的组合。
  4 个自带字体（`DejaVuSans` 系列保留拉丁，`TwemojiCOLRv0` 是引擎的特性字体）。
- **Game-I 0.6.6.0** — 唯一的 **Ren'Py 7.4.11 + Python 2.7**，
  且 lib 里 **32 位与 64 位架构同时存在**，11 个 rpa 全打包。
  生成的垫片脚本刻意写成 **Python 2 语法安全**（无 f-string、无 dict view、
  无 `super()`）。旧版只对它干跑，未留存按功能确认运行时 API 的记录；
  因此不能由 Ren'Py 7 主版本或 Python 2 语法兼容推断它的功能支持，必须用当前预检分别判断，
  且游戏启动状态仍是**未验证**。
- **Game-J 1.01** — 唯一的 **Ren'Py 7.5.3**，也是合并字体路线的实测对象。
  它 5 个自带字体里有 2 个要合并（`DejaVuSans` 系列，各自合并后约 11.6 MB）、
  2 个整体换成 Noto，`game/zz_localization.rpy` 最终重定向 6 个字体名。
  实测步骤：`--dry-run` → 真装 → 确认合并结果里拉丁与汉字**都在**
  （逐个开 `cmap` 数过）→ `--revert` → 确认 `game/` 下不留任何 `.rpy`/`.rpyc`/
  `localization/` 残渣 → 再装一次（走缓存，2.7 秒）。
  合并会丢掉两个字体无法调和的部分：`GSUB`/`GPOS` 等排版表（代价是连字与字距），
  以及只有一边有的提示表。汉字字形本身全部来自 `cmap`，不受影响。
  **游戏启动与渲染仍未验证**，需要在游戏里实际看到汉字才能确认这一条。

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
