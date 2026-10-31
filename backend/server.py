import json
import secrets
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request
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
from risk_settings import RISK_BOUNDS, load_overrides, save_overrides, current_mode
from risk_profiles import PRESETS, PROFILE_LABELS, RISK_MODES
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
    delete_credential_by_id,
    update_sign_count,
)

init_db()

app = FastAPI(title='SuperBot Trading API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True,
                   allow_methods=['*'], allow_headers=['*'])

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
    risk_mode: Optional[str] = None

class WebAuthnRegisterVerifyRequest(BaseModel):
    state_id: str
    credential: dict
    device_label: Optional[str] = None

class WebAuthnLoginVerifyRequest(BaseModel):
    state_id: str
    credential: dict


# ── Autenticazione ───────────────────────────────────────────────────────────────────────

def _login_response(state: str) -> dict:
    if state == 'ok':
        return {'success': True, 'token': create_session_token('full'), 'must_change': None}
    return {'success': True, 'token': create_session_token('change_only'), 'must_change': state}


@app.post('/api/auth/login')
async def login(req: LoginRequest):
    check_login_allowed()
    if not password_login_available():
        raise HTTPException(status_code=503, detail='Password iniziale non configurata sul server')
    state = authenticate_password(req.password)
    if state is None:
        register_failure()
        await asyncio.sleep(0.8)
        bot._log('auth_failed', message='Tentativo di login con password errata')
        raise HTTPException(status_code=401, detail='Password errata')
    register_success()
    return _login_response(state)


@app.post('/api/auth/change-password')
async def change_password_endpoint(body: ChangePasswordRequest, session=Depends(require_change_session)):
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
    try:
        recover_password(body.code, body.new_password)
    except HTTPException as e:
        if e.status_code == 401:
            await asyncio.sleep(0.8)
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
    return password_status()


@app.get('/api/auth/webauthn/status')
async def webauthn_status(db: Session = Depends(get_db)):
    has_credentials = len(get_all_credentials(db)) > 0
    return {'available': has_credentials, 'has_credentials': has_credentials, 'rp_id': config.WEBAUTHN_RP_ID}


@app.post('/api/auth/webauthn/register/options')
async def webauthn_register_options(
    session=Depends(require_session), db: Session = Depends(get_db)
):
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
            resident_key=ResidentKeyRequirement.DISCOURAGED,
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
        device_label=(body.device_label or '')[:60] or None,
    )
    return {'success': True}


@app.get('/api/auth/webauthn/credentials')
async def webauthn_list_credentials(session=Depends(require_session), db: Session = Depends(get_db)):
    return {'credentials': [
        {
            'id': c.id,
            'device_label': c.device_label or 'Dispositivo',
            'created_at': (c.created_at.isoformat() + 'Z') if c.created_at else None,
        }
        for c in get_all_credentials(db)
    ]}


@app.delete('/api/auth/webauthn/credentials/{cred_id}')
async def webauthn_delete_credential(cred_id: int, session=Depends(require_session), db: Session = Depends(get_db)):
    removed = delete_credential_by_id(db, cred_id)
    if removed is None:
        raise HTTPException(status_code=404, detail='Impronta non trovata')
    bot._log('auth_biometric_removed', message=f"Impronta rimossa: {removed['device_label'] or 'dispositivo'}")
    return {'success': True}


@app.post('/api/auth/webauthn/login/options')
async def webauthn_login_options(db: Session = Depends(get_db)):
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


# ── Endpoint bot/trading (tutti protetti da sessione) ────────────────────────

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
    return {
        'trading_mode': config.TRADING_MODE,
        'initial_capital': config.INITIAL_CAPITAL,
        'max_leverage': config.MAX_LEVERAGE,
        'max_daily_loss_percent': config.MAX_DAILY_LOSS_PERCENT,
        'max_open_positions': config.MAX_OPEN_POSITIONS,
        'trading_pairs': config.TRADING_PAIRS,
        'risk_bounds': {k: {'min': v['min'], 'max': v['max']} for k, v in RISK_BOUNDS.items()},
        'risk_mode': current_mode(),
        'effective_risk_mode': current_mode() if config.IS_PAPER else 'conservative',
        'risk_modes': list(RISK_MODES),
        'profiles': {
            name: {
                'label': PROFILE_LABELS[name], 'max_leverage': p.max_lev, 'min_leverage': p.min_lev,
                'exposure_cap_percent': p.cap_ref_pct, 'stop_multiplier': p.sl_scale,
                'min_signal_strength': p.min_strength, 'margin_exponent': p.margin_exp,
            } for name, p in PRESETS.items()
        },
        'paper_costs': {'fee_bps': config.PAPER_FEE_BPS, 'slippage_bps': config.PAPER_SLIPPAGE_BPS},
    }

