import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine_adapters
import patch_transaction as transaction
import proj
import rpgmaker


def game(root, engine="mv", www=False):
    base = root / "www" if www else root
    (base / "js/plugins").mkdir(parents=True)
    stem = "rpg" if engine == "mv" else "rmmz"
    (base / ("js/" + stem + "_core.js")).write_text('Utils.RPGMAKER_VERSION="1.6.2"; Bitmap.prototype._makeFontNameText=function(){};', encoding="utf-8")
    (base / ("js/" + stem + "_scenes.js")).write_text("Scene_Boot.prototype.isReady=function(){};", encoding="utf-8")
    plugins = [{"name": "Existing", "status": True, "description": "自定义", "parameters": {"a": "1", "nested": '["x"]'}},
               {"name": "Disabled", "status": False, "parameters": {}}]
    original = ("// Generated plugins\nvar $plugins =\n" + json.dumps(plugins, ensure_ascii=False) + ";\n// retained tail\n").encode("utf-8")
    (base / "js/plugins.js").write_bytes(original)
    return base, original, plugins


def args(root, work, **kwargs):
    values = dict(game_dir=str(root), work=str(work), dry_run=False, revert=False, mode="luna", features=["fontfix"], skip_intro=False)
    values.update(kwargs)
    return argparse.Namespace(**values)


@pytest.fixture(autouse=True)
def tiny_asset(tmp_path, monkeypatch):
    asset = tmp_path / "asset.ttf"
    asset.write_bytes(b"testfont")
    monkeypatch.setattr(rpgmaker, "ASSET_FONT", str(asset))


@pytest.mark.parametrize("engine,www", [("mv", False), ("mv", True), ("mz", False), ("mz", True)])
def test_install_repeat_and_exact_revert(tmp_path, engine, www):
    root, work = tmp_path / "Game", tmp_path / "work"
    base, original, plugins = game(root, engine, www)
    assert engine_adapters.survey(root)["feature_support"]["fontfix"]["supported"]
    assert rpgmaker.run(args(root, work)) == 0
    after, text, _, _ = rpgmaker.parse_plugins((base / "js/plugins.js").read_bytes())
    assert after[:-1] == plugins
    assert text.startswith("// Generated plugins") and text.endswith("// retained tail\n")
    assert after[-1]["name"] == rpgmaker.PLUGIN_NAME
    first = proj.load_manifest(work)
    rpgmaker.run(args(root, work))
    assert proj.load_manifest(work) == first
    rpgmaker.run(args(root, work, revert=True))
    assert (base / "js/plugins.js").read_bytes() == original
    assert not (base / "js/plugins/RPYKit_CJK_Font.js").exists()
    assert not (base / "fonts/RPYKit-NotoSansSC.ttf").exists()
    # A full installation after a full revert has no stale backup conflict.
    rpgmaker.run(args(root, work))


def test_dry_run_writes_nothing(tmp_path):
    root, work = tmp_path / "Game", tmp_path / "work"
    base, original, _ = game(root)
    rpgmaker.run(args(root, work, dry_run=True))
    assert not work.exists()
    assert (base / "js/plugins.js").read_bytes() == original
    assert not (base / "fonts").exists()


def test_cli_dispatch_installs_and_reverts_minimal_sample(tmp_path, monkeypatch):
    import app_main
    root = tmp_path / "MV-minimal-sample"
    base, original, _ = game(root, www=True)
    monkeypatch.setenv("RPYKIT_WORK", str(tmp_path / "work-root"))
    assert app_main.main([str(root), "--features", "fontfix"]) == 0
    assert (base / "js/plugins/RPYKit_CJK_Font.js").exists()
    state = engine_adapters.installed_state(root)
    assert state["ours"] and state["current"] and state["font"]
    assert not state["runtime_compat"]
    assert app_main.main([str(root), "--revert"]) == 0
    assert (base / "js/plugins.js").read_bytes() == original


def test_transactions_preserve_renpy_manifest_entries(tmp_path):
    root, work = tmp_path / "Game", tmp_path / "work"
    root.mkdir()
    proj.save_manifest(work, {"version": 2, "game_dir": str(root), "game_id": proj.game_identity(root),
                             "files": [{"path": "game/old.rpy", "source": "fontfix:shim", "sha256": "legacy"}],
                             "quarantined": [{"path": "game/conflict.rpy", "stored_as": "old.rpy", "source": "fontfix:intro-conflict"}]})
    transaction.install(root, work, {"new.js": b"new"})
    transaction.revert(root, work)
    manifest = proj.load_manifest(work)
    assert manifest["files"][0]["source"] == "fontfix:shim"
    assert manifest["quarantined"][0]["source"] == "fontfix:intro-conflict"


