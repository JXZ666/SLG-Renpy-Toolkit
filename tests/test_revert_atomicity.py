"""Revert conflicts must preserve dependencies and failed commits restore bytes."""
import argparse
import hashlib
from pathlib import Path

import pytest

import branding
import cmd_fontfix
import proj


def _bytes_tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def _installed(tmp_path, *, quarantine=False, intro=False):
    game = tmp_path / "Game"
    work = tmp_path / "work"
    (game / "game").mkdir(parents=True)
    work.mkdir()
    paths = {"game/" + cmd_fontfix.SHIM_REL: b"# " + cmd_fontfix.MARKER.encode() + b"\ninit 999 python:\n    pass\n",
             "game/" + cmd_fontfix.GAME_FONT_REL: b"CJK dependency",
             "game/localization/rpykit-face.ttf": b"merged dependency"}
    if intro:
        paths["game/" + cmd_fontfix.INTRO_REL] = b"# " + cmd_fontfix.MARKER.encode() + b"\ninit 999 python:\n    pass\n"
    entries = []
    for rel, data in paths.items():
        target = game / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        source = ("fontfix:shim" if rel.endswith(cmd_fontfix.SHIM_REL) else
                  "fontfix:intro" if rel.endswith(cmd_fontfix.INTRO_REL) else
                  "fontfix:cjk-font" if rel.endswith(cmd_fontfix.GAME_FONT_REL) else
                  "fontfix:merged-font")
        entries.append({"path": rel, "source": source, "sha256": hashlib.sha256(data).hexdigest(), "owner": "rpykit"})
        if rel.endswith(".rpy"):
            (game / (rel + "c")).write_bytes(b"compiled " + rel.encode())
    manifest = {"version": 2, "game_dir": str(game), "game_id": proj.game_identity(str(game)),
                "files": entries, "quarantined": []}
    if quarantine:
        qdir = work / "quarantine"
        qdir.mkdir()
        for rel, source in [("game/" + cmd_fontfix.SHIM_REL, cmd_fontfix.QUARANTINE_REPLACED),
                            ("game/zzz_skip.rpy", cmd_fontfix.QUARANTINE_INTRO)]:
            stored = Path(rel).name
            data = b"original " + rel.encode()
            (qdir / stored).write_bytes(data)
            manifest["quarantined"].append({"path": rel, "stored_as": stored, "source": source,
                                             "sha256": hashlib.sha256(data).hexdigest()})
    proj.save_manifest(str(work), manifest)
    return game, work


@pytest.mark.parametrize("changed", ["shim", "font", "merged", "missing-source"])
def test_revert_conflict_preserves_entire_font_feature(tmp_path, changed):
    game, work = _installed(tmp_path)
    rels = {"shim": "game/" + cmd_fontfix.SHIM_REL,
            "font": "game/" + cmd_fontfix.GAME_FONT_REL,
            "merged": "game/localization/rpykit-face.ttf"}
    if changed == "missing-source":
        (game / ("game/" + cmd_fontfix.SHIM_REL)).unlink()
    else:
        (game / rels[changed]).write_bytes(b"player changes")
    game_before, work_before = _bytes_tree(game), _bytes_tree(work)
    result = cmd_fontfix.revert(str(game), str(work))
    assert result["conflicts"]
    assert not result["removed"]
    assert _bytes_tree(game) == game_before
    assert _bytes_tree(work) == work_before


def test_conflict_does_not_block_an_independent_feature(tmp_path):
    game, work = _installed(tmp_path, intro=True)
    (game / ("game/" + cmd_fontfix.SHIM_REL)).write_bytes(b"player changes")
    font_before = (game / ("game/" + cmd_fontfix.GAME_FONT_REL)).read_bytes()
    result = cmd_fontfix.revert(str(game), str(work))
    assert result["conflicts"]
    assert "game/" + cmd_fontfix.INTRO_REL in result["removed"]
    assert not (game / ("game/" + cmd_fontfix.INTRO_REL)).exists()
    assert (game / ("game/" + cmd_fontfix.GAME_FONT_REL)).read_bytes() == font_before
    assert all(entry["source"] != "fontfix:intro" for entry in proj.load_manifest(str(work))["files"])


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_failed_ledger_commit_restores_files_compiled_outputs_and_quarantine(tmp_path, monkeypatch, error):
    game, work = _installed(tmp_path, quarantine=True, intro=True)
    game_before, work_before = _bytes_tree(game), _bytes_tree(work)
    real_save = proj.save_manifest

    def failed_commit(*args):
        real_save(*args)
        raise error("failure after ledger replacement")

    monkeypatch.setattr(proj, "save_manifest", failed_commit)
    with pytest.raises(error):
        cmd_fontfix.revert(str(game), str(work))
    assert _bytes_tree(game) == game_before
    assert _bytes_tree(work) == work_before
    assert (game / "game/localization").is_dir()


def test_changed_quarantine_preserves_the_related_feature(tmp_path):
    game, work = _installed(tmp_path, quarantine=True, intro=True)
    (work / "quarantine" / cmd_fontfix.SHIM_REL).write_bytes(b"changed backup")
    before = _bytes_tree(game)
    result = cmd_fontfix.revert(str(game), str(work))
    assert any("quarantine" in conflict for conflict in result["conflicts"])
    assert (game / ("game/" + cmd_fontfix.SHIM_REL)).read_bytes() == before["game/" + cmd_fontfix.SHIM_REL]
    assert (game / ("game/" + cmd_fontfix.GAME_FONT_REL)).read_bytes() == before["game/" + cmd_fontfix.GAME_FONT_REL]
    assert (work / "quarantine" / cmd_fontfix.SHIM_REL).read_bytes() == b"changed backup"
    assert (game / "game/zzz_skip.rpy").read_bytes().startswith(b"original")


