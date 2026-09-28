"""End-to-end routing between the two font install mechanisms (Task 2).

The incident this file closes: an older build wrote the Ren'Py 7.6+-only shim -
the one that assigns `config.font_name_map` - into a Ren'Py 7.5.3 game, whose
engine has never heard of that variable. The game died on startup with

    Exception: config.font_name_map is not a known configuration variable.

The routing decision in `compat._feature_support` is a per-game choice between
`font_name_map` (7.6+) and `font_replacement_map` (6 - 7.5), so the only test
that would have caught it has to drive a *real install* and look at the file
that lands on disk, not merely at the survey dict. That is what
`test_installing_into_a_753_game_...` below does.

Reused helpers, not reimplemented: `test_compat.make` (synthesizes the game
tree), `test_install.run_fontfix` + `test_install._Env` (run an install against
a temp work dir, so nothing touches %LOCALAPPDATA%) and `cmd_fontfix.
validate_shim_legacy` (the existing negative validator). `test_compat` does no
work at import time, so importing it is clean; no construction was copied.
"""

from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
# Same repo-root insertion as test_release.py / test_rpa.py; HERE so the sibling
# script modules import when this file is run directly too.
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest  # noqa: E402

import cmd_fontfix  # noqa: E402
import compat  # noqa: E402
import font_merge  # noqa: E402
import test_compat  # noqa: E402
import test_fontfix  # noqa: E402
import test_install  # noqa: E402


def _game(tmp_path, name, **kwargs):
    return test_compat.make(str(tmp_path / name), **kwargs)


def _stub_font(tmp_path):
    path = tmp_path / "stub.ttf"
    path.write_bytes(b"TTF")
    return str(path)


def _shim(game):
    with open(os.path.join(game, "game", cmd_fontfix.SHIM_REL),
              encoding="utf-8") as f:
        return f.read()


def _report(work):
    with open(os.path.join(work, "fontfix_report.json"), encoding="utf-8") as f:
        return json.load(f)


def _install_modern(monkeypatch, tmp_path, **kwargs):
    """A real install on the runtime-alias route (Ren'Py 7.6+)."""
    game = _game(tmp_path, "modern", **kwargs)
    work = str(tmp_path / "modern-work")
    monkeypatch.setattr(cmd_fontfix, "ASSET_FONT", _stub_font(tmp_path))
    with test_install._Env(RPYKIT_WORK=work):
        test_install.run_fontfix(game, work=work)
    return game, work


def _install_legacy(monkeypatch, tmp_path, **kwargs):
    """A real install on the font-file route (Ren'Py 6 - 7.5).

    The route's font *bytes* are stubbed for the same reason test_install swaps
    ASSET_FONT for three bytes: preparing the CJK face instances the 17.8 MB
    variable font (~14 s) and merged faces go through fontTools, and neither
    byte changes which shim template is written - the thing under test. run(),
    install(), prepare() and validate_shim_legacy() all still execute for real.
    """
    game = _game(tmp_path, "legacy", **kwargs)
    work = str(tmp_path / "legacy-work")
    stub = _stub_font(tmp_path)
    monkeypatch.setattr(font_merge, "prepared_cjk", lambda *a, **k: stub)
    monkeypatch.setattr(font_merge, "install_cached",
                        lambda src, cjk, dest, cache, **k: (dest, 3, False))
    with test_install._Env(RPYKIT_WORK=work):
        test_install.run_fontfix(game, work=work)
    return game, work


# --- 1. survey() picks the mechanism from the declared hook -----------------

def test_survey_uses_name_map_when_only_that_hook_is_declared(tmp_path):
    game = _game(tmp_path, "name-map", font_map=True, font_group=True,
                 replacement_map=False)
    ff = compat.survey(game)["feature_support"]["fontfix"]
    assert ff["supported"] is True
    assert ff["mechanism"] == "font_name_map"


def test_survey_uses_replacement_map_when_only_that_hook_is_declared(tmp_path):
    game = _game(tmp_path, "replacement", py=2, script_version="(7, 4, 11)",
                 font_map=False, font_group=False, replacement_map=True)
    ff = compat.survey(game)["feature_support"]["fontfix"]
    # This route also needs fontTools, which is installed in this environment;
    # test_missing_fonttools_refuses_the_replacement_route covers its absence.
    assert ff["supported"] is True
    assert ff["mechanism"] == "font_replacement_map"


def test_survey_refuses_an_engine_with_neither_hook(tmp_path):
    game = _game(tmp_path, "neither", font_map=False, font_group=False,
                 replacement_map=False)
    ff = compat.survey(game)["feature_support"]["fontfix"]
    assert ff["supported"] is False
    assert ff["mechanism"] is None


# --- 2/3. the install writes the shim its engine can actually load ----------

def test_installing_into_a_753_game_writes_the_legacy_shim(monkeypatch, tmp_path):
    """The regression test for the startup crash: 7.5.3 must never get the
    font_name_map shim, which its engine does not define."""
    game, work = _install_legacy(
        monkeypatch, tmp_path, py=2, arch=("i686", "x86_64"),
        script_version="(7, 5, 3)", font_map=False, font_group=False,
        replacement_map=True)
    shim = _shim(game)
    assert "config.font_replacement_map[" in shim
    assert "config.font_name_map[" not in shim
    # The install's own legacy self-check agrees the map is assigned; an empty
    # target set only makes it complain about redirects, which is not the point.
    assert not any("no config.font_replacement_map" in p
                   for p in cmd_fontfix.validate_shim_legacy(shim, set()))
    assert _report(work)["mechanism"] == "font_replacement_map"


def test_installing_into_a_76_game_writes_the_name_map_shim(monkeypatch, tmp_path):
    game, work = _install_modern(
        monkeypatch, tmp_path, py=3, script_version="(7, 6, 1)",
        font_map=True, font_group=True, replacement_map=False)
    shim = _shim(game)
    assert "config.font_name_map[" in shim
    assert "config.font_replacement_map[" not in shim
    assert not cmd_fontfix.validate_shim(shim)
    assert _report(work)["mechanism"] == "font_name_map"


# --- 4. the existing negative validator catches the wrong shim --------------

def test_legacy_validator_reports_a_name_map_shim_as_a_problem():
    decisions = [{"names": ["SomeFace.ttf"], "action": "noto-only", "cjk": 0,
                  "why": "synthetic", "where": "loose"}]
    name_map_shim = test_fontfix.build(decisions)
    problems = cmd_fontfix.validate_shim_legacy(name_map_shim, set())
    assert problems
    assert any("config.font_replacement_map" in p for p in problems)


# --- 5. no fontTools means the old route is refused, not degraded -----------

def test_missing_fonttools_refuses_the_replacement_route(monkeypatch, tmp_path):
    game = _game(tmp_path, "no-fonttools", py=2, script_version="(7, 5, 3)",
                 font_map=False, font_group=False, replacement_map=True)
    monkeypatch.setattr(font_merge, "fonttools_available", lambda: False)
    ff = compat.survey(game)["feature_support"]["fontfix"]
    assert ff["supported"] is False
    assert ff["mechanism"] is None
    assert any("fontTools" in r for r in ff["reasons"])
    # Refused outright: run() raises before any file is written, rather than
    # silently falling back to a route the engine cannot use.
    work = str(tmp_path / "no-fonttools-work")
    with test_install._Env(RPYKIT_WORK=work):
        with pytest.raises(cmd_fontfix.FontFixError):
            test_install.run_fontfix(game, work=work)
    assert not os.path.exists(os.path.join(game, "game", cmd_fontfix.SHIM_REL))
