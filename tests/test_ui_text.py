"""Contract tests for the Chinese feature-support copy.

The module is deliberately independent of the window, so these tests can run
without Tk or CustomTkinter.  They pin three things: known backend reasons never
reach the player as English, unknown English never leaks either, and the
support-copy levels always agree with ``TYPE_LABELS``.
"""

from pathlib import Path

import pytest

import ui_text
from ui_text import (
    TYPE_LABELS,
    feature_summary,
    localize_reason,
    localize_reasons,
    reason_code,
    support_copy,
)

EM_DASH = chr(0x2014)

# Every backend reason family the window can receive, with its stable code.
KNOWN_REASONS = [
    ("Ren'Py config.font_name_map is missing in renpy/config.py",
     "font_map_missing"),
    ("Ren'Py config.font_name_map is unknown in renpy/config.py",
     "font_map_missing"),
    ("config.font_name_map is unavailable", "font_map_missing"),
    ("Ren'Py FontGroup.add(font, start, end) is missing in renpy/text/font.py",
     "font_group_missing"),
    ("Ren'Py FontGroup.add(font, start, end) is unknown in renpy/text/font.py",
     "font_group_missing"),
    ("Ren'Py config.font_replacement_map is missing in renpy/config.py, so "
     "there is no fallback route for an engine this old either",
     "font_replacement_missing"),
    ("Ren'Py config.font_replacement_map is unknown in renpy/config.py, so "
     "there is no fallback route for an engine this old either",
     "font_replacement_missing"),
    ("This is Ren'Py 7.5 or older, where a font can only be fixed by merging "
     "Hanzi into it; that needs fontTools. Install it with: python -m pip "
     "install fonttools", "fonttools_missing"),
    ("Ren'Py config.label_overrides is missing in renpy/config.py; intro "
     "cannot install safely.", "label_overrides_missing"),
    ("Ren'Py config.label_overrides is unknown in renpy/config.py; intro "
     "cannot install safely.", "label_overrides_missing"),
    ("Ren'Py APIs could not be inspected.", "api_unreadable"),
    ("MV/MZ intro bypass is not implemented", "rpg_intro_unsupported"),
    ("MV/MZ runtime compatibility patches are not implemented",
     "rpg_runtime_unsupported"),
    ("MV/MZ gallery unlock is not implemented", "rpg_gallery_unsupported"),
    ("required engine hook missing: js/plugins.js", "rpg_plugin_missing"),
    ("plugins.js missing", "rpg_plugin_missing"),
    ("duplicate RPYKit plugin entries", "rpg_plugin_missing"),
    ("RPYKit plugin name is already used by an unknown plugin",
     "rpg_plugin_missing"),
    ("bundled Noto font missing", "rpg_plugin_missing"),
    ("RPG Maker layout is unknown or ambiguous", "rpg_layout_invalid"),
    ("plugins.js is not a generated data-only var $plugins assignment",
     "rpg_plugin_invalid"),
    ("plugins.js must contain strict JSON: Expecting value: line 1 column 1",
     "rpg_plugin_invalid"),
    ("plugins.js contains executable or unknown trailing content",
     "rpg_plugin_invalid"),
    ("plugins.js must contain an array", "rpg_plugin_invalid"),
    ("plugins.js plugin record has an unknown structure",
     "rpg_plugin_invalid"),
    ("Engine has no verified label_overrides API.", "label_overrides_missing"),
    ("Engine default-start fallback is not verified.", "entry_unverified"),
    ("Verified say API; bridge activates only for the recognized Luna Python "
     "embedding hook. Real Luna session verification is still required.",
     "luna_unverified"),
    ("Dialogue Text mismatch found, but this engine source pair is not "
     "reviewed. A real-engine probe is required before enabling the Luna "
     "bridge.", "runtime_unreviewed"),
    ("Game already defines start; no entry fallback is needed.",
     "entry_not_needed"),
    ("Compiled-only or archived scripts prevent proving start is absent.",
     "entry_unverified"),
    ("A unique literal main-menu Start target could not be verified.",
     "entry_unverified"),
    ("Main-menu Start target has no verified label.", "entry_unverified"),
    ("Missing default start; verified native main-menu target: start",
     "entry_target_verified"),
    ("Verified say API; optional bridge activates only for the recognized Luna "
     "embedding hook. It does not repair unverified entry labels.",
     "luna_unverified"),
    ("Runtime compatibility scan failed: [Errno 13] Permission denied",
     "runtime_scan_failed"),
    ("The replay engine implementation has not been reviewed.",
     "gallery_review_required"),
    ("Replay targets are missing (3).", "gallery_missing_resource"),
    ("Replay thumbnails are missing (2).", "gallery_missing_resource"),
    ("Image gallery contains missing placeholder resources; image unlocking "
     "is unavailable.", "gallery_missing_resource"),
    ("Only the reviewed replay gallery is unlocked; image gallery rules are "
     "unchanged.", "gallery_partial_scope"),
    ("The Gallery engine implementation has not been reviewed.",
     "gallery_review_required"),
    ("No reviewed standard Gallery construction was found.",
     "gallery_standard_missing"),
    ("Custom image/replay lock logic needs a dedicated adapter.",
     "gallery_custom_logic"),
    ("Runtime gallery declarations need a dedicated adapter.",
     "gallery_custom_logic"),
    ("Gallery buttons and their screen have not both been identified.",
     "gallery_custom_logic"),
    ("Gallery internals are customized; refusing an unverified override.",
     "gallery_custom_logic"),
    ("Dynamic gallery resources cannot be verified statically.",
     "gallery_dynamic"),
    ("Nonliteral gallery resources need a dedicated adapter.",
     "gallery_dynamic"),
    ("Gallery screen has additional conditional gates.",
     "gallery_custom_logic"),
    ("Gallery image resources are missing or not statically resolvable.",
     "gallery_missing_resource"),
    ("Standard Gallery image/condition/prior locks only; no replay adapter.",
     "gallery_partial_scope"),
    ("Reviewed runtime inventory found 2 standard Gallery entries without "
     "object conditions, separate from 59 custom scenes.",
     "gallery_custom_inventory"),
    ("Screen-level seen_image/seen_label and persistent.gallery_unlocked gates "
     "remain; their replay actions and scoped overrides are not yet adapted.",
     "gallery_custom_logic"),
    ("Archived scripts require a reviewed game adapter.",
     "gallery_source_unverified"),
    ("Compiled scripts have no visible source; their gallery locks are "
     "unverified.", "gallery_source_unverified"),
    ("Gallery inspection failed: [Errno 2] No such file or directory",
     "gallery_scan_failed"),
    ("Only recognized built-in gallery and replay conditions are bypassed; "
     "game-specific custom achievement, inventory and scripted unlock "
     "conditions remain unsupported.", "gallery_partial_scope"),
    ("Unknown engine", "engine_unknown"),
    ("Multiple engine layouts detected", "engine_ambiguous"),
]


