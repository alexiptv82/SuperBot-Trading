"""Autenticazione per la dashboard SuperBot.

Due vie per ottenere una sessione:
  1. Password (config.DASHBOARD_PASSWORD) -- sempre disponibile, fallback.
  2. WebAuthn (impronta digitale / Face ID / PIN del dispositivo) -- richiede
     che il dispositivo abbia già una credenziale registrata (fatta una volta
     sola, da dentro una sessione già autenticata via password) e richiede un
     contesto sicuro (HTTPS + dominio reale, non IP via HTTP).

Entrambe le vie producono lo stesso tipo di sessione: un JWT firmato con
config.SECRET_KEY, da passare come header `Authorization: Bearer <token>`
su ogni chiamata successiva. Tutti gli endpoint /api/* tranne /api/auth/*
e /api/health richiedono questo header (vedi require_session in server.py).
"""
import time
import jwt
from fastapi import Header, HTTPException
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary
from sqlalchemy.orm import Session
from datetime import datetime

from config import config
from database import Base, SessionLocal


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


# ── Sessioni (JWT) ──────────────────────────────────────────────────────────

def create_session_token() -> str:
    now = int(time.time())
    payload = {
        "iat": now,
        "exp": now + config.JWT_EXPIRE_HOURS * 3600,
        "sub": "superbot-dashboard",
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def _verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta, accedi di nuovo")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sessione non valida")


async def require_session(authorization: str = Header(default=None)) -> dict:
    """Dependency FastAPI: protegge un endpoint richiedendo un Bearer token valido."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    token = authorization.removeprefix("Bearer ").strip()
    return _verify_token(token)


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
