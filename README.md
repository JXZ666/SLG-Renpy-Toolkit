# SLG-Renpy神奇妙妙工具 · SLG-Renpy-Toolkit

给游戏安装可选择、可撤销的小补丁。**1.3.0 本地测试版增加实时游戏内汉化、离线帮助检索、游戏库快捷启动与文件夹入口，并将完整模拟操作区移入运行日志。默认仍只安装字体补丁**。其余功能需主动选择，并以目标游戏的预检范围为准。1.2.0 正式版稳定原有四项功能，包含撤销、回滚及界面状态修复。

| 功能 ID | 默认 | 当前范围 |
|---|---|---|
| `fontfix` | 开启 | Ren'Py 中文字体预飞；RPG Maker MV / MZ 的中文字形回退插件 |
| `intro` | 关闭 | Ren'Py 跳过 `splashscreen` 开场 |
| `runtime_compat` | 关闭 | 经检测匹配的 Ren'Py 入口修复 / 文本注入兼容 |
| `gallery` | 关闭 | 已验证的标准 Ren'Py Gallery，或指定机制的回放访问；显示实际覆盖范围 |
| `translation` | 关闭 | 已审核的 Ren'Py 对白与标准 ADV 选项连接补丁；由工具启用实时汉化会话 |

工具不附带游戏文本或预制译文。实时汉化按当前实际执行的文本请求所选服务。**没有通用“全图鉴”支持承诺**；未知引擎、未知画廊和不匹配的游戏版本会拒绝对应功能。

## 快速开始

1. 从 [Releases](../../releases) 下载 GUI `SLG-Renpy-Toolkit.exe`；需要终端操作时下载 `SLG-Renpy-Toolkit-CLI.exe`。单文件版可独立复制；onedir 版需要完整保留同目录的 `_internal`。
2. 打开 GUI，选择游戏根目录，查看每项功能的支持状态、机制、理由和当前安装状态。RPG Maker 根目录可能直接包含 `js/`，也可能包含 `www/js/`。
3. 选择功能，先用“模拟安装并运行”。工具复制游戏，在副本上安装，并隔离普通存档与 multipersistent；原游戏不作为测试写入目标。
4. 启动后检查菜单和实际游玩。**主菜单确认与游玩确认分开**；正常退出、没有新日志、或静态检查通过都不能自动证明游玩成功。新 `traceback.txt` / `errors.txt` 和运行异常会使对应验证失败。
5. 确认所需场景后，再对原游戏安装。需要撤销时使用“撤销还原”，它按安装账本恢复工具改动，不依赖当前勾选状态。

可以把游戏文件夹拖到 GUI exe 图标上预选目录；拖到 CLI exe 则按默认功能处理。

## 帮助与日志

- 左侧“帮助”页提供功能、游戏库、模拟、安装/撤销与常见问题的离线说明。检索匹配标题、摘要、章节和正文，多个空白分隔的词同时匹配，支持中文和全角英文；点击结果定位章节，`Ctrl+F` 聚焦检索。
- 完整模拟操作区移到“运行日志”，包含步骤、结果、确认、结束及重试清理；处理页保留跳转入口。切页或清空日志文本不会丢失会话。
- 本工具不解锁付费、订阅或 DRM 内容，也不伪造购买状态；检测到这类门禁时会明确说明不支持。详见帮助页的“付费/订阅内容”。

## 实时汉化与游戏库

1.3 连接补丁只对已审核的 Ren'Py 8.3 / 8.4 接口提供试验支持，覆盖对白和标准 ADV 选项；NVL、自定义菜单及未验证版本保留原文。只有当前文本实际执行时才请求，预测阶段不联网，不启动前批量预译。

默认免费 Google 无 Key 试验通道可能变更、限流或失效；失败时显示原因并保留原文，不自动转用收费 AI。也可自填 AI 接口地址、模型和 Key，费用由所选服务商决定。默认不记忆 Key；主动记忆时使用 Windows DPAPI 加密。游戏只连接带随机会话凭据的本机代理，Key 和外网请求留在工具侧。

默认源语言 `auto`、目标语言 `zh-CN`，最多等待 2 秒，可调 0–30 秒（0 秒暂停请求并显示原文）；一组菜单共享预算。超时保留原文，迟到结果只缓存，不改写已显示的句子。保留标签、变量占位符及选项行为。内置汉化与外部 Luna 内嵌互斥，请先在隔离副本试用。

