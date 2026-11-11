# 交接文档 · HANDOFF

面向**接手本项目的人或 AI**。用户向文档见 `README.md`；本文讲的是内部结构、坑和纪律。

## 1.3.0 正式版

- 版本渠道为 `stable`。正式界面配置位于 `ui_state.v3.json`，首次从旧正式版及测试版配置原子合并。相同路径优先采用测试版有效字段，原文件保留。
- 游戏库目录可用性独立于引擎能力。普通启动继续使用手选的目录内 exe。实时汉化与副本试用均要求字体和翻译两项预检通过。
- `TranslationHost` 的会话协议和缓存策略沿用。连接测试使用固定示例和独立操作标识。诊断只显示固定分类，启动拒绝会释放准备状态。
- 桥接增加本机已审核的 8.3.6、8.4.1、8.5.0、8.5.2 构建，并审核可读源码的静态外观菜单。引擎指纹、菜单动作及运行时来源校验仍是启用条件。
- 正式构建从 `tools/build_exe.py` 校验依赖并生成许可资料。发布附件包括单文件 GUI、CLI、构建清单、匿名验收报告和 SHA256。

## 1.3.0 本地测试版交接（2026-10-20）

- 1.2 正式版基线先冻结，再在 `local-test` 渠道开发 1.3；最终产物和源码验证记录分别保存，不能把 1.3 功能写进 1.2 正式版范围。
- 新增可选 `translation` 连接补丁，默认仍只有 `fontfix`。补丁不能包含译文、AI Key 或外网凭据；实时会话由 GUI 管理，普通双击游戏保持原文。
- 翻译只在当前对白或标准 ADV 选项实际执行时请求，预测零请求。默认 `auto` → `zh-CN`、2 秒等待，可调 0–30 秒；菜单共用截止时间，迟到结果仅缓存。保留标签、占位符及选项行为，失败显示原因并原文回退。
- 免费 Google 无 Key 通道属于试验端点，失败不能自动切换收费 AI。AI 由用户自填接口、模型与 Key；Key 默认不记忆，主动记忆才用 Windows DPAPI。缓存按游戏、文本、语言、提供商和模型配置隔离。
- 首批桥接范围是已审核 Ren'Py 8.3 / 8.4 对白和标准 ADV 选项；NVL、自定义菜单和未验证版本保持原文。与外部 Luna 内嵌互斥。停止会话或关闭工具不能结束正常游戏，模拟副本则沿用原清理流程。
- 帮助检索是 `help_content.search(query)` 纯函数，不读游戏、不联网。对 NFKC + casefold 后的空白关键词做 AND 匹配，每主题最多一条；字段为 `topic_id/title/section_index/heading/snippet`，无章节定位时索引为 `None`。空查询按主题顺序返回概览，标题和章节优先，得分相同时保持原顺序。
- 帮助新增 `translation` 与 `library` 主题，功能主题仍必须包含“它做什么 / 适用条件 / 风险与验证 / 撤销”。检索回归用合成主题验证排序、跨节多词、正文定位、摘要长度与返回值独立性。
- 游戏库首次启动必须手选目录内 exe，即使只有一个；保存相对路径，支持子目录，失效重选，取消不启动。正常启动参数列表调用，工作目录为 exe 所在目录；文件夹操作依赖对应条目，不依赖处理页当前选择。
- 模拟步骤、结果、确认、结束及重试清理全部在运行日志，切页或清空文本不能清除会话。GUI 预检与后台事件继续携带游戏 / 会话身份，忽略过期事件。
- 两版界面配置隔离，测试版首次只读导入书签和外观；安装账本共用并增加最低可写工具版本保护。1.2 正式版遇到 1.3 账本只能提示使用新版处理，不能部分撤销未知功能。
- 此处不预填完整测试数、真实引擎及 exe 结果；交付时依据实际验证报告补全。AI 本地协议验证不等于实际付费服务验证，冻结源码测试不等于冻结 exe 测试。

