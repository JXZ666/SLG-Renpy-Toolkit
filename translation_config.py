"""Translation preferences. API keys are never stored as plain JSON values."""
from __future__ import annotations

import base64
import ctypes
import json
import math
import os
from pathlib import Path
import tempfile


def default_settings():
    return {"provider": "google", "source_lang": "auto", "target_lang": "zh-CN",
            "wait_seconds": 2.0, "ai_endpoint": "", "ai_model": "", "api_key": ""}


def settings_path():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise OSError("LOCALAPPDATA is unavailable; specify a translation settings path")
    return Path(base) / "rpykit" / "translation" / "settings.json"


def normalize_settings(settings):
    """Copy only documented values, with bounded sizes and a finite wait."""
    result = default_settings()
    if not isinstance(settings, dict):
        return result
    for name in ("source_lang", "target_lang", "ai_endpoint", "ai_model", "api_key"):
        value = settings.get(name)
        if isinstance(value, str):
            result[name] = value[:8192 if name == "api_key" else 2048].strip()
    if settings.get("provider") in ("google", "ai"):
        result["provider"] = settings["provider"]
    value = settings.get("wait_seconds", 2.0)
    if not isinstance(value, bool):
        try:
            number = float(value)
            if math.isfinite(number):
                result["wait_seconds"] = min(30.0, max(0.0, number))
        except (TypeError, ValueError, OverflowError):
            pass
    result["source_lang"] = result["source_lang"] or "auto"
    result["target_lang"] = result["target_lang"] or "zh-CN"
    return result


def _dpapi(data, *, decrypt=False):
    if os.name != "nt":
        raise OSError("Remembering API keys requires Windows DPAPI")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD),
                    ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        function = crypt.CryptUnprotectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        function = crypt.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), "RPYKit translation API key", None, None,
                None, 1, ctypes.byref(target))
    function.restype = wintypes.BOOL
    if not function(*args):
        raise OSError("Windows credential encryption failed")
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def load_settings(path=None):
    location = Path(path) if path is not None else settings_path()
    try:
        if location.stat().st_size > 32768:
            return default_settings()
        data = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, RecursionError):
        return default_settings()
    result = normalize_settings(data)
    # Ignore historical or manually inserted plain-text keys on disk.
    result["api_key"] = ""
    if isinstance(data, dict) and data.get("remember_key") is True:
        encrypted = data.get("api_key_dpapi")
        if isinstance(encrypted, str) and len(encrypted) <= 16384:
            try:
                result["api_key"] = _dpapi(base64.b64decode(encrypted, validate=True),
                                           decrypt=True).decode("utf-8")
            except (OSError, ValueError, UnicodeError):
                pass
    return result


def save_settings(settings, remember_key=False, path=None):
    result = normalize_settings(settings)
    data = {key: value for key, value in result.items() if key != "api_key"}
    data["remember_key"] = bool(remember_key)
    if remember_key and result["api_key"]:
        data["api_key_dpapi"] = base64.b64encode(
            _dpapi(result["api_key"].encode("utf-8"))).decode("ascii")
    location = Path(path) if path is not None else settings_path()
    location.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix=".translation-", suffix=".tmp",
                                        dir=str(location.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, location)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
    return result
