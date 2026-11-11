"""Chinese display copy for the toolkit's feature-support reasons.

The backend reports compatibility in English, often mixed with identifiers such
as ``config.font_name_map``.  The window should greet the player in Chinese while
keeping those identifiers available for support work.  This module performs that
translation and nothing else.

Rules that matter:

* A reason that already contains Chinese is returned unchanged apart from
  surrounding whitespace.
* A known English reason becomes one short Chinese sentence.  Technical
  identifiers stay in Chinese parentheses when they help diagnosis.
* An unknown English reason is never echoed.  The user gets a fixed Chinese
  sentence that points at the run log, where the original text remains.

The module has no UI-toolkit imports, so it can be tested without a display.
"""

from __future__ import annotations

import re

TYPE_LABELS = {
    "supported": "可用",
    "experimental": "实验性",
    "unsupported": "不支持",
    "unknown": "未确认",
}

UNKNOWN_REASON = "检测到未识别的兼容性限制，详细原因已写入运行日志。"

# Reasons that represent an experimental capability even when the backend has
# not set an explicit ``experimental`` flag.
_EXPERIMENTAL_MECHANISMS = {
    "luna_say_bridge",
    "reviewed_replay",
    "custom_gallery_unverified",
}

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _normalize(reason):
    """Collapse backend whitespace so prefix matching is predictable."""
    return " ".join(reason.split())


def _has_chinese(text):
    return _CJK.search(text) is not None


def _count(text):
    match = re.search(r"\((\d+)\)", text)
    return match.group(1) if match else None


