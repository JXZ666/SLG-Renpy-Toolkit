"""RPA archive reading: safe index parsing and entry extraction (stdlib only).

RPA indexes are zlib-compressed pickle data. Game archives are untrusted input,
so the pickle reader below only accepts the primitive data opcodes used by
Ren'Py's index (dict/list/tuple, strings/bytes, integers and memo references).
It never resolves globals or runs pickle constructors.
"""

import io
import os
import pickle
import pickletools
import zlib

SUPPORTED_MAGIC = b"RPA-3.0"

# Keep archive metadata parsing bounded. These limits are intentionally much
# larger than ordinary game indexes while preventing a small RPA from forcing
# an unbounded allocation during a compatibility scan.
MAX_HEADER_BYTES = 128
MAX_COMPRESSED_INDEX_BYTES = 64 * 1024 * 1024
MAX_DECOMPRESSED_INDEX_BYTES = 64 * 1024 * 1024
MAX_ENTRY_READ_BYTES = 256 * 1024 * 1024
MAX_PICKLE_OPS = 2_000_000
MAX_INDEX_ENTRIES = 500_000
MAX_ENTRY_NAME_CHARS = 32_768


# The data produced by Ren'Py's archiver consists of dictionaries whose values
# are lists of tuples. No callable, class, persistent ID or extension opcode is
# needed to represent that data. In particular, GLOBAL/STACK_GLOBAL/REDUCE and
# BUILD/NEWOBJ are deliberately excluded.
_DATA_PICKLE_OPCODES = frozenset((
    "PROTO", "FRAME", "STOP", "MARK",
    "NONE", "NEWTRUE", "NEWFALSE",
    "INT", "BININT", "BININT1", "BININT2", "LONG", "LONG1", "LONG4",
    "FLOAT", "BINFLOAT",
    "STRING", "BINSTRING", "SHORT_BINSTRING",
    "UNICODE", "BINUNICODE", "SHORT_BINUNICODE", "BINUNICODE8",
    "BINBYTES", "SHORT_BINBYTES", "BINBYTES8",
    "EMPTY_TUPLE", "TUPLE", "TUPLE1", "TUPLE2", "TUPLE3",
    "EMPTY_LIST", "APPEND", "APPENDS",
    "EMPTY_DICT", "SETITEM", "SETITEMS",
    "PUT", "BINPUT", "LONG_BINPUT", "GET", "BINGET", "LONG_BINGET",
    "MEMOIZE",
))


class RpaError(Exception):
    pass


def read_header(path):
    with open(path, "rb") as f:
        line = f.readline(MAX_HEADER_BYTES + 1)
    if len(line) > MAX_HEADER_BYTES:
        raise RpaError("archive header exceeds %d bytes" % MAX_HEADER_BYTES)
    if not line.endswith(b"\n"):
        raise RpaError("archive header is incomplete")
    return line.rstrip(b"\r\n")


def describe(path):
    """Return dict with magic/version/offset/key, or {'error': ...}."""
    info = {"path": path, "size": os.path.getsize(path)}
    try:
        header = read_header(path)
    except (OSError, RpaError) as e:
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


def _decompress_index(raw):
    """Decompress one complete zlib stream while enforcing the output limit."""
    if len(raw) > MAX_COMPRESSED_INDEX_BYTES:
        raise RpaError("compressed index exceeds %d bytes" % MAX_COMPRESSED_INDEX_BYTES)
    try:
        decoder = zlib.decompressobj()
        data = decoder.decompress(raw, MAX_DECOMPRESSED_INDEX_BYTES + 1)
    except (zlib.error, MemoryError) as e:
        raise RpaError("invalid or oversized compressed index") from e

    if len(data) > MAX_DECOMPRESSED_INDEX_BYTES or decoder.unconsumed_tail:
        raise RpaError("decompressed index exceeds %d bytes" % MAX_DECOMPRESSED_INDEX_BYTES)
    if not decoder.eof:
        raise RpaError("compressed index is incomplete")
    if decoder.unused_data:
        raise RpaError("compressed index has trailing data")
    return data


class _DataOnlyUnpickler(pickle.Unpickler):
    """Unpickler that refuses all global object resolution."""

    def find_class(self, module, name):
        raise pickle.UnpicklingError("global objects are not allowed in an RPA index")


def _load_data_pickle(data):
    """Load a primitive-only pickle after rejecting executable opcodes."""
    stop_pos = None
    try:
        for count, (opcode, arg, pos) in enumerate(pickletools.genops(data), 1):
            if count > MAX_PICKLE_OPS:
                raise RpaError("index pickle has too many opcodes")
            if opcode.name not in _DATA_PICKLE_OPCODES:
                raise RpaError("index pickle contains unsupported opcode %s" % opcode.name)
            if opcode.name == "PROTO" and arg > pickle.HIGHEST_PROTOCOL:
                raise RpaError("index pickle protocol is not supported")
            if opcode.name == "STOP":
                stop_pos = pos
                break
    except RpaError:
        raise
    except Exception as e:
        raise RpaError("malformed index pickle") from e

    if stop_pos is None or stop_pos + 1 != len(data):
        raise RpaError("index pickle has no final STOP opcode")

    try:
        # encoding='bytes' retains compatibility with Python 2 Ren'Py archives,
        # where str values in the index were byte strings.
        return _DataOnlyUnpickler(io.BytesIO(data), encoding="bytes").load()
    except Exception as e:
        raise RpaError("index pickle could not be parsed") from e


