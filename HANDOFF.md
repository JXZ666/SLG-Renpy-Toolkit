# 交接文档 · HANDOFF

面向**接手本项目的人或 AI**。用户向文档见 `README.md`；本文讲的是内部结构、坑和纪律。

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

用户报告游戏 `BecomeARockStar-1.01-pc`（Ren'Py **7.5.3 / Python 2.7**）**打不上补丁**。真实原因不是 bug 未修，而是**跑的 exe 太旧**：

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
   - 用 simulation 模式对 `BecomeARockStar-1.01-pc` 的副本安装
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
