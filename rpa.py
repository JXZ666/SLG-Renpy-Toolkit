"""RPA archive reading: index parsing and entry extraction (stdlib only)."""

import os
import pickle
import zlib

SUPPORTED_MAGIC = b"RPA-3.0"


class RpaError(Exception):
    pass


def read_header(path):
    with open(path, "rb") as f:
        line = f.readline()
    return line.rstrip(b"\r\n")


def describe(path):
    """Return dict with magic/version/offset/key, or {'error': ...}."""
    info = {"path": path, "size": os.path.getsize(path)}
    try:
        header = read_header(path)
    except OSError as e:
        info["error"] = str(e)
        return info
    parts = header.split()
    if not parts or not parts[0].startswith(b"RPA-"):
        info["error"] = "bad magic: %r" % header[:32]
        return info
    info["magic"] = parts[0].decode("ascii", "replace")
    info["header"] = header.decode("ascii", "replace")
    try:
        info["index_offset"] = int(parts[1], 16)
        info["key"] = int(parts[2], 16)
    except (IndexError, ValueError) as e:
        info["error"] = "unparsable header: %s" % e
    return info


def load_index(path):
    """Return {name: (offset, dlen, start)} with offset already XOR-decoded."""
    info = describe(path)
    if "error" in info:
        raise RpaError("%s: %s" % (path, info["error"]))
    magic = info["magic"]
    if magic != SUPPORTED_MAGIC.decode("ascii"):
        raise RpaError("%s: unsupported archive version %s" % (path, magic))

    key = info["key"]
    with open(path, "rb") as f:
        f.seek(info["index_offset"])
        raw = f.read()
    try:
        index = pickle.loads(zlib.decompress(raw), encoding="bytes")
    except Exception as e:
        raise RpaError("%s: index decompress/unpickle failed: %s" % (path, e))

    if not isinstance(index, dict):
        raise RpaError("%s: index is %s, expected dict" % (path, type(index).__name__))

    # Mirror renpy.loader.RPAv3ArchiveHandler.read_index: both the offset and
    # the uncompressed length are XOR-obfuscated, and the third element may be
    # absent, in which case the payload is stored raw rather than zlib-prefixed.
    out = {}
    for k, v in index.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8", "surrogateescape")
        if not v:
            continue
        item = v[0]
        if len(item) == 2:
            off, dlen = item
            start = b""
        else:
            off, dlen, start = item
        if start and not isinstance(start, bytes):
            start = start.encode("latin-1")
        out[k] = (off ^ key, dlen ^ key, start)
    return out


def read_entry(archive_path, entry):
    """Return the raw bytes of one entry.

    RPA-3.0 stores entries uncompressed. The optional `start` element is a
    prefix buffer kept inside the index pickle and prepended to the on-disk
    run (see renpy.loader.read_archive).
    """
    offset, dlen, start = entry
    with open(archive_path, "rb") as f:
        f.seek(offset)
        body = f.read(dlen)
    if len(body) != dlen:
        raise RpaError(
            "%s: short read at %d (got %d, want %d)" % (archive_path, offset, len(body), dlen)
        )
    return (start or b"") + body


def extract_entry(archive_path, entry, dest_path):
    """Write one entry to dest_path. Returns byte count written."""
    data = read_entry(archive_path, entry)
    d = os.path.dirname(dest_path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = dest_path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest_path)
    return len(data)


def entry_size(entry):
    """Total uncompressed size of an entry, including the inline prefix."""
    offset, dlen, start = entry
    return dlen + len(start or b"")


def classify(name):
    """Bucket an archive entry name into a coarse category."""
    low = name.lower()
    if low.endswith(".rpyc"):
        return "script"
    if low.endswith(".rpy"):
        return "script-source"
    if low.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
        return "image"
    if low.endswith((".ogg", ".opus", ".mp3", ".wav", ".flac")):
        return "audio"
    if low.endswith((".ttf", ".otf", ".ttc")):
        return "font"
    if low.endswith((".avi", ".mp4", ".webm", ".mkv")):
        return "video"
    if low.endswith((".json", ".txt", ".csv", ".xml", ".yaml", ".yml")):
        return "data"
    return "other"