## 1.2.0 正式版稳定化（2026-10-20）

- 发布范围锁定为现有四项功能稳定化；完整适配器契约、跨进程崩溃恢复和字体子集化延期，不能列为本版成果。
- 版本身份由 `branding.APP_VERSION / APP_CHANNEL / CHANNEL_LABEL` 统一提供；该正式版为 `1.2.0 / stable / 正式版`。CLI、GUI、Windows 资源与构建清单必须一致；测试渠道使用 `local-test` 和 Windows prerelease 标志。
- 撤销修复要求按功能依赖成组检查：保留被修改补丁时也保留其字体；文件、隔离备份及安装账本提交失败须回滚。此修复不是完整 journal / 进程锁实现。
- 界面修复覆盖游戏库切页、离线重命名、读取异常和模拟支持矩阵、异常清理、重复确认。
- 默认产物目录是 `release/<version>/<channel>/`，单文件位于 `onefile/`；显式输出路径仍受支持，旧测试产物保持原样。
- provenance schema 2 记录 `channel`；开始时必须存在干净的 Git HEAD，结束时再次比较身份和输入。输入包含嵌套 Python、测试、JS/JSON、资源；不扫描构建输出、虚拟环境和用户配置。
- 下一步 1.3.0 仅走本地测试渠道：实时汉化、帮助检索、库启动 / 打开文件夹、模拟面板迁至日志。测试版界面配置独立，安装账本通过最低可写版本保护与稳定版共存。
- 本节不预填测试数、构建或真实引擎结果；最终验收以本次实际报告和构建清单为准。源码测试不能替代冻结 exe 验证。

## 1.2.0 本地测试版（2026-10-19）

- 版本：`branding.APP_VERSION = "1.2.0"`；本地测试构建，不推送、不打 tag。
- 界面：全宽响应式布局（最大 1440 逻辑像素，宽屏功能卡两列），900×620 保持单列和常驻底栏。
- 帮助：新增 `help_content.py` 和第 6 页“帮助”；每个功能有“说明”模态，覆盖功能/模拟/安装/付费边界/FAQ；`docs/HELP.md` 为导航文档。
- 日志：模拟原始输出统一进入左侧“运行日志”；处理页只保留步骤状态，新增“查看运行日志”，失败自动切页；删除无用的 `var_log`。
- Bug 修复：模拟支持 fail-closed、撤销重新读取安装状态、外来文件确认、初始窗口屏幕钳制、扫描失败状态、游戏库异常、分段控件焦点。
- 安全边界：不实现付费/订阅/DRM 绕过，不伪造购买状态；帮助页明确说明。
- 验证：`python -m pytest -q` → 289 passed、2 skipped、13 subtests passed；截图工具支持 900×620 和 1600×900。
- 仍不包含：适配器契约、事务重构、字体子集化、新引擎。

## 1.1.5 界面测试版（2026-10-18）

- 版本：`branding.APP_VERSION = "1.1.5"`；这是 1.2.0 UI 工作流的测试构建，不改变 1.1.0 的功能范围。
- 新模块：`ui_tokens.py`（颜色/字体/间距/对比度审计）、`ui_text.py`（英文 reason 中文化）、`ui_focus.py`（Tab/焦点环/键盘激活）、`win_platform.py`（DPI awareness + AppUserModelID）。
- 界面：处理页常驻底栏；游戏库与离线条目、日志空状态、安装/撤销/清空确认、模拟清理重试、未知支持 fail-closed。
- 文档：`docs/UI_AUDIT.md`、`docs/UI_SYSTEM.md`；截图工具 `tools/capture_ui_states.py`。
- 验证：`python -m pytest -q` → 257 passed、2 skipped、13 subtests passed；`python tools/check_privacy.py` clean。跳过项仍是可选真实引擎 fixture 与 Windows 符号链接权限。
- 边界：不新增引擎、不改安装事务、不重做 IA/品牌；Tk 屏幕阅读器支持仍有限。