def test_interruption_during_removal_rolls_back_before_any_commit(tmp_path, monkeypatch):
    game, work = _installed(tmp_path, quarantine=True, intro=True)
    game_before, work_before = _bytes_tree(game), _bytes_tree(work)
    real_remove = cmd_fontfix._remove_owned_file

    def interrupted(*args):
        real_remove(*args)
        raise KeyboardInterrupt("interrupted during font removal")

    monkeypatch.setattr(cmd_fontfix, "_remove_owned_file", interrupted)
    with pytest.raises(KeyboardInterrupt):
        cmd_fontfix.revert(str(game), str(work))
    assert _bytes_tree(game) == game_before
    assert _bytes_tree(work) == work_before


def test_failed_revert_cleans_directories_created_for_quarantine_restore(tmp_path, monkeypatch):
    game, work = _installed(tmp_path, quarantine=True, intro=True)
    manifest = proj.load_manifest(str(work))
    manifest["quarantined"][1]["path"] = "game/removed/subdir/zzz_skip.rpy"
    proj.save_manifest(str(work), manifest)
    before = _bytes_tree(tmp_path)

    def fail(*args):
        raise OSError("ledger unavailable")

    monkeypatch.setattr(proj, "save_manifest", fail)
    with pytest.raises(OSError):
        cmd_fontfix.revert(str(game), str(work))
    assert _bytes_tree(tmp_path) == before
    assert not (game / "game/removed").exists()


def test_run_reports_conflicts_and_dry_revert_is_readonly(tmp_path):
    game, work = _installed(tmp_path)
    (game / ("game/" + cmd_fontfix.SHIM_REL)).write_bytes(b"player changes")
    ns = argparse.Namespace(game_dir=str(game), work=str(work), revert=True, dry_run=True)
    before = _bytes_tree(tmp_path)
    assert cmd_fontfix.run(ns) == 0
    assert ns.outcome == "dry_run"
    assert _bytes_tree(tmp_path) == before
    ns.dry_run = False
    assert cmd_fontfix.run(ns) == 1
    assert ns.outcome == "conflicts"
    assert _bytes_tree(tmp_path) == before


@pytest.mark.parametrize("required", [None, "", "1.3", "v1.3.0", "01.3.0", [], 13, True])
def test_invalid_minimum_version_fails_closed(required, monkeypatch):
    monkeypatch.setattr(branding, "APP_VERSION", "1.2.0")
    with pytest.raises(proj.ManifestVersionError):
        proj.ensure_manifest_writable({"min_tool_version": required})


def test_minimum_version_supports_legacy_and_compares_numerically(monkeypatch):
    monkeypatch.setattr(branding, "APP_VERSION", "1.2.0")
    proj.ensure_manifest_writable({})
    proj.ensure_manifest_writable({"min_tool_version": "1.2.0"})
    proj.ensure_manifest_writable({"min_tool_version": "1.1.99"})
    for required in ("1.3.0", "1.10.0", "2.0.0"):
        with pytest.raises(proj.ManifestVersionError, match=required):
            proj.ensure_manifest_writable({"min_tool_version": required})


def test_newer_manifest_is_readable_but_cannot_be_reverted(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "APP_VERSION", "1.2.0")
    game, work = _installed(tmp_path)
    manifest = proj.load_manifest(str(work))
    manifest["min_tool_version"] = "1.3.0"
    proj.save_manifest(str(work), manifest)
    assert proj.load_manifest(str(work))["min_tool_version"] == "1.3.0"
    before = _bytes_tree(tmp_path)
    with pytest.raises(proj.ManifestVersionError):
        cmd_fontfix.revert(str(game), str(work))
    assert _bytes_tree(tmp_path) == before


def test_direct_install_rejects_newer_ledger_before_writing_game(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "APP_VERSION", "1.2.0")
    game, work = _installed(tmp_path)
    manifest = proj.load_manifest(str(work))
    manifest["min_tool_version"] = "1.3.0"
    proj.save_manifest(str(work), manifest)
    args = argparse.Namespace(features=["intro"], dry_run=False)
    before = _bytes_tree(tmp_path)
    with pytest.raises(proj.ManifestVersionError):
        cmd_fontfix.install(args, str(game), str(work), {"stamp": "test"})
    assert _bytes_tree(tmp_path) == before


def test_successful_revert_removes_derived_files_and_restores_originals(tmp_path):
    game, work = _installed(tmp_path, quarantine=True, intro=True)
    result = cmd_fontfix.revert(str(game), str(work))
    assert not result["conflicts"]
    assert set(_bytes_tree(game)) == {"game/" + cmd_fontfix.SHIM_REL, "game/zzz_skip.rpy"}
    assert (game / ("game/" + cmd_fontfix.SHIM_REL)).read_bytes().startswith(b"original")
    manifest = proj.load_manifest(str(work))
    assert manifest["files"] == []
    assert manifest["quarantined"] == []
