"""Bounded, session-authenticated local translation broker.

The game sees only a loopback URL and a random session credential. Provider
credentials remain in this process. A missed deadline yields original text;
late safe results can populate the cache, never rewrite an earlier response.
"""
from __future__ import annotations

import hashlib
import hmac
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import secrets
import sqlite3
import threading
import time
from urllib import error, parse, request

from translation_config import normalize_settings

GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
PROMPT_VERSION = "renpy-tokens-1"
MAX_BODY = 65536
MAX_TEXTS = 64
MAX_RESPONSE = 262144
NETWORK_TIMEOUT = 10.0
PROBE_TEXT = "Hello, world."
WORKERS = 4
QUEUE_SIZE = 64


class TranslationError(Exception):
    """A deliberately non-sensitive error suitable for a status event."""
    def __init__(self, status):
        self.status = status
        super().__init__(status)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _json_request(req, timeout):
    try:
        with request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise TranslationError("invalid_response")
        return json.loads(raw.decode("utf-8"))
    except error.HTTPError as exc:
        status = {401: "auth_error", 403: "auth_error", 429: "rate_limited"}.get(exc.code, "http_error")
        raise TranslationError(status) from None
    except error.URLError as exc:
        status = "timeout" if isinstance(exc.reason, TimeoutError) else "network_error"
        raise TranslationError(status) from None
    except TimeoutError:
        raise TranslationError("timeout") from None
    except OSError:
        raise TranslationError("network_error") from None
    except (ValueError, UnicodeError):
        raise TranslationError("invalid_response") from None


