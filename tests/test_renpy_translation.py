import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import types

import pytest

import renpy_translation as connector
from translation_text import RUNTIME_SOURCE


def engine_files(tmp_path, monkeypatch):
    hashes = []
    for rel in connector.ENGINE_FILES:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture:" + rel, encoding="utf-8")
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(connector, "REVIEWED_ENGINES", {tuple(hashes): "8.3.0"})
    (tmp_path / "game").mkdir()
    return hashes


def standard_screen(tmp_path):
    path = tmp_path / "game/screens.rpy"
    path.write_text('screen choice(items):\n    style_prefix "choice"\n\n    vbox:\n        for i in items:\n            textbutton i.caption action i.action\n', encoding="utf-8")


def test_survey_fails_closed_and_render_deterministic(tmp_path, monkeypatch):
    assert not connector.survey(tmp_path)["supported"]
    engine_files(tmp_path, monkeypatch)
    assert connector.survey(tmp_path)["supported"]
    assert not connector.survey(tmp_path)["coverage"]["standard_adv_menu"]
    standard_screen(tmp_path)
    assert connector.survey(tmp_path)["coverage"]["standard_adv_menu"]
    text = connector.render(tmp_path)
    assert text == connector.render(tmp_path)
    assert connector.MARKER in text
    assert str(tmp_path) not in text
    (tmp_path / "renpy/ast.py").write_text("modified", encoding="utf-8")
    assert not connector.survey(tmp_path)["supported"]
    with pytest.raises(ValueError):
        connector.render(tmp_path)


def test_custom_choice_screen_excluded(tmp_path, monkeypatch):
    engine_files(tmp_path, monkeypatch)
    standard_screen(tmp_path)
    path = tmp_path / "game/screens.rpy"
    path.write_text(path.read_text().replace('textbutton i.caption action i.action', 'textbutton i.caption action [SetVariable("x", 1), i.action]'))
    assert not connector.survey(tmp_path)["coverage"]["standard_adv_menu"]


STYLED_SCREEN = '''screen choice(items):
    style_prefix "choice"  # The existing style family.
    frame xalign 0.5:
        yalign 0.5
        padding (10, 6)
        hbox:
            spacing 10
            for i in items:
                textbutton i.caption action i.action text_size 24:
                    text_font "fonts/a#b.ttf"
                    xsize 240
'''


def test_source_visible_static_appearance_qualifies(tmp_path, monkeypatch):
    engine_files(tmp_path, monkeypatch)
    (tmp_path / "game/screens.rpy").write_text(STYLED_SCREEN, encoding="utf-8")
    assert connector.survey(tmp_path)["coverage"]["standard_adv_menu"]


@pytest.mark.parametrize(("before", "after"), [
    ("for i in items:", "for i in sorted(items):"),
    ("for i in items:", "for i index i.caption in items:"),
    ("spacing 10", "spacing gui.choice_spacing"),
    ("spacing 10", "use another_screen"),
    ("spacing 10", "$ items.reverse()"),
    ("        hbox:", "          hbox:"),
    ("choice(items)", "choice(items, extra=None)"),
    ("action i.action", "action [i.action]"),
    ("action i.action", "action i.action alternate Return()"),
])
def test_styled_menu_with_nonappearance_changes_does_not_qualify(tmp_path, monkeypatch, before, after):
    engine_files(tmp_path, monkeypatch)
    (tmp_path / "game/screens.rpy").write_text(STYLED_SCREEN.replace(before, after), encoding="utf-8")
    coverage = connector.survey(tmp_path)["coverage"]
    assert coverage["dialogue"]
    assert not coverage["standard_adv_menu"]


