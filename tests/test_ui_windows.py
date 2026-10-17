"""Offline checks for the Windows process setup and the GUI entry point.

No real Tk root is created and no real Windows API is required: ``ctypes.windll``
is replaced with small fakes, and the import-time check loads ``app_window``
against fake ``win_platform`` / ``appgui`` modules.
"""

import ctypes
import importlib
import importlib.abc
import importlib.util
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app_window  # noqa: E402
import win_platform  # noqa: E402

REQUIRED_ICON_SIZES = {
    (16, 16), (20, 20), (24, 24), (30, 30), (32, 32), (36, 36),
    (40, 40), (44, 44), (48, 48), (64, 64), (96, 96), (128, 128),
    (256, 256),
}


def _install_windll(monkeypatch, *, user32=None, shcore=None, shell32=None):
    """Replace the WinDLL loader with only the modules a test needs."""
    windll = types.SimpleNamespace()
    if user32 is not None:
        windll.user32 = user32
    if shcore is not None:
        windll.shcore = shcore
    if shell32 is not None:
        windll.shell32 = shell32
    monkeypatch.setattr(win_platform.ctypes, "windll", windll, raising=False)
    return windll


def _recorder(events, name, result):
    def call(*args):
        events.append((name,) + args)
        return result
    return call


def test_dpi_awareness_prefers_per_monitor_v2(monkeypatch):
    events = []
    user32 = types.SimpleNamespace(
        SetProcessDpiAwarenessContext=_recorder(events, "context", 1),
        SetProcessDPIAware=_recorder(events, "legacy", 1),
    )
    shcore = types.SimpleNamespace(
        SetProcessDpiAwareness=_recorder(events, "shcore", 0),
    )
    _install_windll(monkeypatch, user32=user32, shcore=shcore)

    assert win_platform.enable_dpi_awareness() == "per_monitor_v2"
    assert [event[0] for event in events] == ["context"]
    assert events[0][1].value == ctypes.c_void_p(-4).value


def test_dpi_awareness_falls_back_per_monitor_then_system(monkeypatch):
    events = []

    def context(_value):
        events.append(("context",))
        raise OSError("SetProcessDpiAwarenessContext unavailable")

    def shcore(level):
        events.append(("shcore", level))
        return 0x80070005 if level == 2 else 0  # E_ACCESSDENIED, then S_OK

    user32 = types.SimpleNamespace(SetProcessDpiAwarenessContext=context)
    _install_windll(monkeypatch, user32=user32,
                    shcore=types.SimpleNamespace(SetProcessDpiAwareness=shcore))

    assert win_platform.enable_dpi_awareness() == "system"
    assert events == [("context",), ("shcore", 2), ("shcore", 1)]


def test_dpi_awareness_falls_back_to_legacy(monkeypatch):
    events = []

    def context(_value):
        events.append("context")
        raise AttributeError("no context API")

    def shcore(level):
        events.append(("shcore", level))
        raise OSError("shcore unavailable")

    user32 = types.SimpleNamespace(
        SetProcessDpiAwarenessContext=context,
        SetProcessDPIAware=_recorder(events, "legacy", 1),
    )
    _install_windll(monkeypatch, user32=user32,
                    shcore=types.SimpleNamespace(SetProcessDpiAwareness=shcore))

    assert win_platform.enable_dpi_awareness() == "legacy"
    assert events == ["context", ("shcore", 2), ("shcore", 1), ("legacy",)]


def test_dpi_awareness_returns_unavailable_when_every_api_fails(monkeypatch):
    user32 = types.SimpleNamespace(
        SetProcessDpiAwarenessContext=lambda _value: 0,
        SetProcessDPIAware=lambda: 0,
    )
    shcore = types.SimpleNamespace(SetProcessDpiAwareness=lambda _level: 1)
    _install_windll(monkeypatch, user32=user32, shcore=shcore)

    assert win_platform.enable_dpi_awareness() == "unavailable"


def test_dpi_awareness_swallows_missing_modules_and_attributes(monkeypatch):
    _install_windll(monkeypatch)  # no user32, no shcore
    assert win_platform.enable_dpi_awareness() == "unavailable"

    user32 = types.SimpleNamespace(
        SetProcessDpiAwarenessContext=_recorder([], "context", 0))
    _install_windll(monkeypatch, user32=user32)
    assert win_platform.enable_dpi_awareness() == "unavailable"


def test_platform_calls_are_unavailable_without_windll(monkeypatch):
    monkeypatch.delattr(win_platform.ctypes, "windll", raising=False)

    assert win_platform.enable_dpi_awareness() == "unavailable"
    assert win_platform.set_app_user_model_id() is False
    assert win_platform.prepare_windows_process() == {
        "dpi_awareness": "unavailable",
        "app_user_model_id": False,
    }


def test_app_user_model_id_sets_stable_id(monkeypatch):
    seen = []

    def set_id(value):
        seen.append(value)
        return 0

    _install_windll(
        monkeypatch,
        shell32=types.SimpleNamespace(
            SetCurrentProcessExplicitAppUserModelID=set_id),
    )

    assert win_platform.set_app_user_model_id() is True
    assert win_platform.set_app_user_model_id("Contoso.Test.App") is True
    assert seen == ["JXZ666.SLG-Renpy-Toolkit", "Contoso.Test.App"]


