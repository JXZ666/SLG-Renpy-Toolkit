from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import threading
import time
from urllib import error, parse, request

import pytest

import translation_config
import translation_service as service


class FakeProvider:
    def __init__(self, delay=0.0, value=None, failure=None):
        self.calls = []
        self.delay = delay
        self.value = value
        self.failure = failure

    def translate(self, text, timeout=10):
        self.calls.append(text)
        time.sleep(self.delay)
        if self.failure:
            raise self.failure
        return self.value if self.value is not None else "译文 " + text


@pytest.fixture
def host_factory(tmp_path):
    hosts = []

    def make(provider=None, settings=None, game="fixture-game", cache=None, callback=None):
        host = service.TranslationHost(settings or {}, game, cache or tmp_path / "cache.db", callback)
        if provider is not None:
            host._provider = provider
        host.start()
        hosts.append(host)
        return host

    yield make
    for host in hosts:
        host.stop()


def send(host, data=None, *, auth=True, raw=None, path=None):
    env = host.environment()
    body = {"session_id": host.session_id, "game_id": host.game_id,
            "texts": ["Hello"], "kind": "say", "budget_ms": 2000}
    if data:
        body.update(data)
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + env["RPYKIT_TRANSLATION_TOKEN"]
    req = request.Request(path or env["RPYKIT_TRANSLATION_URL"],
                          data=raw if raw is not None else json.dumps(body).encode("utf-8"),
                          headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=4) as response:
            return response.status, json.load(response)
    except error.HTTPError as exc:
        return exc.code, json.load(exc)


@contextmanager
def upstream(response=None, status=200, delay=0.0, raw=None, redirect=None):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            calls.append((self.path, dict(self.headers), body))
            time.sleep(delay)
            self.send_response(status)
            if redirect:
                self.send_header("Location", redirect)
            self.end_headers()
            try:
                self.wfile.write(raw if raw is not None else json.dumps(response).encode("utf-8"))
            except OSError:
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_port, calls
    finally:
        server.shutdown()
        server.server_close()


def test_ipc_success_and_environment_only_contains_session_credentials(host_factory):
    provider = FakeProvider()
    host = host_factory(provider)
    env = host.environment()
    assert env["RPYKIT_TRANSLATION_URL"].startswith("http://127.0.0.1:")
    assert env["RPYKIT_TRANSLATION_WAIT_MS"] == "2000"
    assert "api_key" not in str(env)
    status, data = send(host, {"texts": ["Hello", "Hello"], "kind": "menu"})
    assert status == 200
    assert data["results"] == ["译文 Hello", "译文 Hello"]
    assert provider.calls == ["Hello"]
    assert send(host)[1]["statuses"] == ["cached"]


def test_first_authenticated_game_request_reports_text_once(host_factory):
    events = []
    host = host_factory(FakeProvider(), callback=events.append)
    assert send(host, auth=False)[0] == 403
    assert send(host, {"game_id": "another-game"})[0] == 403
    assert status_request(host) == (200, {"ok": True})
    assert not any(item["status"] == "received_text" for item in events)

    assert send(host, {"texts": ["private fixture line"]})[0] == 200
    assert send(host)[0] == 200
    first_text = [item for item in events if item["status"] == "received_text"]
    assert first_text == [{"session_id": host.session_id, "game_id": host.game_id,
                           "status": "received_text", "count": 0}]
    assert "private fixture line" not in str(events)


def test_token_protection_and_unsafe_results(host_factory):
    provider = FakeProvider()
    host = host_factory(provider)
    original = "Hello [name] {w=0.2}{b}world{/b}"
    result = host.translate_batch([original])["results"][0]
    assert result == "译文 " + original
    assert "[name]" not in provider.calls[0]
    assert "{w=0.2}" not in provider.calls[0]
    unsafe = host_factory(FakeProvider(value="new {p}"), game="unsafe")
    assert unsafe.translate_batch(["Hello"])["statuses"] == ["unsafe"]
    assert unsafe.translate_batch(["Hello"])["statuses"] == ["unsafe"]


@pytest.mark.parametrize("data,auth,expected", [({}, False, 403),
    ({"session_id": "other"}, True, 403), ({"game_id": "other"}, True, 403),
    ({"texts": []}, True, 400), ({"texts": ["x"] * 65}, True, 400),
    ({"texts": [1]}, True, 400), ({"budget_ms": -1}, True, 400),
    ({"budget_ms": 30001}, True, 400), ({"budget_ms": True}, True, 400),
    ({"budget_ms": 10 ** 500}, True, 400),
    ({"budget_ms": float("nan")}, True, 400), ({"kind": "prediction"}, True, 400)])