def test_all_unimplemented_rpg_features_refused(tmp_path):
    root, work = tmp_path / "Game", tmp_path / "work"
    game(root)
    support = engine_adapters.survey(root)["feature_support"]
    for feature in ("intro", "gallery", "runtime_compat"):
        assert not support[feature]["supported"]
        with pytest.raises(transaction.TransactionError, match="only fontfix"):
            rpgmaker.run(args(root, work, features=[feature]))
    assert not work.exists()


@pytest.mark.parametrize("payload", [b'var $plugins=[]; alert(1);', b'var $plugins=[{name:"x"}];', b'let $plugins=[];', b'var $plugins={};'])
def test_executable_or_unknown_plugins_refused(payload):
    with pytest.raises(transaction.TransactionError):
        rpgmaker.parse_plugins(payload)


def test_missing_hooks_and_asset_refused(tmp_path, monkeypatch):
    root = tmp_path / "Game"
    base, _, _ = game(root)
    (base / "js/rpg_scenes.js").unlink()
    assert not engine_adapters.survey(root)["feature_support"]["fontfix"]["supported"]
    (base / "js/rpg_scenes.js").write_text("isReady", encoding="utf-8")
    monkeypatch.setattr(rpgmaker, "ASSET_FONT", str(tmp_path / "missing.ttf"))
    with pytest.raises(transaction.TransactionError, match="Noto font missing"):
        rpgmaker.prepare(root)


@pytest.mark.parametrize("rel", ["../escape", "/escape", "C:/games/escape", "C:escape", "a/../../escape", "a\\..\\escape", "a:stream", "a//b"])
def test_transaction_path_attack_refused(tmp_path, rel):
    with pytest.raises(transaction.TransactionError):
        transaction.install(tmp_path / "game", tmp_path / "work", {rel: b"attack"})
    assert not (tmp_path / "work").exists()


def test_modified_config_preserves_whole_feature(tmp_path):
    root, work = tmp_path / "Game", tmp_path / "work"
    base, _, _ = game(root)
    rpgmaker.run(args(root, work))
    config = base / "js/plugins.js"
    config.write_bytes(config.read_bytes() + b"// player change")
    assert rpgmaker.run(args(root, work, revert=True)) == 1
    assert (base / "fonts/RPYKit-NotoSansSC.ttf").exists()
    assert (base / "js/plugins/RPYKit_CJK_Font.js").exists()
    with pytest.raises(transaction.TransactionError, match="changed"):
        rpgmaker.run(args(root, work))


def test_manifest_failure_rolls_back_original_and_backups(tmp_path, monkeypatch):
    root, work = tmp_path / "Game", tmp_path / "work"
    base, original, _ = game(root)
    def broken(*args):
        raise OSError("injected manifest failure")
    monkeypatch.setattr(proj, "save_manifest", broken)
    with pytest.raises(OSError, match="injected"):
        rpgmaker.run(args(root, work))
    assert (base / "js/plugins.js").read_bytes() == original
    assert not (base / "fonts").exists()
    assert not work.exists()


def test_backup_tamper_blocks_entire_revert(tmp_path):
    root, work = tmp_path / "Game", tmp_path / "work"
    base, _, _ = game(root)
    rpgmaker.run(args(root, work))
    backup = next(e["backup"] for e in proj.load_manifest(work)["files"] if e.get("backup"))
    (work / backup).write_bytes(b"tampered")
    assert rpgmaker.run(args(root, work, revert=True)) == 1
    assert (base / "js/plugins/RPYKit_CJK_Font.js").exists()


def test_symlink_output_refused(tmp_path):
    root, outside = tmp_path / "game", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "fonts").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    with pytest.raises(transaction.TransactionError, match="link"):
        transaction.install(root, tmp_path / "work", {"fonts/test.ttf": b"x"})
    assert not list(outside.iterdir())


def test_minimal_mv_mz_runtime_and_negative_control(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable; run tools/validate_rpgmaker.js in the release gate")
    plugin = tmp_path / "font.js"
    plugin.write_text(rpgmaker.PLUGIN, encoding="utf-8")
    command = [node, str(ROOT / "tools/validate_rpgmaker.js"), str(plugin)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    # Prove the runtime gate catches an implementation which skips waiting.
    plugin.write_text(rpgmaker.PLUGIN.replace("bootReady.apply(this, arguments) && ready", "bootReady.apply(this, arguments)"), encoding="utf-8")
    broken = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert broken.returncode != 0 and "boot must wait" in broken.stderr
