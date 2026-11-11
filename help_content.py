"""Offline help topics for the built-in Help page.

This module contains only content and pure search. It imports no GUI toolkit and performs no network
or filesystem access, so the Help page can render it without starting a game
or reading the user's library.
"""

import copy
import re
import unicodedata


TOPICS = {
    "fontfix": {
        "title": "汉化预飞（字体）",
        "summary": "让游戏用到的字体名都能显示中文；只补字形，不翻译文本。",
        "sections": [
            {
                "heading": "它做什么",
                "body": [
                    "Ren'Py 7.6 及以后：写入可撤销的字体分流补丁，把游戏用到的字体名指向 FontGroup。拉丁字形继续使用游戏自己的字体，汉字使用随包的 Noto。",
                    "更老的 Ren'Py：引擎没有 FontGroup 时，安装阶段把汉字合并进游戏自己的字体文件，再通过字体替换映射加载。这条路线需要 fontTools。",
                    "RPG Maker MV 与 MZ：只注册字体回退插件和字体文件，在保留原字体族的前提下追加中文字形。",
                    "不翻译任何文本，不生成译文，也不修改 tl/ 目录里的翻译内容。",
                ],
            },
            {
                "heading": "适用条件",
                "body": [
                    "Ren'Py 6 到 8，且预检能从实际发行版文件里找到已验证的字体接口。走分流还是合并由实际 API 决定，不能只看版本号。",
                    "旧版合并路线要求安装环境里有 fontTools；缺少时会明确说明，不会静默换成另一种写法。",
                    "RPG Maker MV 或 MZ，根目录包含 js/ 或 www/js/，且核心脚本与 plugins.js 可读。",
                    "游戏根目录必须能识别为单一引擎；未知目录或同时命中多个引擎的目录会被拒绝。",
                ],
            },
            {
                "heading": "风险与验证",
                "body": [
                    "字体补丁会新增字体文件和 zz_ 开头的补丁文件，游戏体积会增加；旧版合并路线还会重写游戏字体。",
                    "所有目标先准备、全部通过后才写入；准备失败时本次不写游戏目录，应用阶段异常会整体回滚。",
                    "预检通过只说明接口存在，不代表每个界面都已渲染验证。先在隔离副本确认主菜单、一段剧情、选项和存档界面都能正常显示中文。",
                    "RPG Maker 插件在缺少字体或启动 API 时会明确报错，不会静默忽略。",
                ],
            },
            {
                "heading": "撤销",
                "body": [
                    "使用“撤销还原”，工具按安装账本恢复自己写入的字体和补丁文件，不依赖当前勾选状态。",
                    "被外部修改过的文件或与账本不匹配的备份会被拒绝覆盖，工具会保留可恢复的备份。",
                    "撤销不修改存档、语言设置和游戏自然进度；它只处理本工具改过的文件。",
                ],
            },
        ],
    },
    "intro": {
        "title": "跳过开场 logo",
        "summary": "把 splashscreen 指向空实现，开局直接进主菜单；可能跳过初始化，请先在副本验证。",
        "sections": [
            {
                "heading": "它做什么",
                "body": [
                    "只对 Ren'Py 写入 label_overrides，把 splashscreen 标签指向一个立即返回的空实现。",
                    "不替换剧情脚本；只新增一个 zz_ 开头的补丁文件。游戏自己的开场标签仍然留在原文件里。",
                    "如果游戏目录里已经有别的 zz_ 覆盖文件在改 splashscreen，会先把它连同同名 .rpyc 备份到工作目录的 quarantine/，再安装本工具的版本。",
                    "Ren'Py 在 Python 运行前绘制的 presplash 图片仍会出现；本功能不处理这部分。",
                ],
            },
            {
                "heading": "适用条件",
                "body": [
                    "目标游戏是 Ren'Py，且预检确认存在 label_overrides 接口。",
                    "适合开场 logo 卡住、黑屏或无法返回主菜单的游戏。",
                    "不适用于 RPG Maker MV 或 MZ；这两个引擎没有实现开场跳过。",
                    "如果游戏依赖 splashscreen 里设置的变量或副作用，跳过它可能导致启动报错。",
                ],
            },
            {
                "heading": "风险与验证",
                "body": [
                    "跳过 splashscreen 会跳过它原本执行的初始化。游戏可能在启动时报 NameError 或停在别的画面，这类错误会正常显示，不会被隐藏。",
                    "先在隔离副本运行，确认能进入主菜单，再开始新游戏、读一次档，检查没有缺少初始化变量。",
                    "如果游戏自己的开场有必须执行的逻辑，请取消本功能，不要把它当成通用加速补丁。",
                    "安装前会检查同名覆盖文件；发现冲突时会要求确认并备份，不会直接覆盖。",
                ],
            },
            {
                "heading": "撤销",
                "body": [
                    "撤销会移除本工具写入的开场补丁，并把安装时隔离的同名覆盖文件原样放回。",
                    "恢复后游戏重新使用原来的 splashscreen 行为。",
                    "撤销不修改存档、语言设置和游戏自然进度。",
                    "如果补丁文件被外部改过，工具会保留该文件并说明原因，不做无依据的删除。",
                ],
            },
        ],
    },
    "runtime_compat": {
        "title": "游戏入口 / 文本注入兼容",
        "summary": "只对已核实机制提供入口回退与文本注入兼容；不隐藏异常，仍属实验性范围。",
        "sections": [
            {
                "heading": "它做什么",
                "body": [
                    "入口回退：当游戏缺少自己的 start 标签、脚本可见且主菜单有唯一明确的 Start 目标时，写入 label_overrides，把默认入口指向这个已验证的标签。",
                    "Luna 桥接：只在引擎源码组合已复核、对白接口存在，并且运行中出现可识别的 Luna 嵌入钩子时生效。没有这个钩子时补丁保持惰性。",
                    "桥接会保留原文的控制和格式标签；翻译结果改动这些标签时退回原文，不制造新的文本或跳过对白。",
                    "不改游戏原始脚本，不用宽泛的 try/except 吞掉游戏异常，开发模式的检查仍然有效。",
                ],
            },
            {
                "heading": "适用条件",
                "body": [
                    "目标游戏是 Ren'Py，预检能在 renpy/config.py 中确认 label_overrides，并在启动脚本中确认默认入口回退机制已复核。",
                    "入口回退还要求游戏没有 start、脚本以可见 .rpy 提供，并且主菜单只有一个可静态确认的 Start 目标。",
                    "Luna 桥接要求引擎源码哈希命中已复核组合，并且对白接口具备桥接所需的函数。",
                    "已经定义 start、存在编译脚本或归档脚本、主菜单目标不唯一时，入口回退会被拒绝。",
                ],
            },
            {
                "heading": "风险与验证",
                "body": [
                    "这是实验性能力：静态匹配、离线探针和真实游戏长时间运行是不同验证层级，预检支持不代表所有翻译器和所有剧情都已实测。",
                    "如果入口匹配错误，游戏可能进入错误标签。先在副本确认主菜单、新游戏和读档。",
                    "Luna 桥接需要实际对白、slow 文本和暂停标签都正常；只看进程启动或正常退出不能证明成功。",
                    "游戏自己的 traceback.txt 或 errors.txt 出现新错误时，模拟会判为失败，补丁不会掩盖它。",
                ],
            },
            {
                "heading": "撤销",
                "body": [
                    "撤销移除本工具写入的运行兼容补丁，恢复游戏原有的入口与对白行为。",
                    "不改游戏原始脚本、语言设置和存档。",
                    "如果补丁文件被外部修改，撤销会保留文件并记录原因，不做覆盖。",
                ],
            },
        ],
    },
    "gallery": {
        "title": "解锁画廊 / 回放",
        "summary": "只放开已复核的标准 Gallery 与回放条件；不承诺全图鉴，不修改存档。",
        "sections": [
            {
                "heading": "它做什么",
                "body": [
                    "标准 Gallery：只在引擎实现和可见声明通过复核时，清空指定 Gallery 实例的 button 与 image 条件，并在载入存档后重新应用。",
                    "回放适配：只对内容指纹匹配的已复核样本，检查 label、缩略图和默认变量作用域，再用 Replay(..., locked=False) 放开真实回放资格。",
                    "只改访问资格，不批量修改 persistent 布尔值，不把全局的 seen_image 或 seen_label 直接改成真。",
                    "不修改存档，不写入永久解锁状态。",
                ],
            },
            {
                "heading": "适用条件",
                "body": [
                    "引擎的 Gallery 或 Replay 实现通过哈希复核，且相关脚本以可见 .rpy 提供。",
                    "标准 Gallery 需要可静态解析的 button 与 image 声明、字面量资源，并且界面没有额外的条件门禁。",
                    "回放适配还要求内容指纹、label、缩略图和默认变量作用域全部匹配。",
                    "编译脚本没有源码、脚本在 .rpa 归档里、使用自定义锁逻辑或带付费与订阅门禁时，功能会被判为不支持。",
                ],
            },
            {
                "heading": "风险与验证",
                "body": [
                    "支持范围可能是局部的。有的样本只放开回放，图片画廊保持原规则，界面会显示 partial 或回放限定。",
                    "按钮可以点击只证明访问资格，不证明每个回放场景都能完整播放；缺少资源或变量的场景仍需实际测试。",
                    "不承诺全图鉴，也不承诺所有回放场景。自定义或编译型锁逻辑一律按不支持处理。",
                    "先在隔离副本打开画廊、进入一个回放、读一次档，确认没有新错误，再考虑写入原目录。",
                ],
            },
            {
                "heading": "撤销",
                "body": [
                    "撤销移除本工具写入的画廊补丁，恢复游戏原有访问规则。",
                    "不修改、不回滚存档；游戏过程中自然记录的已看状态和新进度会保留。",
                    "如果补丁文件被外部修改，撤销会保留文件并说明原因。",
                ],
            },
        ],
    },
    "translation": {
        "title": "实时汉化",
        "summary": "玩到当前对白或选项时才翻译；默认免费机翻，超时保留原文。",
        "sections": [
            {
                "heading": "它做什么",
                "body": [
                    "在游戏库点击“检查并汉化”，通过预检后启动会话。连接补丁可以撤销，普通双击游戏仍显示原文。",
                    "当前对白和符合条件的标准 ADV 选项实际执行时才请求翻译；预测阶段不联网，不在启动前批量预译剧情。",
                    "默认源语言 auto、目标语言 zh-CN，默认最多等待 2 秒；等待时间可调整为 0 到 30 秒。0 秒表示暂停翻译、保留原文且不发请求。一组菜单共享同一等待预算。",
                    "及时成功时显示译文；超时、服务失败或连接断开时保留原文。迟到结果只进入缓存，不改写当前已经显示的句子。",
                    "缓存按游戏、原文、语言、提供商和模型配置隔离。保留原文标签、变量占位符，以及选项顺序、条件和返回值。",
                ],
            },
            {
                "heading": "适用条件",
                "body": [
                    "已审核 Ren'Py 8.3.0、8.3.6、8.4.1、8.4.2、8.5.0、8.5.2 的部分构建。具体范围以预检结果为准。",
                    "预检分别显示标准对白和常规剧情选项的支持情况。仅编译菜单、自定义逻辑菜单和 NVL 保留原文。",
                    "内置汉化与外部 Luna 内嵌互斥，检测到冲突时停止内置模式并说明；不要同时启用两套内嵌翻译。",
                    "其他引擎尚不支持内置汉化；RPG Maker MV / MZ 目前只支持字体回退。",
                ],
            },
            {
                "heading": "服务与凭据",
                "body": [
                    "默认免费机翻使用 Google 无 Key 试验通道，该端点可能变更、失效或限流。失败会说明原因并回退原文，不自动转用收费 AI。",
                    "设置页的“测试连接”只发送固定测试句，报告耗时与失败原因。它适合在启动游戏前确认接口、网络和授权。",
                    "自填 AI 模式需要自行提供兼容接口地址、模型和 Key，可能由你选择的服务商计费。默认不记忆 Key；主动选择记忆时使用 Windows DPAPI 加密。",
                    "游戏只连接带随机会话凭据的本机代理；外网请求与 Key 留在工具侧。被选中翻译的文本会发送给当前配置的服务。",
                    "不要把 Key、账号或完整剧情附在问题反馈中。帮助检索完全离线，不会向翻译服务发送检索词。",
                ],
            },
            {
                "heading": "风险与验证",
                "body": [
                    "先在隔离副本试用，普通存档和 multipersistent 均使用副本独立目录，再验证对白、选项、快进、回滚和读档。",
                    "机翻可能不准确。标签或变量占位符不匹配时保留原文；部分文本保持原文不代表应跳过游戏自己的错误检查。",
                    "点击“停止汉化”或关闭工具后，原游戏继续运行并回退原文；不会为停止翻译而结束正常游戏进程。",
                    "模拟副本仍需使用运行日志页的结束、清理或重试清理操作；关闭工具时会按模拟会话规则处理副本。",
                ],
            },
            {
                "heading": "撤销",
                "body": [
                    "“撤销还原”按安装账本移除工具写入的连接补丁；无需删除游戏文本或修改语言设置。",
                    "停止会话不等于卸载连接补丁；普通双击游戏时连接补丁保持惰性，仍显示原文。",
                    "撤销不修改存档与自然进度。含 1.3 功能的账本需要符合最低工具版本的程序处理，旧版会拒绝修改并提示使用新版。",
                ],
            },
        ],
    },
    "library": {
        "title": "游戏库与快捷启动",
        "summary": "为每个游戏手动选择启动程序，快捷开始游戏或打开本地文件夹。",
        "sections": [
            {
                "heading": "首次选择启动程序",
                "body": [
                    "每个游戏第一次启动都需要你手动选择 exe，即使只找到一个候选。可选择游戏目录内的子目录程序；取消选择不会启动游戏。",
                    "工具只保存相对于该游戏根目录的启动路径；不允许选择游戏目录外的 exe。文件移动或失效后，下一次启动会要求重新选择。",
                    "需要改用其他启动器时，使用“更换启动程序”。名称、目录和启动程序属于该条目，不取决于当前处理页选中的游戏。",
                ],
            },
            {
                "heading": "启动与打开文件夹",
                "body": [
                    "“开始游戏”正常启动已选 exe，工作目录为 exe 所在文件夹。关闭工具不会结束这类正常启动的游戏。",
                    "“打开文件夹”直接打开对应库条目的本地目录。路径失效或目录离线时会明确提示，不会打开其他条目的目录。",
                    "需要实时翻译时使用“检查并汉化”。普通“开始游戏”直接启动游戏。",
                    "“打开处理页”会切到处理页面并选择该游戏；条目暂时离线时仍可重命名。",
                    "未识别引擎的游戏也能加入游戏库，手选 exe 后普通启动，或打开本地目录。",
                ],
            },
            {
                "heading": "版本与配置",
                "body": [
                    "1.3 正式版首次自动合并旧版和测试版游戏库。重复条目优先采用测试版的有效名称、启动程序和界面配置。",
                    "升级保留离线书签和两份旧配置，继续使用原来的翻译设置、缓存、安装账本与备份。",
                    "旧版工具遇到含新版功能的账本会提示使用对应新版撤销。",
                ],
            },
        ],
    },
    "simulation": {
        "title": "模拟运行",
        "summary": "在隔离副本里安装并启动，确认主菜单和剧情后再决定是否写入原目录。",
        "sections": [
            {
                "heading": "流程",
                "body": [
                    "兼容预检只读取游戏结构，不复制、不修改游戏；不通过时直接停止。",
                    "把游戏整树复制到系统临时目录下的独立会话，并在这个会话里准备本工具的账本和备份。",
                    "普通存档和 multipersistent 指向会话自己的目录，不使用原游戏的存档。",
                    "只在副本里安装所选功能，再启动副本根目录的 .exe；不会启动原目录的启动器。",
                    "先确认进入主菜单，再单独确认实际剧情、读档或新游戏等场景。两次确认分别记录。",
                    "模拟步骤、结果、主菜单与剧情确认、结束和重试清理全部在“运行日志”页；处理页入口会跳转到这里。",
                    "结束模拟后清理临时会话；清理失败时保留错误提示和重试入口。切页或清空日志文本不会清除会话状态。",
                ],
            },
            {
                "heading": "失败时",
                "body": [
                    "兼容预检失败：停在预检阶段，不复制、不写入游戏。",
                    "复制或模拟安装失败：清理本次临时会话，原游戏不受影响。",
                    "找不到根目录 .exe：模拟安装可能成功，但无法启动验证，会话会被清理。",
                    "游戏出现新的 traceback.txt 或 errors.txt，或进程异常退出：模拟判为失败，不会因为进程启动过就算通过。",
                    "清理失败：工具显示具体错误，可以点“重试清理”；必要时先关闭窗口再重新打开。",
                ],
            },
            {
                "heading": "注意",
                "body": [
                    "进程正常退出，退出码为 0，不等于进入主菜单。必须由你确认看到主菜单。",
                    "主菜单确认也不等于剧情通过。剧情、读档和中文渲染要单独测试并确认。",
                    "模拟只验证副本，不代表原目录写入一定成功；正式安装前仍会再次确认。",
                    "临时副本需要磁盘空间，大游戏可能复制较慢；空间不足会在复制前失败。",
                    "如果游戏已经装过本工具，模拟会迁移并校验账本和备份，不能借模拟跳过所有权检查。",
                ],
            },
            {
                "heading": "清理策略",
                "body": [
                    "正常结束、取消启动、安装失败和启动失败都会走清理流程。",
                    "关闭窗口时如果模拟仍在进行，工具会先询问是否停止进程并清理副本。",
                    "清理先停止仍在运行的副本进程，再删除整个临时会话目录。",
                    "清理失败不会假装成功；工具会保留错误信息，并提供重试。",
                ],
            },
        ],
    },
    "install": {
        "title": "安装到游戏",
        "summary": "把所选功能写入原游戏目录；写前确认，失败回滚，撤销只恢复工具改过的文件。",
        "sections": [
            {
                "heading": "流程",
                "body": [
                    "安装前先做兼容预检，只让受支持的功能进入安装。",
                    "弹窗会列出将写入的功能和游戏路径，并说明备份与撤销方式，需要你明确确认。",
                    "所有功能先准备，全部通过后才开始应用；不会只装一半就停下。",
                    "遇到别人写的同名文件时会先备份到工作目录的 quarantine/，再放本工具的版本。",
                    "写入后记录 install_manifest.json，保存文件、来源和内容哈希。",
                    "安装完成后建议先开一次游戏，检查主菜单和一段剧情；异常时使用撤销还原。",
                ],
            },
            {
                "heading": "失败时",
                "body": [
                    "任一功能准备失败：本次不向游戏目录写入任何文件。",
                    "应用阶段异常：用安装前的快照整体回滚本次改动。",
                    "外部修改过的文件或与账本不匹配的备份会被拒绝覆盖，避免丢失第三方补丁。",
                    "界面会显示失败信息并保留运行日志；如果提示部分文件已改，先撤销还原再重试。",
                ],
            },
            {
                "heading": "注意",
                "body": [
                    "安装会写入原目录。模拟通过不代表原目录一定没有问题，写入前仍要确认。",
                    "工具工作区默认在 %LOCALAPPDATA%\\rpykit，可用 RPYKIT_WORK 更改。账本和备份不要手动删除，否则撤销会失去依据。",
                    "处理进行中关闭窗口，工具会询问是否等当前操作结束后再退出。",
                    "RPG Maker 会修改 js/plugins.js 的插件注册，并先保存原件；撤销时恢复原注册，不只是删除插件文件。",
                    "安装字体、入口兼容或画廊补丁不生成译文；实时汉化只安装连接补丁，通过工具开始会话后才请求译文。",
                ],
            },
            {
                "heading": "撤销",
                "body": [
                    "撤销需要先选择游戏目录，然后按安装账本恢复，不依赖当前勾选状态。",
                    "恢复前会检查所有权、内容哈希和备份；文件被外部修改时会拒绝覆盖并保留可恢复的备份。",
                    "撤销只恢复本工具改过的文件，不回滚存档、语言设置和游戏自然取得的进度。",
                    "不要手动删除工作区账本后再期待自动还原。",
                ],
            },
        ],
    },
    "paid_content": {
        "title": "付费内容与授权边界",
        "summary": "说明付费/订阅与 DRM 的边界：本工具只做诊断和明确拒绝，不伪造购买或授权状态。",
        "sections": [
            {
                "heading": "本工具不做什么",
                "body": [
                    "不提供付费内容、订阅状态或 DRM 限制的规避功能。",
                    "不伪造 Steam、DLC、订阅或其他平台的购买、拥有或授权状态。",
                    "不修改平台的授权文件、票据、账户数据或联网校验结果。",
                    "不把付费门禁、订阅门禁或 DRM 检查当成 gallery、runtime_compat 等功能的支持范围。",
                    "不承诺让需要购买、订阅或额外授权的内容变得可用。",
                ],
            },
            {
                "heading": "建议",
                "body": [
                    "需要相关内容时，通过游戏或平台的官方渠道购买、补全 DLC，或恢复已有的订阅。",
                    "遇到授权、区域或购买记录问题，优先查看官方商店页面、购买记录或平台客服说明。",
                    "如果是缺文件、路径错误或运行环境导致的报错，可以先用本工具的预检、模拟和日志确认技术原因。",
                    "确认属于技术兼容问题后，再考虑字体、入口或已复核的画廊补丁；授权问题不在补丁范围内。",
                    "不要使用来源不明的授权补丁或修改器，本工具不会为这类做法提供支持。",
                ],
            },
            {
                "heading": "诊断能提供什么",
                "body": [
                    "可以报告引擎类型、版本线索、字体接口、入口标签、画廊机制和已安装补丁状态。",
                    "可以明确说明某项功能为什么不支持，例如引擎实现未复核、资源缺失或访问门禁不在支持范围。",
                    "不能替代购买、订阅或平台授权，也不会尝试让未授权的内容变得可用。",
                ],
            },
        ],
    },
    "faq": {
        "title": "常见问题",
        "summary": "路径、扫描失败、日志位置、模拟失败、撤销和不支持内容的离线说明。",
        "sections": [
            {
                "heading": "常见问题",
                "body": [
                    "路径：Ren'Py 选择包含 game/ 的游戏根目录；RPG Maker MV 或 MZ 选择包含 js/ 或 www/js/ 的根目录。不要选择 game/ 里面的子目录。",
                    "扫描失败：先确认目录结构完整、文件可读。预检只读取结构，不改游戏；具体原因会显示在功能行，英文原文写入运行日志。",
                    "扫描不到可用功能：未知引擎、同时命中多个引擎、编译脚本没有源码、资源缺失或机制未复核时，工具会拒绝对应功能。这是有意的失败关闭，不是漏装。",
                    "日志位置：GUI 的“运行日志”页显示最近的处理和模拟输出，可以复制或导出；完整模拟操作区也在这里，清空文本不会丢失会话状态。",
                    "模拟失败：在日志页查看“模拟步骤”和完整输出，并在同页结束或重试清理。预检失败不会复制游戏；复制或安装失败会清理临时会话。",
                    "模拟启动后没有确认：进程启动或正常退出都不算成功，必须手动确认主菜单；剧情和读档需要单独确认。",
                    "撤销：选择游戏目录后点“撤销还原”。工具按账本恢复自己写过的文件，不回滚存档和自然进度。",
                    "哪些内容不支持：未知引擎、未知画廊机制、编译或归档中的自定义锁、付费与订阅门禁，以及 MV / MZ 的开场、运行兼容、画廊和实时汉化功能。",
                    "为什么不能全图鉴：工具只放开已复核的标准 Gallery 条件和已复核回放，不批量修改 persistent，也不承诺所有场景。",
                    "安装失败后怎么办：先撤销还原，再查看日志。不要手动删除工作区账本或备份。",
                ],
            },
            {
                "heading": "日志与反馈",
                "body": [
                    "运行日志页保留最近一次处理和模拟的输出；复制或导出前先检查是否包含个人路径或隐私信息。",
                    "反馈问题时附上失败步骤、错误提示和日志片段。不要附带账号、密钥、购买凭据或完整存档。",
                    "帮助页的内容和检索都是离线的，不读取游戏文件、账号或授权数据。Ctrl+F 聚焦检索框；空白分隔的多个关键词同时匹配，可搜索中文、英文和全角英文。",
                ],
            },
        ],
    },
}