@pytest.mark.parametrize("reason,code", KNOWN_REASONS)
def test_known_reasons_are_chinese_and_keep_their_code(reason, code):
    localized = localize_reason(reason)
    assert isinstance(localized, str) and localized
    assert reason_code(reason) == code
    assert reason_code(localized) == "unknown"
    assert any("\u4e00" <= char <= "\u9fff" for char in localized)
    assert reason not in localized
    assert EM_DASH not in localized


def test_known_reasons_are_stable_and_do_not_need_a_feature_id():
    reason = "MV/MZ intro bypass is not implemented"
    assert localize_reason(reason) == localize_reason(reason, "intro")
    assert localize_reason(reason) == localize_reason(reason, "gallery")


def test_chinese_reasons_pass_through_stripped():
    cases = [
        "这是中文原因。",
        " 这是中文原因。 ",
        "混合 Ren'Py 中文说明",
        "没有 game/ 子目录，这不是一个 Ren'Py 游戏根目录。",
    ]
    for text in cases:
        assert localize_reason(text) == text.strip()


def test_rpgmaker_intro_reason_is_explicit_and_chinese():
    localized = localize_reason("MV/MZ intro bypass is not implemented")
    assert "RPG Maker" in localized or ("MV" in localized and "暂不支持" in localized)
    assert "暂不支持" in localized
    assert "not implemented" not in localized
    assert "intro" not in localized


def test_long_gallery_reason_stays_readable():
    reason = (
        "Only recognized built-in gallery and replay conditions are bypassed; "
        "game-specific custom achievement, inventory and scripted unlock "
        "conditions remain unsupported."
    )
    localized = localize_reason(reason)
    assert reason not in localized
    assert "画廊" in localized and "回放" in localized
    assert len(localized) <= 120
    assert localized.endswith("。")


