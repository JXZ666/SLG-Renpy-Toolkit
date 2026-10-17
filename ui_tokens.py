"""Canonical UI tokens for the toolkit's desktop interface.

This module is the single source of truth for interface colours, type sizes,
spacing steps, corner radii and contrast auditing.  ``appgui`` and every other
view module must import these tokens instead of scattering literal ``#rrggbb``
strings or one-off font sizes through the widget code.  Changing the visual
system here changes it everywhere, and :func:`audit` proves the text and control
boundaries still meet the WCAG thresholds.

The module is deliberately dependency-free: it imports neither CustomTkinter nor
any other project module, so it can be audited and unit-tested on its own.
"""

from __future__ import annotations

PALETTES = {
    "light": {
        "bg": "#f4f5fb",
        "sidebar": "#ffffff",
        "panel": "#ffffff",
        "panel_alt": "#f6f7fb",
        "input": "#ffffff",
        "fg": "#202136",
        "dim": "#5f6278",
        "border": "#d5d7e6",
        "border_strong": "#8e92a8",
        "accent_fill": "#6a4fdd",
        "accent_hover": "#5a3fce",
        "accent_text": "#5b3fd6",
        "accent_soft": "#eeeaff",
        "on_accent": "#ffffff",
        "focus": "#5b3fd6",
        "ok": "#18794e",
        "warn": "#8a5a00",
        "bad": "#b83245",
        "select": "#ded8ff",
        "text_disabled": "#6b6f86",
    },
    "dark": {
        "bg": "#11121a",
        "sidebar": "#161824",
        "panel": "#1a1c29",
        "panel_alt": "#222437",
        "input": "#202232",
        "fg": "#f0eff8",
        "dim": "#b4b7c9",
        "border": "#3b3e57",
        "border_strong": "#6f7390",
        "accent_fill": "#6a4fdd",
        "accent_hover": "#5a3fce",
        "accent_text": "#b2a3ff",
        "accent_soft": "#302a4a",
        "on_accent": "#ffffff",
        "focus": "#c9bfff",
        "ok": "#79d8a4",
        "warn": "#ffca69",
        "bad": "#ff8797",
        "select": "#463b72",
        "text_disabled": "#9ea2b8",
    },
}

PAIRS = {name: (PALETTES["light"][name], PALETTES["dark"][name])
         for name in PALETTES["light"]}

FONT_ROLES = {
    "page": 24,
    "section": 16,
    "card_title": 13,
    "body": 12,
    "secondary": 11,
    "meta": 10,
    "mono": 11,
}

SPACING = (4, 8, 12, 16, 24, 32)

RADIUS = {"control": 6, "button": 10, "card": 14}

# Audited "foreground/background" pairs and the WCAG minimum each must reach.
# Body copy needs 4.5:1.  Large text, focus rings and the strong border that
# marks a control's edge need 3:1.  ``accent_fill/on_accent`` is the primary
# button's text, so it is held to the body-text threshold even though the
# label is often bold.
_AUDIT_PAIRS = (
    ("dim/bg", 4.5),
    ("dim/panel", 4.5),
    ("fg/panel", 4.5),
    ("accent_fill/on_accent", 4.5),
    ("accent_text/accent_soft", 4.5),
    ("border_strong/panel", 3.0),
    ("ok/panel", 4.5),
    ("warn/panel", 4.5),
    ("bad/panel", 4.5),
    ("focus/bg", 3.0),
)

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _relative_luminance(color):
    """WCAG 2.x relative luminance of an opaque ``#rrggbb`` colour."""
    if not isinstance(color, str) or len(color) != 7 or color[0] != "#":
        raise ValueError(f"expected a #rrggbb colour, got {color!r}")
    digits = color[1:]
    if any(char not in _HEX_DIGITS for char in digits):
        raise ValueError(f"expected a #rrggbb colour, got {color!r}")
    channels = (int(digits[0:2], 16), int(digits[2:4], 16),
                int(digits[4:6], 16))

    def linear(value):
        value = value / 255.0
        if value <= 0.04045:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(fg, bg):
    """Return the WCAG contrast ratio between two ``#rrggbb`` colours.

    Raises :class:`ValueError` for anything that is not an opaque six-digit
    hex colour.  The result is symmetric and ranges from 1.0 to 21.0.
    """
    fg_luminance = _relative_luminance(fg)
    bg_luminance = _relative_luminance(bg)
    lighter = max(fg_luminance, bg_luminance)
    darker = min(fg_luminance, bg_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def palette(theme):
    """Return a copy of the requested palette; unknown themes fall back to dark."""
    key = theme if theme in PALETTES else "dark"
    return dict(PALETTES[key])


def audit():
    """Audit the required foreground/background pairs for both themes.

    Returns ``{theme: {pair: {"ratio": float, "minimum": float, "ok": bool}}}``.
    """
    report = {}
    for theme, colors in PALETTES.items():
        rows = {}
        for pair, minimum in _AUDIT_PAIRS:
            foreground, background = pair.split("/")
            ratio = contrast_ratio(colors[foreground], colors[background])
            rows[pair] = {
                "ratio": ratio,
                "minimum": minimum,
                "ok": ratio >= minimum,
            }
        report[theme] = rows
    return report


__all__ = [
    "PALETTES",
    "PAIRS",
    "FONT_ROLES",
    "SPACING",
    "RADIUS",
    "palette",
    "contrast_ratio",
    "audit",
]
