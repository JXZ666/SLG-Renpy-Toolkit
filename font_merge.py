"""Fuse the bundled CJK font into a game's own face, for engines that need a file.

Ren'Py learned ``config.font_name_map`` at 7.6. That is the clean way to point a
font *name* at a :class:`FontGroup`, and it is what the shim uses on a new
engine. The whole 6 through 7.5 range predates it: there, a name is resolved to
a file inside ``renpy/text/font.py:get_font`` and the only hook is
``config.font_replacement_map``, whose value must be loadable by ``load_face`` -
a path, not a group. So an old engine cannot be handed two fonts; it has to be
handed one file that already contains both the game's Latin and our Hanzi.

That is what this module produces. The game's face supplies the Latin glyphs and
therefore its own styling; Noto Sans SC supplies the Hanzi; the pair is merged
into a single TrueType file that the shim points ``font_replacement_map`` at.

Three properties of the merge turned out to be load-bearing on real games, each
found by trying it and watching it fail:

  * Noto as shipped is a *variable* font, and ``fontTools.merge`` aborts on one
    (``VarStore has no attribute mergeMap``). It is instanced to a static
    weight first, which is also the safer artifact for the FreeType that ships
    in a Ren'Py 7 build.
  * ``merge`` refuses two fonts with different ``unitsPerEm`` outright, and a
    game's display face is often 2048 where Noto is 1000. The CJK side is
    scaled to the base's em, never the reverse: the base's outlines and metrics
    are then untouched, which is the half of the result that must look right.
  * ``merge`` builds the union of every table *key* across both fonts and
    compares the values with ``min``/``max``, so a table only one of them has
    crashes it on ``int < NotImplemented``. Tables absent from either side are
    dropped from both, which is the least destructive way to get a mergeable
    pair.

fontTools is an optional dependency and is imported only when a merge is asked
for: the rest of the toolkit starts without it, and a caller that needs a merge
reports the dependency rather than crashing.

The output is verified by reopening it and re-reading its cmap, because a font
that silently lost its Latin glyphs would render the game's own English as
boxes - a louder failure than the tofu it was meant to fix.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterable

# Bump when the recipe changes in any way that would alter the bytes produced.
# The cache in front of this module is keyed on it, so an old merged font is
# never mistaken for one made by the current code.
MERGE_VERSION = 1

# The weight Noto Sans SC is instanced at. Regular, and the only weight the
# shim asks for - synthetic bold is applied by FreeType on top.
DEFAULT_WEIGHT = 400

# Tables no font can be built without. A merge that drops one of these has
# produced something unloadable, so their absence is checked rather than
# assumed.
REQUIRED_TABLES = ("cmap", "head", "hhea", "hmtx", "maxp", "name")

# Tables `Merger` reconciles by value rather than by union, so a pair that both
# carry them can still abort on a disagreement. Only ever dropped on a second
# attempt, after the union-shaped merge has already failed.
LAYOUT_TABLES = ("GSUB", "GPOS", "GDEF", "BASE", "JSTF")


class FontMergeError(RuntimeError):
    """The fonts could not be merged, or the result did not verify."""


class FontMergeDependencyError(FontMergeError):
    """fontTools is required to merge fonts but is not installed."""


class NotMergedError(FontMergeError):
    """The merge ran but the output lost codepoints the base font had."""

    def __init__(self, lost: Iterable[int]):
        self.lost = tuple(sorted(set(lost)))
        shown = ", ".join("U+%04X" % cp for cp in self.lost[:12])
        if len(self.lost) > 12:
            shown += ", … (%d total)" % len(self.lost)
        super().__init__("Merged font lost base codepoints: " + shown)


@dataclass(frozen=True)
class MergeResult:
    """Verified output information returned by :func:`merge_font`."""

    base_path: Path
    cjk_path: Path
    destination_path: Path
    base_codepoints: int
    added_codepoints: int
    units_per_em: int
    base_size: int
    output_size: int
    dropped_tables: tuple[str, ...]


def fonttools_available() -> bool:
    """Whether a merge can be attempted, without importing fontTools.

    ``find_spec`` is used rather than an import: the pre-flight asks this on
    every folder change and must stay cheap, and a broken fontTools install
    should read as "unavailable" here rather than raising into a survey.
    """
    import importlib.util
    try:
        return importlib.util.find_spec("fontTools") is not None
    except (ImportError, ValueError):
        return False


def _load_fonttools():
    try:
        from fontTools import __version__
        from fontTools.merge import Merger
        from fontTools.ttLib import TTFont
        from fontTools.ttLib.scaleUpem import scale_upem
        from fontTools.varLib import instancer
    except ModuleNotFoundError as exc:
        raise FontMergeDependencyError(
            "Merging a font for this engine requires fontTools. Install it with: "
            "python -m pip install fonttools"
        ) from exc
    return Merger, TTFont, scale_upem, instancer, __version__


def _unicode_cmap(font) -> set:
    table = font.get("cmap")
    if table is None:
        raise FontMergeError("font has no cmap table")
    out = set()
    for sub in table.tables:
        if getattr(sub, "isUnicode", lambda: False)():
            out.update(sub.cmap)
    return out


def cache_key(base_path, cjk_path) -> str:
    """A stable key for the merge of these two files.

    Both sides are hashed: the bundled CJK font is fixed today but is not
    promised to stay so, and a cache that ignored it would serve a stale merge
    after a Noto upgrade.
    """
    h = hashlib.sha256()
    h.update(("rpykit-merge-v%d" % MERGE_VERSION).encode("ascii"))
    for path in (base_path, cjk_path):
        h.update(b"\x00")
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()[:32]


def cached_merge(base, cjk, cache_dir, *, cjk_weight=DEFAULT_WEIGHT):
    """Merge, reusing a previous result when the inputs hash the same.

    Returns ``(path, from_cache)``. The caller gets the cached file's path
    rather than a fresh copy because the merge is defined as a pure function of
    the two inputs: equal key means equal bytes.

    Bytes are accepted as well as paths, because a game's fonts are frequently
    inside an .rpa and only ever exist in memory.
    """
    Merger, TTFont, scale_upem, instancer, _version = _load_fonttools()
    scratch = []
    try:
        base_path, temp_a = _as_path(base)
        cjk_path, temp_b = _as_path(cjk)
        scratch = [p for p in (temp_a, temp_b) if p]

        probe = TTFont(base_path, lazy=True)
        try:
            base_upem = probe["head"].unitsPerEm
        finally:
            probe.close()

        key = cache_key(base_path, cjk_path)
        cached = os.path.join(cache_dir, key + ".ttf")
        os.makedirs(cache_dir, exist_ok=True)
        if os.path.isfile(cached) and os.path.getsize(cached) > 0:
            return cached, True

        prepared = _prepared_cjk(cjk_path, base_upem, cjk_weight, cache_dir)
        result = merge_font(base_path, cjk_path, cached,
                            cjk_weight=cjk_weight, prepared_cjk=prepared)
        return str(result.destination_path), False
    finally:
        for path in scratch:
            try:
                os.remove(path)
            except OSError:
                pass


def prepared_cjk(cjk, cache_dir, *, upem=None, cjk_weight=DEFAULT_WEIGHT):
    """A static copy of the CJK font, at its own em unless ``upem`` says otherwise.

    For a face whose own Latin is unusable the shim needs no merge at all - only
    a font that draws Hanzi. Ren'Py 7 ships FreeType from before variable fonts
    were common, so what it is given here is the instanced static font, never the
    variable original.
    """
    _Merger, TTFont, _scale, _inst, _version = _load_fonttools()
    path, temp = _as_path(cjk)
    try:
        if upem is None:
            probe = TTFont(path, lazy=True)
            try:
                upem = probe["head"].unitsPerEm
            finally:
                probe.close()
        return _prepared_cjk(path, upem, cjk_weight, cache_dir)
    finally:
        if temp:
            try:
                os.remove(temp)
            except OSError:
                pass


def _prepared_cjk(cjk_path, upem, weight, cache_dir):
    """The CJK font instanced and scaled, cached on the em it was scaled to.

    Instancing a 30k-glyph variable font costs about nine seconds and scaling it
    another eight, and both are pure functions of inputs far smaller than the
    work: the file, the weight, the target em. Caching the *prepared* font
    rather than only the final merge is what makes a game's second face cheap,
    and it is why a game whose faces disagree on unitsPerEm does not pay the
    instancing twice.
    """
    Merger, TTFont, scale_upem, instancer, _version = _load_fonttools()
    key = "cjk-%s-w%d-u%d-v%d" % (
        _file_digest(cjk_path)[:16], weight, upem, MERGE_VERSION)
    prepared = os.path.join(cache_dir, key + ".ttf")
    os.makedirs(cache_dir, exist_ok=True)
    if os.path.isfile(prepared) and os.path.getsize(prepared) > 0:
        return prepared

    font = TTFont(cjk_path, lazy=False)
    if "fvar" in font:
        instancer.instantiateVariableFont(font, {"wght": weight}, inplace=True)
    if font["head"].unitsPerEm != upem:
        scale_upem(font, upem)
    fd, tmp = tempfile.mkstemp(prefix="." + key + ".", suffix=".tmp", dir=cache_dir)
    os.close(fd)
    try:
        font.save(tmp)
        font.close()
        os.replace(tmp, prepared)
    except Exception:
        font.close()
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return prepared


def _file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _as_path(data) -> tuple:
    """(a real file path, temp path to clean up or None) for bytes or a path."""
    if isinstance(data, (bytes, bytearray, memoryview)):
        fd, tmp = tempfile.mkstemp(prefix="rpykit-merge-in-", suffix=".font")
        with os.fdopen(fd, "wb") as f:
            f.write(bytes(data))
        return tmp, tmp
    path = str(data)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return path, None


def merge_font(source, cjk, destination, *, cjk_weight=DEFAULT_WEIGHT,
               prepared_cjk=None) -> MergeResult:
    """Merge ``cjk`` into ``source`` and atomically write ``destination``.

    ``source`` keeps its outlines and metrics verbatim; ``cjk`` is instanced to
    a static weight and scaled to the source's ``unitsPerEm`` on the way in.
    Both may be a path or raw bytes.

    ``prepared_cjk`` short-circuits that second step when a caller already has
    the instanced, scaled font - :func:`cached_merge` does, from its own cache.
    The file is still read here, because the tables it ended up with are what
    the merge has to agree with the base about.

    The output is written to a temporary file beside the destination, reopened,
    and checked: every codepoint the base font had must still be there, and the
    tables no font can load without must be present. Only then is it moved into
    place, so a failed merge leaves an existing destination untouched.
    """
    Merger, TTFont, scale_upem, instancer, _version = _load_fonttools()

    destination_path = Path(destination).expanduser().resolve()
    if not destination_path.parent.is_dir():
        raise FileNotFoundError(
            "Destination directory does not exist: %s" % destination_path.parent)

    scratch = []
    prepared = None
    own_prepared = False
    temporary_path = None
    try:
        base_path, temp_a = _as_path(source)
        cjk_path, temp_b = _as_path(cjk)
        scratch = [p for p in (temp_a, temp_b) if p]

        try:
            base_font = TTFont(base_path, lazy=False)
        except Exception as exc:
            raise FontMergeError("Could not read the base font: %s" % exc) from exc

        base_upem = base_font["head"].unitsPerEm
        base_codepoints = _unicode_cmap(base_font)
        base_tables = set(base_font.keys())
        base_font.close()
        if not base_codepoints:
            raise FontMergeError("base font has an empty cmap")

        if prepared_cjk is not None:
            prepared = str(prepared_cjk)
        else:
            # Stage the CJK side as a static font at the base's em. This is done
            # from the loaded font rather than the file because both
            # adjustments have to happen before the merger opens anything.
            try:
                cjk_font = TTFont(cjk_path, lazy=False)
                if "fvar" in cjk_font:
                    instancer.instantiateVariableFont(
                        cjk_font, {"wght": cjk_weight}, inplace=True)
                if cjk_font["head"].unitsPerEm != base_upem:
                    scale_upem(cjk_font, base_upem)
                fd, prepared = tempfile.mkstemp(prefix="rpykit-merge-cjk-", suffix=".ttf")
                os.close(fd)
                cjk_font.save(prepared)
                cjk_font.close()
            except Exception as exc:
                raise FontMergeError("Could not prepare the CJK font: %s" % exc) from exc
            own_prepared = True

        try:
            cjk_probe = TTFont(prepared, lazy=False)
            cjk_codepoints = _unicode_cmap(cjk_probe)
            cjk_tables = set(cjk_probe.keys())
            cjk_probe.close()
        except Exception as exc:
            raise FontMergeError("Could not read the prepared CJK font: %s" % exc) from exc

        # A table only one side has cannot be merged: Merger compares the two
        # values with min/max and trips over the missing one. Dropping it from
        # both is less destructive than dropping it from one, and it is the
        # small, engine-side tables (hinting, vertical metrics, DSIG) that
        # differ in practice.
        asymmetric = sorted(
            (base_tables | cjk_tables) - (base_tables & cjk_tables) - {"GlyphOrder"})
        missing_required = [t for t in REQUIRED_TABLES if t not in (base_tables & cjk_tables)]
        if missing_required:
            raise FontMergeError(
                "font pair is not mergeable; not present in both: %s"
                % ", ".join(missing_required))

        # The layout tables are a second, different problem from the asymmetric
        # ones: they are present in both fonts, so the asymmetry test cannot see
        # them, but `Merger` reconciles them by value and asserts when the two
        # sides disagree. DejaVu's GSUB carries a real LangSys.ReqFeatureIndex
        # where an instanced Noto carries 0xFFFF, which trips mergeLangSyses.
        # Dropping GSUB/GPOS costs kerning and ligatures; refusing to merge costs
        # the whole patch, so they go - but only as a second attempt, so a pair
        # that reconciles keeps them.
        conflicting_layout = [t for t in LAYOUT_TABLES if t in (base_tables & cjk_tables)]
        options = Merger().options
        merged = None
        last_exc = None
        for drop in (asymmetric, asymmetric + conflicting_layout):
            options.drop_tables = sorted(set(drop))
            try:
                merged = Merger(options=options).merge([base_path, prepared])
                break
            except Exception as exc:
                last_exc = exc
        if merged is None:
            raise FontMergeError("Font merge failed: %s: %s"
                                 % (type(last_exc).__name__, last_exc)) from last_exc
        dropped = tuple(options.drop_tables)

        fd, temporary_path = tempfile.mkstemp(
            prefix=".%s." % destination_path.name, suffix=".tmp",
            dir=str(destination_path.parent))
        os.close(fd)
        merged.save(temporary_path)
        merged.close()

        # Verify what reached the disk, not what was in memory: the point of
        # reopening is to catch an output that does not survive a round trip.
        check_font = None
        try:
            check_font = TTFont(temporary_path, lazy=False)
            output_codepoints = _unicode_cmap(check_font)
            output_tables = set(check_font.keys())
        finally:
            if check_font is not None:
                check_font.close()

        lost = base_codepoints - output_codepoints
        if lost:
            raise NotMergedError(lost)
        added = cjk_codepoints - base_codepoints
        still_missing = added - output_codepoints
        if still_missing:
            raise FontMergeError(
                "merged font did not gain %d of %d CJK codepoints"
                % (len(still_missing), len(added)))
        absent = [t for t in REQUIRED_TABLES if t not in output_tables]
        if absent:
            raise FontMergeError("merged font is missing required tables: %s"
                                 % ", ".join(absent))

        output_size = os.path.getsize(temporary_path)
        os.replace(temporary_path, str(destination_path))
        temporary_path = None
        return MergeResult(
            base_path=Path(base_path),
            cjk_path=Path(cjk_path),
            destination_path=destination_path,
            base_codepoints=len(base_codepoints),
            added_codepoints=len(added),
            units_per_em=base_upem,
            base_size=os.path.getsize(base_path),
            output_size=output_size,
            dropped_tables=dropped,
        )
    finally:
        # `prepared` is only ours to delete when this call staged it. When it
        # came in as `prepared_cjk` it is the caller's cache entry, and removing
        # it on a failed merge would throw away the very file that made the
        # retry cheap.
        owned = [prepared] if own_prepared else []
        for path in scratch + owned + [temporary_path]:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def install_cached(source, cjk, destination, cache_dir, *, cjk_weight=DEFAULT_WEIGHT):
    """Merge if needed, then place the result at ``destination``.

    Returns ``(destination, size, from_cache)``.

    The cache entry is copied rather than hard-linked: the game folder and the
    cache must each stay valid on their own, and a game moved to another drive
    must not drag the cache entry with it. The copy is also what keeps the
    cached file immutable - it is the key's referent, so nothing may edit it.
    """
    merged_path, from_cache = cached_merge(
        source, cjk, cache_dir, cjk_weight=cjk_weight)
    destination = str(destination)
    parent = os.path.dirname(destination)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(destination) + ".",
                               suffix=".part", dir=parent or None)
    try:
        with os.fdopen(fd, "wb") as out, open(merged_path, "rb") as src:
            shutil.copyfileobj(src, out, 1024 * 1024)
        os.replace(tmp, destination)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return destination, os.path.getsize(destination), from_cache
