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

import asyncio

from config import config
from database import init_db, get_db, Trade, AuditLog
from bot_engine import bot
from exchange import exchange
from telegram_notifier import notifier
from risk_settings import RISK_BOUNDS, load_overrides, save_overrides
from auth import (
    create_session_token,
    require_session,
    require_change_session,
    init_auth,
    password_login_available,
    authenticate_password,
    session_state_after_biometric,
    change_password,
    reset_password,
    request_recovery_code,
    cancel_recovery_code,
    recover_password,
    RECOVERY_CODE_TTL_S,
    password_status,
    check_login_allowed,
    register_failure,
    register_success,
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

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ForgotConfirmRequest(BaseModel):
    code: str
    new_password: str

class RiskConfigUpdate(BaseModel):
    max_leverage: float
    max_daily_loss_percent: float
    max_open_positions: float

class WebAuthnRegisterVerifyRequest(BaseModel):
    state_id: str
    credential: dict
    device_label: Optional[str] = None

class WebAuthnLoginVerifyRequest(BaseModel):
    state_id: str
    credential: dict


# ── Autenticazione ───────────────────────────────────────────────────────────

def _login_response(state: str) -> dict:
    """state: 'ok' | 'first_login' | 'expired'. Se la password va cambiata
    si rilascia solo il token limitato, che apre solo /api/auth/change-password."""
    if state == 'ok':
        return {'success': True, 'token': create_session_token('full'), 'must_change': None}
    return {'success': True, 'token': create_session_token('change_only'), 'must_change': state}


@app.post('/api/auth/login')
async def login(req: LoginRequest):
    """Login con password. Restituisce un token di sessione da usare come
    header `Authorization: Bearer <token>` su tutte le altre chiamate. Al
    primo accesso (password iniziale) o a password scaduta restituisce un
    token limitato e `must_change`: il frontend deve far cambiare la password."""
    check_login_allowed()
    if not password_login_available():
        raise HTTPException(status_code=503, detail='Password iniziale non configurata sul server')
    state = authenticate_password(req.password)
    if state is None:
        register_failure()
        await asyncio.sleep(0.8)  # rallenta chi prova a indovinare
        bot._log('auth_failed', message='Tentativo di login con password errata')
        raise HTTPException(status_code=401, detail='Password errata')
    register_success()
    return _login_response(state)


@app.post('/api/auth/change-password')
async def change_password_endpoint(body: ChangePasswordRequest, session=Depends(require_change_session)):
    """Cambia la password (serve quella attuale, o quella iniziale al primo
    accesso). Salva solo l'hash, invalida tutte le sessioni precedenti e
    restituisce un nuovo token completo."""
    check_login_allowed()
    try:
        change_password(body.old_password, body.new_password)
    except HTTPException as e:
        if e.status_code == 401:
            register_failure()
            await asyncio.sleep(0.8)
        raise
    register_success()
    bot._log('auth_change', message='Password dashboard cambiata')
    return {'success': True, 'token': create_session_token('full'), 'password_status': password_status()}


@app.post('/api/auth/forgot')
async def forgot_password():
    """Password dimenticata, passo 1: manda un codice monouso (8 cifre,
    valido 10 minuti) sul Telegram del proprietario. Non serve essere
    autenticati, ma il codice arriva solo su Telegram, mai nella risposta."""
    if not notifier.enabled:
        raise HTTPException(status_code=503, detail='Il recupero password via Telegram non è configurato sul server')
    code = request_recovery_code()
    delivered = await notifier.send(
        "🔑 <b>Recupero password SuperBot</b>\n"
        f"Codice: <b>{code}</b>\n"
        "Valido 10 minuti, si usa una volta sola. "
        "Se non l'hai chiesto tu ignora questo messaggio: senza il codice nessuno può cambiare la password."
    )
    if not delivered:
        cancel_recovery_code()
        raise HTTPException(status_code=502, detail='Non sono riuscito a mandare il codice su Telegram, riprova tra poco')
    bot._log('auth_recovery_requested', message='Codice di recupero password inviato su Telegram')
    return {'success': True, 'expires_in': RECOVERY_CODE_TTL_S}


@app.post('/api/auth/forgot/confirm')
async def forgot_password_confirm(body: ForgotConfirmRequest):
    """Password dimenticata, passo 2: con il codice ricevuto su Telegram si
    sceglie la nuova password. Chiude tutte le sessioni precedenti e
    restituisce subito una sessione completa."""
    try:
        recover_password(body.code, body.new_password)
    except HTTPException as e:
        if e.status_code == 401:
            await asyncio.sleep(0.8)  # rallenta chi prova a indovinare il codice
        raise
    register_success()
    bot._log('auth_recovery_done', message='Password dashboard recuperata con codice Telegram')
    await notifier.send(
        "🔐 La password della dashboard è stata cambiata con il recupero password.\n"
        "Se non sei stato tu, scrivi /resetpassword per tornare alla password iniziale."
    )
    return {'success': True, 'token': create_session_token('full'), 'password_status': password_status()}


@app.get('/api/auth/password-status')
async def password_status_endpoint(session=Depends(require_session)):
    """Giorni rimasti alla scadenza della password, per il banner di avviso."""
    return password_status()


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
    return _login_response(session_state_after_biometric())


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
        'risk_bounds': {k: {'min': v['min'], 'max': v['max']} for k, v in RISK_BOUNDS.items()},
    }

