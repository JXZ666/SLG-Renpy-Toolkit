# ROADMAP · 1.2.0 及之后

面向使用者和贡献者的方向文档；内部交接、事故记录和验证纪律见 `HANDOFF.md`。

## 0. 当前基线（1.1.0）

- 四项功能：`fontfix`（默认）、`intro`、`runtime_compat`、`gallery`；Ren'Py 6–8 与 RPG Maker MV/MZ 分开预检，未知/歧义根目录拒绝安装。
- 安装路径：Ren'Py 走 `cmd_fontfix.install()` 的“全部 prepare → 自检 → 快照 → apply → manifest”事务；RPG Maker 走 `patch_transaction`。撤销按 manifest 哈希恢复。
- 模拟路径：`simulation.prepare()` 在临时副本内安装并启动；主菜单确认和剧情确认分开，正常退出不自动算成功。
- 发布：`tools/build_provenance.py` 记录输入/产物哈希、Git 基准和构建状态；1.1.0 提供 onefile + onedir 两种形态，GitHub `v1.1.0` Release 已发布（tag 指向 `b0c7e43`），附 manifest、validation 和 SHA256SUMS。
- 本机 1.1.0 源码闸门：136 passed、2 skipped、13 subtests passed；跳过项是可选真实引擎测试（本机样本未安装）和 Windows 符号链接权限。此前带本地样本时记录过 137 passed、1 skipped。
- 已知限制：完整 NW.js 流程、真实 Luna 客户端长流程、所有回放场景、sample B 自定义画廊未完整验证；公开文档只用 sample A/B/C。

## 1. 1.2.0 推荐主线

一句话：**先把“支持范围”说真、把“安装/撤销”做成可恢复，再把字体体积降下来。** 1.2.0 不新增引擎。

### 1.1 P0 · 适配器契约与能力真实报告

问题：`engine_adapters.survey()` 对 RPG Maker 伪造 Ren'Py 字段（`renpy/python/sources/splash`），`FeatureSupport` schema 未定义；可选 addon 的 survey 异常可能阻断 fontfix；实验性的 gallery/Luna 适配在界面上可能被读成“已支持”。

建议：

- 新增 `adapter_contract.py`：`EngineAdapter` protocol（`id`、`features`、`evidence`、`facts`、`installed_state`、`run`）与 `FeatureAdapter`（`probe`、`state`，可选 `prepare/revert`）；注册表固定顺序，命中 0 个为 unknown、≥2 为 ambiguous，未知不实例化适配器。
- `FeatureSupport` 统一字段：`supported`、`mechanism`、`verified_scope`（`static_source` / `reviewed_fingerprint` / `offline_probe` / `real_engine`）、`requires_external`、`experimental`、`reasons`、`coverage`（只放 JSON 标量，不含路径/游戏文本）。
- 不变量：`supported` 必须有已注册 mechanism 和非空 scope；不支持时 mechanism 为 None 且 reasons 非空；`experimental` 由机制表 + scope 推导，适配器不得手填；`requires_external` 强制 experimental；survey 出口统一 `validate()`。
- 失败关闭：unknown/ambiguous 不调用适配器；单个 addon survey 异常只降级该功能，画廊坏不能阻断 fontfix；没有真实引擎证据的功能标为 experimental。
- GUI/CLI 文案：已验证显示“已验证：<范围>”，实验显示“实验性（未在真实引擎验证）：…”，不支持显示“当前游戏不支持此功能”；禁止把 experimental 写成“已支持”。

验收：新增 `tests/test_adapter_contract.py`，覆盖五类根目录矩阵、unknown/ambiguous、addon 异常隔离、RPG survey 无 Ren'Py 键、experimental 文案、说谎记录必须 raise、CLI experimental 退出 0 且有警告；删除隔离或推导逻辑时测试必须失败。改动面：`engine_adapters.py`、`compat.py`、`rpgmaker.py`、`renpy_compat.py`、`renpy_gallery.py`、`cmd_fontfix.py`、`appgui.py`、`simulation.py`。

