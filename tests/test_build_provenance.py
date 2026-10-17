import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import build_provenance as provenance
from tools import build_exe


def inputs(root):
    root.mkdir()
    (root / "app_main.py").write_text("# source\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets/font.ttf").write_bytes(b"font")
    return root


def artifact(output, mode="onefile", data=b"built-exe"):
    path = output / ("onefile" if mode == "onefile" else "Sample") / "Sample.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mode == "onedir":
        (path.parent / "_internal").mkdir()
        (path.parent / "_internal/library.dll").write_bytes(b"library")
    return path


def test_complete_provenance_has_actual_hashes_and_no_absolute_paths(tmp_path):
    root, output = inputs(tmp_path / "private-user-source"), tmp_path / "private-output"
    manifest = provenance.begin(root, output, "1.1.0", ["onedir", "onefile"])
    artifact(output, "onedir")
    artifact(output)
    result = provenance.finish(root, output, manifest, ["Sample.exe"])
    assert result["status"] == "complete" and result["app_version"] == "1.1.0"
    assert len(result["artifacts"]) == 3
    assert result["inputs"]["app_main.py"] == hashlib.sha256((root / "app_main.py").read_bytes()).hexdigest()
    assert provenance.verify(root, output) == result
    serialized = (output / "build_manifest.json").read_text(encoding="utf-8")
    assert "private-user-source" not in serialized and "private-output" not in serialized
    assert str(tmp_path) not in serialized
    assert set(result["source"]) == {"base_commit", "dirty"}
    assert set(result["windows"]) == {"system", "release", "version"}


def test_inputs_changed_during_build_refuses_success(tmp_path):
    root, output = inputs(tmp_path / "source"), tmp_path / "output"
    manifest = provenance.begin(root, output, "1.1.0", ["onefile"])
    artifact(output)
    (root / "app_main.py").write_text("changed", encoding="utf-8")
    with pytest.raises(provenance.ProvenanceError, match="changed"):
        provenance.finish(root, output, manifest, ["Sample.exe"])
    saved = json.loads((output / "build_manifest.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed" and saved["failure"] == "build_inputs_changed"
    assert not saved["artifacts"]


def test_missing_or_empty_artifact_refuses_success(tmp_path):
    root, output = inputs(tmp_path / "source"), tmp_path / "output"
    manifest = provenance.begin(root, output, "1.1.0", ["onefile"])
    with pytest.raises(provenance.ProvenanceError, match="missing or empty"):
        provenance.finish(root, output, manifest, ["Sample.exe"])
    manifest = provenance.begin(root, output, "1.1.0", ["onefile"])
    artifact(output, data=b"")
    with pytest.raises(provenance.ProvenanceError):
        provenance.finish(root, output, manifest, ["Sample.exe"])


def test_verify_detects_modified_binary_and_source(tmp_path):
    root, output = inputs(tmp_path / "source"), tmp_path / "output"
    manifest = provenance.begin(root, output, "1.1.0", ["onefile"])
    exe = artifact(output)
    provenance.finish(root, output, manifest, ["Sample.exe"])
    exe.write_bytes(b"different")
    with pytest.raises(provenance.ProvenanceError, match="artifact differs"):
        provenance.verify(root, output)
    exe.write_bytes(b"built-exe")
    (root / "assets/font.ttf").write_bytes(b"different")
    with pytest.raises(provenance.ProvenanceError, match="source differs"):
        provenance.verify(root, output)


def test_verify_rejects_manifest_path_escape(tmp_path):
    root, output = inputs(tmp_path / "source"), tmp_path / "output"
    manifest = provenance.begin(root, output, "1.1.0", ["onefile"])
    artifact(output)
    provenance.finish(root, output, manifest, ["Sample.exe"])
    manifest["artifacts"][0]["path"] = "../outside.exe"
    (output / "build_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(provenance.ProvenanceError, match="unsafe"):
        provenance.verify(root, output)


def test_verify_rejects_incomplete_artifact_inventory(tmp_path):
    root, output = inputs(tmp_path / "source"), tmp_path / "output"
    manifest = provenance.begin(root, output, "1.1.0", ["onedir", "onefile"])
    artifact(output, "onedir")
    artifact(output)
    provenance.finish(root, output, manifest, ["Sample.exe"])
    manifest["artifacts"] = [entry for entry in manifest["artifacts"] if not entry["path"].endswith("Sample.exe")]
    (output / "build_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(provenance.ProvenanceError, match="missing an executable"):
        provenance.verify(root, output)


def test_build_records_failed_pyinstaller(tmp_path, monkeypatch):
    root = inputs(tmp_path / "source")
    monkeypatch.setattr(build_exe, "ROOT", root)
    monkeypatch.setattr(build_exe.subprocess, "run", lambda *a, **k: type("Result", (), {"returncode": 7})())
    # The subprocess module is shared; supply identity without invoking git.
    monkeypatch.setattr(provenance, "git_identity", lambda root: {"base_commit": "test", "dirty": True})
    output = tmp_path / "output"
    assert build_exe.build(output, "onefile") == 7
    manifest = json.loads((output / "build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed" and manifest["failure"] == "pyinstaller_failed"


def test_build_exception_is_never_left_as_complete(tmp_path, monkeypatch):
    root = inputs(tmp_path / "source")
    monkeypatch.setattr(build_exe, "ROOT", root)
    def interrupted(*args):
        raise OSError("simulated process failure")
    monkeypatch.setattr(build_exe, "_compile_targets", interrupted)
    output = tmp_path / "output"
    with pytest.raises(OSError, match="simulated"):
        build_exe.build(output, "onefile")
    manifest = json.loads((output / "build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed" and manifest["failure"] == "build_interrupted_or_exception"


def test_build_accepts_only_matching_pre_and_post_inputs(tmp_path, monkeypatch):
    root = inputs(tmp_path / "source")
    monkeypatch.setattr(build_exe, "ROOT", root)
    monkeypatch.setattr(build_exe, "TARGETS", (("fake.spec", "FAKE_VERSION_FILE", "Sample.exe"),))
    def changed(output, mode):
        artifact(output)
        (root / "app_main.py").write_bytes(b"source changed during build")
        return 0
    monkeypatch.setattr(build_exe, "_compile_targets", changed)
    output = tmp_path / "output"
    assert build_exe.build(output, "onefile") == 1
    assert json.loads((output / "build_manifest.json").read_text(encoding="utf-8"))["status"] == "failed"
