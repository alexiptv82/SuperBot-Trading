"""Autenticazione per la dashboard SuperBot.

Due vie per ottenere una sessione:
  1. Password -- al primo accesso vale la password iniziale (GitHub Secret
     DASHBOARD_PASSWORD, arriva in config.DASHBOARD_PASSWORD) e l'app obbliga
     subito a sceglierne una nuova. Quella nuova vive nel DB come hash scrypt
     (mai in chiaro, mai in .env), quindi sopravvive a riavvii e redeploy.
     Scade dopo PASSWORD_MAX_AGE_DAYS giorni: al login successivo bisogna
     cambiarla (serve la vecchia).
  2. WebAuthn (impronta digitale / Face ID / PIN del dispositivo) -- richiede
     che il dispositivo abbia già una credenziale registrata (fatta una volta
     sola, da dentro una sessione già autenticata) e un contesto sicuro
     (HTTPS + dominio reale).

Entrambe le vie producono un JWT, da passare come header
`Authorization: Bearer <token>`. Due tipi ("scope"):
  - "full": accesso completo a tutti gli endpoint /api/*.
  - "change_only": rilasciato quando la password va cambiata (primo accesso o
    scaduta); vale 15 minuti e apre SOLO /api/auth/change-password.

La chiave di firma dei token NON sta nel codice né in .env: viene generata a
caso al primo avvio e salvata nel DB. Ogni cambio password incrementa
token_version e invalida tutte le sessioni precedenti.
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import config
from database import Base, SessionLocal

PASSWORD_MAX_AGE_DAYS = 60
PASSWORD_WARN_DAYS = 7
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
CHANGE_TOKEN_MINUTES = 15
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


class WebAuthnCredential(Base):
    """Una credenziale biometrica registrata su un dispositivo.

    Più righe sono supportate (es. impronta sul telefono + su un altro
    dispositivo), dato che è un sistema a singolo utente senza un vero
    concetto di "account" separato.
    """
    __tablename__ = "webauthn_credentials"
    id = Column(Integer, primary_key=True, index=True)
    credential_id = Column(String, unique=True, index=True)
    public_key = Column(LargeBinary)
    sign_count = Column(Integer, default=0)
    device_label = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuthSettings(Base):
    """Stato di autenticazione, riga unica (id=1)."""
    __tablename__ = "auth_settings"
    id = Column(Integer, primary_key=True)
    password_hash = Column(String, nullable=True)        # NULL = ancora la password iniziale
    password_changed_at = Column(DateTime, nullable=True)  # UTC naive
    token_version = Column(Integer, nullable=False, default=0)
    jwt_secret = Column(String, nullable=True)


# ── Hash della password ─────────────────────────────────────────────────────

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password_hash(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64),
                            n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def _safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ── Stato nel DB ────────────────────────────────────────────────────────────

def _load_settings() -> dict:
    """Legge (creando se manca) la riga di stato. Genera la chiave JWT al
    primo uso."""
    for _ in range(2):
        db = SessionLocal()
        try:
            row = db.query(AuthSettings).filter(AuthSettings.id == 1).first()
            if row is None:
                row = AuthSettings(id=1, token_version=0)
                db.add(row)
            if not row.jwt_secret:
                row.jwt_secret = secrets.token_urlsafe(48)
            db.commit()
            return {
                "password_hash": row.password_hash,
                "changed_at": row.password_changed_at,
                "token_version": row.token_version or 0,
                "jwt_secret": row.jwt_secret,
            }
        except IntegrityError:
            db.rollback()  # due richieste hanno creato la riga insieme: rileggi
        finally:
            db.close()
    raise RuntimeError("auth_settings non leggibile")


def init_auth() -> None:
    """All'avvio: assicura che riga e chiave JWT esistano."""
    _load_settings()


def _update_settings(**fields) -> None:
    db = SessionLocal()
    try:
        row = db.query(AuthSettings).filter(AuthSettings.id == 1).first()
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
    finally:
        db.close()


def _expires_at(changed_at: datetime) -> datetime:
    return changed_at + timedelta(days=PASSWORD_MAX_AGE_DAYS)


def _is_expired(s: dict) -> bool:
    return bool(s["changed_at"]) and datetime.utcnow() >= _expires_at(s["changed_at"])


# ── Login con password ──────────────────────────────────────────────────────

def password_login_available() -> bool:
    s = _load_settings()
    return bool(s["password_hash"]) or bool(config.DASHBOARD_PASSWORD)


def authenticate_password(password: str):
    """None se errata; altrimenti 'ok', 'first_login' (password iniziale: va
    cambiata) o 'expired' (scaduta: va cambiata)."""
    s = _load_settings()
    if s["password_hash"]:
        if not verify_password_hash(password, s["password_hash"]):
            return None
        return "expired" if _is_expired(s) else "ok"
    boot = config.DASHBOARD_PASSWORD
    if not boot or not _safe_equal(password, boot):
        return None
    return "first_login"