def test_auth_and_validation(host_factory, data, auth, expected):
    provider = FakeProvider()
    host = host_factory(provider)
    assert send(host, data, auth=auth)[0] == expected
    assert provider.calls == []


def test_body_and_json_bounds(host_factory):
    host = host_factory(FakeProvider())
    assert send(host, raw=b"x" * 65537)[0] == 413
    assert send(host, raw=b"not json")[0] == 400
    assert send(host, raw=b"null")[0] == 400
    assert send(host, path=host.environment()["RPYKIT_TRANSLATION_URL"] + "/wrong")[0] == 404


def status_request(host, changes=None, *, auth=True, raw=None):
    payload = {"session_id": host.session_id, "game_id": host.game_id,
               "status": "luna_conflict"}
    payload.update(changes or {})
    return send(host, auth=auth, raw=(raw if raw is not None else
                json.dumps(payload).encode("utf-8")),
                path=host.environment()["RPYKIT_TRANSLATION_URL"].replace("/translate", "/status"))


def test_status_reports_local_luna_conflict_without_translation(host_factory):
    events = []
    provider = FakeProvider()
    host = host_factory(provider, callback=events.append)
    assert status_request(host) == (200, {"ok": True})
    assert provider.calls == []
    assert events[-1] == {"session_id": host.session_id, "game_id": host.game_id,
                          "status": "luna_conflict", "count": 0}
    assert "texts" not in events[-1]


@pytest.mark.parametrize("changes,auth,expected", [
    ({}, False, 401), ({"session_id": "wrong"}, True, 403),
    ({"game_id": "wrong"}, True, 403), ({"status": "started"}, True, 400),
    ({"status": ["luna_conflict"]}, True, 400),
    ({"texts": ["private dialogue"]}, True, 400)])
def test_status_rejects_bad_auth_ids_status_and_text(host_factory, changes, auth, expected):
    events = []
    provider = FakeProvider()
    host = host_factory(provider, callback=events.append)
    events.clear()
    assert status_request(host, changes, auth=auth)[0] == expected
    assert provider.calls == []
    assert events == []


def test_common_deadline_and_late_cache(host_factory):
    provider = FakeProvider(delay=0.2)
    host = host_factory(provider)
    started = time.monotonic()
    result = host.translate_batch(["one", "two", "three", "four"], 40, "menu")
    assert time.monotonic() - started < 0.16
    assert result == {"results": [None] * 4, "statuses": ["timeout"] * 4}
    time.sleep(0.3)
    assert host.translate_batch(["one", "two", "three", "four"], 0, "menu")["statuses"] == ["cached"] * 4
    assert len(provider.calls) == 4


def test_zero_wait_returns_original_then_populates_cache(host_factory):
    host = host_factory(FakeProvider(delay=0.05))
    assert host.translate_batch(["zero"], 0)["results"] == [None]
    time.sleep(0.1)
    assert host.translate_batch(["zero"], 0)["results"] == ["译文 zero"]


