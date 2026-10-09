"""Test in-process (FastAPI TestClient + SQLite temporaneo) del flusso di
autenticazione: password iniziale -> cambio forzato -> hash nel DB ->
scadenza 60 giorni -> reset -> limite ai tentativi -> token invalidati.

Non richiede un server in esecuzione (a differenza di test_superbot.py).
Lanciare dalla cartella backend/:  python -m pytest tests/test_auth_flow.py
"""
import asyncio
import base64
import os
import re
import sys
import tempfile
import time
import unicodedata
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
    auth.init_auth()
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


# ── Password dimenticata (codice monouso su Telegram) ───────────────────────

@pytest.fixture()
def telegram(monkeypatch):
    """Telegram finto: raccoglie i messaggi, nessuna rete."""
    sent = []

    async def fake_send(message):
        sent.append(message)
        return True

    monkeypatch.setattr(server.notifier, "enabled", True)
    monkeypatch.setattr(server.notifier, "send", fake_send)
    auth._recovery_requests.clear()
    auth.cancel_recovery_code()
    yield sent
    auth._recovery_requests.clear()
    auth.cancel_recovery_code()


def _confirm(client, code, new):
    return client.post("/api/auth/forgot/confirm", json={"code": code, "new_password": new})


def _code_from(sent):
    return re.search(r"<b>(\d{8})</b>", sent[-1]).group(1)


def test_14_forgot_password_full_flow(client, telegram):
    # senza richiesta non esiste nessun codice valido
    assert _confirm(client, "00000000", "Recuperata-Pw-901").status_code == 401

    r = client.post("/api/auth/forgot")
    assert r.status_code == 200 and r.json()["expires_in"] == 600
    code = _code_from(telegram)
    assert "code" not in r.json() and code not in r.text  # il codice va SOLO su Telegram

    wrong = "11111111" if code != "11111111" else "22222222"
    assert _confirm(client, wrong, "Recuperata-Pw-901").status_code == 401
    # nuova password non valida: errore 400 e il codice NON si brucia
    assert _confirm(client, code, "corta").status_code == 400
    assert _confirm(client, code, "superbot2024-nuova").status_code == 400

    ok = _confirm(client, code, "Recuperata-Pw-901")
    assert ok.status_code == 200
    token = ok.json()["token"]
    assert jwt.decode(token, options={"verify_signature": False})["scope"] == "full"
    assert client.get("/api/bot/status", headers=_hdr(token)).status_code == 200
    assert ok.json()["password_status"]["days_left"] == 60

    # la nuova password vale, la vecchia no
    assert client.post("/api/auth/login", json={"password": "Recuperata-Pw-901"}).status_code == 200
    assert client.post("/api/auth/login", json={"password": "Quarta-Password-88"}).status_code == 401
    pwd_hash, _ = _raw_row()
    assert pwd_hash.startswith("scrypt$") and "Recuperata" not in pwd_hash
    # codice monouso + avviso su Telegram dell'avvenuto cambio
    assert _confirm(client, code, "Un-Altra-Pw-902").status_code == 401
    assert any("cambiata" in m for m in telegram)


def test_15_forgot_password_code_burns_after_five_wrong_attempts(client, telegram):
    assert client.post("/api/auth/forgot").status_code == 200
    code = _code_from(telegram)
    wrong = "11111111" if code != "11111111" else "22222222"
    codes = [_confirm(client, wrong, "Recuperata-Pw-903").status_code for _ in range(5)]
    assert codes == [401] * 5
    # anche il codice giusto ora e' annullato
    assert _confirm(client, code, "Recuperata-Pw-903").status_code == 401


def test_16_forgot_password_rate_limit_and_same_code_reused(client, telegram):
    assert client.post("/api/auth/forgot").status_code == 200
    first = _code_from(telegram)
    assert client.post("/api/auth/forgot").status_code == 200
    assert _code_from(telegram) == first          # chi spamma non invalida il codice in uso
    assert client.post("/api/auth/forgot").status_code == 200
    assert client.post("/api/auth/forgot").status_code == 429   # 4a richiesta nell'ora