def session_state_after_biometric() -> str:
    """Stato da applicare a un login biometrico riuscito: se la password va
    ancora cambiata, anche con l'impronta si passa dal cambio."""
    s = _load_settings()
    if not s["password_hash"]:
        return "first_login"
    return "expired" if _is_expired(s) else "ok"


def validate_new_password(new: str, old: str) -> None:
    if len(new) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"La nuova password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri")
    if len(new) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"La nuova password può avere al massimo {MAX_PASSWORD_LENGTH} caratteri")
    if _safe_equal(new, old):
        raise HTTPException(status_code=400, detail="La nuova password deve essere diversa dall'attuale")
    boot = config.DASHBOARD_PASSWORD
    if (boot and _safe_equal(new, boot)) or "superbot2024" in new.lower():
        raise HTTPException(status_code=400, detail="Scegli una password diversa da quella iniziale")
    if len(set(new)) < 4:
        raise HTTPException(status_code=400, detail="Password troppo semplice")


def change_password(old_password: str, new_password: str) -> None:
    """Verifica la password attuale (o iniziale), controlla la nuova, salva
    l'hash e invalida tutte le sessioni esistenti."""
    s = _load_settings()
    if s["password_hash"]:
        ok = verify_password_hash(old_password, s["password_hash"])
    else:
        boot = config.DASHBOARD_PASSWORD
        ok = bool(boot) and _safe_equal(old_password, boot)
    if not ok:
        raise HTTPException(status_code=401, detail="Password attuale errata")
    validate_new_password(new_password, old_password)
    _update_settings(
        password_hash=hash_password(new_password),
        password_changed_at=datetime.utcnow(),
        token_version=s["token_version"] + 1,
    )


def reset_password() -> None:
    """Torna alla password iniziale (da GitHub Secret) e invalida le
    sessioni. Usato dal comando Telegram /resetpassword."""
    s = _load_settings()
    _update_settings(password_hash=None, password_changed_at=None,
                     token_version=s["token_version"] + 1)


# ── Password dimenticata: codice monouso su Telegram ────────────────────────
# Chi non ricorda la password chiede un codice a 8 cifre, che arriva SOLO sul
# Telegram del proprietario (stesso canale fidato del comando /resetpassword).
# Il codice vive solo in memoria di processo (un riavvio lo annulla), vale 10
# minuti, e' monouso e si annulla dopo 5 tentativi sbagliati. Le richieste di
# codice sono limitate a 3 all'ora, e finche' un codice e' valido una nuova
# richiesta rimanda lo STESSO codice (cosi' chi spamma la richiesta da fuori
# non puo' invalidare il codice che il proprietario sta usando).
RECOVERY_CODE_TTL_S = 600
RECOVERY_MAX_ATTEMPTS = 5
RECOVERY_MAX_REQUESTS = 3
_RECOVERY_WINDOW_S = 3600
_recovery_lock = threading.Lock()
_recovery = {"code": None, "expires": 0.0, "attempts": 0}
_recovery_requests: list = []


def _clear_recovery_locked() -> None:
    _recovery.update(code=None, expires=0.0, attempts=0)


def cancel_recovery_code() -> None:
    with _recovery_lock:
        _clear_recovery_locked()


def request_recovery_code() -> str:
    """Restituisce il codice da mandare su Telegram (nuovo, o quello ancora
    valido). Solleva 429 oltre 3 richieste all'ora."""
    now = time.time()
    with _recovery_lock:
        _recovery_requests[:] = [t for t in _recovery_requests if now - t < _RECOVERY_WINDOW_S]
        if len(_recovery_requests) >= RECOVERY_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Troppe richieste di codice, riprova tra un'ora")
        _recovery_requests.append(now)
        if not (_recovery["code"] and now < _recovery["expires"]):
            _recovery.update(code=f"{secrets.randbelow(10 ** 8):08d}",
                             expires=now + RECOVERY_CODE_TTL_S, attempts=0)
        return _recovery["code"]


def verify_recovery_code(code: str) -> None:
    """Controlla il codice SENZA bruciarlo (si brucia solo a password
    cambiata: se la nuova password e' rifiutata non serve chiederne un altro).
    Ogni errore conta come tentativo."""
    now = time.time()
    with _recovery_lock:
        if not _recovery["code"] or now >= _recovery["expires"]:
            _clear_recovery_locked()
            raise HTTPException(status_code=401, detail="Codice scaduto o non valido: richiedine uno nuovo")
        if not hmac.compare_digest((code or "").strip().encode(), _recovery["code"].encode()):
            _recovery["attempts"] += 1
            if _recovery["attempts"] >= RECOVERY_MAX_ATTEMPTS:
                _clear_recovery_locked()
                raise HTTPException(status_code=401, detail="Troppi errori: il codice è stato annullato, richiedine uno nuovo")
            raise HTTPException(status_code=401, detail="Codice errato")


