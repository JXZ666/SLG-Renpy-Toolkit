"""Offline checks for the SLG-Renpy-Toolkit window.

The window cannot be clicked from here, so this covers what can be asserted
without eyes: that the layout builds at all, that a theme switch repaints the
widgets sv-ttk does not own, and that every branch of the status logic lands on
a colour that exists.

Run:  python tests/test_gui.py
"""

import os
import sys
import tkinter as tk
import tempfile
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

import appgui  # noqa: E402

# The "this is already a Ren'Py game" status branch is the only one that needs a
# real game, and nobody cloning this repo has one. Point RPYKIT_TEST_GAME at any
# Ren'Py game directory to exercise it; otherwise that one case is skipped.
GAME = os.environ.get("RPYKIT_TEST_GAME") or None

failures = []


def check(name, ok, detail=""):
    print("%-52s %s%s" % (name, "ok" if ok else "FAIL",
                          "" if ok else "  <- " + str(detail)))
    if not ok:
        failures.append(name)


def is_hex(value):
    return (isinstance(value, str) and len(value) == 7 and value.startswith("#")
            and all(c in "0123456789abcdefABCDEF" for c in value[1:]))


class FakePopen:
    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode


class FakeSimulationSession:
    def __init__(self, launchers=("Game.exe",)):
        self.staged_dir = "temporary-game-copy"
        self.work_dir = "temporary-work"
        self.launchers = list(launchers)
        self.steps = [
            {"id": "compat", "status": "success", "message": "mock APIs available"},
            {"id": "copy", "status": "success", "message": "mock copy ready"},
            {"id": "install", "status": "success", "message": "mock install ready"},
            {"id": "launch", "status": "pending", "message": "awaiting user check"},
        ]
        self.log_tail = "mock simulation log"
        self.process = None
        self.launcher = None
        self.confirmed = False
        self.stopped = False
        self.cleaned = False

    def launch(self, rel_launcher):
        self.launcher = rel_launcher
        self.process = FakePopen()
        self.steps[-1].update(status="running", message="mock process started")
        return self.process

    def poll(self):
        if self.process is None:
            return None
        return self.process.poll()

    def confirm_main_menu(self):
        code = self.poll()
        if code not in (None, 0):
            raise RuntimeError("mock game crashed")
        self.confirmed = True
        self.steps[-1].update(status="success", message="main menu confirmed")
        return True

    def stop(self):
        self.stopped = True
        if self.process and self.process.poll() is None:
            self.process.returncode = -15

    def cleanup(self):
        if self.process and self.process.poll() is None:
            raise RuntimeError("mock process still running")
        self.cleaned = True


def pump_until(root, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.005)
    root.update()
    return bool(predicate())


def survey_data(supported=True):
    return {
        "verdict": "warn", "label": "Mock Game",
        "renpy": {"version": "8.0", "name": "Ren'Py"},
        "python": {"major": 3},
        "sources": {"loose_rpy": 1, "loose_rpyc": 0, "rpa": []},
        "arch": "both", "splash": {"found": False}, "reasons": [],
        "feature_support": {
            fid: {"supported": supported, "reasons": []}
            for fid in appgui.features.ids()
        },
    }


