from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine_adapters


def test_detect_unknown_and_renpy(tmp_path):
    assert engine_adapters.detect(tmp_path)["id"] == "unknown"
    (tmp_path / "game").mkdir()
    (tmp_path / "renpy").mkdir()
    assert engine_adapters.detect(tmp_path)["id"] == "renpy"
    (tmp_path / "js").mkdir()
    (tmp_path / "js/rpg_core.js").write_text("", encoding="utf-8")
    assert engine_adapters.detect(tmp_path)["id"] == "ambiguous"


def test_detect_root_www_and_conflicting_rpg_layouts(tmp_path):
    (tmp_path / "www/js").mkdir(parents=True)
    core = tmp_path / "www/js/rpg_core.js"
    core.write_text('Utils.RPGMAKER_VERSION = "1.6.2";', encoding="utf-8")
    result = engine_adapters.detect(tmp_path)
    assert result == {"id": "rpgmaker_mv", "version": "1.6.2", "evidence": ["www/js/rpg_core.js"]}
    (tmp_path / "www/js/rmmz_core.js").write_text("", encoding="utf-8")
    assert engine_adapters.detect(tmp_path)["id"] == "ambiguous"
    core.unlink()
    assert engine_adapters.detect(tmp_path)["id"] == "rpgmaker_mz"


def test_launchers_exclude_installer_and_directories(tmp_path):
    (tmp_path / "Game.exe").write_bytes(b"test")
    (tmp_path / "unins000.exe").write_bytes(b"test")
    (tmp_path / "Fake.exe").mkdir()
    assert engine_adapters.launchers(tmp_path) == ["Game.exe"]


def test_unknown_survey_refuses_all_features(tmp_path):
    survey = engine_adapters.survey(tmp_path)
    assert survey["verdict"] == "bad"
    assert all(not row["supported"] for row in survey["feature_support"].values())
    assert set(survey["feature_support"]) == {"fontfix", "intro", "gallery", "runtime_compat"}


def test_ambiguous_installed_state_never_uses_rpg_layout(tmp_path, monkeypatch):
    (tmp_path / "game").mkdir()
    (tmp_path / "renpy").mkdir()
    (tmp_path / "js").mkdir()
    (tmp_path / "js/rpg_core.js").write_text("", encoding="utf-8")
    def unexpected(root):
        raise AssertionError("ambiguous engine must not use an adapter")
    monkeypatch.setattr(engine_adapters.rpgmaker, "installed_state", unexpected)
    state = engine_adapters.installed_state(tmp_path)
    assert state["shim"] is False and state["gallery"] is False
