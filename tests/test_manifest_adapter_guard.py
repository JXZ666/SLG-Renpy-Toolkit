"""The MV/MZ adapter may inspect a newer ledger, but must not change it."""
import json

import pytest

import patch_transaction
import proj


def test_future_ledger_remains_readable_but_not_writable(tmp_path):
    root, work = tmp_path / "game", tmp_path / "work"
    root.mkdir()
    work.mkdir()
    manifest = {"version": 2, "game_dir": str(root), "files": [],
                "quarantined": [], "min_tool_version": "99.0.0"}
    path = work / "install_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    before = path.read_bytes()
    assert patch_transaction._manifest(str(root), str(work))["min_tool_version"] == "99.0.0"
    with pytest.raises(ValueError):
        patch_transaction.install(str(root), str(work), {"file.txt": b"new"})
    with pytest.raises(ValueError):
        patch_transaction.revert(str(root), str(work))
    assert path.read_bytes() == before
    assert not (root / "file.txt").exists()
