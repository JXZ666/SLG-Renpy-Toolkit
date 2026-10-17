# SLG-Renpy神奇妙妙工具 · SLG-Renpy-Toolkit

给游戏安装可选择、可撤销的小补丁。**1.1.0 默认只安装字体补丁**，跳过开场、运行兼容和画廊 / 回放需主动选择，并以目标游戏的预检范围为准。

| 功能 ID | 默认 | 当前范围 |
|---|---|---|
| `fontfix` | 开启 | Ren'Py 中文字体预飞；RPG Maker MV / MZ 的中文字形回退插件 |
| `intro` | 关闭 | Ren'Py 跳过 `splashscreen` 开场 |
| `runtime_compat` | 关闭 | 经检测匹配的 Ren'Py 入口修复 / 文本注入兼容 |
| `gallery` | 关闭 | 已验证的标准 Ren'Py Gallery，或指定机制的回放访问；显示实际覆盖范围 |

这是字体和兼容工具，不提供翻译文本。**没有通用“全图鉴”支持承诺**；未知引擎、未知画廊和不匹配的游戏版本会拒绝对应功能。

## 快速开始

1. 从 [Releases](../../releases) 下载 GUI `SLG-Renpy-Toolkit.exe`；需要终端操作时下载 `SLG-Renpy-Toolkit-CLI.exe`。单文件版可独立复制；onedir 版需要完整保留同目录的 `_internal`。
2. 打开 GUI，选择游戏根目录，查看每项功能的支持状态、机制、理由和当前安装状态。RPG Maker 根目录可能直接包含 `js/`，也可能包含 `www/js/`。
3. 选择功能，先用“模拟安装并运行”。工具复制游戏，在副本上安装，并隔离普通存档与 multipersistent；原游戏不作为测试写入目标。
4. 启动后检查菜单和实际游玩。**主菜单确认与游玩确认分开**；正常退出、没有新日志、或静态检查通过都不能自动证明游玩成功。新 `traceback.txt` / `errors.txt` 和运行异常会使对应验证失败。
5. 确认所需场景后，再对原游戏安装。需要撤销时使用“撤销还原”，它按安装账本恢复工具改动，不依赖当前勾选状态。

可以把游戏文件夹拖到 GUI exe 图标上预选目录；拖到 CLI exe 则按默认功能处理。

## 命令行

```powershell
SLG-Renpy-Toolkit-CLI.exe --version
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --dry-run
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --features fontfix,runtime_compat
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --features gallery
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --skip-intro
SLG-Renpy-Toolkit-CLI.exe "D:\Games\SomeGame" --revert
```

| 参数 | 说明 |
|---|---|
| `<game_dir>` | 目标引擎的游戏根目录；CLI 省略时显示帮助 |
| `--dry-run` | 静态预览，不写游戏、不启动引擎 |
| `--features IDS` | 逗号分隔的显式选择，支持上表四个 ID；省略时只选 `fontfix` |
| `--no-features IDS` | 从默认或显式列表中排除功能 |
| `--skip-intro` | 主动加入跳过开场；`--features intro` 同样有效 |
| `--no-skip-intro` | 保留的旧参数，排除跳过开场 |
| `--revert` | 按所有权和备份记录撤销工具改动 |
| `--force` | 显式允许处理外来同名文件，原文件仍须进入备份 / 隔离记录 |

旧 CLI 参数保留，**默认选择由字体 + 开场调整为仅字体**。升级不会自动撤销此前已安装的开场补丁，需要时单独执行撤销。

## 支持范围与原理

### 字体

Ren'Py 直接读取游戏字体交给 FreeType；外部翻译器替换文本后，原字体可能没有汉字。本工具保留原游戏拉丁字形，补充 Noto Sans SC 中文字形。它不修改 `tl/` 或语言设置。

- 目标引擎提供 `config.font_name_map` 与所需 FontGroup API 时，使用运行时字体分流。
- 较老发行版提供 `config.font_replacement_map` 时，在安装端合并字形，再通过该映射加载。需要 `fontTools`。
- 根据实际发行版 API 判断，不能仅凭 Python 或 Ren'Py 版本号推断。
- RPG Maker MV / MZ 首版只支持 `fontfix`：注册插件和字体，在保留原字体族的基础上追加中文字形回退。插件加载失败会明确报错；没有 MV / MZ 开场、运行兼容或画廊实现。

RPA-3.0 索引使用有边界的数据解析，拒绝可执行 pickle 操作码、路径穿越和超限输入；RPA-1.0 / 2.0 仍不支持。扫描不会反序列化或执行游戏脚本。

### 运行兼容

