"""Tests for explicit, verified font subsetting without touching game files."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import font_subset  # noqa: E402


def test_normalize_codepoints_deduplicates_and_discards_invalid_values():
    assert font_subset.normalize_codepoints(
        [65, 0x4E00, 65, -1, 0x110000, 0xD800, True, "65", None]
    ) == (65, 0x4E00)


@pytest.mark.parametrize("value", ["abc", b"abc", bytearray(b"abc"), None])
def test_normalize_rejects_ambiguous_or_non_iterable_input(value):
    with pytest.raises(TypeError):
        font_subset.normalize_codepoints(value)


def test_subset_fails_clearly_if_fonttools_is_missing(monkeypatch, tmp_path):
    source = tmp_path / "source.ttf"
    source.write_bytes(b"not parsed because dependency import fails")

    def missing_dependency():
        raise font_subset.FontSubsetDependencyError("fontTools missing")

    monkeypatch.setattr(font_subset, "_load_fonttools", missing_dependency)
    with pytest.raises(font_subset.FontSubsetDependencyError, match="fontTools"):
        font_subset.subset_font(source, tmp_path / "out.ttf", [65])


def _make_synthetic_font(path: Path):
    """Build a tiny valid TTF with predictable cmap coverage via fontTools."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    glyph_order = [".notdef", "space", "A", "B", "uni4E00", "uni3002"]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)

    cmap = {
        0x20: "space",
        0x41: "A",
        0x42: "B",
        0x4E00: "uni4E00",
        0x3002: "uni3002",
    }
    fb.setupCharacterMap(cmap)

    glyphs = {}
    for glyph_name in glyph_order:
        pen = TTGlyphPen(None)
        if glyph_name not in (".notdef", "space"):
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
        glyphs[glyph_name] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Subset Fixture", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupMaxp()
    fb.save(str(path))


def test_subset_writes_small_verified_font_atomically(tmp_path):
    pytest.importorskip("fontTools")
    from fontTools.ttLib import TTFont

    source = tmp_path / "source.ttf"
    output = tmp_path / "nested" / "subset.ttf"
    output.parent.mkdir()
    _make_synthetic_font(source)
    old_output = b"previous result"
    output.write_bytes(old_output)

    result = font_subset.subset_font(source, output, [0x4E00, 0x4E00, -1, 0x3002])

    assert result.destination_path == output.resolve()
    assert result.requested_codepoints == (0x3002, 0x4E00)
    assert 0x41 in result.included_codepoints  # printable ASCII baseline
    assert 0x3002 in result.included_codepoints  # caller-requested punctuation
    assert result.output_size == output.stat().st_size
    assert result.output_size <= result.source_size
    with TTFont(str(output)) as font:
        cmap = font.getBestCmap()
        assert 0x4E00 in cmap and 0x3002 in cmap and 0x41 in cmap
        assert 0x42 in cmap  # retained as a baseline ASCII glyph
    assert not list(output.parent.glob(".%s.*.tmp" % output.name))


def test_missing_requested_glyph_keeps_existing_output_untouched(tmp_path):
    pytest.importorskip("fontTools")
    source = tmp_path / "source.ttf"
    output = tmp_path / "out.ttf"
    _make_synthetic_font(source)
    output.write_bytes(b"keep me")

    with pytest.raises(font_subset.UncoveredCodepointsError) as exc:
        font_subset.subset_font(source, output, [0x4E01])
    assert 0x4E01 in exc.value.codepoints
    assert output.read_bytes() == b"keep me"


def test_source_and_destination_must_differ(tmp_path):
    source = tmp_path / "font.ttf"
    source.write_bytes(b"placeholder")
    with pytest.raises(ValueError, match="different files"):
        font_subset.subset_font(source, source, [65])

