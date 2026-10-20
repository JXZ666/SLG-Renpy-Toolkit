"""Launch a manually selected game executable without owning its lifetime.

The library never guesses a launcher.  Stored selections are relative to the
bookmarked directory, and are checked again immediately before every launch.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def normalize_launcher_rel(value):
    """Validate a saved reference without requiring an online game directory."""
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("请选择游戏目录内的 exe 启动程序。")
    value = os.fspath(value)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("启动程序路径无效。")
    value = value.replace("\\", "/")
    parts = value.split("/")
    if (value.startswith("/") or re.match(r"^[A-Za-z]:", value)
            or any(part in ("", ".", "..") or ":" in part
                   or part.endswith((" ", ".")) for part in parts)):
        raise ValueError("启动程序必须位于游戏目录内，不能使用跳转路径。")
    if not parts[-1].lower().endswith(".exe"):
        raise ValueError("请选择 exe 启动程序。")
    return "/".join(parts)


def _check_chain(path):
    """Refuse symlinks and Windows junctions before any realpath resolution."""
    absolute = Path(os.path.abspath(path))
    for item in [*reversed(absolute.parents), absolute]:
        try:
            info = os.lstat(item)
        except OSError as exc:
            raise ValueError("游戏目录或启动程序不存在、不可访问，请重新选择。") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise ValueError("启动路径不能包含符号链接或目录联接，请选择实际游戏文件。")
    return info


def _root_path(game_root):
    try:
        root = os.fspath(game_root)
    except (TypeError, ValueError) as exc:
        raise ValueError("游戏目录无效。") from exc
    if not isinstance(root, str) or not root or "\x00" in root:
        raise ValueError("游戏目录无效。")
    root = os.path.abspath(root)
    info = _check_chain(root)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("游戏目录不存在或不可访问。")
    return root


def validate_launcher(game_root, selected_path):
    """Return a safe relative exe path, or raise ValueError to request selection."""
    root = _root_path(game_root)
    try:
        selected = os.fspath(selected_path)
    except TypeError as exc:
        raise ValueError("请选择游戏目录内的 exe 启动程序。") from exc
    if not isinstance(selected, str) or not selected or "\x00" in selected:
        raise ValueError("启动程序路径无效。")
    if any(part in (".", "..") for part in selected.replace("\\", "/").split("/")):
        raise ValueError("启动程序必须位于游戏目录内，不能使用跳转路径。")
    if os.path.isabs(selected):
        # relpath also rejects a selection on a different Windows drive.
        try:
            reference = os.path.relpath(selected, root)
        except ValueError as exc:
            raise ValueError("启动程序必须位于游戏目录内。") from exc
    else:
        reference = selected
    reference = normalize_launcher_rel(reference)
    absolute = os.path.join(root, *reference.split("/"))
    info = _check_chain(absolute)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("请选择常规 exe 文件，不能选择目录。")
    # The link checks above reject alias paths; retain a final containment check
    # for unusual filesystem spellings and platforms with different drives.
    try:
        inside = os.path.normcase(os.path.commonpath((root, os.path.realpath(absolute))))
    except ValueError as exc:
        raise ValueError("启动程序必须位于游戏目录内。") from exc
    if inside != os.path.normcase(os.path.realpath(root)):
        raise ValueError("启动程序必须位于游戏目录内。")
    return reference


def resolve_launcher(game_root, launcher_rel):
    """Resolve a saved relative selection, rechecking existence and containment."""
    reference = normalize_launcher_rel(launcher_rel)
    reference = validate_launcher(game_root, reference)
    return os.path.join(os.path.abspath(os.fspath(game_root)), *reference.split("/"))


def launch(game_root, launcher_rel, env=None):
    """Start a normal game process; its caller must not terminate it on UI exit."""
    executable = resolve_launcher(game_root, launcher_rel)
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("RPYKIT_TRANSLATION_")}
    if env is not None:
        if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                            for k, v in env.items()):
            raise ValueError("启动环境配置无效。")
        environment.update(env)
    return subprocess.Popen([executable], cwd=os.path.dirname(executable),
                            shell=False, env=environment)


def open_folder(path):
    """Open this exact library directory, independently of the selected game."""
    try:
        directory = os.fspath(path)
    except (TypeError, ValueError) as exc:
        raise ValueError("游戏目录无效。") from exc
    if not isinstance(directory, str) or not directory or "\x00" in directory:
        raise ValueError("游戏目录无效。")
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        raise ValueError("游戏目录不存在或不可访问。")
    os.startfile(directory)
