import json
import secrets
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os

import webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AuthenticatorAttachment,
)

from config import config
from database import init_db, get_db, Trade, AuditLog
from bot_engine import bot
from exchange import exchange
from auth import (
    create_session_token,
    require_session,
    get_all_credentials,
    get_credential_by_id,
    save_credential,
    update_sign_count,
)

init_db()

app = FastAPI(title='SuperBot Trading API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True,
                   allow_methods=['*'], allow_headers=['*'])

# Stato temporaneo delle challenge WebAuthn in corso (registrazione o login),
# in memoria di processo: vive solo per la manciata di secondi tra la
# richiesta delle "options" e la verifica della risposta del dispositivo.
_pending_challenges: dict = {}

WEBAUTHN_USER_ID = b"superbot-owner"


class LoginRequest(BaseModel):
    password: str

class WebAuthnRegisterVerifyRequest(BaseModel):
    state_id: str
    credential: dict
    device_label: Optional[str] = None

class WebAuthnLoginVerifyRequest(BaseModel):
    state_id: str
    credential: dict


# ── Autenticazione ───────────────────────────────────────────────────────────

@app.post('/api/auth/login')
async def login(req: LoginRequest):
    """Login con password. Restituisce un token di sessione da usare come
    header `Authorization: Bearer <token>` su tutte le altre chiamate."""
    if req.password != config.DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail='Password errata')
    return {'success': True, 'token': create_session_token()}


@app.get('/api/auth/webauthn/status')
async def webauthn_status(db: Session = Depends(get_db)):
    """Dice al frontend se esiste già almeno una credenziale biometrica
    registrata, per decidere se mostrare il pulsante 'Sblocca con impronta'
    nella schermata di login (prima ancora di autenticarsi)."""
    has_credentials = len(get_all_credentials(db)) > 0
    return {'available': has_credentials, 'has_credentials': has_credentials, 'rp_id': config.WEBAUTHN_RP_ID}