def test_inflight_deduplicated_across_requests(host_factory):
    provider = FakeProvider(delay=0.1)
    host = host_factory(provider)
    threads = [threading.Thread(target=host.translate_batch, args=(["duplicate"], 500)) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert provider.calls == ["duplicate"]


def test_queue_bound_and_stop_does_not_wait_for_network(host_factory):
    block = threading.Event()
    class Blocking:
        def translate(self, *args, **kwargs):
            block.wait(3)
            return "late"
    host = host_factory(Blocking())
    first = host.translate_batch(["text %d" % index for index in range(64)], 0)
    second = host.translate_batch(["next %d" % index for index in range(64)], 0)
    assert "busy" in second["statuses"]
    assert host._queue.qsize() <= service.QUEUE_SIZE
    started = time.monotonic()
    host.stop()
    host.stop()
    assert time.monotonic() - started < 0.4
    block.set()
    time.sleep(0.1)
    with sqlite3.connect(host.cache_path) as db:
        assert db.execute("SELECT count(*) FROM translations").fetchone()[0] == 0
    assert host.translate_batch(["test"], 100)["statuses"] == ["stopped"]
    with pytest.raises(RuntimeError):
        host.environment()


def test_cache_isolated_by_game_language_provider_model_and_endpoint(host_factory, tmp_path):
    cache = tmp_path / "shared.sqlite3"
    base = host_factory(FakeProvider(), cache=cache)
    base.translate_batch(["Hello"])
    for game, settings in (("other", {}), ("fixture-game", {"target_lang": "ja"}),
                            ("fixture-game", {"ai_model": "different"})):
        provider = FakeProvider()
        host = host_factory(provider, game=game, settings=settings, cache=cache)
        assert host.translate_batch(["Hello"])["statuses"] == ["success"]
        assert provider.calls == ["Hello"]
    same = host_factory(FakeProvider(), cache=cache)
    assert same.translate_batch(["Hello"])["statuses"] == ["cached"]


def test_cache_isolated_by_ai_provider_and_endpoint(host_factory, tmp_path):
    cache = tmp_path / "shared.sqlite3"
    host_factory(FakeProvider(), cache=cache).translate_batch(["Hello"])
    with upstream({"choices": [{"message": {"content": "人工智能译文"}}]}) as (first, first_calls):
        first_settings = {"provider": "ai", "ai_endpoint": first, "ai_model": "fixture"}
        host_factory(settings=first_settings, cache=cache).translate_batch(["Hello"])
        assert len(first_calls) == 1
        assert host_factory(settings=first_settings, cache=cache).translate_batch(["Hello"])["statuses"] == ["cached"]
    with upstream({"choices": [{"message": {"content": "另一接口译文"}}]}) as (second, second_calls):
        other_settings = {"provider": "ai", "ai_endpoint": second, "ai_model": "fixture"}
        assert host_factory(settings=other_settings, cache=cache).translate_batch(["Hello"])["results"] == ["另一接口译文"]
        assert len(second_calls) == 1


def test_stop_wakes_waiting_client_and_discards_late_result(host_factory):
    provider = FakeProvider(delay=0.3)
    host = host_factory(provider)
    results = []
    waiter = threading.Thread(target=lambda: results.append(host.translate_batch(["pending"], 5000)))
    waiter.start()
    cutoff = time.monotonic() + 1
    while not provider.calls and time.monotonic() < cutoff:
        time.sleep(0.005)
    host.stop()
    waiter.join(0.5)
    assert not waiter.is_alive()
    assert results[0]["statuses"] == ["stopped"]
    time.sleep(0.35)
    with sqlite3.connect(host.cache_path) as connection:
        assert connection.execute("SELECT count(*) FROM translations").fetchone()[0] == 0


def test_cache_tampering_cannot_add_renpy_control_syntax(host_factory):
    host = host_factory(FakeProvider())
    host.translate_batch(["Hello"])
    with sqlite3.connect(host.cache_path) as connection:
        connection.execute("UPDATE translations SET value=?", ("malicious {p}",))
    assert host.translate_batch(["Hello"])["results"] == ["译文 Hello"]


def test_sensitive_provider_exception_is_sanitized(host_factory):
    events = []
    provider = FakeProvider(failure=RuntimeError("secret-key-and-private-dialogue"))
    host = host_factory(provider, callback=events.append)
    result = host.translate_batch(["private dialogue"])
    assert result["statuses"] == ["provider_error"]
    assert "secret" not in str(events)
    assert "private dialogue" not in str(events)
    assert all(event["session_id"] == host.session_id for event in events)


def test_google_protocol_and_free_failure_never_calls_ai(host_factory, monkeypatch):
    def no_ai(*args, **kwargs):
        raise AssertionError("free service attempted AI fallback")
    monkeypatch.setattr(service.AIProvider, "translate", no_ai)
    with upstream([[ ["你好", "Hello", None, None] ], None, "en"]) as (url, calls):
        monkeypatch.setattr(service, "GOOGLE_URL", url + "/translate_a/single")
        host = host_factory()
        assert host.translate_batch(["Hello"])["results"] == ["你好"]
        query = parse.parse_qs(parse.urlsplit(calls[0][0]).query)
        assert query["client"] == ["gtx"]
        assert query["q"] == ["Hello"]
    with upstream(status=429) as (url, calls):
        monkeypatch.setattr(service, "GOOGLE_URL", url + "/translate_a/single")
        host = host_factory()
        assert host.translate_batch(["Hello"])["statuses"] == ["rate_limited"]


@pytest.mark.parametrize("raw,status", [(b"bad json", "invalid_response"),
                                       (b"{}", "invalid_response")])
def test_bad_google_response(host_factory, monkeypatch, raw, status):
    with upstream(raw=raw) as (url, _):
        monkeypatch.setattr(service, "GOOGLE_URL", url)
        assert host_factory().translate_batch(["Hello"])["statuses"] == [status]


def test_offline_provider_status(host_factory, monkeypatch):
    def offline(*args, **kwargs):
        raise error.URLError("synthetic network disconnected")
    monkeypatch.setattr(service.request.OpenerDirector, "open", offline)
    assert host_factory().translate_batch(["Hello"])["statuses"] == ["network_error"]


def test_ai_protocol_key_never_sent_to_game_or_events(host_factory):
    events = []
    with upstream({"choices": [{"message": {"content": "你好"}}]}) as (url, calls):
        settings = {"provider": "ai", "ai_endpoint": url + "/v1/", "ai_model": "fixture-model",
                    "api_key": "synthetic-private-key"}
        host = host_factory(settings=settings, callback=events.append)
        assert host.translate_batch(["Hello"])["results"] == ["你好"]
        path, headers, raw = calls[0]
        assert path == "/v1/chat/completions"
        assert headers["Authorization"] == "Bearer synthetic-private-key"
        body = json.loads(raw)
        assert body["model"] == "fixture-model"
        assert body["stream"] is False
        assert body["messages"][1] == {"role": "user", "content": "Hello"}
        assert "synthetic-private-key" not in str(events) + str(host.environment())


def test_ai_rejects_unsafe_endpoints():
    for endpoint in ("http://example.com/v1", "https://key@example.com/v1", "file:///key",
                     "https://example.com/v1?api_key=private", "https://example.com:bad/v1"):
        with pytest.raises(ValueError):
            service.AIProvider(translation_config.normalize_settings(
                {"provider": "ai", "ai_endpoint": endpoint, "ai_model": "fixture"}))


def test_redirect_does_not_forward_ai_authorization(host_factory):
    with upstream({"choices": [{"message": {"content": "unexpected"}}]}) as (target, target_calls):
        with upstream(status=302, redirect=target) as (source, source_calls):
            host = host_factory(settings={"provider": "ai", "ai_endpoint": source,
                                          "ai_model": "fixture", "api_key": "fixture-key"})
            assert host.translate_batch(["Hello"])["statuses"] == ["http_error"]
            assert target_calls == []


def test_google_connection_probe_sends_fixed_text_without_creating_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with upstream([[["你好，世界。", "Hello, world.", None, None]], None, "en"]) as (url, calls):
        monkeypatch.setattr(service, "GOOGLE_URL", url)
        result = service.probe_provider({"provider": "google", "wait_seconds": 0})
    assert len(calls) == 1
    assert parse.parse_qs(parse.urlsplit(calls[0][0]).query)["q"] == ["Hello, world."]
    assert set(result) == {"status", "elapsed_ms"}
    assert result["status"] == "success" and result["elapsed_ms"] >= 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("http_status,reply,expected", [
    (200, "你好，世界。", "success"),
    (200, "你好 {p}", "unsafe"),
    (401, "private response body", "auth_error"),
    (429, "private response body", "rate_limited"),
])
def test_ai_connection_probe_status_and_selected_credentials(http_status, reply, expected):
    response = {"choices": [{"message": {"content": reply}}]}
    with upstream(response, status=http_status) as (url, calls):
        result = service.probe_provider({"provider": "ai", "ai_endpoint": url + "/v1",
                                         "ai_model": "fixture", "api_key": "fixture-key"})
    assert len(calls) == 1
    path, headers, raw = calls[0]
    assert path == "/v1/chat/completions"
    assert headers["Authorization"] == "Bearer fixture-key"
    assert json.loads(raw)["messages"][1]["content"] == "Hello, world."
    assert set(result) == {"status", "elapsed_ms"} and result["status"] == expected
    assert "fixture-key" not in str(result) and reply not in str(result)


def test_connection_probe_distinguishes_timeout_from_network_failure(monkeypatch):
    with upstream(delay=0.2) as (url, _):
        monkeypatch.setattr(service, "GOOGLE_URL", url)
        assert service.probe_provider({}, timeout=0.04)["status"] == "timeout"

    def offline(*args, **kwargs):
        raise error.URLError("private network details")
    monkeypatch.setattr(service.request.OpenerDirector, "open", offline)
    result = service.probe_provider({})
    assert result["status"] == "network_error"
    assert "private network details" not in str(result)