def test_17_forgot_password_expired_unconfigured_and_undelivered(client, telegram, monkeypatch):
    assert client.post("/api/auth/forgot").status_code == 200
    code = _code_from(telegram)
    auth._recovery["expires"] = time.time() - 1
    assert _confirm(client, code, "Recuperata-Pw-904").status_code == 401   # scaduto

    auth._recovery_requests.clear()
    async def failing_send(message):
        return False
    monkeypatch.setattr(server.notifier, "send", failing_send)
    assert client.post("/api/auth/forgot").status_code == 502               # Telegram non risponde
    assert _confirm(client, code, "Recuperata-Pw-904").status_code == 401   # nessun codice rimasto in giro

    monkeypatch.setattr(server.notifier, "enabled", False)
    assert client.post("/api/auth/forgot").status_code == 503               # Telegram non configurato


# ── Copia e incolla / tastiera: spazi e accenti non devono rompere la password ──

COMPOSED = "Perché-Password-55"


def test_18_password_normalization_whitespace_and_unicode(client):
    auth._fail_times.clear()
    auth._locked_until = 0.0
    auth.reset_password()
    # la password iniziale incollata con spazi e a capo attorno vale comunque
    r = client.post("/api/auth/login", json={"password": f"  {BOOT} \n"})
    assert r.status_code == 200 and r.json()["must_change"] == "first_login"
    limited = r.json()["token"]

    decomposed = unicodedata.normalize("NFD", COMPOSED)
    assert decomposed != COMPOSED
    ok = client.post("/api/auth/change-password", headers=_hdr(limited),
                     json={"old_password": f" {BOOT} ", "new_password": f"  {COMPOSED}  "})
    assert ok.status_code == 200
    # una password con spazi finali salvata cosi' non resta "con gli spazi" nel DB
    for variant in (COMPOSED, f"{COMPOSED} ", f" {COMPOSED}", decomposed, f"\u00a0{decomposed}\u00a0"):
        assert client.post("/api/auth/login", json={"password": variant}).status_code == 200, repr(variant)
    # un carattere diverso resta una password diversa
    assert client.post("/api/auth/login", json={"password": COMPOSED + "x"}).status_code == 401
    # le regole di validazione valgono sulla versione normalizzata
    h = _hdr(ok.json()["token"])
    short = client.post("/api/auth/change-password", headers=h,
                        json={"old_password": COMPOSED, "new_password": "   corta   "})
    assert short.status_code == 400


def test_19_biometric_credentials_list_and_remove(client):
    auth._fail_times.clear()
    auth._locked_until = 0.0
    r = client.post("/api/auth/login", json={"password": COMPOSED})
    full = r.json()["token"]
    db = SessionLocal()
    try:
        auth.save_credential(db, "cred-a", b"pk", 0, "Android · Chrome")
        auth.save_credential(db, "cred-b", b"pk", 0, "Mac · Safari")
    finally:
        db.close()
    assert client.get("/api/auth/webauthn/credentials").status_code == 401
    lst = client.get("/api/auth/webauthn/credentials", headers=_hdr(full)).json()["credentials"]
    assert [c["device_label"] for c in lst] == ["Android · Chrome", "Mac · Safari"]
    assert client.get("/api/auth/webauthn/status").json()["has_credentials"] is True

    first = lst[0]["id"]
    assert client.delete(f"/api/auth/webauthn/credentials/{first}", headers=_hdr(full)).status_code == 200
    assert client.delete(f"/api/auth/webauthn/credentials/{first}", headers=_hdr(full)).status_code == 404
    left = client.get("/api/auth/webauthn/credentials", headers=_hdr(full)).json()["credentials"]
    assert [c["device_label"] for c in left] == ["Mac · Safari"]
    assert client.delete(f"/api/auth/webauthn/credentials/{left[0]['id']}", headers=_hdr(full)).status_code == 200
    assert client.get("/api/auth/webauthn/status").json()["has_credentials"] is False


def test_20_register_options_do_not_require_a_passkey(client):
    r = client.post("/api/auth/login", json={"password": COMPOSED})
    full = r.json()["token"]
    # senza sessione non si registra niente
    assert client.post("/api/auth/webauthn/register/options").status_code == 401
    opts = client.post("/api/auth/webauthn/register/options", headers=_hdr(full))
    assert opts.status_code == 200
    sel = opts.json()["options"]["authenticatorSelection"]
    # credenziale "normale" del dispositivo, non una passkey sincronizzata: non
    # richiede Google Password Manager sul telefono
    assert sel["residentKey"] == "discouraged"
    assert not sel.get("requireResidentKey")
    assert sel["authenticatorAttachment"] == "platform"
    assert sel["userVerification"] == "required"