@app.post('/api/auth/webauthn/register/options')
async def webauthn_register_options(
    session=Depends(require_session), db: Session = Depends(get_db)
):
    """Step 1 della registrazione di una nuova credenziale biometrica.
    Richiede una sessione già valida (quindi va fatta una volta, subito
    dopo un login con password)."""
    existing = get_all_credentials(db)
    options = webauthn.generate_registration_options(
        rp_id=config.WEBAUTHN_RP_ID,
        rp_name=config.WEBAUTHN_RP_NAME,
        user_id=WEBAUTHN_USER_ID,
        user_name='superbot',
        user_display_name='SuperBot',
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    state_id = secrets.token_urlsafe(16)
    _pending_challenges[state_id] = options.challenge
    return {'state_id': state_id, 'options': json.loads(webauthn.options_to_json(options))}


@app.post('/api/auth/webauthn/register/verify')
async def webauthn_register_verify(
    body: WebAuthnRegisterVerifyRequest,
    session=Depends(require_session),
    db: Session = Depends(get_db),
):
    """Step 2: verifica la risposta del dispositivo e salva la credenziale."""
    challenge = _pending_challenges.pop(body.state_id, None)
    if not challenge:
        raise HTTPException(status_code=400, detail='Richiesta scaduta, riprova')
    try:
        verification = webauthn.verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=config.WEBAUTHN_RP_ID,
            expected_origin=config.WEBAUTHN_ORIGIN,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Verifica fallita: {e}')

    save_credential(
        db,
        credential_id=bytes_to_base64url(verification.credential_id),
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_label=body.device_label,
    )
    return {'success': True}


@app.post('/api/auth/webauthn/login/options')
async def webauthn_login_options(db: Session = Depends(get_db)):
    """Step 1 del login biometrico: NON richiede una sessione (è proprio
    il modo per ottenerne una nuova senza reinserire la password)."""
    existing = get_all_credentials(db)
    if not existing:
        raise HTTPException(status_code=400, detail='Nessuna impronta registrata su questo bot')
    options = webauthn.generate_authentication_options(
        rp_id=config.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in existing
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    state_id = secrets.token_urlsafe(16)
    _pending_challenges[state_id] = options.challenge
    return {'state_id': state_id, 'options': json.loads(webauthn.options_to_json(options))}


@app.post('/api/auth/webauthn/login/verify')
async def webauthn_login_verify(
    body: WebAuthnLoginVerifyRequest, db: Session = Depends(get_db)
):
    """Step 2: verifica l'impronta e, se corretta, rilascia un token di
    sessione -- stesso risultato del login con password."""
    challenge = _pending_challenges.pop(body.state_id, None)
    if not challenge:
        raise HTTPException(status_code=400, detail='Richiesta scaduta, riprova')

    raw_id = body.credential.get('rawId') or body.credential.get('id')
    credential_id = raw_id if isinstance(raw_id, str) else bytes_to_base64url(raw_id)
    stored = get_credential_by_id(db, credential_id)
    if not stored:
        raise HTTPException(status_code=400, detail='Credenziale non riconosciuta')

    try:
        verification = webauthn.verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=config.WEBAUTHN_RP_ID,
            expected_origin=config.WEBAUTHN_ORIGIN,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Verifica fallita: {e}')

    update_sign_count(db, credential_id, verification.new_sign_count)
    return {'success': True, 'token': create_session_token()}


# ── Endpoint bot/trading (tutti protetti da sessione) ───────────────────────

@app.post('/api/bot/start')
async def start_bot(session=Depends(require_session)):
    await bot.start(); return {'success': True, 'message': 'Bot avviato'}

@app.post('/api/bot/stop')
async def stop_bot(session=Depends(require_session)):
    await bot.stop(); return {'success': True, 'message': 'Bot fermato'}

@app.get('/api/bot/status')
async def get_status(session=Depends(require_session)):
    return bot.get_status()

@app.get('/api/bot/config')
async def get_bot_config(session=Depends(require_session)):
    """Parametri di rischio correnti, per la pagina Impostazioni."""
    return {
        'trading_mode': config.TRADING_MODE,
        'initial_capital': config.INITIAL_CAPITAL,
        'max_leverage': config.MAX_LEVERAGE,
        'max_daily_loss_percent': config.MAX_DAILY_LOSS_PERCENT,
        'max_open_positions': config.MAX_OPEN_POSITIONS,
        'trading_pairs': config.TRADING_PAIRS,
    }

@app.get('/api/market/prices')
async def get_prices(session=Depends(require_session)):
    prices = {}
    for symbol in config.TRADING_PAIRS:
        try: prices[symbol] = await exchange.get_ticker(symbol)
        except Exception as e: prices[symbol] = {'error': str(e)}
    return prices

@app.get('/api/market/indicators/{symbol}')
async def get_indicators(symbol: str, session=Depends(require_session)):
    try:
        ohlcv = await exchange.get_ohlcv(symbol, '1m', 100)
        from indicators import TechnicalIndicators
        return TechnicalIndicators(ohlcv).compute_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/trades')
async def get_trades(session=Depends(require_session), db: Session = Depends(get_db), limit: int = 50, offset: int = 0):
    trades = db.query(Trade).order_by(Trade.open_time.desc()).offset(offset).limit(limit).all()
    return [{'id': t.id, 'order_id': t.order_id, 'symbol': t.symbol, 'side': t.side,
             'trade_type': t.trade_type, 'entry_price': t.entry_price,
             'exit_price': t.exit_price, 'quantity': t.quantity, 'leverage': t.leverage,
             'pnl': t.pnl, 'pnl_percent': t.pnl_percent, 'status': t.status,
             'open_time': t.open_time.isoformat() if t.open_time else None,
             'close_time': t.close_time.isoformat() if t.close_time else None,
             'close_reason': t.close_reason} for t in trades]

@app.get('/api/trades/open')
async def get_open_trades(session=Depends(require_session)):
    return list(bot.open_trades.values())

@app.get('/api/performance')
async def get_performance(session=Depends(require_session), db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.status == 'closed').all()
    total = len(trades)
    if total == 0: return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0, 'equity_curve': []}
    winners = [t for t in trades if t.pnl and t.pnl > 0]
    total_pnl = sum(t.pnl for t in trades if t.pnl)
    ordered = sorted(trades, key=lambda t: t.close_time or t.open_time)
    running = 0.0
    equity_curve = []
    for t in ordered:
        running += (t.pnl or 0)
        equity_curve.append({
            'time': (t.close_time or t.open_time).isoformat(),
            'equity': round(running, 2),
        })
    by_symbol = {}
    for t in trades:
        by_symbol.setdefault(t.symbol, 0.0)
        by_symbol[t.symbol] += (t.pnl or 0)
    return {'total_trades': total, 'winning_trades': len(winners),
            'losing_trades': total - len(winners),
            'win_rate': round(len(winners) / total * 100, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(total_pnl / total, 2),
            'equity_curve': equity_curve,
            'pnl_by_symbol': {k: round(v, 2) for k, v in by_symbol.items()}}

@app.get('/api/logs')
async def get_logs(session=Depends(require_session), db: Session = Depends(get_db), limit: int = 100):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [{'id': l.id, 'timestamp': l.timestamp.isoformat(),
             'event_type': l.event_type, 'symbol': l.symbol, 'message': l.message} for l in logs]

@app.get('/api/health')
async def health():
    return {'status': 'ok', 'mode': config.TRADING_MODE, 'version': '1.0.0'}

# Serve frontend React se la cartella build esiste
frontend_build = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'build')
if os.path.exists(frontend_build):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_build, 'static')), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_build, 'index.html'))

    @app.get("/{path:path}")
    async def serve_frontend_routes(path: str):
        file_path = os.path.join(frontend_build, path)
        if os.path.exists(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_build, 'index.html'))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.server:app', host='0.0.0.0', port=config.BACKEND_PORT, reload=True)
