"""Security and compatibility tests for RPA-3.0 index parsing.

Run: python tests/test_rpa.py
"""

import os
import pickle
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import rpa  # noqa: E402


KEY = 0x42424242
BODY = b"archive-entry-body"


def _archive(path, index_pickle, body=BODY, key=KEY, compressed=True):
    """Write a synthetic RPA-3.0 archive; index_pickle is the raw pickle."""
    header_size = len(b"RPA-3.0 %016x %08x\n" % (0, key))
    index_offset = header_size + len(body)
    header = b"RPA-3.0 %016x %08x\n" % (index_offset, key)
    index_data = zlib.compress(index_pickle) if compressed else index_pickle
    with open(path, "wb") as f:
        f.write(header)
        f.write(body)
        f.write(index_data)
    return index_offset


def _modern_archive(path, protocol=4):
    header_size = len(b"RPA-3.0 %016x %08x\n" % (0, KEY))
    index_offset = header_size + len(BODY)
    index = {
        "game/test.rpy": [((index_offset - len(BODY)) ^ KEY,
                           len(BODY) ^ KEY, b"prefix-")]
    }
    return _archive(path, pickle.dumps(index, protocol=protocol))


def _python2_protocol2_pickle(path, offset, body_length, key=KEY):
    """A protocol-2 fixture using Python 2 BINSTRING values, without GLOBAL."""
    name = path.encode("ascii")
    offset_xor = offset ^ key
    length_xor = body_length ^ key
    assert -0x80000000 <= offset_xor < 0x80000000
    assert -0x80000000 <= length_xor < 0x80000000
    return (b"\x80\x02}" +
            b"U" + bytes((len(name),)) + name +
            b"]" +
            b"J" + struct.pack("<i", offset_xor) +
            b"J" + struct.pack("<i", length_xor) +
            b"U\x00\x87as.")


class _ExecPayload(object):
    def __init__(self, code):
        self.code = code

    def __reduce__(self):
        return (exec, (self.code,))


class RpaIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def archive_path(self, name="test.rpa"):
        return os.path.join(self.tmp.name, name)

    def archive_with_name(self, path, name, body=BODY, key=KEY):
        """Write an archive whose index holds a single entry called `name`."""
        header_size = len(b"RPA-3.0 %016x %08x\n" % (0, key))
        index_offset = header_size + len(body)
        index = {name: [(header_size ^ key, len(body) ^ key, b"")]}
        _archive(path, pickle.dumps(index, protocol=4), body=body, key=key)
        return index_offset

    def test_modern_renpy_index_is_read_and_entry_data_is_unchanged(self):
        path = self.archive_path()
        _modern_archive(path, protocol=4)

        index = rpa.load_index(path)
        self.assertEqual(index, {"game/test.rpy": (len(b"RPA-3.0 %016x %08x\n" % (0, KEY)),
                                                    len(BODY), b"prefix-")})
        self.assertEqual(rpa.read_entry(path, index["game/test.rpy"]), b"prefix-" + BODY)

    def test_read_entry_caps_body_plus_inline_prefix(self):
        path = self.archive_path("entry.bin")
        with open(path, "wb") as f:
            f.write(b"abcdef")

        original_limit = rpa.MAX_ENTRY_READ_BYTES
        try:
            rpa.MAX_ENTRY_READ_BYTES = 5
            self.assertEqual(rpa.read_entry(path, (0, 3, b"12")), b"12abc")
            with self.assertRaisesRegex(rpa.RpaError, "entry exceeds 5 bytes"):
                rpa.read_entry(path, (0, 4, b"12"))
            with self.assertRaisesRegex(rpa.RpaError, "entry exceeds 5 bytes"):
                rpa.read_entry(path, (0, 3, b"123"))
        finally:
            rpa.MAX_ENTRY_READ_BYTES = original_limit

    def test_python2_protocol2_binary_string_index_is_read(self):
        path = self.archive_path()
        header_size = len(b"RPA-3.0 %016x %08x\n" % (0, KEY))
        payload = _python2_protocol2_pickle("game/test.rpy", header_size, len(BODY))
        _archive(path, payload)

        index = rpa.load_index(path)
        self.assertEqual(index, {"game/test.rpy": (header_size, len(BODY), b"")})

    def test_global_opcode_is_rejected(self):
        for protocol in (0, 4):
            with self.subTest(protocol=protocol):
                path = self.archive_path("global-%d.rpa" % protocol)
                _archive(path, pickle.dumps(os.system, protocol=protocol))
                with self.assertRaisesRegex(
                        rpa.RpaError, "unsupported opcode (STACK_)?GLOBAL"):
                    rpa.load_index(path)

    def test_reduce_opcode_is_rejected_even_without_a_global(self):
        path = self.archive_path()
        # A string used as a callable would fail in a real Unpickler, but this
        # assertion proves the constructor opcode itself is rejected in precheck.
        payload = b"\x80\x04\x8c\x04nope\x8c\x00\x85R."
        _archive(path, payload)

        with self.assertRaisesRegex(rpa.RpaError, "unsupported opcode REDUCE"):
            rpa.load_index(path)

    def test_reduce_payload_is_rejected_without_execution(self):
        path = self.archive_path()
        marker = os.path.join(self.tmp.name, "executed.txt")
        code = "open(%r, 'w').write('executed')" % marker
        payload = pickle.dumps(_ExecPayload(code), protocol=4)
        _archive(path, payload)

        with self.assertRaisesRegex(rpa.RpaError, "unsupported opcode (STACK_)?GLOBAL"):
            rpa.load_index(path)
        self.assertFalse(os.path.exists(marker))

    def test_malformed_and_truncated_zlib_streams_fail_as_rpa_errors(self):
        for name, payload in (("bad.rpa", b"not-zlib"),
                              ("truncated.rpa", zlib.compress(pickle.dumps({}, protocol=4))[:-1])):
            with self.subTest(name=name):
                path = self.archive_path(name)
                _archive(path, payload, compressed=False)
                with self.assertRaises(rpa.RpaError):
                    rpa.load_index(path)

    def test_compressed_and_decompressed_size_limits_are_enforced(self):
        path = self.archive_path()
        _modern_archive(path)
        original_limit = rpa.MAX_COMPRESSED_INDEX_BYTES
        try:
            rpa.MAX_COMPRESSED_INDEX_BYTES = 1
            with self.assertRaisesRegex(rpa.RpaError, "compressed index exceeds"):
                rpa.load_index(path)
        finally:
            rpa.MAX_COMPRESSED_INDEX_BYTES = original_limit

        path = self.archive_path("large-output.rpa")
        payload = pickle.dumps({"x": [(1, 1, b"A" * 4096)]}, protocol=4)
        _archive(path, payload)
        original_limit = rpa.MAX_DECOMPRESSED_INDEX_BYTES
        try:
            rpa.MAX_DECOMPRESSED_INDEX_BYTES = 256
            with self.assertRaisesRegex(rpa.RpaError, "decompressed index exceeds"):
                rpa.load_index(path)
        finally:
            rpa.MAX_DECOMPRESSED_INDEX_BYTES = original_limit

    def test_malformed_index_shape_and_out_of_bounds_entries_fail(self):
        path = self.archive_path()
        _archive(path, pickle.dumps(["not", "a", "dict"], protocol=4))
        with self.assertRaisesRegex(rpa.RpaError, "root is not a dictionary"):
            rpa.load_index(path)

        header_size = len(b"RPA-3.0 %016x %08x\n" % (0, KEY))
        index_offset = header_size + len(BODY)
        invalid = {"game/outside.rpy": [(index_offset ^ KEY, 1000 ^ KEY, b"")]}
        _archive(path, pickle.dumps(invalid, protocol=4))
        with self.assertRaisesRegex(rpa.RpaError, "outside archive data"):
            rpa.load_index(path)

    def test_excessive_pickle_opcode_count_fails(self):
        path = self.archive_path()
        _modern_archive(path)
        original_limit = rpa.MAX_PICKLE_OPS
        try:
            rpa.MAX_PICKLE_OPS = 2
            with self.assertRaisesRegex(rpa.RpaError, "too many opcodes"):
                rpa.load_index(path)
        finally:
            rpa.MAX_PICKLE_OPS = original_limit

    def test_index_entry_names_reject_traversal_and_absolute_paths(self):
        unsafe = (b"../../evil.rpy", b"/etc/passwd", b"C:\\Windows\\x",
                  b"a/../b", b"..\\..\\x", b"a\\..\\..\\b")
        for i, raw in enumerate(unsafe):
            name = raw.decode("ascii")
            with self.subTest(name=name):
                path = self.archive_path("unsafe-%d.rpa" % i)
                self.archive_with_name(path, name)
                with self.assertRaisesRegex(rpa.RpaError, "index entry"):
                    rpa.load_index(path)

    def test_index_entry_names_allow_nested_relative_paths(self):
        safe = ("game/script.rpy", "images/bg/room.png", "game/weird..name.png")
        for i, name in enumerate(safe):
            with self.subTest(name=name):
                path = self.archive_path("safe-%d.rpa" % i)
                self.archive_with_name(path, name)
                index = rpa.load_index(path)
                self.assertIn(name, index)

    def test_extract_entry_confines_writes_to_destination_root(self):
        path = self.archive_path()
        self.archive_with_name(path, "images/bg/room.png")
        entry = rpa.load_index(path)["images/bg/room.png"]

        root = os.path.join(self.tmp.name, "out")
        written = rpa.extract_entry(path, entry, root, "images/bg/room.png")
        self.assertEqual(written, len(BODY))
        dest = os.path.join(root, "images", "bg", "room.png")
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), BODY)
        # Nothing was created outside the destination root.
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "images")))

    def test_extract_entry_rejects_escaping_name_without_writing(self):
        path = self.archive_path()
        self.archive_with_name(path, "game/keep.rpy")
        entry = rpa.load_index(path)["game/keep.rpy"]

        root = os.path.join(self.tmp.name, "out-escape")
        escaped = os.path.join(self.tmp.name, "escaped.rpy")
        with self.assertRaisesRegex(rpa.RpaError, "path segment"):
            rpa.extract_entry(path, entry, root, "../escaped.rpy")
        self.assertFalse(os.path.exists(escaped))
        self.assertFalse(os.path.isdir(root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