@app.put('/api/bot/config/risk')
async def update_risk_config(body: RiskConfigUpdate, session=Depends(require_session)):
    data = body.dict()
    mode = data.pop('risk_mode', None)
    try:
        applied = save_overrides(data, risk_mode=mode)
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
             'close_reason': t.close_reason,
             'profile': t.profile, 'profile_label': PROFILE_LABELS.get(t.profile or 'legacy'),
             'margin': t.margin, 'gross_pnl': t.gross_pnl, 'fees': t.fees} for t in trades]

@app.get('/api/trades/open')
async def get_open_trades(session=Depends(require_session)):
    trades = []
    for t in bot.open_trades.values():
        trades.append({**t, 'profile_label': PROFILE_LABELS.get(t.get('profile') or 'legacy')})
    return trades

@app.get('/api/performance')
async def get_performance(session=Depends(require_session), db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.status == 'closed').all()
    total = len(trades)
    if total == 0: return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0, 'equity_curve': [],
                           'total_fees': 0, 'gross_pnl': 0, 'by_profile': {}}
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
    equity_by_profile = {}
    running_by_profile = {}
    for t in ordered:
        key = t.profile or 'legacy'
        running_by_profile[key] = running_by_profile.get(key, 0.0) + (t.pnl or 0)
        equity_by_profile.setdefault(key, []).append({
            'time': (t.close_time or t.open_time).isoformat(),
            'equity': round(running_by_profile[key], 2),
        })
    by_symbol = {}
    for t in trades:
        by_symbol.setdefault(t.symbol, 0.0)
        by_symbol[t.symbol] += (t.pnl or 0)
    gross_profit = sum(t.pnl for t in trades if t.pnl and t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl and t.pnl < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    by_profile = {}
    for t in trades:
        key = t.profile or 'legacy'
        d = by_profile.setdefault(key, {'label': PROFILE_LABELS.get(key, key), 'trades': 0, 'wins': 0,
                                        'net_pnl': 0.0, 'gross_pnl': 0.0, 'fees': 0.0, 'liquidations': 0})
        d['trades'] += 1
        d['wins'] += 1 if (t.pnl or 0) > 0 else 0
        d['net_pnl'] += t.pnl or 0
        d['gross_pnl'] += t.gross_pnl if t.gross_pnl is not None else (t.pnl or 0)
        d['fees'] += t.fees or 0
        d['liquidations'] += 1 if t.close_reason == 'liq' else 0
    for d in by_profile.values():
        d['win_rate'] = round(d['wins'] / d['trades'] * 100, 1) if d['trades'] else 0
        for k in ('net_pnl', 'gross_pnl', 'fees'):
            d[k] = round(d[k], 2)
    return {'total_trades': total, 'winning_trades': len(winners),
            'total_fees': round(sum(t.fees or 0 for t in trades), 2),
            'gross_pnl': round(sum(t.gross_pnl if t.gross_pnl is not None else (t.pnl or 0) for t in trades), 2),
            'by_profile': by_profile,
            'equity_by_profile': equity_by_profile,
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
    return {
        'status': 'ok',
        'mode': config.TRADING_MODE,
        'version': '1.0.0',
        'desk_mode': os.environ.get('DESK_MODE', 'paper'),
        'build': '2026-10-15-live-needs-live-bot',
    }

from desk.brain_view import register_fastapi as register_brain_view
register_brain_view(app, require_session)
from brain_free_api import register as register_brain_free
register_brain_free(app, require_session)
from brain_scalp_api import register as register_brain_scalp
register_brain_scalp(app, require_session)
from brain_operator_api import register as register_brain_operator
register_brain_operator(app, require_session)
from classical_operator_api import register as register_classical_operator
register_classical_operator(app, require_session)

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

# ── Kill switch Telegram (comandi bidirezionali) ──────────────────────────────────────────────
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
    text = (
        f"📊 <b>Stato bot</b>\n"
        f"In esecuzione: {'si' if s['is_running'] else 'no'}\n"
        f"Modalità: {s['mode']}\n"
        f"Capitale: ${s['capital']:,.2f}\n"
        f"P&L oggi: ${s['daily_pnl']:+.2f}\n"
        f"Posizioni aperte: {s['open_positions']}\n"
        f"Trade totali: {s['total_trades']} | Win rate: {s['win_rate']}%"
    )
    if len(s.get('portfolios', [])) > 1:
        for p in s['portfolios']:
            text += (f"\n🎯 {p['label']}: ${p['capital']:,.2f} | oggi ${p['daily_pnl']:+.2f} | "
                     f"aperte {p['open_positions']}{' | in pausa' if p['paused'] else ''}")
    return text

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
    load_overrides()
    init_auth()
    asyncio.create_task(notifier.poll_commands())


# ── Portafogli desk (Hawk e Bull) ───────────────────────────────────────────────────────────────────────
# I bot girano nei container superbot-desk-hawk / -bull e scrivono nei loro volumi; qui si
# legge e si mandano i comandi (file-flag). Tutta la logica sta in desk_view.py / desk_api.py:
# un solo codice per i due portafogli, cosi' non possono piu' divergere.
import desk_api

_DESK_DATA      = os.environ.get("DESK_DATA_DIR",      "/opt/superbot-desk-data/hawk")
_DESK_DATA_BULL = os.environ.get("DESK_DATA_DIR_BULL",  "/opt/superbot-desk-data/bull")

app.include_router(desk_api.make_router("hawk", _DESK_DATA, require_session, exchange.get_ticker),
                   prefix="/api/desk")
app.include_router(desk_api.make_router("bull", _DESK_DATA_BULL, require_session, exchange.get_ticker),
                   prefix="/api/desk/bull")

_prices_cache: dict = {}
_prices_cache_ts: float = 0.0
_PRICES_CACHE_TTL = 30.0

V2_SYMBOLS = [
    'BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'DOGE', 'AVAX',
    'DOT', 'LINK', 'MATIC', 'UNI', 'ATOM', 'LTC', 'BCH',
    'APT', 'ARB', 'OP', 'NEAR', 'FIL', 'INJ', 'SUI', 'TIA',
    'RUNE', 'STX', 'XAU', 'XAG',
]


@app.get("/api/desk/prices")
async def desk_prices(session=Depends(require_session)):
    global _prices_cache, _prices_cache_ts
    import time as _time
    now = _time.monotonic()
    if _prices_cache and (now - _prices_cache_ts) < _PRICES_CACHE_TTL:
        return _prices_cache

    async def one(sym: str):
        for name in (sym + 'USDT', sym + '/USDT'):
            try:
                return sym, await asyncio.wait_for(exchange.get_ticker(name), 5)
            except Exception as e:
                err = str(e)
        return sym, {'error': err}

    prices = dict(await asyncio.gather(*(one(s) for s in V2_SYMBOLS)))
    for sym, t in prices.items():
        desk_api.remember_price(sym, t.get('price'))
    _prices_cache = prices
    _prices_cache_ts = now
    return prices


# ── Pagina Live: saldo reale BitGet, P&L e limite di perdita, interruttore trading ─────────────────
import live_view


def _fetch_bitget_wallet(bot: str) -> dict:
    if os.environ.get("DESK_MODE", "paper").strip().lower() != "live":
        return {"available": False, "error": "modalita' paper: nessun saldo reale da mostrare"}
    creds = live_view.wallet_credentials(os.environ, bot)
    if creds is None:
        names = live_view.wallet_key_names(bot)
        return {"available": False,
                "error": f"chiave BitGet di sola lettura di {bot.capitalize()} non configurata nell'app "
                         f"(Secret {names[0]} / _SECRET_KEY / _PASSPHRASE)"}
    api_key, secret, passphrase = creds
    try:
        import ccxt
        client = ccxt.bitget({"apiKey": api_key, "secret": secret, "password": passphrase,
                              "options": {"defaultType": "swap"}, "timeout": 8000})
        usdt = client.fetch_balance().get("USDT", {}) or {}
        return {
            "available": True,
            "total_usdt": round(float(usdt.get("total") or 0), 2),
            "available_usdt": round(float(usdt.get("free") or 0), 2),
            "used_usdt": round(float(usdt.get("used") or 0), 2),
            "error": None,
        }
    except Exception as e:
        return {"available": False, "error": str(e)[:120]}


_bitget_ro_clients: dict = {}
_bitget_ro_locks: dict = {}


def _fetch_bitget_positions(bot: str) -> dict:
    if os.environ.get("DESK_MODE", "paper").strip().lower() != "live":
        return {"available": False, "positions": [], "error": "modalita' paper: nessuna posizione reale da mostrare"}
    creds = live_view.wallet_credentials(os.environ, bot)
    if creds is None:
        return {"available": False, "positions": [],
                "error": f"chiave BitGet di sola lettura di {bot.capitalize()} non configurata nell'app"}
    import threading
    lock = _bitget_ro_locks.setdefault(bot, threading.Lock())
    try:
        with lock:
            client = _bitget_ro_clients.get(bot)
            if client is None:
                import ccxt
                api_key, secret, passphrase = creds
                client = ccxt.bitget({"apiKey": api_key, "secret": secret, "password": passphrase,
                                      "options": {"defaultType": "swap"}, "timeout": 8000})
                _bitget_ro_clients[bot] = client
            raw = client.fetch_positions()
        return {"available": True, "positions": live_view.normalize_real_positions(raw), "error": None}
    except Exception as e:
        return {"available": False, "positions": [], "error": f"posizioni BitGet non leggibili: {str(e)[:100]}"}


async def _fetch_wallets() -> dict:
    bots = live_view.WALLET_BOTS
    results = await asyncio.gather(*(asyncio.to_thread(_fetch_bitget_wallet, b) for b in bots))
    return live_view.combine_wallets(dict(zip(bots, results)))


@app.get("/api/desk/live/wallet")
async def live_wallet(session=Depends(require_session)):
    return await _fetch_wallets()


@app.get("/api/desk/live/overview")
async def live_overview(session=Depends(require_session)):
    import time as _time
    bots = live_view.WALLET_BOTS
    wallet, hawk_real, bull_real = await asyncio.gather(
        _fetch_wallets(),
        *(asyncio.to_thread(_fetch_bitget_positions, b) for b in bots))
    desk_mode = os.environ.get("DESK_MODE", "paper").strip().lower()
    loss_pct = os.environ.get("DESK_DAILY_LOSS_PCT", "25")
    return {
        "mode": desk_mode,
        "timestamp_ms": int(_time.time() * 1000),
        "wallet": wallet,
        "hawk": live_view.build_portfolio(_DESK_DATA, os.environ.get("DESK_HAWK_CAPITAL"), loss_pct, desk_mode,
                                          real_positions=hawk_real),
        "bull": live_view.build_portfolio(_DESK_DATA_BULL, os.environ.get("DESK_BULL_CAPITAL"), loss_pct, desk_mode,
                                          real_positions=bull_real),
    }


def _trading_switch(portfolio: str, data_dir: str, enabled: bool) -> dict:
    live_view.write_trading_enabled(data_dir, enabled)
    return {"ok": True, "portfolio": portfolio, "trading_enabled": enabled}


@app.post("/api/desk/hawk/trading/enable")
async def hawk_trading_enable(session=Depends(require_session)):
    return _trading_switch("hawk", _DESK_DATA, True)


@app.post("/api/desk/hawk/trading/disable")
async def hawk_trading_disable(session=Depends(require_session)):
    return _trading_switch("hawk", _DESK_DATA, False)


@app.post("/api/desk/bull/trading/enable")
async def bull_trading_enable(session=Depends(require_session)):
    return _trading_switch("bull", _DESK_DATA_BULL, True)


@app.post("/api/desk/bull/trading/disable")
async def bull_trading_disable(session=Depends(require_session)):
    return _trading_switch("bull", _DESK_DATA_BULL, False)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.server:app', host='0.0.0.0', port=config.BACKEND_PORT, reload=True)