## 1.1.0 当前交接（2026-10-17）

下面的 1.0.0 快照保留作历史记录。当前版本以 `branding.APP_VERSION` 为准，本文历史行号、测试数量和双功能描述不能作为 1.1.0 实现依据。

- **默认与接口**：四个独立功能 `fontfix`、`intro`、`runtime_compat`、`gallery`，默认只有字体开启。GUI / CLI 都走功能目录；保留 `--no-skip-intro`，新增主动加入的 `--skip-intro`，`--features intro` 是有效显式选择。升级不自动删除旧补丁。
- **跨引擎路由**：`engine_adapters.py` 识别 Ren'Py 与 RPG Maker MV / MZ，未知或歧义根目录拒绝安装。MV / MZ 当前只提供字体回退；`rpgmaker.py` 安装字体 / 插件并修改数据型 `plugins.js`，必须备份注册文件。`patch_transaction.py` 管理该引擎的所有权、哈希检查和失败回滚，撤销要恢复原注册而不只是删除插件文件。
- **Ren'Py 扩展**：`cmd_fontfix` 动态接入 addon 的 survey / render / REL；prepare 全通过后才 apply 的事务纪律保留。`renpy_compat.py` 提供 `custom_start_fallback` 与 `luna_say_bridge`：缺少标准入口时恢复已匹配的原入口，对控制 / 格式 tags 改变拒绝套用桥接，不能用宽泛 try/except 隐藏原始异常。
- **画廊实现**：`renpy_gallery.py` 静态检查可见声明、资源和已审查引擎哈希，不执行游戏源码、不读取 pickle。标准 Gallery 只修改指定实例的 button / image conditions，载入存档后重新应用。游戏专用回放适配还锁定内容指纹，检查 label、缩略图和默认变量作用域；局部生成回放屏幕，以 `locked=False` 创建真实 Replay 动作。
- **画廊边界**：sample A 的两张图片占位资源缺失，支持范围是 partial / replay-only；图片画廊不改。sample B 经隔离运行发现标准 Gallery 只有 2 张对象本身无条件的图片，另有 59 条自定义场景；画廊屏幕仍含 `persistent.gallery_unlocked`、`renpy.seen_label` / `seen_image` 门槛。解除标准 Gallery 条件不能解除这些 screen 门槛。原 screen 解锁按钮有 SetField 写入、回放 label 另加后缀，局部代理的动作和完整作用域尚未验证，标为不支持。禁止给这两项写“已全图鉴解锁”。卸载恢复访问规则，但游戏自然取得的已看状态保留，不回滚玩家存档。
- **真实探针**：`tools/probe_gallery.py` 通过 `simulation.prepare/launch` 在完整副本内检查真实 Replay 资格、作用域及 seen 状态；sample A 源码启动探针得到 46 个资格通过、34 个默认变量、seen 状态未变。报告明确 `scene_playback_tested=False`，该结果不能冒充 46 个场景播放验收。
- **入口 / 注入实测**：`tools/verify_game_copies.py` 在 sample A 副本复现缺少 `start`，补丁后查询解析到原有入口对象（`--kind replay` 的 `--label` 由调用者传入，仓库不写真实 label）。sample B 副本使用官方 hook 形态的离线 mock 复现相同内容的对白对象过期错误；桥接后通过实际交互、自动推进、slow 分支和开发模式检查，进程正常退出。它是离线注入形态实验，真实 Luna 客户端联网、长流程和旧存档仍未实测。
- **自定义画廊研究**：`tools/inspect_gallery_copy.py` 让副本自己的引擎加载正常脚本后，记录标准 Gallery 对象、条件类型、screen 条件计数、persistent 字段名及自定义容器计数。报告不含剧情文本、persistent 值；宿主不反序列化外来脚本。sample B 的上述 2 / 59 与锁字段来自此真实探针，并以编译文件字节哈希识别为已调查但未适配机制。
- **模拟验证**：启动前记录诊断基线，只把新增 / 变化错误归入本轮；主菜单与游玩确认独立，进程未出现错误不自动计为成功。普通存档与 multipersistent 均隔离。对已安装样本复制时，必须同时迁移并校验所属账本 / 备份，不能借模拟绕过所有权检查。
- **发布构建**：1.1.0 保留单文件 GUI / CLI 与 onedir 形态，`tools/build_provenance.py` 写 `build_manifest.json`。输入哈希、基准提交、构建状态和产物哈希须一致，构建中源码变化必须判失败。只看 exe 版本资源或 mtime 不够；源码测试与真实 exe 副本测试分别记录。
- **隐私清洗**：公开源码中的真实游戏缩写 / 真实 label 已移除，文档统一 sample A / B / C；`tools/verify_game_copies.py --kind replay` 的原生入口标签改由调用者 `--label` 传入。
- **发布状态（2026-10-17）**：GitHub `v1.1.0` Release 已发布（https://github.com/JXZ666/SLG-Renpy-Toolkit/releases/tag/v1.1.0），tag 指向 `b0c7e43`。资产包含 onefile GUI / CLI、两个 `-win64.zip` onedir 包、`build_manifest.json`、`validation_report.json`、`SHA256SUMS.txt`；`source.dirty=false`，provenance 校验通过。源码闸门 136 passed / 2 skipped / 13 subtests。下一版方向见 `ROADMAP.md`。

