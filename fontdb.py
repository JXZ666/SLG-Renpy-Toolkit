"""Minimal TTF/OTF cmap reader: what codepoints does a face actually cover?

Stdlib only, so a font can be measured without booting the engine and without
trusting fontTools to be installed. This is the decision input for fontfix:
a face that already covers Hanzi is left alone, a face with complete Latin is
kept for Latin and given a CJK fallback, and anything else is replaced.

Ported from the ad-hoc probe in _work/scratch/fontinfo.py, with the truncation
checks tightened so a malformed table yields partial coverage rather than an
exception that would abort a whole scan.
"""

import struct

_CJK_UNIFIED = (0x4E00, 0x9FFF)
_LATIN = (0x0020, 0x007E)

# A face is treated as "already Chinese-capable" at this many Unified
# Ideographs. Real CJK faces clear it by an order of magnitude; a Latin face
# with a handful of borrowed ideographs does not.
CJK_FONT_THRESHOLD = 3000

REPORT_RANGES = {
    "CJK 统一表意": _CJK_UNIFIED,
    "CJK 扩展A": (0x3400, 0x4DBF),
    "CJK 标点": (0x3000, 0x303F),
    "全角形式": (0xFF00, 0xFFEF),
    "CJK 扩展B+": (0x20000, 0x2FA1F),
    "拉丁 (ASCII)": _LATIN,
}


def _tables(data):
    tag = data[:4]
    if tag == b"ttcf":
        if len(data) < 16:
            raise ValueError("truncated ttc header")
        off = struct.unpack(">I", data[12:16])[0]
        data = data[off:]
        tag = data[:4]
    if tag not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ValueError("not a ttf/otf: %r" % tag)
    if len(data) < 12:
        raise ValueError("truncated sfnt header")
    num = struct.unpack(">H", data[4:6])[0]
    out = {}
    for i in range(num):
        o = 12 + i * 16
        if o + 16 > len(data):
            break
        name, _cs, off, ln = struct.unpack(">4sIII", data[o:o + 16])
        out[name.decode("latin1")] = (off, ln)
    return out, data


def _subtable_offsets(data, base):
    if base + 4 > len(data):
        return []
    n = struct.unpack(">H", data[base + 2:base + 4])[0]
    subs = []
    for i in range(n):
        o = base + 4 + i * 8
        if o + 8 > len(data):
            break
        _pid, _eid, off = struct.unpack(">HHI", data[o:o + 8])
        subs.append(base + off)
    return subs


def _fmt4(data, o):
    """Segment-mapped BMP subtable. Yields codepoints one contiguous run at a
    time so the caller never builds a huge set for nothing."""
    if o + 16 > len(data):
        return
    segx2 = struct.unpack(">H", data[o + 6:o + 8])[0]
    seg = segx2 // 2
    if not seg:
        return
    end = struct.unpack(">%dH" % seg, data[o + 14:o + 14 + segx2])
    p = o + 16 + segx2
    if p + 3 * segx2 > len(data):
        return
    start = struct.unpack(">%dH" % seg, data[p:p + segx2])
    p += segx2
    delta = struct.unpack(">%dh" % seg, data[p:p + segx2])
    p += segx2
    ro_base = p
    ro = struct.unpack(">%dH" % seg, data[p:p + segx2])
    for i in range(seg):
        if start[i] == 0xFFFF or start[i] > end[i]:
            continue
        if ro[i] == 0:
            for c in range(start[i], end[i] + 1):
                yield (c + delta[i]) & 0xFFFF
        else:
            for c in range(start[i], end[i] + 1):
                gi = ro_base + i * 2 + ro[i] + (c - start[i]) * 2
                if gi + 2 > len(data):
                    break
                if struct.unpack(">H", data[gi:gi + 2])[0]:
                    yield (c + delta[i]) & 0xFFFF


def _fmt12(data, o):
    """Segmented coverage, used for anything past the BMP."""
    if o + 16 > len(data):
        return
    ngroups = struct.unpack(">I", data[o + 12:o + 16])[0]
    for i in range(ngroups):
        p = o + 16 + i * 12
        if p + 12 > len(data):
            break
        s, e, _g = struct.unpack(">III", data[p:p + 12])
        if e < s or e > 0x10FFFF:
            continue
        for c in range(s, e + 1):
            yield c


def _walk(data):
    tabs, data = _tables(data)
    if "cmap" not in tabs:
        return
    off, _ln = tabs["cmap"]
    seen = set()
    for so in _subtable_offsets(data, off):
        if so in seen or so + 2 > len(data):
            continue
        seen.add(so)
        fmt = struct.unpack(">H", data[so:so + 2])[0]
        yield fmt, so, data


def codepoints(src):
    """Set of codepoints `src` can render. `src` is a path or raw bytes.

    Raises ValueError if the file is not a font. A font whose cmap is
    unreadable returns an empty set rather than raising.
    """
    if isinstance(src, (bytes, bytearray)):
        data = bytes(src)
    else:
        with open(src, "rb") as f:
            data = f.read()
    out = set()
    try:
        for fmt, so, blob in _walk(data):
            if fmt == 4:
                out.update(_fmt4(blob, so))
            elif fmt == 12:
                out.update(_fmt12(blob, so))
    except (struct.error, ValueError, IndexError):
        pass
    return out


def coverage(cps):
    """{label: (have, total)} over the ranges that decide readability."""
    out = {}
    for label, (a, z) in REPORT_RANGES.items():
        have = sum(1 for c in range(a, z + 1) if c in cps)
        out[label] = (have, z - a + 1)
    return out


def cjk_count(cps):
    return sum(1 for c in range(_CJK_UNIFIED[0], _CJK_UNIFIED[1] + 1) if c in cps)


def latin_complete(cps):
    """True when every printable ASCII codepoint is present.

    This is the gate for delegating the Latin range back to the game's own
    face. tycho.ttf and undefeated.ttf fail it badly (52-58%), and delegating
    a range the face cannot fill produces blanks - so the gate matters.
    """
    return all(c in cps for c in range(_LATIN[0], _LATIN[1] + 1))


def describe(cps):
    cov = coverage(cps)
    have, total = cov["CJK 统一表意"]
    return "cjk %d/%d, latin %s" % (
        have, total, "complete" if latin_complete(cps) else "partial")