def test_unknown_english_uses_the_fixed_chinese_fallback():
    reason = "A completely novel backend failure occurred."
    localized = localize_reason(reason)
    assert localized == ui_text.UNKNOWN_REASON
    assert reason not in localized
    assert "completely" not in localized
    assert reason_code(reason) == "unknown"


def test_reason_code_is_stable_for_non_string_and_blank_input():
    for value in (None, 1, 3.14, [], {}, object(), "", "   "):
        assert reason_code(value) == "unknown"


def test_support_copy_supported_with_scope():
    level, label, detail = support_copy({
        "supported": True,
        "mechanism": "standard_gallery",
        "reasons": ["Standard Gallery image/condition/prior locks only; "
                    "no replay adapter."],
    }, "gallery")
    assert (level, label) == ("supported", "可用")
    assert detail.startswith("适配范围：")
    assert "Gallery" in detail


def test_support_copy_experimental_by_flag_and_mechanism():
    level, label, detail = support_copy({
        "supported": True,
        "mechanism": None,
        "experimental": True,
        "reasons": ["Verified say API; optional bridge activates only for the "
                    "recognized Luna embedding hook. It does not repair "
                    "unverified entry labels."],
    })
    assert (level, label) == ("experimental", "实验性")
    assert detail.startswith("实验性功能，尚未在真实引擎完整验证：")

    for mechanism in ("luna_say_bridge", "reviewed_replay",
                      "custom_gallery_unverified"):
        level, label, _ = support_copy({
            "supported": True,
            "mechanism": mechanism,
            "reasons": [],
        })
        assert (level, label) == ("experimental", "实验性")


def test_support_copy_unsupported_and_unknown():
    level, label, detail = support_copy({
        "supported": False,
        "mechanism": None,
        "reasons": ["MV/MZ intro bypass is not implemented"],
    }, "intro")
    assert (level, label) == ("unsupported", "不支持")
    assert detail.startswith("当前游戏不支持此功能：")
    assert "RPG Maker" in detail
    assert "not implemented" not in detail

    for spec in ({}, {"supported": None}, {"supported": "yes"}):
        level, label, detail = support_copy(spec)
        assert (level, label) == ("unknown", "未确认")
        assert detail.startswith("兼容性尚未确认")


def test_support_copy_supported_without_reasons_has_empty_detail():
    assert support_copy({"supported": True, "reasons": []}) == (
        "supported", "可用", "")


def test_empty_reasons_never_leave_a_trailing_colon():
    specs = [
        {"supported": False, "reasons": []},
        {"supported": True, "experimental": True, "reasons": []},
        {"supported": True, "mechanism": "luna_say_bridge", "reasons": []},
        {"supported": True, "mechanism": "reviewed_replay", "reasons": []},
        {"supported": True, "reasons": []},
        {"supported": None, "reasons": []},
        {"reasons": []},
        {},
    ]
    for spec in specs:
        _, _, detail = support_copy(spec)
        assert not detail.endswith("：")
        assert not detail.endswith(":")
        assert "：" not in detail


def test_localize_reasons_accepts_str_list_and_none():
    font_reason = "Ren'Py APIs could not be inspected."
    expected = localize_reason(font_reason)
    assert localize_reasons(font_reason) == [expected]
    assert localize_reasons(None) == []
    assert localize_reasons("") == []
    assert localize_reasons("   ") == []
    assert localize_reasons([None, "", "   ", 7]) == []
    assert localize_reasons([]) == []


def test_localize_reasons_deduplicates_and_keeps_order():
    font_reason = "Ren'Py APIs could not be inspected."
    chinese = "已有中文原因。"
    source = [font_reason, font_reason, chinese, " " + chinese + " ",
              None, "", 3]
    result = localize_reasons(source)
    assert result == [localize_reason(font_reason), chinese]
    assert source[0] == font_reason
    assert localize_reasons(tuple(source)) == result


def test_feature_summary_is_one_line():
    assert feature_summary("跳过开场 logo", {
        "supported": False, "reasons": [],
    }) == "跳过开场 logo · 不支持"
    assert feature_summary("", {}) == "此功能 · 未确认"
    assert "\n" not in feature_summary("标题", {"supported": True,
                                                "reasons": []})


def test_module_source_has_no_em_dash_and_no_ui_toolkit_import():
    source = Path(__file__).resolve().parents[1].joinpath("ui_text.py")
    text = source.read_text(encoding="utf-8")
    assert EM_DASH not in text
    assert "tkinter" not in text.lower()
    assert "customtkinter" not in text.lower()