def simulation_checks(app, root, check):
    """Drive the complete simulation UI with fake sessions and processes."""
    with tempfile.TemporaryDirectory(prefix="rpykit-gui-sim-") as game_dir:
        os.makedirs(os.path.join(game_dir, "game"))
        app.game_dir = game_dir
        app.var_dir.set(game_dir)
        app._apply_feature_support(survey_data(True))
        for var in app.var_on.values():
            var.set(True)
        app._set_buttons()

        def run_session(session, chosen=None, survey=None):
            pump_until(root, lambda: app.sim_session is None and not app.busy)
            app._reset_simulation_status()
            prepare_patch = mock.patch.object(
                appgui.simulation, "prepare", return_value=session)
            survey_patch = mock.patch.object(
                appgui.compat, "survey",
                return_value=survey if survey is not None else survey_data(True))
            prepare_patch.start()
            survey_patch.start()
            chooser_patch = None
            if chosen is not None:
                chooser_patch = mock.patch.object(
                    app, "_choose_launcher", return_value=chosen)
                chooser_patch.start()
            try:
                app.simulate_run()
                completed = pump_until(
                    root, lambda: app.sim_launched
                    or (session.cleaned and app.sim_session is None and not app.busy))
                return completed
            finally:
                if chooser_patch:
                    chooser_patch.stop()
                survey_patch.stop()
                prepare_patch.stop()

        # An unsupported API must fail before the staging function is called.
        app._reset_simulation_status()
        unsupported_prepare = mock.Mock()
        with mock.patch.object(appgui.compat, "survey",
                               return_value=survey_data(False)), \
                mock.patch.object(appgui.simulation, "prepare",
                                  unsupported_prepare):
            app.simulate_run()
            pump_until(root, lambda: not app.sim_preparing)
        check("unsupported API stops before simulation prepare",
              not unsupported_prepare.called
              and app.sim_stage_state["compat"][0] == "bad",
              app.sim_result_message)

        # A valid staged install without a root-level exe is installation
        # success but cannot claim a runnable game.
        no_launcher = FakeSimulationSession(launchers=())
        with mock.patch.object(appgui.compat, "survey",
                               return_value=survey_data(True)), \
                mock.patch.object(appgui.simulation, "prepare",
                                  return_value=no_launcher):
            app.simulate_run()
            pump_until(root, lambda: no_launcher.cleaned
                       and app.sim_session is None and not app.busy)
        check("no launcher reports install success and run failure",
              app.sim_stage_state["install"][0] == "ok"
              and app.sim_stage_state["launch"][0] == "bad"
              and "exe" in app.sim_result_message.lower()
              and no_launcher.cleaned,
              app.sim_result_message)

        # A non-zero process exit is reported as a crash and its copy cleaned.
        crashed = FakeSimulationSession()
        check("mock launcher reaches running state",
              run_session(crashed), app.sim_result_message)
        crashed.process.returncode = 9
        app._poll_simulation()
        pump_until(root, lambda: crashed.cleaned
                   and app.sim_session is None and not app.busy)
        check("non-zero game exit reports startup failure",
              app.sim_stage_state["launch"][0] == "bad"
              and "\u542f\u52a8\u5931\u8d25" in app.sim_result_message
              and crashed.cleaned,
              app.sim_result_message)

        # Multiple launchers require an explicit selection. A live process is
        # still only "waiting for confirmation" until the user confirms menu.
        chosen = FakeSimulationSession(
            launchers=("Game-J-32.exe", "Game-J.exe"))
        check("multiple launcher session starts with explicit selected item",
              run_session(chosen, chosen="Game-J.exe"),
              app.sim_result_message)
        check("process start remains pending main-menu confirmation",
              "\u7b49\u5f85\u786e\u8ba4" in app.sim_result_message
              and "\u8fd0\u884c\u9a8c\u8bc1\u6210\u529f" not in app.sim_result_message
              and chosen.launcher == "Game-J.exe",
              app.sim_result_message)
        app.confirm_simulation_success()
        check("user confirmation is recorded by the simulation session",
              pump_until(root, lambda: app.sim_confirmed)
              and chosen.confirmed,
              app.sim_result_message)
        chosen.process.returncode = 0
        app._poll_simulation()
        pump_until(root, lambda: chosen.cleaned
                   and app.sim_session is None and not app.busy)
        check("confirmed main menu reports success and cleans the copy",
              app.sim_result_level == "ok" and chosen.cleaned
              and "\u4e3b\u83dc\u5355" in app.sim_result_message,
              app.sim_result_message)

        # The game may close normally before the user confirms that the menu
        # appeared. Confirmation must still finish the result and clean the copy.
        exited_early = FakeSimulationSession()
        check("early-exit session launches",
              run_session(exited_early), app.sim_result_message)
        exited_early.process.returncode = 0
        app._poll_simulation()
        check("zero exit waits for menu confirmation",
              app.sim_process_exited
              and app.sim_stage_state["launch"][1] == "pending_confirmation",
              app.sim_result_message)
        app.confirm_simulation_success()
        pump_until(root, lambda: exited_early.cleaned
                   and app.sim_session is None and not app.busy)
        check("confirmation after zero exit marks success and cleans copy",
              app.sim_result_level == "ok" and exited_early.cleaned
              and app.sim_stage_state["launch"][0] == "ok",
              app.sim_result_message)

        # Explicit user failure stops a still-running mock process first.
        rejected = FakeSimulationSession()
        check("failure-confirmation session launches",
              run_session(rejected), app.sim_result_message)
        app.confirm_simulation_failure()
        pump_until(root, lambda: rejected.cleaned
                   and app.sim_session is None and not app.busy)
        check("user-reported failure stops process and cleans copy",
              rejected.stopped and rejected.cleaned
              and app.sim_result_level == "bad",
              app.sim_result_message)

        # Closing while a staged process is active asks first, then stops and
        # cleans on a worker before the UI closes.
        closing = FakeSimulationSession()
        check("close-cleanup session launches",
              run_session(closing), app.sim_result_message)
        destroyed = []
        with mock.patch.object(appgui.messagebox, "askyesno", return_value=True), \
                mock.patch.object(app, "_destroy_root",
                                  side_effect=lambda: destroyed.append(True)):
            app.close()
            pump_until(root, lambda: closing.cleaned and app.sim_session is None
                       and bool(destroyed))
        check("close confirmation stops process and removes session",
              closing.stopped and closing.cleaned and destroyed,
              (closing.stopped, closing.cleaned, destroyed))


