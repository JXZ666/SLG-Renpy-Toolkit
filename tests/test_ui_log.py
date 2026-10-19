"""运行日志页与“查看运行日志”入口的行为测试。

所有日志文本都由测试注入，不启动真实模拟，也不读取或写入任何游戏文件。
窗口来自 ``conftest.py`` 的 ``ui_app`` fixture，并已重置到处理页。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")


def _pump(root, rounds=6):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def _log_action_buttons(instance):
    return (instance.btn_copy_log, instance.btn_export_log,
            instance.btn_clear_log)


def test_sim_log_is_written_without_switching_pages(ui_app):
    """收到 __sim_log__ 只追加日志，不应替用户切换页面。"""
    app, root, _game = ui_app
    app._show_page("process")
    _pump(root)

    app._handle_event(("__sim_log__", "simulation line\n"))
    _pump(root)

    text = app._log_text()
    assert "simulation line" in text
    assert text.count("simulation line") == 1
    assert app.active_page == "process", "写入日志不应自动切到运行日志页"


def test_view_log_button_navigates_to_log_and_keeps_text(ui_app):
    """app.btn_view_log 必须存在，并把用户带到保留原有文本的日志页。"""
    app, root, _game = ui_app
    app._show_page("process")
    _pump(root)

    assert hasattr(app, "btn_view_log"), "缺少 app.btn_view_log（查看运行日志）"
    button = app.btn_view_log
    assert button.winfo_exists()

    # 日志为空时，禁用或可用都合理；写入后 test_view_log_button_is_invokable
    # 会进一步要求按钮可用。
    assert str(button.cget("state")) in ("normal", "disabled")

    app._handle_event(("__sim_log__", "view button line\n"))
    _pump(root)

    command = button.cget("command")
    assert callable(command), "app.btn_view_log 必须绑定“查看运行日志”命令"
    command()
    _pump(root)

    assert app.active_page == "log"
    assert "view button line" in app._log_text()


def test_simulation_failure_switches_to_log(ui_app):
    """模拟失败路径应自动把用户带到运行日志页。"""
    app, _root, _game = ui_app
    app._show_page("process")

    app._simulation_failed(
        "synthetic failure",
        [{"id": "compat", "status": "failed",
          "message": "synthetic failure"}],
    )

    assert app.active_page == "log"


def test_log_text_is_not_duplicated(ui_app):
    """一条 __sim_log__ 只落一行，_log 的文本计数与写入次数一致。"""
    app, _root, _game = ui_app

    app._handle_event(("__sim_log__", "unique simulation line\n"))
    assert app._log_text().count("unique simulation line") == 1

    app._log("second unique line\n")
    text = app._log_text()
    assert text.count("unique simulation line") == 1
    assert text.count("second unique line") == 1


def test_log_action_buttons_follow_empty_state(ui_app):
    """复制/导出/清空按钮的启用状态由 _update_log_actions 统一决定。"""
    app, _root, _game = ui_app
    assert app._log_text().strip() == ""

    for button in _log_action_buttons(app):
        assert str(button.cget("state")) == "disabled"

    app._log("action line\n")
    for button in _log_action_buttons(app):
        assert str(button.cget("state")) == "normal"

    # 再次清空文本后调用统一刷新函数，三个按钮应一起回到禁用。
    app.log.configure(state="normal")
    app.log.delete("1.0", "end")
    app.log.configure(state="disabled")
    app._update_log_actions()
    expected = "normal" if app._log_text().strip() else "disabled"
    assert expected == "disabled"
    for button in _log_action_buttons(app):
        assert str(button.cget("state")) == expected


def test_view_log_button_is_invokable(ui_app):
    """日志有内容时，用户应能通过 invoke() 真正点击“查看运行日志”。"""
    app, root, _game = ui_app
    app._show_page("process")
    app._handle_event(("__sim_log__", "invoke view log line\n"))
    _pump(root)

    assert hasattr(app, "btn_view_log"), "缺少 app.btn_view_log（查看运行日志）"
    button = app.btn_view_log
    state = str(button.cget("state"))
    assert state != "disabled", (
        "日志已有内容时 app.btn_view_log 仍为 disabled，用户无法点击查看日志")

    button.invoke()
    _pump(root)

    assert app.active_page == "log"
    assert "invoke view log line" in app._log_text()