`runtime_compat` 针对已匹配的入口初始化和对白注入接口生成独立补丁。它恢复缺失入口的必要初始化，或在引擎对白接口处接纳实际文本参数，**不会吞掉游戏自己的异常**。静态匹配、合成注入实验和真实翻译客户端的完整游玩是不同验证层级；预检支持不代表所有外部翻译器均已实测。

### 画廊 / 回放

- 标准 Gallery 仅在已审查引擎实现、可读声明和资源检查通过时支持，局部解除图片、表达式及前序条件；存档载入后重新应用。
- 游戏专用回放适配按内容指纹匹配，检查 label、缩略图与必要作用域，通过 `Replay(..., locked=False)` 放开真实回放资格。
- 部分样本的图片画廊只有缺失资源的占位声明；此时只能支持其已验证回放，并明确显示 **partial / 回放限定**。编译或归档中的自定义锁逻辑尚未验证时，功能标为不支持。
- 不把全局“图片 / label 已看过”接口改为真，不批量修改 persistent 布尔值，不永久写入解锁存档。移除补丁恢复访问规则；游玩过程中游戏自然记录的已看状态保留。
- 按钮能点击只证明访问资格，不能证明每个回放场景都已完整播放。缺少资源或变量的场景仍需实际测试；当前不承诺全场景回放或全图鉴。

## 安装与撤销

Ren'Py 功能主要添加独立 `.rpy` 和字体，不替换剧情脚本；RPG Maker 字体功能会修改 `js/plugins.js` 的插件注册，并先保存原件。撤销按 `install_manifest.json` 检查所有权、内容哈希和备份，再恢复原注册表及工具文件。

所有功能先准备、全部通过后才应用；失败时回滚本次改动。遇到别人修改过的文件或不匹配的备份会拒绝覆盖 / 撤销，避免丢失第三方补丁。**不要手动删除工作区账本后再期待自动还原**。

工作区位于 `%LOCALAPPDATA%\rpykit`，可通过 `RPYKIT_WORK` 更改。语言、存档和游戏自然产生的进度不属于补丁撤销范围。

## 源码、测试与构建

```powershell
git clone https://github.com/JXZ666/SLG-Renpy-Toolkit.git
cd SLG-Renpy-Toolkit
python -m pip install -r requirements.txt
python app_window.py
python app_main.py "D:\Games\SomeGame" --dry-run
python -m pytest tests -q
python tools/check_privacy.py
```

源码要求 Python 3.9+，GUI 依赖 tkinter / CustomTkinter。测试涵盖路由、安装 / 撤销事务、运行兼容、画廊资格、模拟异常和发布 provenance；关键回归含内存变异测试，验证错误实现能使测试失败。真实游戏与构建后的 exe 必须另行在副本上验证，不能用源码测试数量代替。

```bat
python -m venv .venv-build
.venv-build\Scripts\activate
python -m pip install -r requirements-build.txt
python -m pip check
build_exe.bat
```

构建依赖固定在 `requirements-build.txt`；构建脚本校验版本，不自动升级。产物位于 `release\1.1.0\`，单文件 GUI / CLI 位于其 `onefile\` 子目录；onedir 版须连同 `_internal` 保留。需要指定形态时使用 `python tools/build_exe.py --mode onefile` 或 `--mode onedir`。

`build_manifest.json` 记录构建输入哈希、Git 基准、构建状态和产物哈希。构建期间输入变化、exe 过旧或哈希不匹配会使验证失败；显示 `1.1.0` 不能单独证明 exe 来自当前源码。

## 验证边界

Windows 为当前验证平台；Linux / macOS 未验证。静态预检不能替代菜单、存档、中文渲染与剧情场景测试。MV / MZ 已有脚本行为和字体回退验证，但完整 NW.js 游戏流程仍需单独验收。真实 Luna 客户端全流程、所有回放场景及其他自定义图鉴机制尚未完整实测。

开发交接、历史事故和验证纪律见 [HANDOFF.md](HANDOFF.md)；本版变化见 [1.1.0 发布说明](release_notes/1.1.0.md)。

## English

Version 1.1.0 defaults to font fixes only. Opening-logo skipping, reviewed runtime compatibility and qualified gallery / replay access are optional. Ren'Py and RPG Maker MV / MZ are detected separately; MV / MZ currently implement font fallback only. Unknown gallery mechanisms remain unsupported, and partial adapters report their actual coverage.

Simulation installs into a temporary copy with isolated saves. Menu confirmation and gameplay confirmation are separate, and newly observed errors invalidate the test. Runtime qualification is not a promise that every scene or an external translation client has been tested. Changes are recorded for safe revert; ordinary gameplay progress is retained.

## 许可

代码采用 [MIT](LICENSE)。`assets/NotoSansSC-VF.ttf` 采用 SIL Open Font License 1.1，全文见 [OFL.txt](assets/OFL.txt)。本工具不包含游戏内容或翻译文本，请支持正版游戏。
