"""Small, non-game state store for the desktop interface.

Only user preferences and manually registered game locations belong in
this file.  It never walks a selected game tree and never writes inside one.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile

import branding
import game_launch


SCHEMA_VERSION = 3
DEFAULT_WINDOW = {"width": 1180, "height": 780}
APPEARANCES = {"system", "light", "dark"}
_LEGACY_SETTINGS = "ui_state.json"
_PREVIEW_SETTINGS = "ui_state.preview.json"
_STABLE_SETTINGS = "ui_state.v3.json"


def _settings_path(filename):
    """Return the per-user settings path without creating any directories."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.expanduser("~")
    return os.path.join(base, "rpykit", filename)


def state_path():
    """Keep launcher preferences separate from the old stable configuration."""
    filename = _PREVIEW_SETTINGS if branding.APP_CHANNEL == "local-test" else _STABLE_SETTINGS
    return _settings_path(filename)


def default_state():
    return {
        "schema": SCHEMA_VERSION,
        "appearance": "system",
        "window": dict(DEFAULT_WINDOW),
        "active_game": "",
        "games": [],
    }


def _clean_name(value, fallback):
    name = str(value or "").strip()
    return name[:120] or fallback


def _normal_path(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def validate_game_path(path):
    """Validate directory availability independently of patch support."""
    if not path:
        raise ValueError("请选择游戏根目录。")
    path = os.fspath(path)
    if not isinstance(path, str) or "\x00" in path:
        raise ValueError("游戏目录无效。")
    normalized = os.path.realpath(os.path.abspath(path))
    if not os.path.isdir(normalized):
        raise ValueError("游戏目录不存在或不可访问。")
    return normalized


def _sanitize(raw, *, partial=False):
    """Keep missing preferences distinguishable from defaults during import."""
    state = {"schema": SCHEMA_VERSION, "games": []} if partial else default_state()
    if not isinstance(raw, dict):
        return state
    appearance = raw.get("appearance")
    if isinstance(appearance, str) and appearance in APPEARANCES:
        state["appearance"] = appearance

    window = raw.get("window")
    if isinstance(window, dict):
        width, height = window.get("width"), window.get("height")
        if (isinstance(width, int) and not isinstance(width, bool)
                and isinstance(height, int) and not isinstance(height, bool)):
            # Schema 1 stored physical pixels.  On a 150% display that turns
            # 900×620 into 1350×930 and the next launch grows again.  Migrate
            # once to the safe default cap; schema 2 values are logical.
            raw_schema = raw.get("schema", 1)
            migrating = not isinstance(raw_schema, int) or raw_schema < 2
            width = min(2400, max(760, width))
            height = min(1800, max(560, height))
            if migrating:
                width = min(width, 1180)
                height = min(height, 780)
            state["window"] = {"width": width, "height": height}

    games = raw.get("games")
    if isinstance(games, list):
        seen = set()
        for entry in games:
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            raw_path = entry.get("path")
            if not isinstance(raw_path, (str, os.PathLike)):
                continue
            raw_path = os.fspath(raw_path)
            if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
                continue
            try:
                path = validate_game_path(raw_path)
                available = True
            except (OSError, TypeError, ValueError):
                # Keep the manual bookmark when a game is moved or its drive is
                # offline.  Re-validating on every save used to delete it during
                # an unrelated window resize.  The UI must show it as
                # unavailable and must never scan beneath it until it returns.
                path = os.path.abspath(raw_path)
                available = False
            key = _normal_path(path)
            if key in seen:
                continue
            seen.add(key)
            cleaned_entry = {"path": path, "available": available}
            name = entry.get("name")
            if not partial:
                cleaned_entry["name"] = _clean_name(name, os.path.basename(path))
            elif isinstance(name, str) and name.strip():
                cleaned_entry["name"] = _clean_name(name, "")
            if entry.get("launcher_rel"):
                try:
                    # Keep a safe reference while a drive is offline or an exe
                    # is missing.  Every launch validates the live file again.
                    cleaned_entry["launcher_rel"] = game_launch.normalize_launcher_rel(
                        entry["launcher_rel"])
                except (TypeError, ValueError):
                    pass
            state["games"].append(cleaned_entry)

    active = raw.get("active_game")
    if isinstance(active, str) and active and "\x00" not in active:
        if partial:
            state["active_game"] = active
        else:
            key = _normal_path(active)
            state["active_game"] = next((item["path"] for item in state["games"]
                                         if _normal_path(item["path"]) == key), "")
    return state


def _read_settings(filename):
    try:
        with open(filename, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, ValueError, RecursionError):
        return None
    return raw if isinstance(raw, dict) else None


def _migrate_stable(filename):
    legacy = _read_settings(_settings_path(_LEGACY_SETTINGS))
    preview = _read_settings(_settings_path(_PREVIEW_SETTINGS))
    if legacy is None and preview is None:
        return default_state()

    legacy = _sanitize(legacy, partial=True)
    preview = _sanitize(preview, partial=True)
    state = default_state()
    bookmarks = {}
    for source in (legacy, preview):
        for preference in ("appearance", "window"):
            if preference in source:
                state[preference] = source[preference]
        for entry in source["games"]:
            bookmarks.setdefault(_normal_path(entry["path"]), {}).update(entry)
    for entry in bookmarks.values():
        entry.setdefault("name", os.path.basename(entry["path"]))
    state["games"] = list(bookmarks.values())
    for source in (preview, legacy):
        active = source.get("active_game")
        if active and _normal_path(active) in bookmarks:
            state["active_game"] = bookmarks[_normal_path(active)]["path"]
            break

    try:
        _write_settings(state, filename, create_only=True)
    except FileExistsError:
        # Another instance finished the first import while this one was reading.
        existing = _read_settings(filename)
        if existing is not None:
            return _sanitize(existing)
    except OSError:
        # Keep the merged preferences usable in memory and retry on next load.
        pass
    return state


def load_state(path=None):
    """Read one settings file, importing older preferences on first stable use."""
    filename = state_path() if path is None else os.fspath(path)
    if path is None and not os.path.lexists(filename):
        if branding.APP_CHANNEL == "stable":
            return _migrate_stable(filename)
        if branding.APP_CHANNEL == "local-test":
            # The preview's first load reads the legacy file without saving.
            filename = _settings_path(_LEGACY_SETTINGS)
    return _sanitize(_read_settings(filename))


def _write_settings(state, filename, *, create_only=False):
    filename = os.path.abspath(filename)
    parent = os.path.dirname(filename)
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ui_state-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if not create_only:
            os.replace(temporary, filename)
        elif os.name == "nt":
            os.rename(temporary, filename)  # Windows rename refuses an existing destination.
        else:
            os.link(temporary, filename)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    return filename


def save_state(state, path=None):
    """Atomically write a validated settings snapshot and return its path."""
    filename = state_path() if path is None else os.fspath(path)
    return _write_settings(_sanitize(state), filename)


def add_game(state, path, name=None):
    """Return a copy with a validated game added or its display name updated."""
    game_path = validate_game_path(path)
    result = copy.deepcopy(_sanitize(state))
    key = _normal_path(game_path)
    for item in result["games"]:
        if _normal_path(item["path"]) == key:
            item["name"] = _clean_name(name, item["name"])
            item["available"] = True
            result["active_game"] = item["path"]
            return result
    entry = {"path": game_path,
             "name": _clean_name(name, os.path.basename(game_path)),
             "available": True}
    result["games"].append(entry)
    result["active_game"] = game_path
    return result


def remove_game(state, path):
    """Return a copy with one library entry removed, without touching files."""
    result = copy.deepcopy(_sanitize(state))
    key = _normal_path(path)
    result["games"] = [item for item in result["games"]
                       if _normal_path(item["path"]) != key]
    if result["active_game"] and _normal_path(result["active_game"]) == key:
        result["active_game"] = ""
    return result


def rename_game(state, path, name):
    """Rename an existing bookmark even when its game is offline."""
    result = copy.deepcopy(_sanitize(state))
    key = _normal_path(path)
    for item in result["games"]:
        if _normal_path(item["path"]) == key:
            item["name"] = _clean_name(name, item["name"])
            return result
    raise ValueError("该游戏已不在游戏库中，请刷新后重试。")


def set_launcher(state, path, launcher_rel):
    """Return a copy with this bookmark's manually chosen exe, or clear it."""
    result = copy.deepcopy(_sanitize(state))
    key = _normal_path(path)
    for item in result["games"]:
        if _normal_path(item["path"]) == key:
            if launcher_rel is None or launcher_rel == "":
                item.pop("launcher_rel", None)
            else:
                item["launcher_rel"] = game_launch.validate_launcher(item["path"], launcher_rel)
            return result
    raise ValueError("该游戏已不在游戏库中，请刷新后重试。")