@app.put('/api/bot/config/risk')
async def update_risk_config(body: RiskConfigUpdate, session=Depends(require_session)):
    """Salva i parametri di rischio modificati dall'app. Validati contro
    RISK_BOUNDS, persistiti in DB e applicati subito al bot (nessun riavvio)."""
    try:
        applied = save_overrides(body.dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    bot._log('config_change', message=f'Parametri di rischio aggiornati dall\'app: {applied}')
    return {'success': True, 'applied': applied}

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
    gross_profit = sum(t.pnl for t in trades if t.pnl and t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl and t.pnl < 0))
    # Profit factor: utile lordo / perdita lorda. Senza perdite, non è infinito
    # per convenzione del settore ma "N/A" se non c'è nemmeno un trade perdente
    # da confrontare (coerente con "non inventare metriche").
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    return {'total_trades': total, 'winning_trades': len(winners),
            'losing_trades': total - len(winners),
            'win_rate': round(len(winners) / total * 100, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(total_pnl / total, 2),
            'profit_factor': profit_factor,
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

# ── Kill switch Telegram (comandi bidirezionali) ────────────────────────────
# Il polling gira indipendentemente da bot.is_running, cosi' /resume
# funziona anche a bot fermo. Registrato qui (non in telegram_notifier.py)
# per evitare un import circolare notifier<->bot_engine.

async def _cmd_halt() -> str:
    await bot.stop()
    return "⏹️ Bot fermato da comando Telegram (/halt). Usa /resume per far ripartire."

async def _cmd_resume() -> str:
    await bot.start()
    return "✅ Bot riavviato da comando Telegram (/resume)."

async def _cmd_status() -> str:
    s = bot.get_status()
    return (
        f"📊 <b>Stato bot</b>\n"
        f"In esecuzione: {'si' if s['is_running'] else 'no'}\n"
        f"Modalità: {s['mode']}\n"
        f"Capitale: ${s['capital']:,.2f}\n"
        f"P&L oggi: ${s['daily_pnl']:+.2f}\n"
        f"Posizioni aperte: {s['open_positions']}\n"
        f"Trade totali: {s['total_trades']} | Win rate: {s['win_rate']}%"
    )

async def _cmd_closeall() -> str:
    closed = await bot.close_all_positions(reason='manual_telegram')
    if not closed:
        return "ℹ️ Nessuna posizione aperta da chiudere."
    return f"🔒 Chiuse {len(closed)} posizioni: {', '.join(closed)}"

notifier.register_command('halt', _cmd_halt)
notifier.register_command('stop', _cmd_halt)
notifier.register_command('resume', _cmd_resume)
notifier.register_command('start', _cmd_resume)
notifier.register_command('status', _cmd_status)
notifier.register_command('closeall', _cmd_closeall)


async def _cmd_resetpassword() -> str:
    reset_password()
    bot._log('auth_reset', message='Password dashboard resettata da comando Telegram')
    return ("🔑 Password della dashboard resettata. Tutte le sessioni sono state chiuse.\n"
            "Accedi con la password iniziale (GitHub Secret DASHBOARD_PASSWORD) "
            "e scegline una nuova.")

notifier.register_command('resetpassword', _cmd_resetpassword)


@app.on_event('startup')
async def _on_startup():
    # Riapplica gli override di rischio salvati dall'app (sopravvivono a
    # riavvii e redeploy perche' stanno nel DB, non in .env).
    load_overrides()
    init_auth()
    # Il listener dei comandi Telegram parte sempre, a prescindere dal bot --
    # è l'unico modo per cui /resume possa funzionare se il bot è fermo o il
    # processo è appena stato riavviato.
    asyncio.create_task(notifier.poll_commands())


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.server:app', host='0.0.0.0', port=config.BACKEND_PORT, reload=True)