def _match(reason):
    """Return ``(code, chinese_text)`` for a known English reason, else None."""
    text = _normalize(reason)

    # --- Ren'Py font routing ---------------------------------------------
    if (text.startswith("Ren'Py config.font_name_map is")
            or text.startswith("config.font_name_map is")):
        if " is unknown" in text:
            return ("font_map_missing",
                    "无法确认字体名映射 API（config.font_name_map）是否可用。")
        return ("font_map_missing",
                "引擎缺少字体名映射 API（config.font_name_map）。")

    if text.startswith("Ren'Py FontGroup.add("):
        if " is unknown" in text:
            return ("font_group_missing",
                    "无法确认字体分组 API（FontGroup.add）是否可用。")
        return ("font_group_missing",
                "引擎缺少字体分组 API（FontGroup.add）。")

    if (text.startswith("Ren'Py config.font_replacement_map is")
            or text.startswith("config.font_replacement_map is")):
        if " is unknown" in text:
            return ("font_replacement_missing",
                    "无法确认字体替换映射 API（config.font_replacement_map）是否可用。")
        return ("font_replacement_missing",
                "引擎缺少字体替换映射 API（config.font_replacement_map），"
                "也没有旧版回退路径。")

    if text.startswith("This is Ren'Py 7.5 or older"):
        return ("fonttools_missing",
                "旧版 Ren'Py 只能把汉字合并进字体文件，需要安装 fontTools"
                "（python -m pip install fonttools）。")

    if (text.startswith("Ren'Py config.label_overrides is")
            or text.startswith("config.label_overrides is")):
        if " is unknown" in text:
            return ("label_overrides_missing",
                    "无法确认标签覆盖 API（config.label_overrides）是否可用，"
                    "开场跳过无法安全安装。")
        return ("label_overrides_missing",
                "引擎缺少标签覆盖 API（config.label_overrides），"
                "开场跳过无法安全安装。")

    if text.startswith("Engine has no verified label_overrides API"):
        return ("label_overrides_missing",
                "引擎没有可验证的标签覆盖 API（label_overrides），"
                "入口兼容补丁不可用。")

    if text.startswith("Ren'Py APIs could not be inspected"):
        return ("api_unreadable", "无法读取 Ren'Py API，兼容性尚未确认。")

    # --- RPG Maker --------------------------------------------------------
    if text.startswith("MV/MZ intro bypass is not implemented"):
        return ("rpg_intro_unsupported", "RPG Maker MV/MZ 暂不支持跳过开场。")

    if text.startswith("MV/MZ runtime compatibility patches are not implemented"):
        return ("rpg_runtime_unsupported",
                "RPG Maker MV/MZ 暂不支持运行兼容补丁。")

    if text.startswith("MV/MZ gallery unlock is not implemented"):
        return ("rpg_gallery_unsupported",
                "RPG Maker MV/MZ 暂不支持解锁画廊。")

    if text.startswith("MV/MZ live translation is not implemented"):
        return ("rpg_translation_unsupported", "RPG Maker MV/MZ 目前仅支持字体补丁。")

    if text.startswith("required engine hook missing:"):
        detail = text.split(":", 1)[1].strip()
        if detail:
            return ("rpg_plugin_missing",
                    "RPG Maker 引擎缺少必需钩子文件（%s）。" % detail)
        return ("rpg_plugin_missing", "RPG Maker 引擎缺少必需钩子文件。")

    if text.startswith("plugins.js missing"):
        return ("rpg_plugin_missing",
                "RPG Maker 缺少插件清单文件（js/plugins.js）。")

    if text.startswith("duplicate RPYKit plugin entries"):
        return ("rpg_plugin_missing",
                "RPG Maker 插件清单中存在重复的 RPYKit 条目。")

    if text.startswith("RPYKit plugin name is already used by an unknown plugin"):
        return ("rpg_plugin_missing", "RPG Maker 插件名 RPYKit 已被未知插件占用。")

    if text.startswith("bundled Noto font missing"):
        return ("rpg_plugin_missing", "安装包内缺少随包的 Noto 字体文件。")

    if text.startswith("RPG Maker layout is unknown or ambiguous"):
        return ("rpg_layout_invalid",
                "RPG Maker 目录结构未知或不明确，无法安装字体插件。")

    if text.startswith("plugins.js is not a generated data-only var $plugins assignment"):
        return ("rpg_plugin_invalid",
                "RPG Maker 插件清单不是纯数据格式（var $plugins = ...）。")

    if text.startswith("plugins.js must contain strict JSON:"):
        return ("rpg_plugin_invalid",
                "RPG Maker 插件清单不是严格 JSON，详细原因已写入运行日志。")

    if text.startswith("plugins.js contains executable or unknown trailing content"):
        return ("rpg_plugin_invalid",
                "RPG Maker 插件清单包含可执行或未知的尾部内容。")

    if text.startswith("plugins.js must contain an array"):
        return ("rpg_plugin_invalid", "RPG Maker 插件清单必须是数组。")

    if text.startswith("plugins.js plugin record has an unknown structure"):
        return ("rpg_plugin_invalid", "RPG Maker 插件清单条目结构未知。")

    # --- Ren'Py runtime compatibility ------------------------------------
    if text.startswith("Runtime compatibility scan failed"):
        return ("runtime_scan_failed",
                "运行兼容性扫描失败，详细原因已写入运行日志。")

    if text.startswith("Dialogue Text mismatch found"):
        return ("runtime_unreviewed",
                "检测到对话文本不一致，但该引擎源码组合尚未复核，"
                "需要真实引擎探测后才能启用 Luna 桥接。")

    if text.startswith("Verified say API"):
        if "Real Luna session verification" in text:
            return ("luna_unverified",
                    "已验证 say API，Luna 桥接仍需真实引擎会话验证。")
        return ("luna_unverified",
                "已验证 say API，可选 Luna 桥接仅在识别到嵌入钩子时生效，"
                "且不会修复未验证的入口标签。")

    if text.startswith("Engine default-start fallback is not verified"):
        return ("entry_unverified", "引擎默认 start 回退尚未验证。")

    if text.startswith("Game already defines start"):
        return ("entry_not_needed", "游戏已定义 start 入口，无需额外回退。")

    if text.startswith("Compiled-only or archived scripts"):
        return ("entry_unverified",
                "脚本只有编译版或打包在归档中，无法确认 start 是否存在。")

    if text.startswith("A unique literal main-menu Start target could not be verified"):
        return ("entry_unverified",
                "无法验证主菜单中唯一的字面量 Start 目标。")

    if text.startswith("Main-menu Start target has no verified label"):
        return ("entry_unverified", "主菜单 Start 目标没有已验证的标签。")

    if text.startswith("Missing default start; verified native main-menu target:"):
        target = text.split(":", 1)[1].strip()
        if target:
            return ("entry_target_verified",
                    "缺少默认 start，已验证主菜单原生入口（%s）。" % target)
        return ("entry_target_verified", "缺少默认 start，已验证主菜单原生入口。")

    # --- Ren'Py gallery ---------------------------------------------------
    if text.startswith("The Gallery engine implementation has not been reviewed"):
        return ("gallery_review_required", "画廊引擎实现尚未复核，无法安全启用。")

    if text.startswith("The replay engine implementation has not been reviewed"):
        return ("gallery_review_required", "回放引擎实现尚未复核，无法安全启用。")

    if text.startswith("No reviewed standard Gallery construction was found"):
        return ("gallery_standard_missing",
                "未找到已复核的标准 Gallery 结构。")

    if text.startswith("Archived scripts require a reviewed game adapter"):
        return ("gallery_source_unverified",
                "脚本打包在归档中，需要已复核的游戏适配器。")

    if text.startswith("Compiled scripts have no visible source"):
        return ("gallery_source_unverified",
                "画廊脚本只有编译版，没有可见源码，锁定逻辑尚未核实。")

    if text.startswith("Custom image/replay lock logic"):
        return ("gallery_custom_logic",
                "自定义图片或回放锁定逻辑需要专门的适配器。")

    if text.startswith("Runtime gallery declarations"):
        return ("gallery_custom_logic", "运行时画廊声明需要专门的适配器。")

    if text.startswith("Gallery buttons and their screen"):
        return ("gallery_custom_logic",
                "未能同时识别画廊按钮及其所属界面。")

    if text.startswith("Gallery internals are customized"):
        return ("gallery_custom_logic",
                "画廊内部实现已被定制，拒绝使用未经验证的覆盖。")

    if text.startswith("Gallery screen has additional conditional gates"):
        return ("gallery_custom_logic", "画廊界面还有额外的条件门禁。")

    if text.startswith("Dynamic gallery resources"):
        return ("gallery_dynamic", "动态画廊资源无法静态核对。")

    if text.startswith("Nonliteral gallery resources"):
        return ("gallery_dynamic", "非字面量画廊资源需要专门的适配器。")

    if text.startswith("Gallery image resources are missing"):
        return ("gallery_missing_resource",
                "画廊图片资源缺失或无法静态解析。")

    if text.startswith("Image gallery contains missing placeholder resources"):
        return ("gallery_missing_resource",
                "图片画廊缺少占位资源，无法解锁图片。")

    if text.startswith("Replay targets are missing"):
        count = _count(text)
        if count:
            return ("gallery_missing_resource",
                    "回放目标缺失（%s 个）。" % count)
        return ("gallery_missing_resource", "回放目标缺失。")

    if text.startswith("Replay thumbnails are missing"):
        count = _count(text)
        if count:
            return ("gallery_missing_resource",
                    "回放缩略图缺失（%s 个）。" % count)
        return ("gallery_missing_resource", "回放缩略图缺失。")

    if text.startswith("Only the reviewed replay gallery is unlocked"):
        return ("gallery_partial_scope",
                "只解锁已复核的回放画廊，图片画廊规则保持不变。")

    if text.startswith("Standard Gallery image/condition/prior locks only"):
        return ("gallery_partial_scope",
                "仅适配标准 Gallery 的图片、条件和前置解锁，不含回放适配。")

    if text.startswith("Only recognized built-in gallery and replay conditions are bypassed"):
        return ("gallery_partial_scope",
                "仅绕过已核实的内置画廊与回放条件，游戏自定义的成就、物品栏"
                "和脚本解锁条件仍不受支持。")

    if text.startswith("Reviewed runtime inventory found"):
        match = re.search(r"found (\d+) standard Gallery entries.*?(\d+) custom scenes",
                          text)
        if match:
            return ("gallery_custom_inventory",
                    "已核对运行时清单：%s 个标准画廊条目无对象条件，"
                    "另有 %s 个自定义场景。" % (match.group(1), match.group(2)))
        return ("gallery_custom_inventory",
                "已核对运行时清单：标准画廊条目之外还有自定义场景，"
                "尚未全部适配。")

    if text.startswith("Screen-level seen_image/seen_label"):
        return ("gallery_custom_logic",
                "屏幕级 seen_image / seen_label 与 persistent.gallery_unlocked "
                "门禁仍然存在，其回放动作和作用域覆盖尚未适配。")

    if text.startswith("Gallery inspection failed:"):
        return ("gallery_scan_failed", "画廊检查失败，详细原因已写入运行日志。")

    if text.startswith("Ren'Py dialogue/menu interfaces are not a reviewed"):
        return ("translation_engine_unreviewed", "此 Ren’Py 构建尚未审核，实时汉化保留原文。")
    if text.startswith("Translation interface inspection failed"):
        return ("translation_scan_failed", "无法完成汉化接口检查，请检查游戏文件后重试。")

    # --- Engine detection -------------------------------------------------
    if text.startswith("Unknown engine"):
        return ("engine_unknown", "未识别游戏引擎，无法确定支持范围。")

    if text.startswith("Multiple engine layouts detected"):
        return ("engine_ambiguous", "检测到多种引擎目录结构，无法确定支持范围。")

    return None


