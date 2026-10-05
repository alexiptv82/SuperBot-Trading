import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealth:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data['status'] == 'ok'
        assert data['mode'] == 'paper'
        print(f"Health: {data}")

class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": "superbot2024"})
        assert r.status_code == 200
        assert r.json()['success'] == True

    def test_login_fail(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

class TestBotStatus:
    def test_get_status(self):
        r = requests.get(f"{BASE_URL}/api/bot/status")
        assert r.status_code == 200
        data = r.json()
        assert 'is_running' in data
        assert 'capital' in data
        assert 'open_positions' in data
        print(f"Bot status: {data}")

    def test_start_bot(self):
        r = requests.post(f"{BASE_URL}/api/bot/start")
        assert r.status_code == 200
        assert r.json()['success'] == True
        # Verify status
        status = requests.get(f"{BASE_URL}/api/bot/status").json()
        assert status['is_running'] == True

class TestMarket:
    def test_prices(self):
        r = requests.get(f"{BASE_URL}/api/market/prices")
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
        r = requests.get(f"{BASE_URL}/api/trades")
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
        r = requests.get(f"{BASE_URL}/api/trades/open")
        assert r.status_code == 200
        print(f"Open trades: {r.json()}")

class TestLogs:
    def test_get_logs(self):
        r = requests.get(f"{BASE_URL}/api/logs")
        assert r.status_code == 200
        logs = r.json()
        print(f"Total logs: {len(logs)}")
        if logs:
            l = logs[0]
            assert 'event_type' in l
            assert 'message' in l
            assert 'timestamp' in l