### 1.1.0 验证交接要求

1. 运行完整 `python -m pytest tests -q`，同时运行历史脚本套件包装闸门。本次本机复跑记录为 136 passed、2 skipped、13 subtests passed：一项是可选真实引擎测试（本机样本未安装），一项是 Windows 符号链接权限；画廊模块 16 项通过、1 项可选跳过。此前配置已审查样本时记录过 137 passed、1 skipped；后续修改应重新运行并记录实际输出，不能沿用旧快照数字。
2. 画廊关键测试包含内存变异：仅解按钮而保留图片条件、以及回放恢复 `locked=None` 都必须被断言抓到。可设置 `RPYKIT_GALLERY_GAME` 启用已审查本地引擎类测试；它只执行已核验的引擎类定义，真实游戏运行另在副本内完成。
3. `python tools/check_privacy.py` 覆盖未跟踪新文件；公开文档 / 报告只用 sample A / B，不记录个人绝对路径、游戏目录或凭据。
4. 本次发布目标为单文件 + onedir 双形态；构建完成后以 `build_manifest.json` 的 `status=complete`、`source.dirty=false`、输入 / 产物哈希一致为准，并附 `validation_report.json` / `SHA256SUMS.txt`。GUI exe 做隔离启动冒烟，CLI exe 做 `--version` 冒烟。1.1.0 构建前的真实样本记录（sample A / B 入口与离线 Luna、sample A 画廊 46 项资格与撤销、MV / MZ 最小 API 安装 / 重装 / 加载 / 撤销）保留在 `release_notes/1.1.0.md`；本次重建只做隐私标识重命名，未重复完整样本矩阵。完整 NW.js 流程、真实 Luna 客户端全流程和全场景回放尚未完整验证，继续明确保留这些边界。

## 1.0.0 历史快照

- 快照时间：2026-09-28
- 版本：`branding.py:19` `APP_VERSION = "1.0.0"`（唯一版本来源）
- 测试现状：`python -m pytest tests -q` → `58 passed, 13 subtests passed`，覆盖全部 10 个测试文件

---

## 1. 这个项目在做什么

给 Ren'Py / SLG 游戏注入中文字形。游戏自带字体通常只有拉丁字形，中文会渲染成方框或直接崩溃；本工具把 CJK 字形补进去。

