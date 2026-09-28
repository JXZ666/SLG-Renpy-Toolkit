"""Release identity and generated Windows version-resource tests."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import branding
import app_main
import app_window
from tools.write_version_info import render_version_info


def test_version_is_single_release_constant():
    assert branding.APP_VERSION == "1.0.0"


def test_cli_version(capsys):
    try:
        app_main.main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert capsys.readouterr().out.strip() == "SLG-Renpy-Toolkit 1.0.0"


def test_cli_without_game_prints_help_instead_of_opening_gui(capsys, monkeypatch):
    monkeypatch.setattr(app_window, "main", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("the CLI entry point must not open the GUI")
    ))
    assert app_main.main([]) == 0
    output = capsys.readouterr().out
    assert "usage:" in output.lower()
    assert "--revert" in output


def test_window_entry_forwards_only_first_path_to_gui(monkeypatch):
    calls = []
    monkeypatch.setattr(app_window.appgui, "main", lambda **kwargs: calls.append(kwargs))
    assert app_window.main([r"D:\Games\Example", "--dry-run"]) == 0
    assert calls == [{"initial_dir": r"D:\Games\Example"}]


def test_version_resource_has_numeric_and_string_version_fields():
    resource = render_version_info("SLG-Renpy-Toolkit-CLI.exe")
    assert "filevers=(1, 0, 0, 0)" in resource
    assert "prodvers=(1, 0, 0, 0)" in resource
    assert "StringStruct('FileVersion', '1.0.0')" in resource
    assert "StringStruct('ProductVersion', '1.0.0')" in resource
    assert "StringStruct('OriginalFilename', 'SLG-Renpy-Toolkit-CLI.exe')" in resource


def test_gui_and_cli_specs_select_correct_subsystems():
    gui_spec = (ROOT / "SLG-Renpy-Toolkit.spec").read_text(encoding="utf-8")
    cli_spec = (ROOT / "SLG-Renpy-Toolkit-CLI.spec").read_text(encoding="utf-8")
    assert "console=False" in gui_spec
    assert "console=True" in cli_spec
    assert "collect_data_files('customtkinter')" in gui_spec
    assert "exclude_binaries=True" in gui_spec
    assert "COLLECT(" in gui_spec and "COLLECT(" in cli_spec
    assert "app_window.py" in gui_spec
    assert "app_main.py" in cli_spec