def test_app_user_model_id_failure_returns_false(monkeypatch):
    def reject(_value):
        return 0x80070005

    def explode(_value):
        raise OSError("shell32 unavailable")

    _install_windll(monkeypatch, shell32=types.SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=reject))
    assert win_platform.set_app_user_model_id() is False

    _install_windll(monkeypatch, shell32=types.SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=explode))
    assert win_platform.set_app_user_model_id() is False


def test_prepare_windows_process_reports_both_results(monkeypatch):
    monkeypatch.setattr(win_platform, "enable_dpi_awareness",
                        lambda: "per_monitor_v2")
    monkeypatch.setattr(win_platform, "set_app_user_model_id", lambda: True)

    assert win_platform.prepare_windows_process() == {
        "dpi_awareness": "per_monitor_v2",
        "app_user_model_id": True,
    }


def test_prepare_windows_process_never_raises(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("platform probe broke")

    monkeypatch.setattr(win_platform, "enable_dpi_awareness", explode)
    monkeypatch.setattr(win_platform, "set_app_user_model_id", explode)

    assert win_platform.prepare_windows_process() == {
        "dpi_awareness": "unavailable",
        "app_user_model_id": False,
    }


def test_win_platform_is_silent(monkeypatch, capsys):
    _install_windll(monkeypatch)  # everything unavailable
    win_platform.prepare_windows_process()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def _run_app_window_import(monkeypatch):
    """Execute app_window.py with fake platform and GUI modules.

    Returns the recorded import events and the resulting module namespace.
    The appgui finder records that the GUI module is imported after the
    platform preparation, and a fake tkinter.Tk would record any root attempt.
    """
    events = []

    fake_platform = types.ModuleType("win_platform")

    def prepare():
        events.append("prepare")
        return {"dpi_awareness": "unavailable", "app_user_model_id": False}

    fake_platform.prepare_windows_process = prepare

    class FakeAppguiLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return types.ModuleType("appgui")

        def exec_module(self, module):
            events.append("import appgui")
            module.main = lambda **_kwargs: None

    class FakeAppguiFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "appgui":
                return importlib.util.spec_from_loader(
                    "appgui", FakeAppguiLoader())
            return None

    fake_tk = types.ModuleType("tkinter")

    def forbidden_tk(*_args, **_kwargs):
        events.append("tk-root")
        raise AssertionError("importing app_window must not create a Tk root")

    fake_tk.Tk = forbidden_tk

    monkeypatch.setitem(sys.modules, "win_platform", fake_platform)
    monkeypatch.delitem(sys.modules, "appgui", raising=False)
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
    monkeypatch.setattr(sys, "meta_path",
                        [FakeAppguiFinder()] + list(sys.meta_path))

    source = (os.path.join(ROOT, "app_window.py"))
    with open(source, "r", encoding="utf-8") as handle:
        code = compile(handle.read(), source, "exec")

    namespace = {"__name__": "app_window_import_probe", "__file__": source}
    saved_path = list(sys.path)
    try:
        exec(code, namespace)
    finally:
        sys.path[:] = saved_path
    return events, namespace


def test_app_window_import_prepares_process_without_tk_root(monkeypatch):
    events, namespace = _run_app_window_import(monkeypatch)

    assert events == ["prepare", "import appgui"]
    assert callable(namespace["main"])


def test_app_window_main_forwards_only_the_first_path(monkeypatch):
    calls = []
    monkeypatch.setattr(app_window.appgui, "main",
                        lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(app_window.win_platform, "prepare_windows_process",
                        lambda: {})

    assert app_window.main([r"D:\Games\Example", "--dry-run", "--force"]) == 0
    assert calls == [{"initial_dir": r"D:\Games\Example"}]


def test_app_window_main_without_a_path_passes_none(monkeypatch):
    calls = []
    monkeypatch.setattr(app_window.appgui, "main",
                        lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(app_window.win_platform, "prepare_windows_process",
                        lambda: {})

    assert app_window.main([]) == 0
    assert calls == [{"initial_dir": None}]


def test_app_window_main_reads_sys_argv_and_ignores_extras(monkeypatch):
    calls = []
    monkeypatch.setattr(app_window.appgui, "main",
                        lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(app_window.win_platform, "prepare_windows_process",
                        lambda: {})
    monkeypatch.setattr(sys, "argv",
                        ["app_window.py", "OtherGame", "--ignored"])

    assert app_window.main() == 0
    assert calls == [{"initial_dir": "OtherGame"}]


def test_icon_has_all_thirteen_windows_frames():
    Image = pytest.importorskip("PIL.Image")

    icon_path = os.path.join(ROOT, "assets", "SLG-Renpy-Toolkit.ico")
    with Image.open(icon_path) as icon:
        sizes = set(icon.ico.sizes())

    assert sizes == REQUIRED_ICON_SIZES
    assert len(sizes) == 13


def test_icon_generator_lists_the_same_frames():
    pytest.importorskip("PIL")

    make_icon = importlib.import_module("tools.make_icon")
    assert set(make_icon.SIZES) == REQUIRED_ICON_SIZES
    assert len(make_icon.SIZES) == 13
