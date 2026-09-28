"""Tests for the font merge an engine older than Ren'Py 7.6 needs.

The interesting properties are not "does it produce a file" but the four that
each broke the merge against a real game before they were handled, so each has
a test that names it:

  * a base font with a codepoint the CJK font also has must keep its own glyph -
    losing Latin is the one failure worse than the tofu being fixed;
  * the two fonts routinely disagree on unitsPerEm, and one of them has to be
    scaled;
  * a table only one of them carries aborts the merge outright, so it has to be
    dropped from both rather than left to the merger;
  * a table both of them carry can still abort it, because the merger
    reconciles the layout tables by value - so those are dropped on a second
    attempt rather than on the first.

All input fonts here are synthesized, so the suite proves the code's own
contract rather than the behaviour of a particular shipped Noto build.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import font_merge  # noqa: E402


def _make_font(path, codepoints, *, upem=1000, family="Fixture", extra_tables=(),
               features=None):
    """A tiny valid TTF with exactly the given cmap coverage."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = [".notdef"] + ["g%04X" % cp for cp in codepoints]
    fb = FontBuilder(upem, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({cp: "g%04X" % cp for cp in codepoints})

    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 0) for name in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    if features:
        fb.addOpenTypeFeatures(features)
    fb.save(str(path))

    if extra_tables:
        from fontTools.ttLib import TTFont
        font = TTFont(str(path), lazy=False)
        for tag, value in extra_tables:
            font[tag] = value
        font.save(str(path))


def _cvt(values):
    """A `cvt ` table, which is the cheapest way to make one side asymmetric."""
    import array
    from fontTools.ttLib import newTable

    table = newTable("cvt ")
    table.values = array.array("h", values)
    return ("cvt ", table)


def _cmap(path):
    from fontTools.ttLib import TTFont
    font = TTFont(str(path), lazy=False)
    try:
        out = set()
        for table in font["cmap"].tables:
            if getattr(table, "isUnicode", lambda: False)():
                out.update(table.cmap)
        return out
    finally:
        font.close()


def test_merge_keeps_every_base_codepoint_and_adds_the_cjk_ones(tmp_path):
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, range(0x41, 0x5B), family="Base")
    _make_font(cjk, [0x4E2D, 0x9F99, 0x4F60, 0x3002], family="Cjk")

    result = font_merge.merge_font(base, cjk, tmp_path / "merged.ttf")

    merged = _cmap(result.destination_path)
    assert set(range(0x41, 0x5B)) <= merged
    assert {0x4E2D, 0x9F99, 0x4F60, 0x3002} <= merged
    assert result.base_codepoints == 26
    assert result.added_codepoints == 4
    assert result.output_size > 0


def test_the_cjk_font_is_scaled_to_the_base_em_not_the_other_way_round(tmp_path):
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41], upem=2048, family="Base")
    _make_font(cjk, [0x4E2D], upem=1000, family="Cjk")

    result = font_merge.merge_font(base, cjk, tmp_path / "merged.ttf")

    from fontTools.ttLib import TTFont
    merged = TTFont(str(result.destination_path), lazy=True)
    try:
        assert merged["head"].unitsPerEm == 2048
    finally:
        merged.close()
    assert result.units_per_em == 2048
    assert {0x41, 0x4E2D} <= _cmap(result.destination_path)


def test_a_table_only_one_side_has_is_dropped_rather_than_aborting_the_merge(tmp_path):
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41], family="Base")
    _make_font(cjk, [0x4E2D], family="Cjk", extra_tables=[_cvt([10, 20])])

    result = font_merge.merge_font(base, cjk, tmp_path / "merged.ttf")

    assert result.dropped_tables == ("cvt ",)
    from fontTools.ttLib import TTFont
    merged = TTFont(str(result.destination_path), lazy=True)
    try:
        assert "cvt " not in merged
    finally:
        merged.close()


def test_a_matched_pair_drops_nothing(tmp_path):
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41], family="Base")
    _make_font(cjk, [0x4E2D], family="Cjk")

    result = font_merge.merge_font(base, cjk, tmp_path / "merged.ttf")

    assert result.dropped_tables == ()


# A GSUB both fixtures can carry, spelled against the glyph names _make_font
# mints. Two fonts built from the same source get structurally identical tables,
# which is the point: they match.
_GSUB = "languagesystem DFLT dflt;\nfeature liga { sub g0041 by g0042; } liga;\n"


def test_a_table_both_fonts_carry_is_dropped_on_a_second_attempt(tmp_path, monkeypatch):
    """DejaVu's GSUB aborts the merger; a second attempt without it succeeds.

    `mergeLangSyses` asserts every LangSys.ReqFeatureIndex is 0xFFFF, and
    DejaVu's `latn` langsys has a real one where an instanced Noto has the
    sentinel. Because both fonts carry GSUB the asymmetry test cannot see it, so
    the first attempt is made with it kept.

    The first attempt is stubbed rather than reproduced, because the assertion
    lives deep inside fontTools and no fixture cheaply provokes it. What is under
    test is this module's retry and its honest report of what the retry cost.
    """
    pytest.importorskip("fontTools")
    import fontTools.merge
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.scaleUpem import scale_upem
    from fontTools.varLib import instancer

    real = fontTools.merge.Merger
    attempted = []

    class FlakyMerger(object):
        """The real merger, failing the first call the way fontTools does."""

        def __init__(self, options=None):
            if options is None:
                self.options = real().options
                self._delegate = None
            else:
                self.options = options
                self._delegate = real(options=options)

        def merge(self, paths):
            attempted.append(tuple(self.options.drop_tables))
            if len(attempted) == 1:
                raise AssertionError("same as mergeLangSyses")
            return self._delegate.merge(paths)

    monkeypatch.setattr(
        font_merge, "_load_fonttools",
        lambda: (FlakyMerger, TTFont, scale_upem, instancer, None))

    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41, 0x42], family="Base", features=_GSUB)
    _make_font(cjk, [0x41, 0x42, 0x4E2D], family="Cjk", features=_GSUB)

    result = font_merge.merge_font(base, cjk, tmp_path / "merged.ttf")

    assert len(attempted) == 2, attempted
    assert "GSUB" not in attempted[0], "the first attempt must keep a shared table"
    assert "GSUB" in attempted[1], "the retry must drop it"
    assert "GSUB" in result.dropped_tables, result.dropped_tables
    assert {0x41, 0x42, 0x4E2D} <= _cmap(result.destination_path)