两条完全不同的技术路线，由引擎版本决定：

| 路线 | 适用引擎 | 做法 |
|---|---|---|
| `font_name_map` | Ren'Py **7.6+** | 写一个运行时 shim（`config.font_name_map` 指向 FontGroup），把全量 Noto 拷进游戏 |
| `font_replacement_map` | Ren'Py **6 – 7.5** | 把汉字**合并进游戏自己的字体文件**（`font_merge.py`），再写 `config.font_replacement_map` shim |

第二路线是重活：要实例化可变字体、缩放 em、用 `fontTools.merge` 合并，并验证原有字形一个都没丢。

---

## 2. 架构与数据流

```
用户选游戏目录
  │
  ├─ app_window.py ──→ appgui.main()        GUI 入口（22 行转发垫片）
  └─ app_main.py   ──→ cmd_fontfix.run()    CLI 入口（只装 fontfix 依赖，exe 才小）
        │
        ├─ compat.survey(game_dir)          预检。读 renpy/config.py，绝不启动游戏、绝不反序列化脚本
        │     └─ _feature_support()         决定 mechanism（compat.py:289-349）
        │           ├─ 有 font_name_map        → "font_name_map"
        │           ├─ 有 font_replacement_map → "font_replacement_map"
        │           └─ 都没有                  → unsupported，拒绝安装
        │
        ├─ fontscan.recon() / font_inventory()   正则扫 .rpyc / .rpa 负载找字体引用（不 unpickle）
        │
        ├─ cmd_fontfix.run()  (:1497)
        │     ├─ analyse()                     逐字体决策 keep-latin / noto-only / skip
        │     ├─ _legacy_plan()                旧引擎：生成合并任务清单
        │     ├─ install()  (:1350)            ★先 prepare 全部 feature，全成功才 apply
        │     │     ├─ _prepare_font()          (7.6+)  写 zz_localization.rpy + 全量 Noto
        │     │     └─ _prepare_font_legacy()   (6–7.5) 合并字形 + 写 SHIM_REPLACEMENT
        │     └─ revert()   (:1466)            按 manifest 撤销，校验 sha256 后才还原隔离文件
        │
        └─ proj.py                             工作区 + 安装账本
              ├─ work_root  %LOCALAPPDATA%\rpykit
              └─ manifest v2  files[] / quarantined[] / game_dir / game_id
```

GUI 的 `simulation.py` **不是假数据**：它把游戏整树复制到 `%TEMP%/rpykit-simulation-*`，在副本上以 `force=True` 跑 `cmd_fontfix.run()` 并启动副本，用户确认主菜单后才能清理。名字叫 simulation，实际是真实的隔离运行。

### 关键设计约束（改代码时别破坏）

- **`install()` 的先准备后应用 + 快照回滚**（`cmd_fontfix.py:1350-1427`）：任何 feature 的 prepare 失败就一个字节都不写。apply 前把所有目标 + manifest + quarantine 快照到临时目录，异常则整体还原。这是数据安全的核心，不要为了「少写点代码」拆掉。
- **`compat.survey` 绝不执行游戏代码**：只读文件内容做静态判断。
- **`fontscan` 绝不 unpickle**：只对解压后的负载跑正则。
- **`rpa.py` 只用标准库**：不要 import 项目内其他模块。

---

## 3. 模块职责