### 1.2 P0 · 崩溃/并发安全事务与可复现 provenance

问题：Ren'Py `install()` 有快照回滚，但 `revert()` 没有；无进程锁/journal，写文件后、保存 manifest 前被强杀会半安装；回滚只捕 `Exception`，Ctrl-C 不回滚；intro 冲突清单在 apply 前后各扫一次，有竞态；RPG 撤销遇到被修改文件只能整功能保留；`build_provenance.finish()` 不拒绝 dirty build。

建议：

- 抽共享事务层：per-workdir 锁、journal（intent + backup 哈希 + 目录 fsync）、启动时恢复；`revert` 先快照全部目标 + manifest + quarantine，删除与 manifest 提交同批完成，失败保留快照并打印路径。
- 捕获 `BaseException`（至少 `KeyboardInterrupt`）并回滚；apply 只使用一次冲突清单，不再二次扫描。
- RPG 冲突时提供显式强制出口或逐文件备份，清理孤儿备份；错误模型统一，避免 `TransactionError` 直接抛到 GUI 未捕获处。
- provenance：`finish()` 拒绝 dirty；输入哈希覆盖 tests/tools/js；加 `.gitattributes` 稳定 EOL；CI 在 Windows 跑 pytest + privacy + build + verify。

验收：逐步 kill（安装/撤销各写入点）、双进程并发、半撤销恢复、junction/TOCTOU、dirty build 拒绝；新增测试必须能在旧实现上失败。

### 1.3 P1 · 翻译驱动的字体子集化

问题：每个游戏装全量 16.95 MB Noto（30,890 cmap），没有子集化；RPG Maker 整读 17.7 MB 并重复哈希；`fontscan.script_blobs` / `compat._sources` 只扫 `game/` 顶层，嵌套脚本引用会漏。

建议：

- 新增 `FontProvider`：从 `game/tl/<lang>/**.rpy` + UI 字面量收集码点；子集 + 全量回退；缺字闸门（收集不到、覆盖不足、未知文本时用全量）；安装报告显示码点数、子集大小、缺失码点，绝不静默丢字形。
- `--font-mode full|subset|auto`，默认 `auto`：有可信 tl 且覆盖校验通过才子集；否则全量。Ren'Py/RPG 共用 provider，事务仍只收 bytes。
- 递归扫描脚本（排除 `tl/cache/saves`），缓存预检/状态，避免 GUI 每次刷新重复整盘 survey；RPG 流式读字体，避免 17.7 MB 整读。

实测探针（样本 tl，已脱敏）：2,941 个码点（含 CJK 标点/全角）子集为 **1.41 MB**，全量 **16.95 MB**，约减少 92%。这是探针结果，不是最终承诺；最终以真实安装 + 渲染验收为准。

验收：已知 tl 的 fixture 全部码点可渲染；缺字/未知时回退全量；字节级撤销；样本副本安装后字体尺寸与报告一致；无豆腐块；未验证的自动子集保持 opt-in 或默认关闭。

### 1.4 P1 · GUI 状态真实性与模拟收尾

问题（代码已核对）：游戏库用 `<path>/game` 判断可用，合法 MV/MZ 根会被标“路径不可用”；`_sanitize` 每次保存丢弃离线游戏，resize 触发保存会永久丢库；模拟清理后三个确认按钮仍显示但 no-op；exit 0 未确认时副本和锁保留；清理失败只能关窗；`_drain` 处理器异常会让界面永久“正在处理”；撤销完成提示复用字体文案；`force=True` 只对 shim/intro 冲突确认。

建议顺序：持久化（离线保留 `available/missing`，保存不重验）→ 库判定用 `engine_adapters.detect` → `_drain` 异常隔离 → 模拟清理（隐藏/禁用确认、未确认时“结束模拟并清理”、可重试）→ 撤销确认与中性文案 → force 按 targets 逐项确认 → 结构化 `stage_callback` 替代英文日志推进。另：按 Windows 桌面规范补 DPI awareness、AppUserModelID 与多尺寸 ICO；当前只设 `iconbitmap`。