def test_a_pair_whose_layout_tables_reconcile_keeps_them(tmp_path):
    """The retry must not fire when the first attempt was never needed."""
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41, 0x42], family="Base", features=_GSUB)
    _make_font(cjk, [0x41, 0x42, 0x4E2D], family="Cjk", features=_GSUB)

    result = font_merge.merge_font(base, cjk, tmp_path / "merged.ttf")

    assert result.dropped_tables == ()
    from fontTools.ttLib import TTFont
    merged = TTFont(str(result.destination_path), lazy=True)
    try:
        assert "GSUB" in merged
    finally:
        merged.close()


def test_a_failed_merge_leaves_an_existing_destination_untouched(tmp_path):
    pytest.importorskip("fontTools")
    cjk = tmp_path / "cjk.ttf"
    _make_font(cjk, [0x4E2D], family="Cjk")
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"\x00\x01\x00\x00 not a font at all")
    destination = tmp_path / "merged.ttf"
    destination.write_bytes(b"the previous install")

    with pytest.raises(font_merge.FontMergeError):
        font_merge.merge_font(broken, cjk, destination)

    assert destination.read_bytes() == b"the previous install"
    assert [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")] == []


def test_bytes_are_accepted_where_a_path_is(tmp_path):
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41], family="Base")
    _make_font(cjk, [0x4E2D], family="Cjk")

    result = font_merge.merge_font(base.read_bytes(), cjk.read_bytes(),
                                   tmp_path / "merged.ttf")

    assert {0x41, 0x4E2D} <= _cmap(result.destination_path)


def test_missing_dependency_is_reported_rather_than_raised_raw(monkeypatch, tmp_path):
    def missing():
        raise font_merge.FontMergeDependencyError("fontTools missing")

    monkeypatch.setattr(font_merge, "_load_fonttools", missing)
    with pytest.raises(font_merge.FontMergeDependencyError, match="fontTools"):
        font_merge.merge_font(tmp_path / "a.ttf", tmp_path / "b.ttf",
                              tmp_path / "out.ttf")


def test_fonttools_available_matches_whether_the_import_works():
    import importlib.util
    assert font_merge.fonttools_available() == (
        importlib.util.find_spec("fontTools") is not None)


def test_cache_key_changes_with_either_input(tmp_path):
    a = tmp_path / "a.ttf"
    b = tmp_path / "b.ttf"
    c = tmp_path / "c.ttf"
    for path, payload in ((a, b"one"), (b, b"two"), (c, b"three")):
        path.write_bytes(payload)

    assert font_merge.cache_key(a, b) == font_merge.cache_key(a, b)
    assert font_merge.cache_key(a, b) != font_merge.cache_key(a, c)
    assert font_merge.cache_key(a, b) != font_merge.cache_key(b, a)


def test_a_second_install_reuses_the_cached_merge(tmp_path):
    pytest.importorskip("fontTools")
    base = tmp_path / "base.ttf"
    cjk = tmp_path / "cjk.ttf"
    _make_font(base, [0x41], family="Base")
    _make_font(cjk, [0x4E2D], family="Cjk")
    cache = tmp_path / "cache"

    first = tmp_path / "one" / "merged.ttf"
    first.parent.mkdir()
    _dest, _size, from_cache = font_merge.install_cached(base, cjk, first, cache)
    assert from_cache is False

    second = tmp_path / "two" / "merged.ttf"
    second.parent.mkdir()
    _dest, _size, from_cache = font_merge.install_cached(base, cjk, second, cache)
    assert from_cache is True
    assert first.read_bytes() == second.read_bytes()


def test_a_borrowed_cache_entry_survives_a_failed_merge(tmp_path):
    """The caller's cleanup must not delete a `prepared_cjk` it was lent.

    Staging the CJK font costs about a dozen seconds on the real Noto, so a
    failed merge that took the staged file down with it would make the retry pay
    that cost again for nothing.
    """
    pytest.importorskip("fontTools")
    cjk = tmp_path / "cjk.ttf"
    _make_font(cjk, [0x4E2D], family="Cjk")
    cache = tmp_path / "cache"
    prepared = font_merge.prepared_cjk(cjk, cache)
    assert os.path.isfile(prepared)

    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")
    with pytest.raises(font_merge.FontMergeError):
        font_merge.merge_font(broken, cjk, tmp_path / "merged.ttf",
                              prepared_cjk=prepared)

    assert os.path.isfile(prepared)