def reason_code(reason):
    """Stable short code for a compatibility reason.

    Non-string input has no code and returns ``unknown``.  Chinese-only reasons
    also return ``unknown``: they need no translation, and no backend code is
    invented for them.
    """
    if not isinstance(reason, str):
        return "unknown"
    text = reason.strip()
    if not text or _has_chinese(text):
        return "unknown"
    match = _match(text)
    return match[0] if match else "unknown"


def localize_reason(reason, feature_id=None):
    """Return one Chinese sentence for ``reason``.

    ``feature_id`` is accepted so callers can pass the row being described
    without branching on it.  The text itself is feature-independent.
    """
    if not isinstance(reason, str):
        return UNKNOWN_REASON
    text = reason.strip()
    if not text:
        return ""
    if _has_chinese(text):
        return text
    match = _match(text)
    if match:
        return match[1]
    return UNKNOWN_REASON


def localize_reasons(reasons, feature_id=None):
    """Localize a string, list or None into a deduplicated Chinese list."""
    if isinstance(reasons, str):
        items = [reasons]
    elif isinstance(reasons, (list, tuple)):
        items = list(reasons)
    else:
        items = []

    localized = []
    for item in items:
        if not isinstance(item, str):
            continue
        sentence = localize_reason(item, feature_id)
        if sentence and sentence not in localized:
            localized.append(sentence)
    return localized


