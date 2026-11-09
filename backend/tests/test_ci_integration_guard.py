"""Sicurezza della CI offline: i test `integration` non possono inviare richieste a un server per errore.

Un finto server locale CONTA ogni richiesta ricevuta (metodo e percorso). Sottoprocessi pytest selezionano
`test_superbot.py` con REACT_APP_BACKEND_URL puntato al finto server o a un host fittizio non locale:
senza opt-in esplicito il contatore deve restare a ZERO (nessun GET, nessun POST /api/bot/start).
Il controllo positivo (opt-in locale) prova che il contatore funziona davvero.
Nessuna rete esterna: solo 127.0.0.1.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from backend.tests.conftest import integration_allowed

ROOT = Path(__file__).resolve().parents[2]
TARGET = "backend/tests/test_superbot.py"


class _Counter(BaseHTTPRequestHandler):
    seen: list = []

    def _answer(self):
        type(self).seen.append((self.command, self.path))
        body = b'{"status":"ok","mode":"paper","success":true,"is_running":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = _answer

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_server():
    handler = type("H", (_Counter,), {"seen": []})
    srv = HTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", handler.seen
    finally:
        srv.shutdown()
        srv.server_close()


def _run(url, extra_env=None, args=()):
    env = {k: v for k, v in os.environ.items() if k not in ("REACT_APP_BACKEND_URL", "SUPERBOT_ALLOW_INTEGRATION",
                                                            "SUPERBOT_TEST_PASSWORD")}
    env.update(PYTHONPATH=f"{ROOT}:{ROOT / 'backend'}", REACT_APP_BACKEND_URL=url, **(extra_env or {}))
    proc = subprocess.run([sys.executable, "-m", "pytest", TARGET, "-p", "no:cacheprovider", "-q", "-rs",
                           "--strict-markers", *args], cwd=str(ROOT), env=env, capture_output=True, text=True,
                          timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def test_fake_url_without_opt_in_sends_zero_requests_and_skips_all_nine(fake_server):
    url, seen = fake_server
    rc, out = _run(url)
    assert seen == [], f"richieste inviate al server: {seen}"
    assert "9 skipped" in out and "passed" not in out and "failed" not in out
    assert "SUPERBOT_ALLOW_INTEGRATION" in out                      # motivo dello skip visibile
    assert rc == 0


def test_excluding_integration_by_marker_deselects_everything_and_sends_zero_requests(fake_server):
    url, seen = fake_server
    rc, out = _run(url, args=("-m", "not integration"))
    assert seen == []
    assert "9 deselected" in out and "passed" not in out
    assert rc in (0, 5)                                              # 5 = nessun test raccolto


def test_opt_in_with_a_non_local_host_is_refused_without_any_request(fake_server):
    _, seen = fake_server
    rc, out = _run("http://backend.invalid:9", {"SUPERBOT_ALLOW_INTEGRATION": "1"})
    assert seen == [] and "9 skipped" in out and "host rifiutato" in out
    rc, out = _run("https://staging.example.org", {"SUPERBOT_ALLOW_INTEGRATION": "1"})
    assert "9 skipped" in out and "host rifiutato" in out


def test_opt_in_alone_without_a_url_does_nothing(fake_server):
    _, seen = fake_server
    rc, out = _run("", {"SUPERBOT_ALLOW_INTEGRATION": "1"})
    assert seen == [] and "9 skipped" in out


def test_control_explicit_local_opt_in_does_reach_the_counter(fake_server):
    """Controllo positivo: senza questo, 'zero richieste' non proverebbe nulla. Solo verso il finto server locale."""
    url, seen = fake_server
    _run(url, {"SUPERBOT_ALLOW_INTEGRATION": "1"})
    assert ("GET", "/api/health") in seen
    assert ("POST", "/api/bot/start") in seen                        # esattamente la richiesta che la CI deve evitare
    assert not any("/api/auth/login" == p and m == "POST" and False for m, p in seen)


@pytest.mark.parametrize("env, expected", [
    ({}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1"}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "0", "REACT_APP_BACKEND_URL": "http://127.0.0.1:8001"}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "http://127.0.0.1:8001"}, True),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "http://localhost:8001"}, True),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "http://127.0.0.1.evil.example:80"}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "http://user@evil.example/127.0.0.1"}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "ftp://127.0.0.1"}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "true", "REACT_APP_BACKEND_URL": "http://127.0.0.1"}, False),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "http://[::1]:8001"}, True),
    ({"SUPERBOT_ALLOW_INTEGRATION": "1", "REACT_APP_BACKEND_URL": "http://0.0.0.0:8001"}, False),
])
def test_integration_allowed_decision_table(env, expected):
    assert integration_allowed(env)[0] is expected


def test_the_integration_module_contains_no_static_password_and_refuses_unguarded_calls(monkeypatch):
    src = (ROOT / TARGET).read_text(encoding="utf-8")
    assert "superbot2024" not in src
    from backend.tests import test_superbot
    monkeypatch.delenv("SUPERBOT_ALLOW_INTEGRATION", raising=False)
    with pytest.raises(RuntimeError, match="bloccata"):
        test_superbot.http.post("http://127.0.0.1:9/api/bot/start")
    with pytest.raises(RuntimeError, match="bloccata"):
        test_superbot.http.get("http://127.0.0.1:9/api/health")


# ---------------------------------------------------------------- redirect, proxy, URL effettivo, timeout (in-process)

import requests
from requests.adapters import HTTPAdapter


class _Redirecting(BaseHTTPRequestHandler):
    seen: list = []
    location = "http://sentinel.invalid:9/leak"

    def _answer(self):
        type(self).seen.append((self.command, self.path))
        if self.path.startswith("/redir"):
            self.send_response(302)
            self.send_header("Location", type(self).location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer

    def log_message(self, *a):
        pass


def _serve(handler_cls):
    handler = type("H", (handler_cls,), {"seen": []})
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, handler


@pytest.fixture
def origin():
    srv, handler = _serve(_Redirecting)
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", handler
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def spy(monkeypatch, origin):
    """Registra ogni richiesta inviata. Verso il server finto passa davvero; verso QUALSIASI altro URL non fa
    nessuna connessione: registra e risponde con una risposta finta (cosi' il test non tocca mai la rete)."""
    url, _ = origin
    host_port = url.split("//", 1)[1]
    calls = []
    real_send = HTTPAdapter.send

    def fake_send(self, request, **kwargs):
        calls.append({"url": request.url, "timeout": kwargs.get("timeout"), "proxies": kwargs.get("proxies")})
        if request.url.split("//", 1)[1].split("/", 1)[0] == host_port:
            return real_send(self, request, **kwargs)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"{}"
        resp.url = request.url
        resp.request = request
        return resp

    monkeypatch.setattr(HTTPAdapter, "send", fake_send)
    monkeypatch.setenv("SUPERBOT_ALLOW_INTEGRATION", "1")
    monkeypatch.setenv("REACT_APP_BACKEND_URL", url)
    return calls


def _guarded():
    from backend.tests import test_superbot
    return test_superbot.http


@pytest.mark.parametrize("target", [
    "http://sentinel.invalid:9/leak",                      # host non locale
    "https://example.org/leak",                            # https esterno
    "http://127.0.0.1:1/leak",                             # altro server locale (altra porta)
    "//evil.invalid/leak",                                 # relativo allo schema
])
def test_a_redirect_to_another_host_is_refused_and_no_second_request_is_ever_sent(origin, spy, target):
    url, handler = origin
    handler.location = target
    with pytest.raises(RuntimeError, match="redirect rifiutato"):
        _guarded().get(url + "/redir")
    with pytest.raises(RuntimeError, match="redirect rifiutato"):
        _guarded().post(url + "/redir")
    assert [c["url"] for c in spy] == [url + "/redir", url + "/redir"]     # solo le due richieste al server finto
    assert handler.seen == [("GET", "/redir"), ("POST", "/redir")]
    handler.location = "http://sentinel.invalid:9/leak"


def test_control_a_plain_requests_session_does_follow_the_redirect_to_the_sentinel(origin, spy):
    """Controllo positivo: senza il wrapper il redirect parte davvero (la spia lo vede, senza connessione reale)."""
    url, _ = origin
    session = requests.Session()
    session.trust_env = False
    session.get(url + "/redir", timeout=5)
    assert "http://sentinel.invalid:9/leak" in [c["url"] for c in spy]


@pytest.mark.parametrize("bad", [
    "http://localhost:{port}/x",              # stesso loopback ma host diverso da quello dichiarato
    "http://127.0.0.1:{other}/x",             # altra porta
    "https://127.0.0.1:{port}/x",             # altro schema
    "ftp://127.0.0.1:{port}/x",
    "http://sentinel.invalid:{port}/x",
    "http://127.0.0.1.evil.invalid:{port}/x",
    "",
    None,
])
def test_a_request_whose_effective_url_is_not_the_declared_server_is_refused_before_sending(origin, spy, bad):
    url, handler = origin
    port = int(url.rsplit(":", 1)[1])
    target = bad.format(port=port, other=port + 1) if isinstance(bad, str) else bad
    with pytest.raises(RuntimeError, match="bloccata"):
        _guarded().get(target)
    with pytest.raises(RuntimeError, match="bloccata"):
        _guarded().post(target)
    assert spy == [] and handler.seen == []


def test_inherited_proxies_are_not_used(origin, spy, monkeypatch):
    url, handler = origin
    proxy_srv, proxy_handler = _serve(_Redirecting)
    try:
        proxy_url = f"http://127.0.0.1:{proxy_srv.server_address[1]}"
        for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(var, proxy_url)
        for var in ("NO_PROXY", "no_proxy"):
            monkeypatch.setenv(var, "")
        plain = requests.Session()                           # controllo: sessione che eredita l'ambiente
        plain.get(url + "/ok", timeout=5)
        assert any(c["proxies"] for c in spy), "il controllo avrebbe dovuto usare il proxy ereditato"
        spy.clear()
        _guarded().get(url + "/ok")
        assert all(not c["proxies"] for c in spy)            # nessun proxy applicato dal wrapper
        assert [c["url"] for c in spy] == [url + "/ok"]
    finally:
        proxy_srv.shutdown()
        proxy_srv.server_close()


def test_every_request_has_a_bounded_timeout(origin, spy):
    url, _ = origin
    _guarded().get(url + "/ok")
    _guarded().post(url + "/ok")
    assert all(c["timeout"] is not None and 0 < c["timeout"] <= 30 for c in spy) and len(spy) == 2
    spy.clear()
    _guarded().get(url + "/ok", timeout=3, allow_redirects=True, proxies={"http": "http://evil.invalid:1"})
    assert spy[0]["timeout"] == 3 and not spy[0]["proxies"]  # allow_redirects e proxies passati dal chiamante vengono ignorati