def main():
    check("CustomTkinter production UI is importable", appgui.ctk is not None)

    root = tk.Tk()
    root.withdraw()
    try:
        state_file = os.path.join(tempfile.gettempdir(),
                                  "rpykit-gui-test-%d.json" % os.getpid())
        with mock.patch.object(appgui.branding, "APP_VERSION", "0.9.0"):
            app = appgui.App(root, state_path=state_file)
        root.update()

        check("window builds", app.log is not None
              and set(app.pages) == {"process", "library", "toolbox", "log", "settings"})
        check("version is visible in the window",
              app.version_label.cget("text") == "v0.9.0",
              app.version_label.cget("text"))
        check("simulation action has a readable label",
              app.btn_dry.cget("text") == "\u6a21\u62df\u5b89\u88c5\u5e76\u8fd0\u884c",
              ascii(app.btn_dry.cget("text")))
        check("simulation shows the five explicit result stages",
              sorted(app.sim_stage_vars) ==
              ["compat", "confirm", "copy", "install", "launch"])
        check("process and log controls are real widgets",
              app.btn_go.cget("command") is not None and app.log.winfo_exists())

        # The skip-the-logos box. Default on, and it has to reach the Namespace
        # the worker thread reads - the GUI only ever reads the Tk variable on
        # the main thread, so this is the seam worth pinning.
        check("the skip-intro box starts ticked", app.var_skip.get() is True)
        check("it is live before a game is picked",
              app.chk_skip.cget("state") == "normal")
        check("it rides into the namespace",
              appgui._namespace("x", skip_intro=False).skip_intro is False
              and appgui._namespace("x").skip_intro is True)

        # The boxes are drawn from features.CATALOG rather than from a list in
        # the layout, which is the whole point of the catalogue: a third feature
        # must appear in the window without an edit to appgui.py.
        check("one card per catalogue entry",
              sorted(app.rows) == sorted(appgui.features.ids()), sorted(app.rows))
        check("every card is ticked the way its entry says",
              {fid: app.var_on[fid].get() for fid in app.rows}
              == {e["id"]: bool(e.get("default_on", True))
                  for e in appgui.features.CATALOG})
        # Both spellings of the selection travel together, or the runner would
        # have to guess which one the window meant.
        check("the two spellings agree",
              appgui._namespace("x", feature_ids=["intro"]).features == ["intro"]
              and appgui._namespace("x", feature_ids=["intro"]).skip_intro is True)
        check("unticking the intro wins over an explicit list",
              appgui._namespace("x", feature_ids=["fontfix", "intro"],
                                 skip_intro=False).features == ["fontfix"])

        # A theme switch updates CustomTkinter's system appearance and all paired colors.
        seen = set()
        for theme in ("dark", "light", "dark"):
            app._apply_theme(theme)
            root.update()
            p = appgui._palette(root, app._theme)
            seen.add(p["theme"])
            check("%s: palette is all hex" % theme,
                  all(is_hex(p[k]) for k in
                      ("bg", "fg", "dim", "panel", "selbg", "selfg")), p)
            check("%s: log uses the paired panel colors" % theme,
                  app.log.cget("fg_color") == appgui._PAIR["panel"])
            check("%s: main shell uses paired colors" % theme,
                  app.shell.cget("fg_color") == appgui._PAIR["bg"])
        check("toggling actually changes theme", seen == {"dark", "light"}, seen)
        check("navigation switches pages", app._show_page("toolbox") is None
              and app.active_page == "toolbox")
        app._show_page("process")

        # System mode follows Windows while keeping the saved mode as system.
        with mock.patch.object(appgui, "_system_theme", return_value="light"):
            app._apply_theme("system")
            root.update()
            check("system theme mode is retained",
                  app._theme_mode == "system" and app._theme == "light",
                  (app._theme_mode, app._theme))
            check("system mode saves a valid appearance preference",
                  app.state["appearance"] == "system")
            app._toggle_theme()
            check("theme cycle reaches light", app._theme_mode == "light")
            app._toggle_theme()
            check("theme cycle reaches dark", app._theme_mode == "dark")
            app._toggle_theme()
            check("theme cycle returns to system", app._theme_mode == "system")

        persisted_theme = appgui.app_state.load_state(state_file)["appearance"]
        check("appearance preference is saved outside the game", persisted_theme == "system")

        # Register a game through the same path used by the process-page picker.
        with tempfile.TemporaryDirectory(prefix="rpykit-gui-library-") as library_root:
            game_dir = os.path.join(library_root, "Example")
            os.makedirs(os.path.join(game_dir, "game"))
            installed = {"shim": False, "ours": False, "current": False,
                         "mode": None}
            for entry in appgui.features.CATALOG:
                installed.update({key: False for key in entry["state"].values()})
            with mock.patch.object(appgui.compat, "survey",
                                   return_value=survey_data(True)), \
                    mock.patch.object(appgui.cmd_fontfix, "installed_state",
                                      return_value=installed):
                app.set_game_dir(game_dir)
                check("game scan starts without blocking the view", app.scan_busy)
                check("background game scan completes", pump_until(
                    root, lambda: not app.scan_busy))
                saved = appgui.app_state.load_state(state_file)
                check("selected game path is saved in the library",
                      len(saved["games"]) == 1
                      and saved["games"][0]["path"] == os.path.realpath(game_dir))
                app.remove_game(game_dir)
                check("removing from the library leaves game files untouched",
                      os.path.isdir(os.path.join(game_dir, "game"))
                      and not appgui.app_state.load_state(state_file)["games"])

        # An older survey without feature_support remains permissive. The new
        # matrix disables unsupported items independently, and selections are
        # filtered before they can reach the worker Namespace.
        with tempfile.TemporaryDirectory(prefix="rpykit-gui-") as tmp:
            os.makedirs(os.path.join(tmp, "game"))
            survey = {
                "verdict": "warn", "label": "Test Game",
                "renpy": {"version": "7.5.3", "name": "Ren'Py"},
                "python": {"major": 2},
                "sources": {"loose_rpy": 1, "loose_rpyc": 0, "rpa": []},
                "arch": "both", "splash": {"found": False}, "reasons": [],
            }
            installed = {"shim": False, "ours": False, "current": False,
                         "intro": False, "intro_ours": False,
                         "intro_current": False, "mode": None}
            with mock.patch.object(appgui.compat, "survey", return_value=survey), \
                    mock.patch.object(appgui.cmd_fontfix, "installed_state",
                                      return_value=installed):
                app.game_dir = tmp
                app.var_dir.set(tmp)
                app._refresh_state()
                pump_until(root, lambda: not app.scan_busy)
                app._set_buttons()
                check("legacy survey keeps features available",
                      all(row.supported for row in app.rows.values()))

                survey["feature_support"] = {
                    "fontfix": {"supported": False,
                                "reasons": ["config.font_name_map is unavailable"]},
                    "intro": {"supported": True, "reasons": []},
                }
                app._refresh_state()
                pump_until(root, lambda: not app.scan_busy)
                app._set_buttons()
                check("unsupported feature is unchecked",
                      app.var_on["fontfix"].get() is False)
                check("unsupported feature checkbox is disabled",
                      app.rows["fontfix"].toggle.cget("state") == "disabled",
                      app.rows["fontfix"].toggle.cget("state"))
                check("unsupported feature reason is visible",
                      "config.font_name_map" in app.rows["fontfix"].reason_var.get(),
                      app.rows["fontfix"].reason_var.get())
                check("unsupported reason starts with readable Chinese status",
                      app.rows["fontfix"].reason_var.get().startswith(
                          "\u5f53\u524d\u6e38\u620f\u4e0d\u652f\u6301\u6b64\u529f\u80fd\uff1a"),
                      ascii(app.rows["fontfix"].reason_var.get()))
                check("independently supported intro stays selectable",
                      app.rows["intro"].supported
                      and app.var_on["intro"].get()
                      and app.rows["intro"].toggle.cget("state") == "normal")
                check("worker namespace only contains supported choice",
                      app._args().features == ["intro"], app._args().features)
                check("primary action remains available for intro",
                      app.btn_go.cget("state") == "normal", app.btn_go.cget("state"))

                survey["feature_support"] = {
                    fid: {"supported": False, "reasons": ["test unsupported"]}
                    for fid in app.rows
                }
                app._refresh_state()
                pump_until(root, lambda: not app.scan_busy)
                app._set_buttons()
                check("all unsupported choices are disabled",
                      all(row.toggle.cget("state") == "disabled"
                          for row in app.rows.values()))
                check("primary action is disabled when nothing is available",
                      app.btn_go.cget("state") == "disabled"
                      and app.btn_dry.cget("state") == "disabled")
                check("revert remains independently available",
                      app.btn_undo.cget("state") == "normal")

        simulation_checks(app, root, check)

        # Every branch of the status logic, through the real code path.
        cases = [
            (None, "info"),
            (os.path.join(HERE, "no-such-game"), "bad"),
        ]
        if GAME:
            cases.append((GAME, None))
        else:
            print("%-52s SKIP" % "real-game status branch",
                  "  <- set RPYKIT_TEST_GAME=<game dir> to enable")
        for game, want in cases:
            app.game_dir = game
            got = app._refresh_state()
            level = got[0] if isinstance(got, tuple) else None
            check("state %s" % (want or "real game"),
                  level in appgui._GLYPH, got)
            if want and level != want:
                check("state %s is %s" % (want, level), False, got)

        # No stale Markdown emphasis should survive into a Label.
        check("no asterisk emphasis in status text",
              "**" not in app.var_state.get(), app.var_state.get())

        app.game_dir = None
        app.var_dir.set("")
        app.close_after_cleanup = False
        app._refresh_state()
        app._set_buttons()
        check("all actions disable without a directory",
              all(button.cget("state") == "disabled"
                  for button in app.action_buttons.values()),
              {name: button.cget("state") for name, button in app.action_buttons.items()})

        with mock.patch.object(root, "destroy") as destroy_root:
            app.close()
            check("window close destroys the Tk root", destroy_root.called)
    finally:
        root.destroy()
        try:
            os.unlink(state_file)
        except (OSError, UnboundLocalError):
            pass

    fake_root = mock.Mock()
    fake_app = mock.Mock()
    dropped_dir = r"D:\Games\DroppedGame"
    with mock.patch.object(appgui.ctk, "CTk", return_value=fake_root), \
            mock.patch.object(appgui, "App", return_value=fake_app):
        result = appgui.main(initial_dir=dropped_dir)
    check("window entrypoint preselects a dropped folder",
          result == 0
          and fake_app.set_game_dir.call_args.args == (dropped_dir,)
          and fake_root.mainloop.called,
          fake_app.set_game_dir.call_args)

    print()
    if failures:
        print("%d FAILED: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
