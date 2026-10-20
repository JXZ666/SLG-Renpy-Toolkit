"""Offline real-engine probes using copied runtimes and synthetic scripts only.

No original game script, asset or save is launched. Optional --cli verifies the
source/frozen install and revert paths on the disposable synthetic game.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import renpy_translation
import simulation

SCREENS = '''screen say(who, what):
    window:
        text what id "what"

screen choice(items):
    style_prefix "choice"

    vbox:
        for i in items:
            textbutton i.caption action i.action
'''

PROBE = r'''
init -10 python:
    config.name = "Translation connector synthetic probe"
    config.version = "0"
    config.save_directory = "rpykit-synthetic-translation"
    config.developer = True
    config.log = "translation-probe.txt"
    config.screen_width = 640
    config.screen_height = 480
    config.window = "hide"
    config.autosave_on_choice = False
    config.autosave_on_quit = False
    config.autosave_frequency = 0
    config.say_menu_text_filter = lambda text: text.replace("GreetingsToken", "HelloToken")

init 1000 python hide:
    import renpy as engine
    import sys
    probe = sys.modules["_rpykit_translation_runtime_v1"]
    probe._probe_seen = []
    probe._probe_loaded = False
    probe._probe_rolled_back = False
    original_update = engine.text.text.Text.update
    def capture(self, *args, **kwargs):
        if self.text and isinstance(self.text[0], str) and "TranslatedHelloToken" in self.text[0]:
            probe._probe_seen.append((self.text[0], self.start, self.end, self.slow))
        return original_update(self, *args, **kwargs)
    engine.text.text.Text.update = capture
    class AdvanceAction(engine.ui.Action):
        def __call__(self):
            screen = engine.exports.get_screen("choice")
            if screen is not None:
                items = screen.scope.get("items", [])
                action = next((i.action for i in items if i.action is not None), None)
                if action is not None:
                    return action()
            return engine.store.Return()()
    def advance():
        engine.ui.timer(0.12, action=AdvanceAction())
    engine.config.overlay_functions.append(advance)
    engine.game.preferences.text_cps = 60

default probe_name = "SyntheticName"
default probe_set = ["AlreadyToken"]
default probe_selected = ""

label probe_prediction:
    "PredictOnlyToken"
    return

label start:
    python:
        import sys
        prediction_label = renpy.game.script.lookup("probe_prediction")
        prediction_label.block[0].predict()
    "GreetingsToken {b}[probe_name]{/b}{w=0.05} end"
    python:
        assert "TranslatedHelloToken" in _last_say_what, _last_say_what
        assert sys.modules["_rpykit_translation_runtime_v1"]._probe_seen, "translated Text not observed"
        assert any(row[3] for row in sys.modules["_rpykit_translation_runtime_v1"]._probe_seen), "slow dialogue was disabled"
        assert config.developer is True
    menu:
        set probe_set
        "AlreadyToken":
            $ probe_selected = "already"
        "FirstToken [probe_name]" if True:
            $ probe_selected = "first"
        "HiddenToken" if False:
            $ probe_selected = "hidden"
        "SecondToken" if True:
            $ probe_selected = "second"
    python:
        assert probe_selected == "first", probe_selected
        assert "FirstToken [probe_name]" in probe_set, probe_set
        assert "TranslatedFirstToken [probe_name]" not in probe_set
        chosen_keys = list(persistent._chosen.keys())
        assert any(key[1] == "FirstToken [probe_name]" for key in chosen_keys), chosen_keys
        assert not any("Translated" in key[1] for key in chosen_keys), chosen_keys
    if not sys.modules["_rpykit_translation_runtime_v1"]._probe_loaded:
        $ renpy.save("connector-probe")
        $ sys.modules["_rpykit_translation_runtime_v1"]._probe_loaded = True
        $ renpy.load("connector-probe")
    python:
        assert sys.modules["_rpykit_translation_runtime_v1"]._probe_loaded
        assert menu is sys.modules["_rpykit_translation_runtime_v1"]._menu
    "HelloToken after load"
    $ assert "TranslatedHelloToken" in _last_say_what
    "HelloToken rollback checkpoint"
    if not sys.modules["_rpykit_translation_runtime_v1"]._probe_rolled_back:
        $ sys.modules["_rpykit_translation_runtime_v1"]._probe_rolled_back = True
        $ renpy.rollback(force=True, checkpoints=1, greedy=False)
    $ assert "TranslatedHelloToken" in _last_say_what
    "StopToken"
    $ assert _last_say_what == "StopToken"
    "HelloToken after stop"
    python:
        assert _last_say_what == "HelloToken after stop", _last_say_what
        renpy.log("RPYKIT_TRANSLATION_PROBE: dialogue/tag/interpolation/slow/menu/set/chosen/save/load/rollback/stop PASS")
        renpy.quit()
'''

NOHOST = PROBE.split("label probe_prediction:", 1)[0] + r'''
label start:
    "GreetingsToken {b}[probe_name]{/b}{w=0.05} end"
    $ assert _last_say_what == "HelloToken {b}[probe_name]{/b}{w=0.05} end", _last_say_what
    menu:
        "FirstToken":
            $ probe_selected = "first"
        "SecondToken":
            $ probe_selected = "second"
    $ assert probe_selected == "first"
    $ renpy.log("RPYKIT_TRANSLATION_PROBE: ordinary launch original text PASS")
    $ renpy.quit()
'''


def _run_probe(launcher, stage, env):
    for name in ("traceback.txt", "translation-probe.txt"):
        path = stage / name
        if path.exists():
            path.unlink()
    process = subprocess.Popen([str(launcher)], cwd=stage, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if (stage / "traceback.txt").exists() or time.monotonic() >= deadline:
                    raise
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            process.kill()
        process.communicate(timeout=10)
        error_path = stage / "traceback.txt"
        error = error_path.read_text(encoding="utf-8", errors="replace")[-7000:] if error_path.exists() else ""
        raise RuntimeError("Synthetic game failed or timed out. " + error)
    traceback = stage / "traceback.txt"
    if traceback.exists():
        raise RuntimeError(traceback.read_text(encoding="utf-8", errors="replace")[-7000:])
    assert process.returncode == 0, "Synthetic game exit " + str(process.returncode)
    return " ".join((stage / "translation-probe.txt").read_text(encoding="utf-8", errors="replace").split())


def _copy_runtime(source, destination):
    simulation._scan_tree(str(source / "renpy"))
    simulation._scan_tree(str(source / "lib"))
    shutil.copytree(source / "renpy", destination / "renpy", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(source / "lib", destination / "lib")
    launchers = list(source.glob("*.exe"))
    if len(launchers) != 1:
        raise ValueError("Synthetic probe requires one unambiguous root launcher")
    launcher = launchers[0]
    script = launcher.with_suffix(".py")
    if not script.is_file():
        raise ValueError("Launcher Python bootstrap not found")
    shutil.copy2(launcher, destination / launcher.name)
    shutil.copy2(script, destination / script.name)
    return destination / launcher.name


def verify(game, cli=None):
    source = Path(game).resolve()
    survey = renpy_translation.survey(source)
    if not survey["supported"]:
        raise ValueError("Engine not reviewed: " + "; ".join(survey["reasons"]))
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            assert self.headers.get("Authorization") == "Bearer synthetic-probe-token"
            stop = any("StopToken" in t for t in body["texts"])
            self.send_response(410 if stop else 200)
            self.end_headers()
            values = [t.replace("HelloToken", "TranslatedHelloToken").replace("FirstToken", "TranslatedFirstToken").replace("SecondToken", "TranslatedSecondToken") for t in body["texts"]]
            self.wfile.write(json.dumps({"results": values, "statuses": ["success"] * len(values)}).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="rpykit-translation-engine-") as temporary:
            stage = Path(temporary)
            launcher = _copy_runtime(source, stage)
            game_dir = stage / "game"
            game_dir.mkdir()
            (game_dir / "screens.rpy").write_text(SCREENS, encoding="utf-8")
            (game_dir / "script.rpy").write_text(NOHOST, encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("RENPY_", "RPYKIT_TRANSLATION_"))}
            env.update(RENPY_PATH_TO_SAVES=str(stage / "isolated-saves"),
                       RENPY_MULTIPERSISTENT=str(stage / "isolated-multipersistent"),
                       RENPY_SKIP_MAIN_MENU="1", RPYKIT_WORK=str(stage / "isolated-tool-state"))
            if cli:
                cli_path = Path(cli).resolve()
                command = [sys.executable, str(cli_path)] if cli_path.suffix.lower() == ".py" else [str(cli_path)]
                installed = subprocess.run(command + [str(stage), "--features", "translation", "--force"],
                                           cwd=ROOT, env=env, capture_output=True, timeout=90)
                if installed.returncode:
                    raise RuntimeError("CLI connector install failed: " + installed.stdout.decode("utf-8", "replace")[-1500:])
            else:
                (game_dir / renpy_translation.REL).write_text(renpy_translation.render(stage), encoding="utf-8")
            nohost_log = _run_probe(launcher, stage, env)
            assert "RPYKIT_TRANSLATION_PROBE: ordinary launch original text PASS" in nohost_log, nohost_log[-2000:]
            assert not requests, "Ordinary launcher contacted translation host"
            (game_dir / "script.rpy").write_text(PROBE, encoding="utf-8")
            compiled = game_dir / "script.rpyc"
            if compiled.exists():
                compiled.unlink()
            env.update(RPYKIT_TRANSLATION_URL="http://127.0.0.1:%s/translate" % server.server_port,
                       RPYKIT_TRANSLATION_TOKEN="synthetic-probe-token", RPYKIT_TRANSLATION_SESSION="synthetic-session",
                       RPYKIT_TRANSLATION_GAME="synthetic-game", RPYKIT_TRANSLATION_WAIT_MS="2000")
            log = _run_probe(launcher, stage, env)
            marker = "RPYKIT_TRANSLATION_PROBE: dialogue/tag/interpolation/slow/menu/set/chosen/save/load/rollback/stop PASS"
            assert marker in log, log[-2000:]
            assert not any("PredictOnlyToken" in text or "HiddenToken" in text or "AlreadyToken" in text
                           for request in requests for text in request["texts"]), requests
            menus = [request for request in requests if request["kind"] == "menu"]
            assert len(menus) == 1 and len(menus[0]["texts"]) == 2, menus
            assert not any("after stop" in text for request in requests for text in request["texts"]), requests
            reverted = False
            if cli:
                result = subprocess.run(command + [str(stage), "--features", "translation", "--revert", "--force"],
                                        cwd=ROOT, env=env, capture_output=True, timeout=60)
                reverted = result.returncode == 0 and not (game_dir / renpy_translation.REL).exists()
                assert reverted, "CLI connector revert failed"
            return {"engine": survey["engine_version"], "passed": True, "synthetic_only": True,
                    "requests": len(requests), "menu_batch": True, "prediction_requests": 0,
                    "save_load": True, "rollback": True, "ordinary_launch": True,
                    "stop_fallback": True, "reverted": reverted,
                    "packaged_cli_verified": bool(cli and Path(cli).suffix.lower() == ".exe"),
                    "source_cli_verified": bool(cli and Path(cli).suffix.lower() == ".py")}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, help="Read-only original engine source")
    parser.add_argument("--cli", help="Source app_main.py or built CLI exe to install/revert in the synthetic game")
    args = parser.parse_args()
    print(json.dumps(verify(args.game, args.cli), ensure_ascii=False))
