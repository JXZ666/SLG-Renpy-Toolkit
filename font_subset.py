"""Create a checked, atomic Unicode subset of a TrueType/OpenType font.

fontTools is deliberately imported only when :func:`subset_font` is called,
so the rest of the toolkit can still start when the optional subsetting
dependency has not been installed.  The caller supplies the codepoints to
keep; this module never scans a game or guesses which text it needs.  The
caller must derive them from the text that will actually be displayed (for
example translated strings or an explicit corpus).  Original English scripts
alone do not describe future Chinese translations and are not a safe source
for deciding which Hanzi to retain.

By default, the subset also keeps printable ASCII (U+0020..U+007E) and a
small, fixed set of common CJK punctuation.  Only baseline characters that
exist in the source font are kept.  Requested valid characters must exist in
the source cmap; otherwise the operation fails before touching the output.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Iterable


# Keep this list deliberately small and explicit.  It covers common Chinese
# sentence punctuation and quotation/bracket marks, rather than all Unicode
# punctuation or every full-width symbol.
BASE_CJK_PUNCTUATION = "　、。，．！？；：‘’“”「」『』《》〈〉（）【】—…·"
BASE_CODEPOINTS = frozenset(range(0x20, 0x7F)) | frozenset(
    ord(char) for char in BASE_CJK_PUNCTUATION
)


class FontSubsetError(RuntimeError):
    """The font could not be safely subsetted or verified."""


class FontSubsetDependencyError(FontSubsetError):
    """fontTools is required to create a subset but is not installed."""


class UncoveredCodepointsError(FontSubsetError):
    """The source font does not contain one or more requested characters."""

    def __init__(self, codepoints: Iterable[int]):
        self.codepoints = tuple(sorted(set(codepoints)))
        shown = ", ".join("U+%04X" % cp for cp in self.codepoints[:12])
        if len(self.codepoints) > 12:
            shown += ", … (%d total)" % len(self.codepoints)
        super().__init__("Source font is missing requested codepoints: " + shown)


class SubsetTooLargeError(FontSubsetError):
    """The generated subset is larger than its source font."""


@dataclass(frozen=True)
class SubsetResult:
    """Verified output information returned by :func:`subset_font`."""

    source_path: Path
    destination_path: Path
    requested_codepoints: tuple[int, ...]
    included_codepoints: tuple[int, ...]
    added_baseline_codepoints: tuple[int, ...]
    source_size: int
    output_size: int


def normalize_codepoints(codepoints: Iterable[object]) -> tuple[int, ...]:
    """Return unique valid Unicode scalar values, in ascending order.

    Non-integer values, values outside U+0000..U+10FFFF, and UTF-16
    surrogate values are discarded.  ``bool`` is excluded even though it is
    an ``int`` subclass.  A string/bytes object is rejected because accepting
    it would ambiguously treat its characters as codepoints.
    """
    if isinstance(codepoints, (str, bytes, bytearray)):
        raise TypeError("codepoints must be an iterable of integer codepoints")
    try:
        iterator = iter(codepoints)
    except TypeError as exc:
        raise TypeError("codepoints must be an iterable of integer codepoints") from exc

    valid = set()
    for cp in iterator:
        if not isinstance(cp, int) or isinstance(cp, bool):
            continue
        if cp < 0 or cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            continue
        valid.add(cp)
    return tuple(sorted(valid))


def _load_fonttools():
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ModuleNotFoundError as exc:
        raise FontSubsetDependencyError(
            "Font subsetting requires fontTools. Install it with: "
            "python -m pip install fonttools"
        ) from exc
    return subset, TTFont


def _font_codepoints(font) -> set[int]:
    cmap = font.get("cmap")
    if cmap is None:
        raise FontSubsetError("Source font has no cmap table")
    result = set()
    for table in cmap.tables:
        if getattr(table, "isUnicode", lambda: False)():
            result.update(table.cmap)
    return result


def subset_font(
    source: os.PathLike | str,
    destination: os.PathLike | str,
    codepoints: Iterable[object],
    *,
    preserve_baseline: bool = True,
) -> SubsetResult:
    """Subset ``source`` for ``codepoints`` and atomically write destination.

    ``codepoints`` should be derived from the expected display corpus.  Do
    not use only the original scripts of a game when the font will render
    Chinese text introduced by a translation; the original scripts cannot
    reveal those translated Hanzi.

    Invalid Unicode values in the request are ignored; an empty valid request
    raises ``ValueError``.  All remaining requested values must be covered by
    the source font.  When ``preserve_baseline`` is true, printable ASCII and
    the punctuation listed in :data:`BASE_CODEPOINTS` are included where the
    source has glyphs for them.

    The function writes a same-directory temporary font, reopens it to verify
    the cmap, checks that it is no larger than the source, and only then uses
    ``os.replace``.  Existing output is therefore left intact on failure.
    The source and destination must be different files and the destination
    directory must already exist.
    """
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if source_path == destination_path:
        raise ValueError("source and destination must be different files")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if not destination_path.parent.is_dir():
        raise FileNotFoundError("Destination directory does not exist: %s" % destination_path.parent)

    requested = normalize_codepoints(codepoints)
    if not requested:
        raise ValueError("At least one valid requested codepoint is required")

    subset, TTFont = _load_fonttools()
    source_size = source_path.stat().st_size
    font = None
    check_font = None
    temporary_path = None
    try:
        try:
            font = TTFont(str(source_path), lazy=False)
            source_cmap = _font_codepoints(font)
        except FontSubsetError:
            raise
        except Exception as exc:
            raise FontSubsetError("Could not read source font: %s" % exc) from exc

        missing = set(requested) - source_cmap
        if missing:
            raise UncoveredCodepointsError(missing)

        baseline = BASE_CODEPOINTS & source_cmap if preserve_baseline else set()
        included = set(requested) | baseline

        options = subset.Options()
        options.layout_features = ["*"]
        options.notdef_glyph = True
        options.notdef_outline = True
        options.recommended_glyphs = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=sorted(included))
        subsetter.subset(font)

        with tempfile.NamedTemporaryFile(
            prefix=".%s." % destination_path.name,
            suffix=".tmp",
            dir=str(destination_path.parent),
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        font.save(str(temporary_path))
        if temporary_path.stat().st_size > source_size:
            raise SubsetTooLargeError(
                "Subset is larger than source (%d > %d bytes)"
                % (temporary_path.stat().st_size, source_size)
            )

        try:
            check_font = TTFont(str(temporary_path), lazy=False)
            output_cmap = _font_codepoints(check_font)
        except Exception as exc:
            raise FontSubsetError("Generated subset could not be reopened: %s" % exc) from exc
        missing_after_save = included - output_cmap
        if missing_after_save:
            raise FontSubsetError(
                "Generated subset did not retain codepoints: "
                + ", ".join("U+%04X" % cp for cp in sorted(missing_after_save)[:12])
            )

        output_size = temporary_path.stat().st_size
        # Close before replacement: Windows does not allow renaming an open
        # file in the usual sharing mode.
        check_font.close()
        check_font = None
        os.replace(str(temporary_path), str(destination_path))
        temporary_path = None
        return SubsetResult(
            source_path=source_path,
            destination_path=destination_path,
            requested_codepoints=requested,
            included_codepoints=tuple(sorted(included)),
            added_baseline_codepoints=tuple(sorted(baseline - set(requested))),
            source_size=source_size,
            output_size=output_size,
        )
    finally:
        if check_font is not None:
            check_font.close()
        if font is not None:
            font.close()
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
