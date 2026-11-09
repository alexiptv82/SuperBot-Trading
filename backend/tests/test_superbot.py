import os
import time

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


class _Guarded:
    """requests.get/post, ma rifiuta prima di inviare se l'opt-in locale non c'e'."""

    @staticmethod
    def _check():
        ok, why = integration_allowed()
        if not ok:
            raise RuntimeError("richiesta di integrazione bloccata: " + why)

    def get(self, *a, **k):
        self._check()
        return requests.request('GET', *a, **k)

    def post(self, *a, **k):
        self._check()
        return requests.request('POST', *a, **k)


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
