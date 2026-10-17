"""Contract tests for the shared UI tokens.

These tests never import ``appgui``: they only exercise the dependency-free
token module so the palette can be verified without a display or Tk runtime.
"""

import re

import pytest

from ui_tokens import (
    FONT_ROLES,
    PALETTES,
    PAIRS,
    RADIUS,
    SPACING,
    audit,
    contrast_ratio,
    palette,
)

EXPECTED_KEYS = {
    "bg", "sidebar", "panel", "panel_alt", "input", "fg", "dim", "border",
    "border_strong", "accent_fill", "accent_hover", "accent_text",
    "accent_soft", "on_accent", "focus", "ok", "warn", "bad", "select",
    "text_disabled",
}

REQUIRED_AUDITS = {
    "dim/bg",
    "dim/panel",
    "fg/panel",
    "accent_fill/on_accent",
    "accent_text/accent_soft",
    "border_strong/panel",
    "ok/panel",
    "warn/panel",
    "bad/panel",
    "focus/bg",
}

# Old literal values from appgui's ad-hoc palette.  They were too weak for
# button labels (dark light-purple text and the muted grey), so the token
# source must not carry them forward into any button text role.
LEGACY_TEXT_VALUES = ("#777a92", "#9a85ff")


def test_each_theme_has_the_same_hex_keys():
    assert set(PALETTES) == {"light", "dark"}
    for theme, colors in PALETTES.items():
        assert set(colors) == EXPECTED_KEYS, theme
        for key, value in colors.items():
            assert isinstance(value, str), (theme, key)
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), (theme, key, value)


def test_pairs_are_built_from_both_palettes():
    assert set(PAIRS) == EXPECTED_KEYS
    for key, (light, dark) in PAIRS.items():
        assert light == PALETTES["light"][key]
        assert dark == PALETTES["dark"][key]


def test_audit_is_v1_and_all_pairs_pass():
    report = audit()
    assert set(report) == {"light", "dark"}
    for theme in ("light", "dark"):
        assert set(report[theme]) == REQUIRED_AUDITS
        for pair, row in report[theme].items():
            assert isinstance(row["ratio"], float), (theme, pair)
            assert isinstance(row["minimum"], float), (theme, pair)
            assert isinstance(row["ok"], bool), (theme, pair)
            assert row["ratio"] >= row["minimum"], (theme, pair, row)
            assert row["ok"] is True, (theme, pair, row)

    assert all(row["ok"] for rows in report.values() for row in rows.values())


def test_critical_pairs_meet_direct_thresholds():
    light = PALETTES["light"]
    dark = PALETTES["dark"]

    # Body/secondary copy and status text: 4.5:1.
    for colors in (light, dark):
        assert contrast_ratio(colors["dim"], colors["bg"]) >= 4.5
        assert contrast_ratio(colors["dim"], colors["panel"]) >= 4.5
        assert contrast_ratio(colors["fg"], colors["panel"]) >= 4.5
        assert contrast_ratio(colors["ok"], colors["panel"]) >= 4.5
        assert contrast_ratio(colors["warn"], colors["panel"]) >= 4.5
        assert contrast_ratio(colors["bad"], colors["panel"]) >= 4.5
        assert contrast_ratio(colors["accent_text"],
                              colors["accent_soft"]) >= 4.5

    # Primary-button label: this is the pair that was 2.28:1 before.
    for colors in (light, dark):
        assert contrast_ratio(colors["on_accent"],
                              colors["accent_fill"]) >= 4.5

    # Control boundary and focus ring: 3:1.
    for colors in (light, dark):
        assert contrast_ratio(colors["border_strong"],
                              colors["panel"]) >= 3.0
        assert contrast_ratio(colors["focus"], colors["bg"]) >= 3.0


def test_font_roles_have_readable_minimums():
    assert FONT_ROLES == {
        "page": 24,
        "section": 16,
        "card_title": 13,
        "body": 12,
        "secondary": 11,
        "meta": 10,
        "mono": 11,
    }
    assert min(FONT_ROLES.values()) >= 10
    assert FONT_ROLES["body"] >= 12
    assert FONT_ROLES["page"] >= 24
    assert FONT_ROLES["page"] > FONT_ROLES["section"] > FONT_ROLES["body"]
    assert FONT_ROLES["body"] > FONT_ROLES["secondary"] >= FONT_ROLES["meta"]


def test_spacing_and_radius_only_increase():
    assert SPACING == (4, 8, 12, 16, 24, 32)
    assert all(later > earlier
               for earlier, later in zip(SPACING, SPACING[1:]))
    assert set(RADIUS) == {"control", "button", "card"}
    assert RADIUS["control"] < RADIUS["button"] < RADIUS["card"]
    assert all(value % 2 == 0 for value in SPACING)


def test_palette_falls_back_to_dark_and_returns_a_copy():
    fallback = palette("nope")
    assert fallback == PALETTES["dark"]
    assert fallback is not PALETTES["dark"]

    fallback["bg"] = "#123456"
    assert PALETTES["dark"]["bg"] == "#11121a"

    light = palette("light")
    assert light == PALETTES["light"]
    assert light is not PALETTES["light"]
    light["fg"] = "#000000"
    assert PALETTES["light"]["fg"] == "#202136"

    assert palette("dark") == PALETTES["dark"]
    assert palette(None) == PALETTES["dark"]


def test_legacy_appgui_values_are_not_button_text_tokens():
    tokens = {
        value.lower()
        for colors in PALETTES.values()
        for value in colors.values()
    }
    for legacy in LEGACY_TEXT_VALUES:
        assert legacy not in tokens, legacy
        assert legacy not in PAIRS["on_accent"]
        assert legacy not in PAIRS["accent_text"]


def test_contrast_ratio_reference_values_and_symmetry():
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert contrast_ratio("#777777", "#ffffff") == contrast_ratio(
        "#ffffff", "#777777")
    assert contrast_ratio(PALETTES["light"]["fg"],
                          PALETTES["light"]["fg"]) == pytest.approx(1.0)


def test_contrast_ratio_rejects_malformed_colours():
    for bad in ("", "#fff", "#1234567", "123456", "#gggggg", "#12 456",
                None, 0xFFFFFF):
        with pytest.raises(ValueError):
            contrast_ratio(bad, "#ffffff")
        with pytest.raises(ValueError):
            contrast_ratio("#ffffff", bad)