可以向原游戏安装可撤销连接补丁，它不含译文或 Key。普通双击游戏显示原文；从工具“开始汉化”才启用本次会话。停止汉化或关闭工具让原游戏继续运行并回退原文；模拟副本仍需按日志页操作结束与清理。

游戏库每个条目首次启动都需手动选择目录内的 exe，即使只有一个候选。支持子目录，保存相对路径；取消不启动，文件失效后重新选择，也可“更换启动程序”。“开始游戏”的工作目录为 exe 所在目录，关闭工具不结束正常游戏。“打开文件夹”直接打开该条目的本地目录，离线时明确提示。

1.3 测试版与 1.2 正式版使用独立界面配置，首次只读导入书签和外观；两版共用账本与备份，通过最低可写工具版本保护，旧版遇到新版功能会拒绝修改并提示使用新版撤销。

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
| `--features IDS` | 逗号分隔的显式选择，支持上表五个 ID；省略时只选 `fontfix`。`translation` 安装连接补丁，实时会话由 GUI 管理 |
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

构建依赖固定在 `requirements-build.txt`；构建脚本校验版本，不自动升级。产物按 `release/<version>/<channel>/` 分开保存：1.2.0 正式版使用 `stable`，1.3.0 本地测试版使用 `local-test`，单文件 GUI / CLI 位于 `onefile/` 子目录；onedir 版须连同 `_internal` 保留。需要指定形态时使用 `python tools/build_exe.py --mode onefile` 或 `--mode onedir`。

`build_manifest.json` 记录版本、渠道、构建输入哈希、Git 基准、构建状态和产物哈希。正式版使用 `stable`，本地测试版使用 `local-test`；两者均要求已提交且干净的 Git 源码。构建期间输入或 Git 身份变化、exe 缺失或哈希不匹配会使验证失败；显示版本号不能单独证明 exe 来自当前源码。输入覆盖嵌套 Python 包、测试、运行时 JS/JSON 和资源，排除输出、虚拟环境与用户配置。

1.2.0 正式版以现有四项功能稳定化为范围。此前路线图中的完整适配器契约、可跨进程恢复的崩溃事务、字体子集化仍未完成，已延期；它们不因正式版名称而视为已实现。1.3.0 实时汉化使用独立本地测试渠道，不计入 1.2 正式版。

## 验证边界

Windows 为当前验证平台；Linux / macOS 未验证。静态预检不能替代菜单、存档、中文渲染与剧情场景测试。MV / MZ 已有脚本行为和字体回退验证，但完整 NW.js 游戏流程仍需单独验收。真实 Luna 客户端全流程、所有回放场景及其他自定义图鉴机制尚未完整实测。

开发交接、历史事故和验证纪律见 [HANDOFF.md](HANDOFF.md)；变化见 [1.2.0 正式版说明](release_notes/1.2.0.md)及 [1.3.0 本地测试版说明](release_notes/1.3.0-test.md)，功能说明见 [帮助文档](docs/HELP.md)，界面规则见 [UI 审计](docs/UI_AUDIT.md) 与 [UI 系统](docs/UI_SYSTEM.md)。

## English

Version 1.3.0 is a local test release with optional live translation, offline Help search, explicit game launcher selection and local-folder actions. Simulation controls are in the Run Log. Reviewed Ren'Py 8.3 / 8.4 dialogue and standard ADV choices use a shared default two-second deadline; timeouts keep the original text. Free translation never automatically falls back to paid AI. Ordinary launches stay untranslated; live sessions are started through the tool. The stable 1.2.0 release retains the original four patch features with revert and interface fixes. Font fixes remain the only default selection, and MV / MZ currently implement font fallback only.

Simulation installs into a temporary copy with isolated saves. Menu confirmation and gameplay confirmation are separate, and newly observed errors invalidate the test. Runtime qualification is not a promise that every scene or an external translation client has been tested. Changes are recorded for safe revert; ordinary gameplay progress is retained.

## 许可

代码采用 [MIT](LICENSE)。`assets/NotoSansSC-VF.ttf` 采用 SIL Open Font License 1.1，全文见 [OFL.txt](assets/OFL.txt)。本工具不包含游戏内容或翻译文本，请支持正版游戏。
