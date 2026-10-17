"""Cross-subsystem acceptance checks for 1.1; no real game runs or user state."""
import argparse
from pathlib import Path
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(Path(__file__).resolve().parent)):
    sys.path.insert(0, entry)
import cmd_fontfix
import fontscan
import proj
import rpgmaker
import simulation
import test_rpgmaker
import test_runtime_compat


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_nested_font_reference_uses_fonts_loader_prefix(tmp_path):
    path = tmp_path / "game/fonts/sub/face.ttf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"correct nested face")
    inventory = fontscan.font_inventory(str(tmp_path), [])
    assert cmd_fontfix._resolve("sub/face.ttf", inventory)[0] == b"correct nested face"


def test_exact_fonts_path_wins_over_alternate_extension(tmp_path):
    path = tmp_path / "game/fonts/same.ttf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"actual engine face")
    (tmp_path / "game/same.otf").write_bytes(b"different alternate face")
    inventory = fontscan.font_inventory(str(tmp_path), [])
    assert cmd_fontfix._resolve("same.ttf", inventory)[0] == b"actual engine face"


def test_unrelated_unique_basename_is_not_a_loader_font(tmp_path):
    path = tmp_path / "game/other/face.ttf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not loadable as bare face.ttf")
    inventory = fontscan.font_inventory(str(tmp_path), [])
    assert cmd_fontfix._resolve("face.ttf", inventory) == (None, None)


def test_runtime_only_installs_with_zero_font_work_and_dry_revert_is_readonly(tmp_path, monkeypatch):
    root, work = tmp_path / "game-root", tmp_path / "work"
    root.mkdir()
    test_runtime_compat.fixture(root)
    monkeypatch.setattr(cmd_fontfix, "analyse", lambda _: ({"refs": [], "inventory": {}}, []))
    args = argparse.Namespace(game_dir=str(root), work=str(work), mode="luna", features=["runtime_compat"],
                              revert=False, dry_run=False, force=False, skip_intro=False)
    assert cmd_fontfix.run(args) == 0
    assert (root / "game/zz_rpykit_compat.rpy").exists()
    before = snapshot(tmp_path)
    args.revert = True
    args.dry_run = True
    assert cmd_fontfix.run(args) == 0
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("engine,www", [("mv", True), ("mz", False)])
def test_installed_rpg_copy_inherits_backup_and_can_revert(tmp_path, monkeypatch, engine, www):
    monkeypatch.setenv("RPYKIT_WORK", str(tmp_path / "work-root"))
    asset = tmp_path / "font.ttf"
    asset.write_bytes(b"test asset")
    monkeypatch.setattr(rpgmaker, "ASSET_FONT", str(asset))
    root = tmp_path / "RPG-game"
    base, original, _ = test_rpgmaker.game(root, engine=engine, www=www)
    work = Path(proj.work_dir_for(str(root)))
    rpgmaker.run(test_rpgmaker.args(root, work))
    source_before = snapshot(root)
    ownership_before = snapshot(work)
    session = simulation.prepare(str(root), ["fontfix"])
    try:
        staged = Path(session.staged_dir)
        copied_work = Path(session.work_dir)
        manifest = proj.load_manifest(str(copied_work))
        backed = [entry for entry in manifest["files"] if entry.get("backup")]
        assert backed and all((copied_work / entry["backup"]).exists() for entry in backed)
        rpgmaker.run(test_rpgmaker.args(staged, copied_work, revert=True))
        config = staged / ("www/js/plugins.js" if www else "js/plugins.js")
        assert config.read_bytes() == original
        assert snapshot(root) == source_before
        assert snapshot(work) == ownership_before
    finally:
        session.cleanup()


def test_menu_confirmation_cannot_override_later_new_log_error(tmp_path):
    staged = tmp_path / "copy"
    staged.mkdir()
    session = simulation.SimulationSession(str(tmp_path), str(staged), str(tmp_path / "work"), [], [])
    session.process = mock.Mock()
    session.process.poll.return_value = None
    session.confirm_main_menu()
    (staged / "log.txt").write_text("Full traceback:\nException: new synthetic failure", encoding="utf-8")
    session.process.poll.return_value = 0
    assert session.poll() == 0
    assert next(step for step in session.steps if step["id"] == "launch")["status"] == "failed"
    with pytest.raises(RuntimeError, match="new error"):
        session.confirm_gameplay()