| 文件 | 职责 | 关键 API |
|---|---|---|
| `app_main.py` | CLI 入口 | `main(argv)` :99 |
| `app_window.py` | GUI 入口垫片 | 转发 `argv[0]` |
| `appgui.py` | CustomTkinter 界面（侧栏 + 5 个堆叠页） | `App` :698, `main()` :1583 |
| `app_state.py` | 界面偏好持久化 | `%LOCALAPPDATA%\rpykit\ui_state.json`，`SCHEMA_VERSION=1` |
| `features.py` | **静态**功能目录（**只有 2 项**：`fontfix`、`intro`） | `CATALOG` :23, `ids()`, `default_selection()` |
| `compat.py` | 引擎预检 + 机制路由 | `survey()` :352 |
| `rpa.py` | RPA-3.0 安全读取 | `load_index()`, `read_entry()`, `extract_entry(archive, entry, dest_root, name)`, `_unsafe_name_reason()`, `_safe_member_path()` |
| `proj.py` | 工作区 + 安装账本 | `work_dir_for()` :73, `load_manifest()` :170 |
| `cmd_fontfix.py` | 安装/卸载/回滚总控（68 KB，最重） | `run()` :1497, `install()` :1350, `revert()` :1466, `_safe_join()` :411 |
| `font_merge.py` | 把 CJK 合并进游戏字体（旧引擎） | `merge_font()` :289, `install_cached()` :461, `fonttools_available()` :105 |
| `fontdb.py` | 标准库 cmap 读取（无需 fontTools） | `codepoints()` :125, `cjk_count()` :148 |
| `fontscan.py` | 在 .rpyc/.rpa 中找字体引用 | `recon()` :240, `font_inventory()` :179 |
| `simulation.py` | 隔离副本安装 + 启动 | `prepare()` :383, `SimulationSession` :195 |

---

## 4. 五个必须知道的坑

### 坑 1 ★ 发布包可能比源码旧 —— 本次真实事故

用户报告 sample C（Ren'Py **7.5.3 / Python 2.7**）**打不上补丁**。真实原因不是 bug 未修，而是**跑的 exe 太旧**：

- `release/1.0.0/SLG-Renpy-Toolkit.exe` 构建于 **22:03**
- 修复代码 `cmd_fontfix.py` 写于 **23:02**、`compat.py` **22:54**、`font_merge.py` **22:59**

旧构建无条件写 7.6+ 专用的 `config.font_name_map`，而 7.5.3 没有这个变量，于是游戏启动即崩：

```
File "game/zz_localization.rpy", line 101, in <module>
  config.font_name_map[_loc_name] = _loc_group_obj
Exception: config.font_name_map is not a known configuration variable.
```

**纪律：改完源码必须重新构建，并且要在产物 exe 上实测，不能只跑源码。** 仓库里 0.9-era 的 `dist/SLG-Renpy-Toolkit.exe`（09:11）和 `build/`（09-19）都是陈旧残留，不要拿来判断当前行为。

### 坑 2 ★ 测试闸门曾只跑一半（已修复，2026-09-28）

**历史情况**：`python -m pytest tests -q` 只收集 **5/10** 个文件，共 42 项。另外 5 个是 `check()` 脚本式（`__main__` 里跑断言），pytest 不识别，从不被执行：

```
未收集过：test_compat  test_fontfix  test_gui  test_install  test_simulation
```

**这正是坑 1 能泄漏到发布包的原因**：`tests/test_compat.py:217-232` **早就写好了**机制路由断言（`route-old` → `font_replacement_map`），但从不被默认闸门执行。*断言存在 ≠ 断言被执行。*

**现在怎么修的**（不要退回去）：

- `tests/test_script_suites.py`：把 5 个脚本式测试的 `main()` 逐个包成 pytest 用例，断言返回值为 `0`。**没有改动那 5 个文件本身**，它们仍可脱离 pytest 直接跑。
- `tests/test_mechanism_routing.py`：端到端路由回归测试。它**真的跑一次安装**再读盘上的 `game/zz_localization.rpy`，断言 7.5.3 的树里只有 `config.font_replacement_map[`、没有 `config.font_name_map[`，7.6+ 反向断言。

**这份回归测试验证过「能失败」**：把 `compat._feature_support` 的 legacy 分支改成返回 `font_name_map`（即复现原事故），`test_mechanism_routing.py` 立刻挂 2 项；改回后全绿。新增测试时请保持这个标准 —— **不能失败的测试等于没有测试。**