def recover_password(code: str, new_password: str) -> None:
    """Imposta una nuova password dopo la verifica del codice Telegram.
    L'ordine conta: prima il codice (cosi' chi non lo ha non puo' nemmeno
    sondare le regole sulla password), poi la validazione, poi il salvataggio."""
    verify_recovery_code(code)
    validate_new_password(new_password, "")
    s = _load_settings()
    _update_settings(
        password_hash=hash_password(new_password),
        password_changed_at=datetime.utcnow(),
        token_version=s["token_version"] + 1,
    )
    cancel_recovery_code()


def password_status() -> dict:
    s = _load_settings()
    if not s["password_hash"] or not s["changed_at"]:
        return {"set": False, "days_left": None, "warn": False, "expires_at": None}
    expires = _expires_at(s["changed_at"])
    days_left = max(0, -(-int((expires - datetime.utcnow()).total_seconds()) // 86400))
    return {"set": True, "days_left": days_left, "warn": days_left <= PASSWORD_WARN_DAYS,
            "expires_at": expires.replace(tzinfo=timezone.utc).isoformat()}


# ── Limite ai tentativi di password ─────────────────────────────────────────
# Globale e non per IP: l'app e' raggiungibile anche direttamente sulla porta
# 8002 (non solo via nginx), quindi un IP letto da un header sarebbe
# falsificabile. Il prezzo: chi tenta a raffica puo' bloccare il login con
# password per qualche minuto -- l'impronta resta disponibile.
_FAIL_WINDOW_S = 600
_FAIL_MAX = 8
_LOCK_S = 600
_fail_lock = threading.Lock()
_fail_times: list = []
_locked_until = 0.0


def check_login_allowed() -> None:
    with _fail_lock:
        remaining = _locked_until - time.time()
    if remaining > 0:
        raise HTTPException(status_code=429, detail=f"Troppi tentativi errati, riprova tra {int(remaining // 60) + 1} minuti")


def register_failure() -> None:
    global _locked_until
    now = time.time()
    with _fail_lock:
        _fail_times[:] = [t for t in _fail_times if now - t < _FAIL_WINDOW_S]
        _fail_times.append(now)
        if len(_fail_times) >= _FAIL_MAX:
            _locked_until = now + _LOCK_S
            _fail_times.clear()


def register_success() -> None:
    with _fail_lock:
        _fail_times.clear()


# ── Sessioni (JWT) ──────────────────────────────────────────────────────────

def create_session_token(scope: str = "full") -> str:
    s = _load_settings()
    now = int(time.time())
    if scope == "change_only":
        exp = now + CHANGE_TOKEN_MINUTES * 60
    else:
        exp = now + config.JWT_EXPIRE_HOURS * 3600
        if s["changed_at"]:
            # La sessione non puo' sopravvivere alla scadenza della password.
            pwd_exp = int(_expires_at(s["changed_at"]).replace(tzinfo=timezone.utc).timestamp())
            exp = min(exp, pwd_exp)
    payload = {"iat": now, "exp": exp, "sub": "superbot-dashboard",
               "scope": scope, "ver": s["token_version"]}
    return jwt.encode(payload, s["jwt_secret"], algorithm="HS256")


def _verify_token(token: str, allowed_scopes: tuple) -> dict:
    s = _load_settings()
    try:
        payload = jwt.decode(token, s["jwt_secret"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta, accedi di nuovo")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sessione non valida")
    if payload.get("ver") != s["token_version"]:
        raise HTTPException(status_code=401, detail="Sessione non più valida, accedi di nuovo")
    if payload.get("scope") not in allowed_scopes:
        raise HTTPException(status_code=403, detail="Prima devi cambiare la password")
    return payload


def _bearer(authorization) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    return authorization.removeprefix("Bearer ").strip()


async def require_session(authorization: str = Header(default=None)) -> dict:
    """Dependency FastAPI: richiede un Bearer token valido con scope full."""
    return _verify_token(_bearer(authorization), ("full",))


async def require_change_session(authorization: str = Header(default=None)) -> dict:
    """Come require_session ma accetta anche il token limitato 'change_only'
    (usato solo da /api/auth/change-password)."""
    return _verify_token(_bearer(authorization), ("full", "change_only"))


# ── Helper per il DB delle credenziali WebAuthn ─────────────────────────────

def get_all_credentials(db: Session):
    return db.query(WebAuthnCredential).all()


def get_credential_by_id(db: Session, credential_id: str):
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.credential_id == credential_id
    ).first()


def save_credential(db: Session, credential_id: str, public_key: bytes, sign_count: int, device_label: str | None = None):
    row = WebAuthnCredential(
        credential_id=credential_id,
        public_key=public_key,
        sign_count=sign_count,
        device_label=device_label,
    )
    db.add(row)
    db.commit()
    return row


def update_sign_count(db: Session, credential_id: str, new_count: int):
    row = get_credential_by_id(db, credential_id)
    if row:
        row.sign_count = new_count
        db.commit()
