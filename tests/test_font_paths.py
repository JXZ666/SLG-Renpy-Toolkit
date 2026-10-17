"""Equal basenames in different directories must never share measured faces."""
from pathlib import Path

import cmd_fontfix
import fontscan


def test_explicit_font_paths_are_distinct_and_bare_name_is_ambiguous(tmp_path):
    for folder, payload in (("a", b"face A"), ("b", b"face B")):
        directory = tmp_path / "game" / folder
        directory.mkdir(parents=True)
        (directory / "same.ttf").write_bytes(payload)
    inventory = fontscan.font_inventory(str(tmp_path), [])
    assert "same.ttf" not in inventory
    assert cmd_fontfix._resolve("a/same.ttf", inventory)[0] == b"face A"
    assert cmd_fontfix._resolve("b/same.ttf", inventory)[0] == b"face B"
    assert cmd_fontfix._resolve("missing/same.ttf", inventory) == (None, None)
    assert cmd_fontfix._resolve("same.ttf", inventory) == (None, None)


def test_unambiguous_basename_and_extensionless_path_still_work(tmp_path):
    folder = tmp_path / "game" / "fonts"
    folder.mkdir(parents=True)
    (folder / "one.ttf").write_bytes(b"only face")
    inventory = fontscan.font_inventory(str(tmp_path), [])
    assert cmd_fontfix._resolve("one.ttf", inventory)[0] == b"only face"
    assert cmd_fontfix._resolve("fonts/one", inventory)[0] == b"only face"


def test_archive_reader_uses_exact_entry(monkeypatch):
    index = {"a/same.ttf": (1, 2, b""), "b/same.ttf": (3, 4, b"")}
    monkeypatch.setattr(fontscan.rpa, "load_index", lambda _: index)
    monkeypatch.setattr(fontscan.rpa, "read_entry", lambda _, entry: str(entry[0]).encode())
    assert fontscan.font_bytes({"where": "rpa", "archive": "synthetic", "entry": "b/same.ttf"}) == b"3"