```bash
python -m pytest tests -q          # 58 passed，覆盖全部 10 个文件
# 仍然可以单独跑（脚本式）
python tests/test_compat.py && python tests/test_fontfix.py && python tests/test_gui.py
python tests/test_install.py && python tests/test_simulation.py
```

### 坑 3 RPA 索引名路径校验（已加固，2026-09-28）

**曾经的状态**：`rpa.py:_validated_index` 只拒绝空名、超长名、含 `\x00` 的名，**不拒绝 `..`、绝对路径、盘符**；`extract_entry` 也是无包含性检查直接写盘。始终**没有实际漏洞**，因为 `extract_entry` **零调用点**（所有消费者只调 `load_index`/`read_entry` 并把字节留在内存），属于纵深防御。

**加固内容**：

- `rpa.py` 新增 `_unsafe_name_reason(name)`：拒绝绝对路径、盘符（`C:\x` 与驱动器相对 `C:x`）、UNC、以及任何 `..` 路径段。`_validated_index` 在 `\x00` 检查之后调用它。
- `rpa.py` 新增 `_safe_member_path(root, rel)`：私有镜像 `cmd_fontfix._safe_join` 的算法（逐段 `islink` 检查 + `realpath` + `commonpath`），**`rpa.py` 保持零项目依赖，没有 import `cmd_fontfix`**。
- `extract_entry` 签名改为 `extract_entry(archive_path, entry, dest_root, name)`：目的根目录显式传入，条目名单独给（因为 `(off, dlen, start)` 元组不携带名字，而 `load_index` 的返回形状被测试固定住）。包含性检查在任何 `makedirs`/写入**之前**执行。

**两条踩过的坑，改这块时别踩回去**：

1. **绝不能一刀切拒绝 `/`**。真实 RPA 索引里就是嵌套相对路径（`game/script.rpyc`、`images/bg/room.png`），现有测试夹具也是 `game/test.rpy`。只拒绝绝对路径、盘符、UNC 和 `..` 段。有测试专门断言 `game/weird..name.png` 这种「段内合法含点」的名字必须**被接受**。
2. **`os.path.isabs()` 在 Python 3.13 上对 `/etc/passwd` 返回 False**（已在本机 3.13.12 实测）。只靠 `isabs` 会漏掉 POSIX 绝对路径。所以额外显式检查规范化后是否以 `/` 开头 —— 这一条与宿主平台和 Python 版本无关。

### 坑 4 字体子集化的前置条件

模块完整、逻辑正确，但已删除：装补丁时实际是把 **17.77 MB** 的全量 Noto 拷进游戏。

**为什么暂缓接入**：子集化需要调用方给出「要保留哪些码点」，但**安装时这个集合不可知**。`cmd_fontfix._legacy_plan` 里的 `cjk` 字段来自 `fontdb.codepoints()`，那是**游戏自带字体的中文覆盖量**，不是游戏将渲染的文本。真正要渲染的汉字来自之后才打的中文补丁。喂空集/猜测集会**静默丢字形、渲染成豆腐块** —— 比占磁盘严重得多。

要接入就得先能扫描「游戏将来实际会显示的中文文本」，在那之前不要接。

### 坑 5 `prototype/` 是假数据设计稿，不要打包、不要照搬

`prototype/app_prototype.py`（639 行，自包含，只 import tkinter/customtkinter）是下一版界面的形态草稿，docstring 自己写明「全是字面量假数据，形态定稿后本文件删除」。

里面宣传 6 个功能，**4 个不存在**（字体子集化、整目录快照备份、解锁开发者控制台、解锁画廊/跳过已读），还有 **14 个死按钮**和假进度/假游戏列表。

它不在两个 `.spec` 的入口里，**不会进 exe** —— 保持这样。任何转正的功能必须映射到 `features.py` 真实的 2 项，或先在 `features.py` 里真实实现。

