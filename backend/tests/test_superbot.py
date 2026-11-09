import math
import os
import time
from urllib.parse import urlparse

import pytest
import requests

from backend.tests.conftest import integration_allowed

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test di INTEGRAZIONE: parlano con un server in esecuzione. Fuori dalla suite offline.
# Vengono SALTATI (mai contati come superati) salvo opt-in esplicito verso un server locale effimero:
# vedi backend/tests/conftest.py. Qui c'e' una seconda barriera: nessuna richiesta parte senza opt-in.
# La password di accesso NON e' nel repository: SUPERBOT_TEST_PASSWORD, solo per il server effimero.
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not BASE_URL, reason="integrazione: richiede un server attivo (REACT_APP_BACKEND_URL)")]


_TIMEOUT_S = 10
_MAX_TIMEOUT_S = 30
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str):
    """(schema, host, porta) di un URL, oppure None se non e' un http(s) valido."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _DEFAULT_PORTS or not parsed.hostname:
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or _DEFAULT_PORTS[parsed.scheme]
    except ValueError:
        return None


class _Guarded:
    """GET/POST verso il solo server locale effimero dichiarato, mai altrove.

    - opt-in locale obbligatorio (conftest.integration_allowed);
    - l'URL EFFETTIVO di ogni richiesta deve avere lo stesso schema/host/porta di REACT_APP_BACKEND_URL;
    - nessun redirect seguito (un 3xx e' un errore: nessuna seconda richiesta puo' partire);
    - nessun proxy ereditato dall'ambiente (sessione con trust_env=False);
    - timeout su ogni richiesta.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.proxies = {}

    @staticmethod
    def _check(url):
        ok, why = integration_allowed()
        if not ok:
            raise RuntimeError("richiesta di integrazione bloccata: " + why)
        base = _origin(os.environ.get("REACT_APP_BACKEND_URL", ""))
        target = _origin(url) if isinstance(url, str) else None
        if base is None or target is None or target != base:
            raise RuntimeError("richiesta di integrazione bloccata: l'URL non appartiene al server locale dichiarato")

    @staticmethod
    def _valid_timeout(value):
        """Solo un numero finito, > 0 e <= 30 s. None (= attesa infinita), bool, stringhe, tuple, nan/inf: rifiutati."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        return math.isfinite(value) and 0 < value <= _MAX_TIMEOUT_S

    def _send(self, method, url, **kwargs):
        self._check(url)
        kwargs.pop("allow_redirects", None)
        kwargs.pop("proxies", None)
        kwargs.setdefault("timeout", _TIMEOUT_S)
        if not self._valid_timeout(kwargs["timeout"]):
            raise RuntimeError("richiesta di integrazione bloccata: timeout non valido "
                               f"(ammesso un numero finito > 0 e <= {_MAX_TIMEOUT_S} s)")
        resp = self._session.request(method, url, allow_redirects=False, **kwargs)
        if 300 <= resp.status_code < 400:
            raise RuntimeError("richiesta di integrazione bloccata: redirect rifiutato (nessun redirect viene seguito)")
        return resp

    def get(self, url, **kwargs):
        return self._send("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._send("POST", url, **kwargs)


http = _Guarded()
TEST_PASSWORD = os.environ.get('SUPERBOT_TEST_PASSWORD', '')

class TestHealth:
    def test_health(self):
        r = http.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data['status'] == 'ok'
        assert data['mode'] == 'paper'
        print(f"Health: {data}")

class TestAuth:
    def test_login_success(self):
        if not TEST_PASSWORD:
            pytest.skip("SUPERBOT_TEST_PASSWORD non impostata")
        r = http.post(f"{BASE_URL}/api/auth/login", json={"password": TEST_PASSWORD})
        assert r.status_code == 200
        assert r.json()['success'] == True

    def test_login_fail(self):
        r = http.post(f"{BASE_URL}/api/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

class TestBotStatus:
    def test_get_status(self):
        r = http.get(f"{BASE_URL}/api/bot/status")
        assert r.status_code == 200
        data = r.json()
        assert 'is_running' in data
        assert 'capital' in data
        assert 'open_positions' in data
        print(f"Bot status: {data}")

    def test_start_bot(self):
        r = http.post(f"{BASE_URL}/api/bot/start")
        assert r.status_code == 200
        assert r.json()['success'] == True
        # Verify status
        status = http.get(f"{BASE_URL}/api/bot/status").json()
        assert status['is_running'] == True

class TestMarket:
    def test_prices(self):
        r = http.get(f"{BASE_URL}/api/market/prices")
        assert r.status_code == 200
        data = r.json()
        for sym in ['BTCUSDT', 'ETHUSDT', 'XAUUSDT', 'XAGUSDT']:
            assert sym in data
            if 'error' not in data[sym]:
                assert 'price' in data[sym]
                assert data[sym]['price'] > 0
        print(f"Prices: { {k: v.get('price', v) for k, v in data.items()} }")

class TestTrades:
    def test_get_trades(self):
        r = http.get(f"{BASE_URL}/api/trades")
        assert r.status_code == 200
        trades = r.json()
        print(f"Total trades: {len(trades)}")
        if trades:
            t = trades[0]
            assert 'symbol' in t
            assert 'entry_price' in t
            assert 'quantity' in t
            assert 'status' in t

    def test_open_trades(self):
        r = http.get(f"{BASE_URL}/api/trades/open")
        assert r.status_code == 200
        print(f"Open trades: {r.json()}")

class TestLogs:
    def test_get_logs(self):
        r = http.get(f"{BASE_URL}/api/logs")
        assert r.status_code == 200
        logs = r.json()
        print(f"Total logs: {len(logs)}")
        if logs:
            l = logs[0]
            assert 'event_type' in l
            assert 'message' in l
            assert 'timestamp' in l
