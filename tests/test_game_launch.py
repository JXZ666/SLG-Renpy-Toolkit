"""Manual launcher references are checked without starting real games."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import game_launch


def make_exe(root, name="启动 游戏 & Test.EXE"):
    root.mkdir(parents=True, exist_ok=True)
    executable = root / name
    executable.write_bytes(b"launcher fixture, never executed")
    return executable


def test_selected_absolute_and_relative_subdirectory_paths_round_trip(tmp_path):
    root = tmp_path / "中文 游戏 & 目录"
    executable = make_exe(root / "bin")
    expected = "bin/" + executable.name
    assert game_launch.validate_launcher(root, executable) == expected
    assert game_launch.validate_launcher(root, expected.replace("/", "\\")) == expected
    assert game_launch.resolve_launcher(root, expected) == str(executable)


@pytest.mark.parametrize("reference", [
    "", None, b"Game.exe", "../Outside.exe", "bin/../Game.exe", "./Game.exe",
    "/Outside.exe", "C:Game.exe", "C:/games/Outside.exe", "Game.exe:stream", "Game.bat",
    "Game.exe/", "bin//Game.exe", "bin./Game.exe", "bin /Game.exe", "Game.exe\x00",
])
def test_unsafe_saved_references_request_new_selection(tmp_path, reference):
    root = tmp_path / "game"
    make_exe(root, "Game.exe")
    with pytest.raises(ValueError):
        game_launch.resolve_launcher(root, reference)


def test_external_directory_and_missing_exe_are_rejected(tmp_path):
    root = tmp_path / "game"
    executable = make_exe(root, "Game.exe")
    outside = make_exe(tmp_path / "other", "Outside.exe")
    with pytest.raises(ValueError):
        game_launch.validate_launcher(root, outside)
    executable.unlink()
    with pytest.raises(ValueError, match="重新选择"):
        game_launch.resolve_launcher(root, "Game.exe")
    (root / "Game.exe").mkdir()
    with pytest.raises(ValueError, match="常规"):
        game_launch.resolve_launcher(root, "Game.exe")


def test_absolute_path_cannot_hide_an_intermediate_link_with_parent_segment(tmp_path):
    root = tmp_path / "game"
    make_exe(root, "Game.exe")
    with pytest.raises(ValueError, match="跳转"):
        game_launch.validate_launcher(root, str(root / "link" / ".." / "Game.exe"))


def test_symbolic_link_file_and_directory_and_root_are_rejected(tmp_path):
    root = tmp_path / "game"
    executable = make_exe(root, "Game.exe")
    try:
        (root / "Alias.exe").symlink_to(executable)
        (root / "linked-bin").symlink_to(root, target_is_directory=True)
        alias_root = tmp_path / "alias-root"
        alias_root.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic link permission unavailable")
    for base, reference in ((root, "Alias.exe"), (root, "linked-bin/Game.exe"),
                            (alias_root, "Game.exe")):
        with pytest.raises(ValueError, match="符号链接"):
            game_launch.resolve_launcher(base, reference)


def test_windows_reparse_flag_is_rejected_even_without_symlink_mode(tmp_path, monkeypatch):
    root = tmp_path / "game"
    executable = make_exe(root / "bin", "Game.exe")
    original = os.lstat

    def flagged(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if os.path.normcase(os.fspath(path)) == os.path.normcase(str(executable.parent)):
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(game_launch.os, "lstat", flagged)
    with pytest.raises(ValueError, match="目录联接"):
        game_launch.resolve_launcher(root, "bin/Game.exe")


def test_launch_uses_one_argument_and_exe_working_directory_without_capturing(tmp_path, monkeypatch):
    root = tmp_path / "游戏 & test"
    executable = make_exe(root / "bin")
    environment = {"CUSTOM_TEST": "local"}
    monkeypatch.setattr(game_launch.os, "environ", {"PATH": "system-path", "RPYKIT_TRANSLATION_TOKEN": "stale"})
    with mock.patch.object(game_launch.subprocess, "Popen") as popen:
        process = game_launch.launch(root, "bin/" + executable.name, env=environment)
    popen.assert_called_once_with([str(executable)], cwd=str(executable.parent),
                                  shell=False, env={"PATH": "system-path", "CUSTOM_TEST": "local"})
    assert process is popen.return_value
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_normal_launch_cannot_inherit_a_translation_session(tmp_path, monkeypatch):
    executable = make_exe(tmp_path / "game")
    monkeypatch.setattr(game_launch.os, "environ", {"SystemRoot": "system", "RPYKIT_TRANSLATION_URL": "stale"})
    with mock.patch.object(game_launch.subprocess, "Popen") as popen:
        game_launch.launch(executable.parent, executable.name)
    assert popen.call_args.kwargs["env"] == {"SystemRoot": "system"}


def test_system_launch_errors_remain_visible(tmp_path):
    executable = make_exe(tmp_path / "game")
    with mock.patch.object(game_launch.subprocess, "Popen", side_effect=OSError("blocked")):
        with pytest.raises(OSError, match="blocked"):
            game_launch.launch(executable.parent, executable.name)


def test_open_folder_uses_supplied_bookmark_without_engine_detection(tmp_path):
    folder = tmp_path / "普通目录 & 中文"
    folder.mkdir()
    with mock.patch.object(game_launch.os, "startfile", create=True) as open_file:
        game_launch.open_folder(folder)
    open_file.assert_called_once_with(str(folder))
    for missing in (tmp_path / "missing", folder / "file.exe", "", None):
        with pytest.raises(ValueError):
            game_launch.open_folder(missing)


def test_open_folder_system_error_is_not_swallowed(tmp_path):
    with mock.patch.object(game_launch.os, "startfile", create=True,
                           side_effect=OSError("Explorer failed")):
        with pytest.raises(OSError, match="Explorer failed"):
            game_launch.open_folder(tmp_path)