def topics():
    """Return (id, topic) pairs in insertion order, as independent copies."""
    return [(topic_id, copy.deepcopy(topic))
            for topic_id, topic in TOPICS.items()]


def topic_for(topic_id):
    """Return a copy of one topic, or None when the id is unknown."""
    topic = TOPICS.get(topic_id)
    return copy.deepcopy(topic) if topic is not None else None


def topic_ids():
    """Return topic ids in the order the Help page should list them."""
    return list(TOPICS)


def _normalise(text):
    return unicodedata.normalize("NFKC", text).casefold()


def _snippet(parts, words, limit=132):
    """Choose one relevant paragraph and return plain text, never markup."""
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in parts if part]
    if not paragraphs:
        return ""
    paragraph = max(paragraphs, key=lambda part: sum(
        word in _normalise(part) for word in words))
    normal = _normalise(paragraph)
    positions = [normal.find(word) for word in words if word in normal]
    start = max(0, min(positions) - 30) if positions else 0
    if len(paragraph) <= limit:
        return paragraph
    start = min(start, max(0, len(paragraph) - limit))
    excerpt = paragraph[start:start + limit]
    return ("…" if start else "") + excerpt + (
        "…" if start + limit < len(paragraph) else "")


def search(query):
    """Search all offline topic text with whitespace-separated AND terms.

    Return at most one result per topic. Title and heading hits rank first;
    ties preserve topic and section order. A match spanning several sections
    still finds the topic and opens its strongest matching section. Empty
    queries return topic overviews. Results contain only independent values.
    """
    words = list(dict.fromkeys(_normalise(query or "").split()))
    ranked = []
    for topic_id, topic in TOPICS.items():
        title = topic["title"]
        summary = topic["summary"]
        title_text = _normalise(title)
        summary_text = _normalise(summary)
        header = title_text + "\n" + summary_text
        sections = topic["sections"]
        section_texts = [
            _normalise(section["heading"] + "\n" + "\n".join(section["body"]))
            for section in sections
        ]
        text = header + "\n" + "\n".join(section_texts)
        if not all(word in text for word in words):
            continue

        section_index = None
        heading = ""
        snippet = _snippet([summary], words)
        score = sum(100 * (word in title_text) + 30 * (word in summary_text)
                    for word in words)
        if words:
            section_scores = []
            for index, section in enumerate(sections):
                heading_text = _normalise(section["heading"])
                body_text = _normalise("\n".join(section["body"]))
                points = sum(70 * (word in heading_text) + 10 * (word in body_text)
                             for word in words)
                section_scores.append(points)
            best = max(range(len(sections)), key=section_scores.__getitem__)
            best_section = sections[best]
            has_heading_hit = any(word in _normalise(best_section["heading"])
                                  for word in words)
            if section_scores[best] and (
                    has_heading_hit or not all(word in header for word in words)):
                section_index = best
                heading = best_section["heading"]
                snippet = _snippet(best_section["body"], words)
            score += section_scores[best]
        ranked.append((score, {
            "topic_id": topic_id,
            "title": title,
            "section_index": section_index,
            "heading": heading,
            "snippet": snippet,
        }))
    ranked.sort(key=lambda entry: -entry[0])
    return [result for _score, result in ranked]