def _validated_index(index, key, index_offset, header_size):
    if not isinstance(index, dict):
        raise RpaError("index root is not a dictionary")
    if len(index) > MAX_INDEX_ENTRIES:
        raise RpaError("index contains too many entries")

    out = {}
    for name, variants in index.items():
        if isinstance(name, bytes):
            name = name.decode("utf-8", "surrogateescape")
        if not isinstance(name, str) or not name or len(name) > MAX_ENTRY_NAME_CHARS:
            raise RpaError("index contains an invalid entry name")
        if "\x00" in name:
            raise RpaError("index contains an invalid entry name")
        if not isinstance(variants, (list, tuple)):
            raise RpaError("index entry %r has an invalid record list" % name[:80])
        if not variants:
            continue

        item = variants[0]
        if not isinstance(item, (tuple, list)) or len(item) not in (2, 3):
            raise RpaError("index entry %r has an invalid record" % name[:80])
        off, dlen = item[:2]
        if (not isinstance(off, int) or isinstance(off, bool) or
                not isinstance(dlen, int) or isinstance(dlen, bool)):
            raise RpaError("index entry %r has non-integer bounds" % name[:80])
        off ^= key
        dlen ^= key
        if off < header_size or dlen < 0 or off > index_offset or dlen > index_offset - off:
            raise RpaError("index entry %r points outside archive data" % name[:80])

        start = item[2] if len(item) == 3 else b""
        if start is None:
            start = b""
        elif isinstance(start, str):
            try:
                start = start.encode("latin-1")
            except UnicodeEncodeError as e:
                raise RpaError("index entry %r has an invalid prefix" % name[:80]) from e
        elif not isinstance(start, bytes):
            raise RpaError("index entry %r has an invalid prefix" % name[:80])
        out[name] = (off, dlen, start)
    return out


def load_index(path):
    """Return {name: (offset, dlen, start)} with offset already XOR-decoded.

    The RPA index is third-party pickle input, but only its primitive data
    representation is accepted. No classes, globals, or pickle constructors
    are evaluated.
    """
    info = describe(path)
    if "error" in info:
        raise RpaError("%s: %s" % (path, info["error"]))
    magic = info["magic"]
    if magic != SUPPORTED_MAGIC.decode("ascii"):
        raise RpaError("%s: unsupported archive version %s" % (path, magic))

    key = info["key"]
    index_offset = info["index_offset"]
    with open(path, "rb") as f:
        header = f.readline(MAX_HEADER_BYTES + 1)
        file_size = os.fstat(f.fileno()).st_size
        if index_offset < len(header) or index_offset > file_size:
            raise RpaError("%s: index offset is outside the archive" % path)
        compressed_size = file_size - index_offset
        if compressed_size > MAX_COMPRESSED_INDEX_BYTES:
            raise RpaError("%s: compressed index exceeds %d bytes" %
                           (path, MAX_COMPRESSED_INDEX_BYTES))
        f.seek(index_offset)
        raw = f.read(MAX_COMPRESSED_INDEX_BYTES + 1)

    try:
        data = _decompress_index(raw)
        index = _load_data_pickle(data)
        # RPA-3.0 archives put payloads before the index. Validate this before
        # returning offsets that read_entry() may later use.
        return _validated_index(index, key, index_offset, len(header))
    except RpaError as e:
        raise RpaError("%s: RPA-3.0 index %s" % (path, e)) from e


def read_entry(archive_path, entry):
    """Return the raw bytes of one entry.

    RPA-3.0 stores entries uncompressed. The optional `start` element is a
    prefix buffer kept inside the index pickle and prepended to the on-disk
    run (see renpy.loader.read_archive).
    """
    offset, dlen, start = entry
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise RpaError("%s: invalid entry offset" % archive_path)
    if not isinstance(dlen, int) or isinstance(dlen, bool) or dlen < 0:
        raise RpaError("%s: invalid entry length" % archive_path)
    prefix = start or b""
    if isinstance(prefix, str):
        try:
            prefix = prefix.encode("latin-1")
        except UnicodeEncodeError as e:
            raise RpaError("%s: invalid entry prefix" % archive_path) from e
    if not isinstance(prefix, bytes):
        raise RpaError("%s: invalid entry prefix" % archive_path)
    if dlen + len(prefix) > MAX_ENTRY_READ_BYTES:
        raise RpaError("%s: entry exceeds %d bytes" %
                       (archive_path, MAX_ENTRY_READ_BYTES))

    with open(archive_path, "rb") as f:
        f.seek(offset)
        body = f.read(dlen)
    if len(body) != dlen:
        raise RpaError(
            "%s: short read at %d (got %d, want %d)" % (archive_path, offset, len(body), dlen)
        )
    return prefix + body


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