def _ai_url(endpoint):
    try:
        parts = parse.urlsplit(endpoint)
        if (parts.scheme not in ("https", "http") or not parts.hostname or
                parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError()
        if parts.scheme == "http":
            loopback = parts.hostname.lower() == "localhost"
            try:
                loopback = loopback or ipaddress.ip_address(parts.hostname).is_loopback
            except ValueError:
                pass
            if not loopback:
                raise ValueError()
        # Force validation of malformed ports before starting a session.
        parts.port
    except ValueError:
        raise ValueError("AI endpoint must use HTTPS, or HTTP on loopback, without URL credentials") from None
    path = parts.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions"
    return parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class GoogleProvider:
    def __init__(self, settings):
        self.settings = settings

    def translate(self, text, timeout=NETWORK_TIMEOUT):
        query = parse.urlencode({"client": "gtx", "sl": self.settings["source_lang"],
                                 "tl": self.settings["target_lang"], "dt": "t", "q": text})
        data = _json_request(request.Request(GOOGLE_URL + "?" + query,
                                            headers={"User-Agent": "RPYKit/1.3"}), timeout)
        try:
            pieces = data[0]
            if not isinstance(pieces, list) or not pieces:
                raise ValueError()
            result = "".join(piece[0] for piece in pieces
                             if isinstance(piece, list) and piece and isinstance(piece[0], str))
            if not result:
                raise ValueError()
            return result
        except (KeyError, IndexError, TypeError, ValueError):
            raise TranslationError("invalid_response") from None


class AIProvider:
    def __init__(self, settings):
        self.settings = settings
        self.url = _ai_url(settings["ai_endpoint"])
        if not settings["ai_model"]:
            raise ValueError("An AI model is required")

    def translate(self, text, timeout=NETWORK_TIMEOUT):
        prompt = ("Translate the supplied game text from %s to %s. Return only the translation. "
                  "Keep every __RPYKIT token byte-for-byte in the same order. "
                  "Do not add formatting, explanations or new placeholders.") % (
                      self.settings["source_lang"], self.settings["target_lang"])
        body = {"model": self.settings["ai_model"], "stream": False,
                "messages": [{"role": "system", "content": prompt},
                             {"role": "user", "content": text}]}
        headers = {"Content-Type": "application/json", "User-Agent": "RPYKit/1.3"}
        if self.settings["api_key"]:
            headers["Authorization"] = "Bearer " + self.settings["api_key"]
        data = _json_request(request.Request(self.url,
                             data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                             headers=headers, method="POST"), timeout)
        try:
            result = data["choices"][0]["message"]["content"]
            if not isinstance(result, str) or not result.strip():
                raise ValueError()
            return result
        except (KeyError, IndexError, TypeError, ValueError):
            raise TranslationError("invalid_response") from None


def _provider_for(settings):
    return AIProvider(settings) if settings["provider"] == "ai" else GoogleProvider(settings)


def _translate_checked(provider, text, timeout):
    from translation_text import protect, restore, is_safe_translation

    masked, tokens = protect(text)
    candidate = provider.translate(masked, timeout=timeout)
    if not isinstance(candidate, str) or len(candidate) > 65536 or not candidate.strip():
        raise TranslationError("invalid_response")
    result = restore(candidate, tokens)
    if result is None or not is_safe_translation(text, result):
        raise TranslationError("unsafe")
    return result


def probe_provider(settings, timeout=NETWORK_TIMEOUT):
    """Send one fixed sample through the selected provider and return status only."""
    started = time.monotonic()
    try:
        provider = _provider_for(normalize_settings(settings))
        _translate_checked(provider, PROBE_TEXT, timeout)
        status = "success"
    except TranslationError as exc:
        status = exc.status
    except Exception:
        status = "provider_error"
    return {"status": status, "elapsed_ms": round((time.monotonic() - started) * 1000)}


class _Pending:
    def __init__(self, text):
        self.text = text
        self.event = threading.Event()
        self.result = None
        self.status = "timeout"
        self.completed_at = None


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, handler)

    def process_request(self, sock, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(sock)
            return
        try:
            super().process_request(sock, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, sock, address):
        try:
            super().process_request_thread(sock, address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # HTTP/server exceptions must not dump request data or credentials.
        pass


class TranslationHost:
    def __init__(self, settings, game_id, cache_path=None, event_callback=None):
        self.settings = normalize_settings(settings)
        if not isinstance(game_id, str) or not game_id or len(game_id) > 512:
            raise ValueError("A bounded game identifier is required")
        self.game_id = game_id
        self.session_id = secrets.token_urlsafe(24)
        self.token = secrets.token_urlsafe(32)
        self.event_callback = event_callback
        if cache_path is None:
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                raise OSError("LOCALAPPDATA is unavailable; specify a translation cache path")
            cache_path = Path(local) / "rpykit" / "translation" / "cache.sqlite3"
        self.cache_path = str(cache_path)
        self._lock = threading.RLock()
        self._cache_lock = threading.Lock()
        self._active = False
        self._stopped = False
        self._received_text = False
        self._server = None
        self._queue = queue.Queue(QUEUE_SIZE)
        self._inflight = {}
        self._provider = _provider_for(self.settings)
        self._endpoint = (self._provider.url if self.settings["provider"] == "ai"
                          else GOOGLE_URL)

    def _notify(self, status, count=1, elapsed_ms=None):
        if not self.event_callback:
            return
        event = {"session_id": self.session_id, "game_id": self.game_id,
                 "status": status, "count": count}
        if elapsed_ms is not None:
            event["elapsed_ms"] = elapsed_ms
        try:
            self.event_callback(event)
        except Exception:
            pass

    def _notify_first_text(self):
        with self._lock:
            if not self._active or self._received_text:
                return
            self._received_text = True
        self._notify("received_text", 0)

    @contextmanager
    def _database(self):
        # A locked cache must never spend the dialogue's budget waiting on IO.
        connection = sqlite3.connect(self.cache_path, timeout=0.0)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self):
        with self._lock:
            if self._active:
                return self
            if self._stopped:
                raise RuntimeError("A stopped translation host cannot be restarted")
            Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
            with self._database() as connection:
                connection.execute("CREATE TABLE IF NOT EXISTS translations "
                                   "(cache_key TEXT PRIMARY KEY, value TEXT NOT NULL, used REAL NOT NULL)")
            host = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def setup(self):
                    super().setup()
                    self.connection.settimeout(2.0)

                def _reply(self, status, value):
                    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
                    try:
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(raw)))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.wfile.write(raw)
                    except (OSError, ValueError):
                        pass

                def do_POST(self):
                    if self.path not in ("/translate", "/status"):
                        self._reply(404, {"error": "not_found"})
                        return
                    supplied = self.headers.get("Authorization", "")
                    if not hmac.compare_digest(supplied.encode("utf-8"),
                                               ("Bearer " + host.token).encode("ascii")):
                        self._reply(401 if self.path == "/status" else 403,
                                    {"error": "unauthorized"})
                        return
                    try:
                        raw_length = self.headers.get("Content-Length", "")
                        if self.headers.get("Transfer-Encoding") or not raw_length.isdecimal():
                            raise ValueError()
                        length = int(raw_length)
                        if not 0 < length <= MAX_BODY:
                            self._reply(413, {"error": "request_too_large"})
                            return
                        raw = self.rfile.read(length)
                        if len(raw) != length:
                            raise ValueError()
                        data = json.loads(raw.decode("utf-8"))
                        if self.path == "/status":
                            host._validate_status(data)
                        else:
                            host._validate_request(data)
                    except (ValueError, UnicodeError, OSError, RecursionError):
                        self._reply(400, {"error": "invalid_request"})
                        return
                    if (data["session_id"] != host.session_id or data["game_id"] != host.game_id):
                        self._reply(403, {"error": "wrong_session"})
                        return
                    if self.path == "/status":
                        host._notify("luna_conflict", 0)
                        self._reply(200, {"ok": True})
                        return
                    host._notify_first_text()
                    results = host.translate_batch(data["texts"], data["budget_ms"], data["kind"])
                    self._reply(200, results)

            self._server = _Server(("127.0.0.1", 0), Handler)
            self._active = True
            try:
                for index in range(WORKERS):
                    threading.Thread(target=self._worker, name="translation-worker-%d" % index,
                                     daemon=True).start()
                threading.Thread(target=self._server.serve_forever,
                                 kwargs={"poll_interval": 0.05}, name="translation-loopback",
                                 daemon=True).start()
            except Exception:
                # The server thread did not start, so shutdown() would block.
                self._active = False
                server, self._server = self._server, None
                server.server_close()
                raise
        self._notify("started", 0)
        return self

    def environment(self):
        with self._lock:
            if not self._active:
                raise RuntimeError("Translation host is not running")
            return {"RPYKIT_TRANSLATION_URL": "http://127.0.0.1:%d/translate" % self._server.server_port,
                    "RPYKIT_TRANSLATION_TOKEN": self.token,
                    "RPYKIT_TRANSLATION_SESSION": self.session_id,
                    "RPYKIT_TRANSLATION_GAME": self.game_id,
                    "RPYKIT_TRANSLATION_WAIT_MS": str(round(self.settings["wait_seconds"] * 1000))}

    @staticmethod
    def _validate_status(data):
        if (not isinstance(data, dict) or
                set(data) != {"session_id", "game_id", "status"} or
                not isinstance(data["session_id"], str) or
                not isinstance(data["game_id"], str) or
                data["status"] != "luna_conflict"):
            raise ValueError()

    @staticmethod
    def _validate_request(data):
        if not isinstance(data, dict):
            raise ValueError()
        texts = data.get("texts")
        budget = data.get("budget_ms")
        if (not isinstance(texts, list) or not 1 <= len(texts) <= MAX_TEXTS or
                any(not isinstance(text, str) or len(text) > 16384 for text in texts) or
                not isinstance(budget, (int, float)) or isinstance(budget, bool) or
                not 0 <= budget <= 30000 or not math.isfinite(budget) or
                data.get("kind") not in ("say", "menu") or
                not isinstance(data.get("session_id"), str) or
                not isinstance(data.get("game_id"), str)):
            raise ValueError()

    def _key(self, text):
        config = {name: self.settings[name] for name in
                  ("provider", "source_lang", "target_lang", "ai_model")}
        config.update(endpoint=self._endpoint, prompt=PROMPT_VERSION,
                      game=self.game_id, text=text)
        return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _cached(self, key, original):
        from translation_text import is_safe_translation
        try:
            with self._cache_lock, self._database() as connection:
                row = connection.execute("SELECT value FROM translations WHERE cache_key=?", (key,)).fetchone()
            if row and is_safe_translation(original, row[0]):
                return row[0]
        except (sqlite3.Error, OSError):
            self._notify("cache_unavailable")
        return None

    def _put_cache(self, key, value):
        try:
            with self._cache_lock, self._database() as connection:
                connection.execute("INSERT OR REPLACE INTO translations VALUES (?,?,?)",
                                   (key, value, time.time()))
                connection.execute("DELETE FROM translations WHERE cache_key IN "
                                   "(SELECT cache_key FROM translations ORDER BY used DESC LIMIT -1 OFFSET 20000)")
        except (sqlite3.Error, OSError):
            self._notify("cache_unavailable")

    def translate_batch(self, texts, budget_ms=None, kind="say"):
        budget_ms = round(self.settings["wait_seconds"] * 1000) if budget_ms is None else budget_ms
        self._validate_request({"texts": texts, "budget_ms": budget_ms, "kind": kind,
                                "session_id": self.session_id, "game_id": self.game_id})
        deadline = time.monotonic() + budget_ms / 1000.0
        pending = []
        for text in texts:
            key = self._key(text)
            with self._lock:
                if not self._active:
                    pending.append((None, None, "stopped"))
                    continue
                cached = self._cached(key, text)
                if cached is not None:
                    pending.append((None, cached, "cached"))
                    continue
                job = self._inflight.get(key)
                if job is None:
                    job = _Pending(text)
                    self._inflight[key] = job
                    try:
                        self._queue.put_nowait((key, job))
                    except queue.Full:
                        self._inflight.pop(key, None)
                        pending.append((None, None, "busy"))
                        continue
                pending.append((job, None, None))
        results, statuses = [], []
        for job, result, status in pending:
            if job is not None:
                job.event.wait(max(0.0, deadline - time.monotonic()))
                with self._lock:
                    if not self._active:
                        result, status = None, "stopped"
                    elif (job.event.is_set() and job.completed_at is not None and
                          job.completed_at <= deadline):
                        result, status = job.result, job.status
                    else:
                        result, status = None, "timeout"
            results.append(result)
            statuses.append(status)
        elapsed = max(0, round((time.monotonic() - deadline + budget_ms / 1000.0) * 1000))
        for status in sorted(set(statuses)):
            self._notify(status, statuses.count(status), elapsed)
        return {"results": results, "statuses": statuses}

    def _worker(self):
        while True:
            try:
                key, job = self._queue.get(timeout=0.1)
            except queue.Empty:
                with self._lock:
                    if not self._active:
                        return
                continue
            with self._lock:
                if not self._active:
                    self._queue.task_done()
                    return
            result, status = None, "invalid_response"
            try:
                result = _translate_checked(self._provider, job.text, NETWORK_TIMEOUT)
                status = "success"
            except TranslationError as exc:
                status = exc.status
            except Exception:
                # Do not expose exception strings: providers may include URLs/keys.
                result, status = None, "provider_error"
            with self._lock:
                if self._active:
                    if result is not None:
                        self._put_cache(key, result)
                    job.result, job.status = result, status
                else:
                    job.result, job.status = None, "stopped"
                job.completed_at = time.monotonic()
                job.event.set()
                self._inflight.pop(key, None)
            self._queue.task_done()

    def stop(self):
        with self._lock:
            if self._stopped:
                return
            self._active = False
            self._stopped = True
            for job in self._inflight.values():
                job.result, job.status = None, "stopped"
                job.event.set()
            self._inflight.clear()
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
            server = self._server
        if server is not None:
            server.shutdown()
            server.server_close()
        self._notify("stopped", 0)