def _empty_detail(level):
    if level == "unsupported":
        return "当前游戏不支持此功能，详细原因已写入运行日志。"
    if level == "unknown":
        return "兼容性尚未确认，详细原因已写入运行日志。"
    if level == "experimental":
        return "实验性功能，尚未在真实引擎完整验证。"
    return ""


def support_copy(spec, feature_id=None):
    """Build ``(level, label, detail)`` for one feature's support matrix row."""
    data = spec if isinstance(spec, dict) else {}
    localized = localize_reasons(data.get("reasons"), feature_id)
    joined = "；".join(localized)
    mechanism = data.get("mechanism")
    experimental = (data.get("experimental") is True
                    or mechanism in _EXPERIMENTAL_MECHANISMS)
    supported = data.get("supported")

    if supported is False:
        level = "unsupported"
        if joined:
            detail = "当前游戏不支持此功能：" + joined
        else:
            detail = _empty_detail(level)
        return (level, TYPE_LABELS[level], detail)

    if supported is True:
        coverage = data.get("coverage")
        if feature_id == "translation" and isinstance(coverage, dict) and coverage.get("dialogue") is True:
            version = data.get("engine_version")
            prefix = "已审核 Ren’Py %s 构建。" % version if isinstance(version, str) else ""
            options = ("检测到常规选项源码，运行时核对后翻译。" if coverage.get("standard_adv_menu") is True
                       else "选项保留原文。")
            return ("supported", TYPE_LABELS["supported"], prefix + "支持标准对白。" + options)
        if experimental:
            level = "experimental"
            detail = ("实验性功能，尚未在真实引擎完整验证：" + joined
                      if joined else _empty_detail(level))
            return (level, TYPE_LABELS[level], detail)
        level = "supported"
        detail = "适配范围：" + joined if joined else ""
        return (level, TYPE_LABELS[level], detail)

    level = "unknown"
    detail = ("兼容性尚未确认：" + joined
              if joined else _empty_detail(level))
    return (level, TYPE_LABELS[level], detail)


def feature_summary(title, spec, feature_id=None):
    """One-line summary such as ``跳过开场 logo · 不支持``."""
    _, label, _ = support_copy(spec, feature_id)
    name = title.strip() if isinstance(title, str) and title.strip() else "此功能"
    return name + " · " + label
