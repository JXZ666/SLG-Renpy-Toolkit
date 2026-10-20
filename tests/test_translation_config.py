import json
import os

import pytest

import translation_config as config


def test_defaults_and_bad_documents(tmp_path):
    path = tmp_path / "settings.json"
    assert config.load_settings(path) == config.default_settings()
    for raw in ("not-json", "[]", "null", '{"wait_seconds":NaN}', "x" * 33000):
        path.write_text(raw, encoding="utf-8")
        result = config.load_settings(path)
        assert result["wait_seconds"] == 2.0
        assert result["api_key"] == ""


def test_deeply_nested_json_falls_back_without_breaking_startup(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
    assert path.stat().st_size < 32768
    assert config.load_settings(path) == config.default_settings()


def test_normalize_bounds_and_unknown_fields():
    result = config.normalize_settings({"wait_seconds": 300, "provider": "other",
                                        "target_lang": "", "api_key": " secret ", "unknown": "x"})
    assert result["wait_seconds"] == 30.0
    assert result["provider"] == "google"
    assert result["target_lang"] == "zh-CN"
    assert result["api_key"] == "secret"
    assert "unknown" not in result
    for invalid in (float("inf"), float("nan"), True, object()):
        assert config.normalize_settings({"wait_seconds": invalid})["wait_seconds"] == 2.0


def test_plain_config_does_not_save_key(tmp_path):
    path = tmp_path / "config.json"
    settings = config.default_settings() | {"provider": "ai", "api_key": "private-fixture-key"}
    returned = config.save_settings(settings, path=path)
    assert returned["api_key"] == "private-fixture-key"
    assert "private-fixture-key" not in path.read_text(encoding="utf-8")
    assert config.load_settings(path)["api_key"] == ""
    # Even hand-edited plain-text secrets are not imported.
    path.write_text(json.dumps(settings), encoding="utf-8")
    assert config.load_settings(path)["api_key"] == ""


def test_remembered_key_is_dpapi_only(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    calls = []

    def protect(data, *, decrypt=False):
        calls.append(decrypt)
        return data.removeprefix(b"encrypted:") if decrypt else b"encrypted:" + data

    monkeypatch.setattr(config, "_dpapi", protect)
    config.save_settings({"api_key": "private-fixture-key"}, True, path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert "api_key" not in stored
    assert stored["remember_key"] is True
    assert "private-fixture-key" not in path.read_text(encoding="utf-8")
    assert config.load_settings(path)["api_key"] == "private-fixture-key"
    assert calls == [False, True]
    config.save_settings(config.load_settings(path), False, path)
    assert "api_key_dpapi" not in path.read_text(encoding="utf-8")
    assert config.load_settings(path)["api_key"] == ""


def test_failed_decryption_falls_back_without_secret(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"remember_key":true,"api_key_dpapi":"YWJj"}', encoding="utf-8")
    def fail(*args, **kwargs):
        raise OSError("fixture decryption failure")
    monkeypatch.setattr(config, "_dpapi", fail)
    assert config.load_settings(path)["api_key"] == ""


def test_save_is_atomic_if_encryption_fails(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config.save_settings({}, path=path)
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError("fixture encryption failure")
    monkeypatch.setattr(config, "_dpapi", fail)
    with pytest.raises(OSError):
        config.save_settings({"api_key": "fixture"}, True, path)
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_real_windows_dpapi_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config.save_settings({"api_key": "synthetic-dpapi-roundtrip"}, True, path)
    assert config.load_settings(path)["api_key"] == "synthetic-dpapi-roundtrip"
    assert "synthetic-dpapi-roundtrip" not in path.read_text(encoding="utf-8")


def test_default_path_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.settings_path() == tmp_path / "rpykit/translation/settings.json"