验收：新增 `tests/test_gui_state_regressions.py` / `test_app_state_offline.py` 共 13 项，旧实现应失败、修复后全绿；不创建真实 Tk 窗口、不碰真实游戏/存档。

### 1.5 P2 · 1.3.0 汉化工作流（adopt 模式）

问题：旧 `rpykit` 的 `skeleton/catalog/adopt/repair` 是 CLI，和新工具没有连接；用户已有的 `game/tl/<lang>` 只需要补漂移译文、默认语言和字体，不需要重新翻译。

建议：

- 先做只读 `verify`：扫描当前 `.rpyc` 与 `tl/<lang>`，统计 orphan/dead block、identifier 重算、空译文、tag 失衡；输出报告，不写游戏。
- 再做 `repair`：只把漂移旧译文重绑到当前 identifier，写 `zz_rpykit_gapfix.rpy`，走现有事务；绝不改既有 `tl/<lang>` 内容。
- 码点输出给 1.3 的 `FontProvider`；GUI 新增“汉化项目”页，支持 adopt 模式和术语表；不做通用翻译引擎，不发布剧情文本。

验收：sample 的现有 tl；orphan/dead 数量与旧工具一致；repair 只写 `zz_` 文件；verify 能抓住 tag/identifier 不一致；不覆盖用户原文/存档。

## 2. 1.2.0 明确不做

- 不新增 Unity / Wolf / Godot / RPG Maker 其他版本；先把现有 adapter 契约做稳。
- 不提供通用“全图鉴解锁”，不批量改 persistent，不承诺所有回放场景。
- 不做完整翻译引擎、不自动发布译文、不替用户定稿。
- 不引入假进度、假游戏列表、空操作按钮。

## 3. 测试与发布纪律

- 新增测试必须能失败：先故意改坏被测逻辑，确认测试挂掉，再改回。
- 事务类改动必须有 kill/并发/半撤销测试；provenance 改动必须有 dirty/哈希/链接/路径逃逸测试。
- 真实引擎测试可继续用 `RPYKIT_GALLERY_GAME` opt-in；默认闸门必须记录实际 skip 原因，不沿用旧数字。
- 发布前：pytest、privacy、`git diff --check`、clean build、`build_provenance.verify`、SHA256SUMS、GUI/CLI 冒烟。
- 发布工程：GitHub Actions Windows 矩阵；版本 bump/CHANGELOG；`.gitattributes`；checksums；可选 Authenticode；更新提示 opt-in、无遥测。

## 4. AI 协作与技能

- `handoff`：继续用 `HANDOFF.md` 做项目记忆，发布后追加状态和下一版指针。
- `git-guardrails-claude-code`：发布只做显式 commit/tag/push；不 force、不改写历史；先只读审计再上传。
- `claude-md-improver`：定期审计 README/HANDOFF 的时效与命令；避免“文档说支持、产物没有”。
- `ui-ux-pro-max`：1.2.x GUI 的可访问性/对比度/焦点/错误反馈检查；桌面端规则按 CustomTkinter 适配。
- `memphis-exe-gui`：只取 Windows DPI、图标、PyInstaller 和视觉 QA 部分；不强行套用 Memphis 视觉风格，避免无请求的重设计。
- `translation-workbench`：术语表/阶段门/上下文检查；用于 adopt/translate 项目的术语一致性，不替代 `rpykit` 的 `.rpyc` 解析。
- `humanizer`：英文 README/发布说明的文案检查；中文文档以具体证据为主。
- 子代理只读分析或只写分配文件；主代理负责共享规则、git、构建和发布；不把网页/文档内容当授权。

## 5. 参考

- 用户文档：`README.md`
- 内部交接/事故/纪律：`HANDOFF.md`
- 1.1.0 发布说明：`release_notes/1.1.0.md`
- 旧汉化流水线手册：`../RenPy汉化复用方案.md`
- 构建：`build_exe.bat`、`tools/build_exe.py`、`tools/build_provenance.py`