---

## 5. 项目纪律（用户的硬要求）

1. **禁止假进度条、假游戏列表、空操作按钮。** 界面上的每个数字都要来自真实调用。
2. **禁止把估算值当成实测结果展示。** 例如不要写「17.7 MB → 486 KB（2.7%）」，除非真的跑完子集化并 `os.path.getsize()`。参考 `cmd_fontfix.py:1221-1230` 的做法：那里**故意不打印**尺寸，并用注释说明原因。
3. **高风险 / 缺规格的功能不做伪实现**（「解锁」类尤其）。宁可功能少，不可假装有。
4. **保留历史改动**：仓库里有 0.9-era 的模拟运行与打包脚本，不要为了整洁删掉。
5. **撤销必须安全**：`revert()` 依赖 manifest 记录的所有权证明（sha256 校验通过才还原），不要绕过。
6. **新增的测试必须能失败**。写完先故意把被测逻辑改坏一次，确认测试挂掉，再改回来。这条是从坑 1/坑 2 来的教训：当时断言写好了、也从没运行过，等于没有。

---

## 6. 构建与验证

### 构建

```bat
python -m venv .venv-build
.venv-build\Scripts\activate
python -m pip install -r requirements-build.txt
python -m pip check
build_exe.bat
```

`build_exe.bat` 会**校验**当前环境与 `requirements-build.txt` 完全一致，不一致直接拒绝构建（不会自动装/升级）。产物默认 `release\<APP_VERSION>\`，GUI 与 CLI 各一个 onedir 文件夹，**必须完整保留 `_internal`**（CustomTkinter 的主题字体靠它收集，只拷 exe 会坏）。

构建脚本用临时工作目录，不覆盖仓库里的 `dist\` / `build\`。

### 验证清单（改完必做）

1. 两份测试都跑（见坑 2），全绿
2. 构建，并确认产物 mtime **晚于所有源文件**
3. **在产物 exe 上**实测，不是源码：
   - 用 simulation 模式对 sample C 的副本安装
   - diff 产出的 `game/zz_localization.rpy` 与已知正确版本
   - 确认 `game/localization/rpykit-*.ttf` 合并字体存在
   - **启动游戏**，确认没有新的 `traceback.txt`、中文正常渲染
4. 确认 `fontTools` 打进了包（spec 里有 `collect_submodules('fontTools')`）—— 旧引擎路线运行时缺它必失败
5. 若游戏目录里有**过期**的 `traceback.txt`，删掉再测，否则会误判

---

## 7. 未完成事项

| 项 | 状态 | 备注 |
|---|---|---|
| py2.7 实测 | **未验证** | `compat.py` 自己写着「本工具从未在 py2 上实测过」。本 game 就是 py2.7，只能靠真机启动关闭这条 |
| RPA 路径校验加固 | **已完成** | 见坑 3，纵深防御 |
| 测试闸门补齐 | **已完成** | 见坑 2，pytest 现覆盖全部 10 个文件 |
| 界面重构 | 待启动 | 用户认为现界面不佳；需先锁定 `prototype` 形态再动手 |
| 字体子集化 | **有意暂缓** | 见坑 4，前置条件是能扫描游戏将渲染的中文文本 |
| OTF/CFF 基字体 | **无覆盖** | `font_merge` 只有 TrueType 路径有测试，OTF 基字体走同一条码路径但未验证 |

---

## 8. 快速上手

```bash
cd rpykit-luna
python -m pytest tests -q                    # 58 项，覆盖全部 10 个测试文件
python app_window.py                         # 起 GUI
python app_main.py "<游戏目录>"               # 起 CLI
python prototype/app_prototype.py            # 看界面设计稿（假数据）
```

需要 `fontTools`（旧引擎路线）与 `customtkinter`（GUI），见 `requirements.txt`。
