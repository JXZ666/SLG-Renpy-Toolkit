"""Regression: in-game exceptions can occur while the launcher keeps running."""
from pathlib import Path
from unittest import mock

import pytest

import simulation


def session(tmp_path):
    staged = tmp_path / "copy"
    staged.mkdir()
    return simulation.SimulationSession(str(tmp_path), str(staged), str(tmp_path / "work"), [], [])


def test_unchanged_historical_traceback_is_ignored(tmp_path):
    s = session(tmp_path)
    error = Path(s.staged_dir, "traceback.txt")
    error.write_text("Exception: old error", encoding="utf-8")
    s._diagnostics_seen = simulation._diagnostic_snapshot(s.staged_dir)
    s.process = mock.Mock()
    s.process.poll.return_value = None
    assert s.poll() is None
    assert s.runtime_errors == []


def test_new_traceback_rejects_confirmation_even_when_process_runs(tmp_path):
    s = session(tmp_path)
    s.process = mock.Mock()
    s.process.poll.return_value = None
    Path(s.staged_dir, "traceback.txt").write_text("Exception: dialogue mismatch", encoding="utf-8")
    assert s.poll() is None
    assert s.steps[-1]["status"] == "failed"
    with pytest.raises(RuntimeError, match="new error"):
        s.confirm_main_menu()
    assert "dialogue mismatch" in s.log_tail


def test_error_after_menu_overrides_success_and_zero_exit(tmp_path):
    s = session(tmp_path)
    s.process = mock.Mock()
    s.process.poll.return_value = None
    s.confirm_main_menu()
    assert not s.gameplay_confirmed
    Path(s.staged_dir, "errors.txt").write_text("ParseError: invalid screen", encoding="utf-8")
    s.process.poll.return_value = 0
    assert s.poll() == 0
    assert s.steps[-1]["status"] == "failed"
    with pytest.raises(RuntimeError):
        s.confirm_gameplay()


def test_normal_log_and_explicit_gameplay_confirmation(tmp_path):
    s = session(tmp_path)
    s.process = mock.Mock()
    s.process.poll.return_value = None
    Path(s.staged_dir, "log.txt").write_text("Loading scripts completed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="main menu"):
        s.confirm_gameplay()
    s.confirm_main_menu()
    assert not s.gameplay_confirmed
    assert s.confirm_gameplay()
    assert s.steps[-1]["id"] == "gameplay"
    assert not s.runtime_errors


def test_log_traceback_is_detected(tmp_path):
    s = session(tmp_path)
    Path(s.staged_dir, "log.txt").write_text("Full traceback:\nScriptError: no entry", encoding="utf-8")
    assert s.check_runtime_errors()
