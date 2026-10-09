"""Test in-process (FastAPI TestClient + SQLite temporaneo) del flusso di
autenticazione: password iniziale -> cambio forzato -> hash nel DB ->
scadenza 60 giorni -> reset -> limite ai tentativi -> token invalidati.

Non richiede un server in esecuzione (a differenza di test_superbot.py).
Lanciare dalla cartella backend/:  python -m pytest tests/test_auth_flow.py
"""
import asyncio
import base64
import os
import sys
import tempfile
from datetime import datetime, timedelta

import jwt
import pytest

# Ambiente PRIMA di importare l'app (config e database leggono env all'import).
_TMP = tempfile.mkdtemp(prefix="sb-auth-test-")
os.environ["DB_PATH"] = os.path.join(_TMP, "t.db")
os.environ["DASHBOARD_PASSWORD_B64"] = base64.b64encode(b"IniziALE-pw-2026").decode()
os.environ.pop("DASHBOARD_PASSWORD", None)
os.environ["TELEGRAM_BOT_TOKEN"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(_TMP)

from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import server  # noqa: E402
from database import SessionLocal  # noqa: E402

BOOT = "IniziALE-pw-2026"
NEW = "NuovaPassword-Sicura-1"


@pytest.fixture(scope="module")
def client():
    # sleep di rallentamento istantaneo, per non allungare i test
    async def _no_sleep(_):
        return None

    class _FastAsyncio:  # proxy di asyncio con sleep istantaneo, solo dentro server.py
        sleep = staticmethod(_no_sleep)
        def __getattr__(self, name):
            return getattr(asyncio, name)

    real = server.asyncio
    server.asyncio = _FastAsyncio()
    auth.init_auth()
    yield TestClient(server.app)
    server.asyncio = real


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _set_changed_at(days_ago):
    db = SessionLocal()
    try:
        row = db.query(auth.AuthSettings).filter(auth.AuthSettings.id == 1).first()
        row.password_changed_at = datetime.utcnow() - timedelta(days=days_ago)
        db.commit()
    finally:
        db.close()


def _raw_row():
    db = SessionLocal()
    try:
        r = db.query(auth.AuthSettings).filter(auth.AuthSettings.id == 1).first()
        return r.password_hash, r.jwt_secret
    finally:
        db.close()


def test_01_jwt_secret_random_and_persisted():
    _, secret = _raw_row()
    assert secret and secret != "superbot-secret-key" and len(secret) >= 40
    assert auth._load_settings()["jwt_secret"] == secret


def test_02_old_default_password_and_forged_token_rejected(client):
    assert client.post("/api/auth/login", json={"password": "superbot2024"}).status_code == 401
    forged = jwt.encode({"iat": 1, "exp": 9999999999, "sub": "superbot-dashboard", "scope": "full", "ver": 0},
                        "superbot-secret-key", algorithm="HS256")
    assert client.get("/api/bot/status", headers=_hdr(forged)).status_code == 401


def test_03_first_login_gives_limited_token(client):
    r = client.post("/api/auth/login", json={"password": BOOT})
    assert r.status_code == 200
    body = r.json()
    assert body["must_change"] == "first_login"
    limited = body["token"]
    assert jwt.decode(limited, options={"verify_signature": False})["scope"] == "change_only"
    # il token limitato non apre nient'altro
    assert client.get("/api/bot/status", headers=_hdr(limited)).status_code == 403
    assert client.put("/api/bot/config/risk", headers=_hdr(limited),
                      json={"max_leverage": 5, "max_daily_loss_percent": 3, "max_open_positions": 2}).status_code == 403
    pytest.limited = limited


def test_04_change_password_validation(client):
    h = _hdr(pytest.limited)
    def go(old, new):
        return client.post("/api/auth/change-password", headers=h, json={"old_password": old, "new_password": new})
    assert go("sbagliata", NEW).status_code == 401
    assert go(BOOT, "corta").status_code == 400
    assert go(BOOT, BOOT).status_code == 400
    assert go(BOOT, "superbot2024-nuova").status_code == 400
    assert go(BOOT, "aaaaaaaaaaaa").status_code == 400


def test_05_change_password_success_stores_only_hash(client):
    r = client.post("/api/auth/change-password", headers=_hdr(pytest.limited),
                    json={"old_password": BOOT, "new_password": NEW})
    assert r.status_code == 200
    full = r.json()["token"]
    assert jwt.decode(full, options={"verify_signature": False})["scope"] == "full"
    assert client.get("/api/bot/status", headers=_hdr(full)).status_code == 200
    pwd_hash, _ = _raw_row()
    assert pwd_hash.startswith("scrypt$") and NEW not in pwd_hash
    assert r.json()["password_status"]["days_left"] == 60
    pytest.full = full


def test_06_old_sessions_invalidated_and_passwords_switch(client):
    # il token limitato precedente non vale piu' (token_version incrementata)
    again = client.post("/api/auth/change-password", headers=_hdr(pytest.limited),
                        json={"old_password": NEW, "new_password": "AltraPassword-2-xyz"})
    assert again.status_code == 401
    assert client.post("/api/auth/login", json={"password": BOOT}).status_code == 401
    r = client.post("/api/auth/login", json={"password": NEW})
    assert r.status_code == 200 and r.json()["must_change"] is None
    pytest.full = r.json()["token"]


def test_07_password_status_and_warning(client):
    st = client.get("/api/auth/password-status", headers=_hdr(pytest.full)).json()
    assert st["set"] and st["days_left"] == 60 and st["warn"] is False
    _set_changed_at(55)
    st = client.get("/api/auth/password-status", headers=_hdr(pytest.full)).json()
    assert st["days_left"] == 5 and st["warn"] is True


def test_08_expired_password_forces_change(client):
    _set_changed_at(61)
    r = client.post("/api/auth/login", json={"password": NEW})
    assert r.json()["must_change"] == "expired"
    limited = r.json()["token"]
    assert client.get("/api/bot/status", headers=_hdr(limited)).status_code == 403
    # il cambio richiede la vecchia password
    bad = client.post("/api/auth/change-password", headers=_hdr(limited),
                      json={"old_password": "no", "new_password": "Terza-Password-77"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/change-password", headers=_hdr(limited),
                     json={"old_password": NEW, "new_password": "Terza-Password-77"})
    assert ok.status_code == 200
    assert client.get("/api/bot/status", headers=_hdr(ok.json()["token"])).status_code == 200
    assert auth.session_state_after_biometric() == "ok"
    _set_changed_at(61)
    assert auth.session_state_after_biometric() == "expired"
    _set_changed_at(0)


def test_09_full_token_cannot_outlive_password(client):
    _set_changed_at(59)
    tok = auth.create_session_token("full")
    exp = jwt.decode(tok, options={"verify_signature": False})["exp"]
    assert exp - datetime.utcnow().timestamp() < 2 * 86400
    _set_changed_at(0)


def test_10_telegram_reset_returns_to_initial_password(client):
    msg = asyncio.run(server._cmd_resetpassword())
    assert "Password" in msg and BOOT not in msg
    assert client.post("/api/auth/login", json={"password": "Terza-Password-77"}).status_code == 401
    r = client.post("/api/auth/login", json={"password": BOOT})
    assert r.json()["must_change"] == "first_login"
    assert _raw_row()[0] is None


def test_11_rate_limit_blocks_after_repeated_failures(client):
    auth._fail_times.clear()
    auth._locked_until = 0.0
    codes = [client.post("/api/auth/login", json={"password": f"sbagliata-{i}"}).status_code for i in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429
    # anche la password giusta e' bloccata finche' dura il lock
    assert client.post("/api/auth/login", json={"password": BOOT}).status_code == 429
    auth._locked_until = 0.0
    auth._fail_times.clear()
    assert client.post("/api/auth/login", json={"password": BOOT}).status_code == 200


def test_12_missing_bootstrap_password_disables_login(client, monkeypatch):
    monkeypatch.setattr(auth.config, "DASHBOARD_PASSWORD", "")
    r = client.post("/api/auth/login", json={"password": ""})
    assert r.status_code == 503


def test_13_risk_config_requires_full_session(client):
    r = client.post("/api/auth/login", json={"password": BOOT})
    limited = r.json()["token"]
    done = client.post("/api/auth/change-password", headers=_hdr(limited),
                       json={"old_password": BOOT, "new_password": "Quarta-Password-88"})
    full = done.json()["token"]
    ok = client.put("/api/bot/config/risk", headers=_hdr(full),
                    json={"max_leverage": 5, "max_daily_loss_percent": 3, "max_open_positions": 2})
    assert ok.status_code == 200
    bad = client.put("/api/bot/config/risk", headers=_hdr(full),
                     json={"max_leverage": 99, "max_daily_loss_percent": 3, "max_open_positions": 2})
    assert bad.status_code == 400
    assert client.put("/api/bot/config/risk", json={"max_leverage": 5, "max_daily_loss_percent": 3,
                                                    "max_open_positions": 2}).status_code == 401