@pytest.fixture
def host():
    state = {"calls": [], "statuses": [], "mode": "good"}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/status":
                state["statuses"].append((body, self.headers.get("Authorization")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                return
            assert self.path == "/translate"
            state["calls"].append((body, self.headers.get("Authorization")))
            if state["mode"] == "slow":
                time.sleep(0.15)
            values = [text.replace("Hello", "你好").replace("First", "第一").replace("Second", "第二") for text in body["texts"]]
            if state["mode"] == "unsafe":
                values = [text + "{nw}" for text in values]
            if state["mode"] == "stop":
                self.send_response(410)
            else:
                self.send_response(200)
            self.end_headers()
            try:
                raw = json.dumps({"results": values, "statuses": ["ok"] * len(values)}).encode()
                if state["mode"] == "drip":
                    for index in range(0, len(raw), 6):
                        self.wfile.write(raw[index:index + 6])
                        self.wfile.flush()
                        time.sleep(0.025)
                else:
                    self.wfile.write(raw)
            except OSError:
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, state
    server.shutdown()
    server.server_close()
    thread.join()


def runtime(tmp_path, monkeypatch, host=None, install_env=True):
    hashes = engine_files(tmp_path, monkeypatch)
    standard_screen(tmp_path)
    state = {"predicting": False, "menu_items": None}
    module = types.ModuleType("_connector_test_runtime")
    class ADV:
        screen = "say"
    class NVL(ADV):
        pass
    class ChoiceReturn:
        def __init__(self, label, value):
            self.label, self.value = label, value
    class Say:
        def execute(self, text, speaker=None):
            who = speaker
            return engine.config.say_menu_text_filter(text)
        def predict(self, text):
            return engine.config.say_menu_text_filter(text)
    def display_menu(items, *args, **kwargs):
        state["menu_items"] = items
        return items[0][1].value
    def menu(items):
        return engine.store.menu(items)

    class SLScreen(types.SimpleNamespace):
        pass

    class SLFor(types.SimpleNamespace):
        pass

    class SLDisplayable(types.SimpleNamespace):
        pass

    textbutton = object()
    multi_box = object()
    button = SLDisplayable(name="textbutton", displayable=textbutton, variable=None,
                           positional=["i.caption"], keyword=[("action", "i.action")],
                           default_keywords={}, atl_transform=None, children=[])
    loop = SLFor(variable="i", expression="items", index_expression=None,
                 keyword=[], atl_transform=None, children=[button])
    layout = SLDisplayable(name="vbox", displayable=multi_box, variable=None,
                           positional=[], keyword=[], default_keywords={"layout": "vertical"},
                           atl_transform=None, children=[loop])
    empty = object()
    parameter = types.SimpleNamespace(kind=1, POSITIONAL_OR_KEYWORD=1, default=empty, empty=empty)
    screen_ast = SLScreen(name="choice", parameters=types.SimpleNamespace(parameters={"items": parameter}),
                          keyword=[("style_prefix", '"choice"')], atl_transform=None, children=[layout])
    choice_screen = types.SimpleNamespace(ast=screen_ast, function=screen_ast, location=("game/screens.rpy", 1))
    engine = types.SimpleNamespace(
        config=types.SimpleNamespace(basedir=str(tmp_path), gamedir=str(tmp_path / "game"),
                                    say_menu_text_filter=lambda s: s.replace("Greetings", "Hello"),
                                    menu_actions=True, after_load_callbacks=[]),
        store=types.SimpleNamespace(narrator=ADV(), NVLCharacter=NVL, menu=display_menu),
        exports=types.SimpleNamespace(display_menu=display_menu, menu=menu, predicting=lambda: state["predicting"],
                                      get_menu_args=lambda: ((), {}), log=lambda message: None),
        character=types.SimpleNamespace(ADVCharacter=ADV, display_say=lambda: None),
        ast=types.SimpleNamespace(Say=Say),
        ui=types.SimpleNamespace(ChoiceReturn=ChoiceReturn, _textbutton=textbutton),
        game=types.SimpleNamespace(context=lambda: types.SimpleNamespace(init_phase=False)),
        sl2=types.SimpleNamespace(slast=types.SimpleNamespace(SLScreen=SLScreen, SLFor=SLFor,
                                                             SLDisplayable=SLDisplayable)),
        display=types.SimpleNamespace(screen=types.SimpleNamespace(get_screen_variant=lambda name: choice_screen),
                                      layout=types.SimpleNamespace(MultiBox=multi_box)),
        text=types.SimpleNamespace(text=types.SimpleNamespace(Text=type("Text", (), {"render": lambda self: None}))),
    )
    for key in ("URL", "TOKEN", "SESSION", "GAME", "WAIT_MS"):
        monkeypatch.delenv("RPYKIT_TRANSLATION_" + key, raising=False)
    if host and install_env:
        monkeypatch.setenv("RPYKIT_TRANSLATION_URL", "http://127.0.0.1:%s/translate" % host[0])
        monkeypatch.setenv("RPYKIT_TRANSLATION_TOKEN", "test-secret")
        monkeypatch.setenv("RPYKIT_TRANSLATION_SESSION", "session-1")
        monkeypatch.setenv("RPYKIT_TRANSLATION_GAME", "game-1")
    source = (RUNTIME_SOURCE + "\n_engine_hashes=" + repr(list(zip(connector.ENGINE_FILES, hashes))) +
              "\n_choices=" + repr(connector._standard_choice_sources(tmp_path / "game")) + "\n" + connector._CONNECTOR)
    exec(compile(source, "<test-connector>", "exec"), module.__dict__)
    module.install(engine)
    return module, engine, state, Say, ADV, NVL, ChoiceReturn


def test_no_environment_normal_game_zero_network(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host, install_env=False)
    assert Say().execute("Greetings") == "Hello"
    assert not host[1]["calls"]
    assert engine.store.menu is engine.exports.display_menu


def test_actual_say_only_preserves_filter_and_nvl_original(tmp_path, monkeypatch, host):
    module, engine, state, Say, ADV, NVL, _ = runtime(tmp_path, monkeypatch, host)
    assert Say().execute("Greetings {b}[name]{/b}{w=1}") == "你好 {b}[name]{/b}{w=1}"
    assert Say().predict("Greetings") == "Hello"
    state["predicting"] = True
    assert Say().execute("Greetings") == "Hello"
    state["predicting"] = False
    assert Say().execute("Greetings", NVL()) == "Hello"
    assert Say().execute("Greetings", "Literal speaker") == "Hello"
    assert len(host[1]["calls"]) == 1
    body, auth = host[1]["calls"][0]
    assert body["kind"] == "say" and body["session_id"] == "session-1" and body["game_id"] == "game-1"
    assert auth == "Bearer test-secret"


def test_menu_batch_keeps_original_action_labels_values_and_identity(tmp_path, monkeypatch, host):
    module, engine, state, Say, ADV, NVL, Action = runtime(tmp_path, monkeypatch, host)
    a, b = Action("First", 42), Action("Second", 99)
    items = [("First", a), ("Second [name]", b)]
    assert engine.exports.menu(items) == 42
    translated = state["menu_items"]
    assert translated == [("第一", a), ("第二 [name]", b)]
    assert a.label == "First" and b.label == "Second"
    assert len(host[1]["calls"]) == 1
    assert host[1]["calls"][0][0]["kind"] == "menu"
    assert host[1]["calls"][0][0]["texts"] == ["First", "Second [name]"]
    engine.store.menu(items, predict_only=True)
    assert len(host[1]["calls"]) == 1
    engine.config.menu_actions = False
    engine.exports.menu(items)
    assert len(host[1]["calls"]) == 1


def test_custom_menu_arguments_and_screen_remain_original(tmp_path, monkeypatch, host):
    module, engine, state, Say, ADV, NVL, Action = runtime(tmp_path, monkeypatch, host)
    items = [("First", Action("First", 42))]
    engine.exports.get_menu_args = lambda: ((), {"screen": "custom_choice"})
    engine.exports.menu(items)
    assert state["menu_items"] == items
    assert not host[1]["calls"]


@pytest.mark.parametrize("change", ["source", "site", "cached_action", "compiled_only"])
def test_menu_requires_visible_source_and_matching_loaded_shape(tmp_path, monkeypatch, host, change):
    module, engine, state, Say, ADV, NVL, Action = runtime(tmp_path, monkeypatch, host)
    screen = engine.display.screen.get_screen_variant("choice")
    source = tmp_path / "game/screens.rpy"
    if change == "source":
        source.write_bytes(source.read_bytes() + b"\n# Edited after inspection.")
    elif change == "site":
        screen.location = ("game/screens.rpy", 2)
    elif change == "cached_action":
        button = screen.ast.children[0].children[0].children[0]
        button.keyword = [("action", "[i.action]")]
    else:
        source.unlink()
    items = [("First", Action("First", 42))]
    assert engine.exports.menu(items) == 42
    assert state["menu_items"] == items
    assert not host[1]["calls"]


def test_unsafe_response_original_and_timeout_does_not_update_current_line(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host)
    host[1]["mode"] = "unsafe"
    assert Say().execute("Hello {w}") == "Hello {w}"
    host[1]["mode"] = "slow"
    module._wait = 30
    started = time.monotonic()
    result = Say().execute("Hello")
    assert result == "Hello" and time.monotonic() - started < 0.12
    time.sleep(0.17)
    assert result == "Hello"
    assert Say().execute("Hello again") == "Hello again"
    assert len(host[1]["calls"]) == 2  # cooldown avoids per-line timeout


def test_stop_disables_session_and_load_reinstates_only_default_menu(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host)
    host[1]["mode"] = "stop"
    assert Say().execute("Hello") == "Hello"
    host[1]["mode"] = "good"
    assert Say().execute("Hello") == "Hello"
    assert len(host[1]["calls"]) == 1
    engine.store.menu = engine.exports.display_menu
    engine.config.after_load_callbacks[0]()
    assert engine.store.menu is module._menu
    custom = lambda items: None
    engine.store.menu = custom
    engine.config.after_load_callbacks[0]()
    assert engine.store.menu is custom


def test_external_luna_embedding_stops_before_double_translation(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host)
    namespace = {"callLunaHost": lambda *a: None, "callLunaIsUsingEmbed": lambda *a: True}
    exec("def new_init(self, text):\n    return None\n", namespace)
    engine.text.text.Text.__init__ = namespace["new_init"]
    assert Say().execute("Hello") == "Hello"
    assert module._disabled
    assert not host[1]["calls"]
    assert host[1]["statuses"] == [({"session_id": "session-1", "game_id": "game-1", "status": "luna_conflict"}, "Bearer test-secret")]
    assert Say().execute("Hello again") == "Hello again"
    assert len(host[1]["statuses"]) == 1


def test_status_report_has_no_environment_or_prediction_traffic(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host, install_env=False)
    module._report_luna_conflict()
    assert not host[1]["statuses"]
    module._endpoint = host[0]
    state["predicting"] = True
    module._report_luna_conflict()
    assert not host[1]["statuses"]
    assert not module._conflict_reported


def test_zero_wait_never_waits_for_or_requests_speculative_translation(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host)
    module._wait = 0
    assert Say().execute("Hello") == "Hello"
    assert not host[1]["calls"]


def test_engine_changed_after_inspection_fails_closed(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host, install_env=False)
    monkeypatch.setenv("RPYKIT_TRANSLATION_URL", "http://127.0.0.1:%s/translate" % host[0])
    monkeypatch.setenv("RPYKIT_TRANSLATION_TOKEN", "test-secret")
    monkeypatch.setenv("RPYKIT_TRANSLATION_SESSION", "session-1")
    monkeypatch.setenv("RPYKIT_TRANSLATION_GAME", "game-1")
    (tmp_path / "renpy/ast.py").write_text("unreviewed runtime", encoding="utf-8")
    module.install(engine)
    assert Say().execute("Hello") == "Hello"
    assert not host[1]["calls"]


def test_non_loopback_endpoint_is_not_installed(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host, install_env=False)
    monkeypatch.setenv("RPYKIT_TRANSLATION_URL", "http://example.invalid/translate")
    monkeypatch.setenv("RPYKIT_TRANSLATION_TOKEN", "test-secret")
    monkeypatch.setenv("RPYKIT_TRANSLATION_SESSION", "session-1")
    monkeypatch.setenv("RPYKIT_TRANSLATION_GAME", "game-1")
    module.install(engine)
    assert Say().execute("Hello") == "Hello"
    assert not host[1]["calls"]


def test_shared_deadline_includes_a_partial_response_body(tmp_path, monkeypatch, host):
    module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, host)
    host[1]["mode"] = "drip"
    module._wait = 50
    started = time.monotonic()
    assert Say().execute("Hello") == "Hello"
    assert time.monotonic() - started < 0.2


def test_real_host_and_connector_share_auth_tags_cache_and_stop_protocol(tmp_path, monkeypatch):
    from translation_service import TranslationHost
    calls = []
    class Provider:
        def translate(self, text, timeout=10):
            calls.append(text)
            return text.replace("Hello", "你好")
    host = TranslationHost({}, "synthetic-game", tmp_path / "cache.sqlite")
    host._provider = Provider()
    host.start()
    try:
        module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, install_env=False)
        for key, value in host.environment().items():
            monkeypatch.setenv(key, value)
        module.install(engine)
        assert Say().execute("Hello {b}[name]{/b}{w=1}") == "你好 {b}[name]{/b}{w=1}"
        assert Say().execute("Hello {b}[name]{/b}{w=1}") == "你好 {b}[name]{/b}{w=1}"
        assert len(calls) == 1
        assert "[name]" not in calls[0] and "{w=1}" not in calls[0]
        host.stop()
        assert Say().execute("Hello after stop") == "Hello after stop"
    finally:
        host.stop()


def test_real_host_receives_one_text_free_luna_status_without_provider(tmp_path, monkeypatch):
    from translation_service import TranslationHost
    events, calls = [], []
    class Provider:
        def translate(self, text, timeout=10):
            calls.append(text)
            return text
    host = TranslationHost({}, "synthetic-game", tmp_path / "cache.sqlite", events.append)
    host._provider = Provider()
    host.start()
    try:
        module, engine, state, Say, *_ = runtime(tmp_path, monkeypatch, install_env=False)
        for key, value in host.environment().items():
            monkeypatch.setenv(key, value)
        namespace = {"callLunaHost": lambda *a: None, "callLunaIsUsingEmbed": lambda *a: True}
        exec("def new_init(self, text):\n    return None\n", namespace)
        engine.text.text.Text.__init__ = namespace["new_init"]
        module.install(engine)
        module._report_luna_conflict()
        assert Say().execute("Hello") == "Hello"
        assert not calls
        conflicts = [event for event in events if event["status"] == "luna_conflict"]
        assert len(conflicts) == 1
        assert set(conflicts[0]) == {"game_id", "session_id", "status", "count"}
    finally:
        host.stop()
