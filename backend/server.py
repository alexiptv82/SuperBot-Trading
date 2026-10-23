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
import capital_view as capital_v1_view

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
    # Opzionale: i client vecchi (app in cache) non lo mandano e la
    # modalita' di rischio resta quella attuale.
    risk_mode: Optional[str] = None

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
        device_label=(body.device_label or '')[:60] or None,
    )
    return {'success': True}


@app.get('/api/auth/webauthn/credentials')
async def webauthn_list_credentials(session=Depends(require_session), db: Session = Depends(get_db)):
    """Elenco dei dispositivi con impronta registrata (per Impostazioni)."""
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
    """Rimuove l'impronta di un dispositivo (cambio telefono, impronta
    cambiata, o semplicemente non la si vuole piu')."""
    removed = delete_credential_by_id(db, cred_id)
    if removed is None:
        raise HTTPException(status_code=404, detail='Impronta non trovata')
    bot._log('auth_biometric_removed', message=f"Impronta rimossa: {removed['device_label'] or 'dispositivo'}")
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
        # Profili di rischio: la modalita' scelta, quella effettivamente in
        # uso (in reale solo 'conservative') e i parametri dei due profili.
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
    """Salva i parametri di rischio modificati dall'app. Validati contro
    RISK_BOUNDS, persistiti in DB e applicati subito al bot (nessun riavvio)."""
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
    # Curva del capitale separata per profilo (ognuno ha il suo portafoglio).
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
    # Profit factor: utile lordo / perdita lorda. Senza perdite, non è infinito
    # per convenzione del settore ma "N/A" se non c'è nemmeno un trade perdente
    # da confrontare (coerente con "non inventare metriche").
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    # Dettaglio per profilo di rischio: netto (dopo commissioni), lordo e
    # commissioni, per confrontare Conservativo e Aggressivo.
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
    # Riapplica gli override di rischio salvati dall'app (sopravvivono a
    # riavvii e redeploy perche' stanno nel DB, non in .env).
    load_overrides()
    init_auth()
    # Il listener dei comandi Telegram parte sempre, a prescindere dal bot --
    # è l'unico modo per cui /resume possa funzionare se il bot è fermo o il
    # processo è appena stato riavviato.
    asyncio.create_task(notifier.poll_commands())


# ── V2 Desk Bot endpoints ────────────────────────────────────────────────────
# Leggono dal volume persistente del container superbot-desk.
# Nessuna dipendenza con il DB V1: tutto viene dai file JSON/JSONL.
# Prefisso /api/desk/ per non collidere con gli endpoint V1.
# Hawk: DESK_DATA_DIR (default /opt/superbot-desk-data/hawk)
# Bull: DESK_DATA_DIR_BULL (default /opt/superbot-desk-data/bull)

_DESK_DATA      = os.environ.get("DESK_DATA_DIR",      "/opt/superbot-desk-data/hawk")
_DESK_DATA_BULL = os.environ.get("DESK_DATA_DIR_BULL",  "/opt/superbot-desk-data/bull")


def _read_state(data_dir: str) -> dict:
    """Legge state_v2.json dal volume desk. Ritorna dict vuoto se non esiste."""
    path = os.path.join(data_dir, "state_v2.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _desk_state() -> dict:
    return _read_state(_DESK_DATA)


def _bull_state() -> dict:
    return _read_state(_DESK_DATA_BULL)


def _read_trades_raw(data_dir: str, last_n: int = 200) -> list:
    """Legge le ultime N righe da trade_history.jsonl."""
    path = os.path.join(data_dir, "trade_history.jsonl")
    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception:
        return []
    trades = []
    for line in lines[-last_n:]:
        line = line.strip()
        if not line:
            continue
        try:
            trades.append(json.loads(line))
        except Exception:
            pass
    return trades


def _desk_trades_raw(last_n: int = 200) -> list:
    return _read_trades_raw(_DESK_DATA, last_n)


def _bull_trades_raw(last_n: int = 200) -> list:
    return _read_trades_raw(_DESK_DATA_BULL, last_n)


def _read_lessons(data_dir: str) -> str:
    """Legge lessons.md (poi errors.md come fallback) dal volume desk."""
    for fname in ("lessons.md", "errors.md"):
        path = os.path.join(data_dir, fname)
        try:
            with open(path) as f:
                return f.read()
        except Exception:
            pass
    return ""


def _desk_lessons() -> str:
    return _read_lessons(_DESK_DATA)


def _bull_lessons() -> str:
    return _read_lessons(_DESK_DATA_BULL)


@app.get("/api/desk/status")
async def desk_status(session=Depends(require_session)):
    """Stato live del bot V2 desk: cash, equity, posizioni aperte, budget Claude."""
    state = _desk_state()
    if not state:
        return {"available": False, "message": "Bot V2 non ancora attivo o nessun dato disponibile"}

    # state_v2.json usa chiave "main" per il conto (non "account")
    acc = state.get("main", state.get("account", {}))
    budget = state.get("budget", {})
    positions = acc.get("positions", {})

    open_list = []
    for sym, pos in positions.items():
        open_list.append({
            "symbol": sym,
            "side": pos.get("side"),
            "entry_price": pos.get("entry_price", pos.get("entry")),
            "quantity": pos.get("qty"),
            "leverage": pos.get("leverage", pos.get("lev")),
            "margin": pos.get("total_margin", pos.get("margin")),
            "trade_type": pos.get("trade_type", pos.get("type")),
            "dca_count": pos.get("dca_count", 0),
            "open_ms": pos.get("open_ms"),
            # TP/SL e DCA levels per il modal dettaglio
            "tp": pos.get("tp"),
            "sl": pos.get("sl"),
            "dca_levels": pos.get("dca_levels", []),
        })

    return {
        "available": True,
        "mode": "paper",
        "cash": round(acc.get("cash", 0), 2),
        "equity": round(acc.get("cash", 0), 2),
        "open_positions": len(positions),
        "positions": open_list,
        # "closed" nel PaperAccount può essere una lista (engine.py) oppure un int.
        # Gestiamo entrambi i casi per robustezza.
        "total_closed": (len(acc["closed"]) if isinstance(acc.get("closed"), list)
                         else acc.get("closed", state.get("total_closed", 0))),
        "day": acc.get("day", state.get("day", "")),
        "cycle": state.get("cycle", 0),
        "halt": state.get("halt"),
        "budget_spent_usd": round(budget.get("spent", 0), 4),
        "budget_daily_cap_usd": budget.get("daily_cap", 0.70),
        "last_report_day": state.get("last_report_day", ""),
    }


@app.get("/api/desk/trades")
async def desk_trades(session=Depends(require_session), limit: int = 100):
    """Ultimi N trade chiusi dal log JSONL permanente."""
    trades = _desk_trades_raw(last_n=limit)
    trades.reverse()  # più recenti prima
    result = []
    for t in trades:
        result.append({
            "symbol": t.get("symbol"),
            "side": t.get("side"),
            "entry_price": t.get("entry"),
            "exit_price": t.get("exit"),
            "quantity": t.get("qty"),
            "leverage": t.get("lev"),
            "margin": t.get("margin"),
            "gross_pnl": t.get("gross"),
            "pnl": t.get("net"),
            "fees": t.get("fees"),
            "trade_type": t.get("type"),
            "close_reason": t.get("reason"),
            "open_ms": t.get("open_ms"),
            "close_ms": t.get("close_ms"),
            "dca_count": t.get("dca_count", 0),
        })
    return result


@app.get("/api/desk/performance")
async def desk_performance(session=Depends(require_session)):
    """Statistiche aggregate del bot V2 calcolate live sul log JSONL."""
    trades = _desk_trades_raw(last_n=5000)
    if not trades:
        return {
            "available": False,
            "total_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "equity_curve": [],
            "by_symbol": {},
            "by_type": {},
        }

    closed = [t for t in trades if t.get("net") is not None]
    total = len(closed)
    winners = [t for t in closed if (t.get("net") or 0) > 0]
    total_pnl = sum(t.get("net", 0) for t in closed)
    total_fees = sum(t.get("fees", 0) for t in closed)

    # Equity curve ordinata per close_ms
    ordered = sorted(closed, key=lambda t: t.get("close_ms", 0))
    running = 0.0
    equity_curve = []
    for t in ordered:
        running += t.get("net", 0)
        equity_curve.append({
            "time": t.get("close_ms"),
            "equity": round(running, 2),
        })

    # Per simbolo
    by_symbol: dict = {}
    for t in closed:
        sym = t.get("symbol", "?")
        d = by_symbol.setdefault(sym, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        d["trades"] += 1
        d["wins"] += 1 if (t.get("net") or 0) > 0 else 0
        d["net_pnl"] += t.get("net", 0)
    for d in by_symbol.values():
        d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
        d["net_pnl"] = round(d["net_pnl"], 2)

    # Per tipo (scalp / medio)
    by_type: dict = {}
    for t in closed:
        tp = t.get("type", "?")
        d = by_type.setdefault(tp, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        d["trades"] += 1
        d["wins"] += 1 if (t.get("net") or 0) > 0 else 0
        d["net_pnl"] += t.get("net", 0)
    for d in by_type.values():
        d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
        d["net_pnl"] = round(d["net_pnl"], 2)

    gross_profit = sum(t.get("net", 0) for t in closed if (t.get("net") or 0) > 0)
    gross_loss = abs(sum(t.get("net", 0) for t in closed if (t.get("net") or 0) < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None

    return {
        "available": True,
        "total_trades": total,
        "winning_trades": len(winners),
        "losing_trades": total - len(winners),
        "win_rate": round(len(winners) / total * 100, 1) if total else 0,
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 2),
        "avg_pnl_per_trade": round(total_pnl / total, 2) if total else 0,
        "profit_factor": profit_factor,
        "equity_curve": equity_curve,
        "by_symbol": by_symbol,
        "by_type": by_type,
    }


@app.get("/api/desk/diary")
async def desk_diary(session=Depends(require_session)):
    """Diario giornaliero: trade chiusi raggruppati per giorno e per simbolo.
    Restituisce i giorni in ordine cronologico inverso (più recente prima).
    """
    from datetime import datetime, timezone
    trades = _desk_trades_raw(last_n=5000)
    closed = [t for t in trades if t.get("net") is not None]

    # raggruppa per giorno UTC
    days: dict = {}
    for t in closed:
        ms = t.get("close_ms", 0)
        day = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if ms else "?"
        days.setdefault(day, []).append(t)

    result = []
    for day in sorted(days.keys(), reverse=True):
        day_trades = sorted(days[day], key=lambda x: x.get("close_ms", 0))
        wins = [t for t in day_trades if (t.get("net") or 0) > 0]
        losses = [t for t in day_trades if (t.get("net") or 0) <= 0]
        total_pnl = sum(t.get("net", 0) for t in day_trades)

        # per simbolo in questo giorno
        by_sym: dict = {}
        for t in day_trades:
            sym = t.get("symbol", "?")
            s = by_sym.setdefault(sym, {"trades": 0, "wins": 0, "losses": 0,
                                        "total_pnl": 0.0, "best": 0.0, "worst": 0.0})
            net = t.get("net", 0)
            s["trades"] += 1
            s["total_pnl"] += net
            if net > 0:
                s["wins"] += 1
                s["best"] = max(s["best"], net)
            else:
                s["losses"] += 1
                s["worst"] = min(s["worst"], net)
        for s in by_sym.values():
            s["total_pnl"] = round(s["total_pnl"], 2)
            s["best"] = round(s["best"], 2)
            s["worst"] = round(s["worst"], 2)

        result.append({
            "day": day,
            "total_trades": len(day_trades),
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": round(total_pnl, 2),
            "by_symbol": by_sym,
            "trades": [
                {
                    "symbol": t.get("symbol"),
                    "side": t.get("side"),
                    "net": round(t.get("net", 0), 2),
                    "why": t.get("why", t.get("reason", "")),
                    "trade_type": t.get("trade_type", t.get("type", "?")),
                    "leverage": t.get("lev", t.get("leverage")),
                    "margin": t.get("margin"),
                    "close_ms": t.get("close_ms"),
                    "partial": t.get("partial", False),
                    "confidence": t.get("confidence"),
                }
                for t in day_trades
            ],
        })

    return {"days": result, "total_closed": len(closed)}


@app.get("/api/desk/logs")
async def desk_logs(session=Depends(require_session)):
    """Lezioni e note di coaching (lessons.md) generate giornalmente da Claude."""
    content = _desk_lessons()
    return {"content": content, "available": bool(content)}


@app.post("/api/desk/reset-budget")
async def desk_reset_budget(request: Request, session=Depends(require_session)):
    """Azzera il budget giornaliero AI del bot V2.
    Body JSON opzionale: {"equity_reset": true} per ripristinare anche equity a 1000$
    e azzerare le posizioni aperte (solo paper mode).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    equity_reset = bool(body.get("equity_reset", False))
    flag_path = os.path.join(_DESK_DATA, "budget_reset.flag")
    os.makedirs(_DESK_DATA, exist_ok=True)
    content = "equity_reset" if equity_reset else "budget_only"
    with open(flag_path, "w") as f:
        f.write(content)
    msg = "Budget AI azzerato + equity ripristinata a 1000$" if equity_reset else "Budget AI azzerato"
    return {"ok": True, "message": msg, "equity_reset": equity_reset}


@app.get("/api/desk/health")
async def desk_health():
    """Health check per il bot V2 Hawk (non richiede sessione)."""
    state = _desk_state()
    return {
        "available": bool(state),
        "cycle": state.get("cycle", 0),
        "day": state.get("day", ""),
        "halt": state.get("halt"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# PORTAFOGLIO BULL  (/api/desk/bull/*)
# ──────────────────────────────────────────────────────────────────────────────

def _bull_status_data() -> dict:
    """Stato live del portafoglio Bull (logica condivisa)."""
    state = _bull_state()
    if not state:
        return {"available": False, "message": "Bull non ancora attivo o nessun dato disponibile"}
    main = state.get("main", {})
    positions = main.get("positions", {})
    closed = main.get("closed", [])
    cash = float(main.get("cash", 1000.0))
    # equity approssimata
    equity = cash + sum(float(p.get("total_margin", 0)) for p in positions.values())
    budget = state.get("budget", {})
    pos_list = [
        {
            "symbol": sym,
            "side": p.get("side"),
            "leverage": p.get("leverage"),
            "margin": p.get("total_margin"),
            "entry": p.get("entry"),
            "sl": p.get("sl"),
            "tp": p.get("tp"),
            "trade_type": p.get("trade_type", "medio"),
            "dca_count": p.get("dca_count", 0),
            "confidence": p.get("confidence"),
            "reason": p.get("reason", "")[:80],
        }
        for sym, p in positions.items()
    ]
    return {
        "available": True,
        "portfolio": "bull",
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "margin_used": round(sum(float(p.get("total_margin", 0)) for p in positions.values()), 2),
        "open_positions": len(positions),
        "positions": pos_list,
        "total_closed": len(closed),
        "budget_spent_usd": round(float(budget.get("spent", 0)), 4),
        "budget_daily_cap_usd": float(os.getenv("DESK_DAILY_CAP_USD", "0.70")),
        "cycle": state.get("cycle", 0),
        "day": state.get("day", ""),
        "halt": state.get("halt"),
    }


@app.get("/api/desk/bull/status")
async def bull_status(session=Depends(require_session)):
    """Stato live del portafoglio Bull."""
    return _bull_status_data()


@app.get("/api/desk/bull/trades")
async def bull_trades(limit: int = 100, session=Depends(require_session)):
    """Ultimi N trade chiusi del portafoglio Bull."""
    trades = _bull_trades_raw(last_n=limit)
    result = []
    for t in trades:
        result.append({
            "id": t.get("id"),
            "symbol": t.get("symbol"),
            "side": t.get("side"),
            "leverage": t.get("lev"),
            "margin": t.get("margin"),
            "gross_pnl": t.get("gross"),
            "pnl": t.get("net"),
            "fees": t.get("fees"),
            "trade_type": t.get("type"),
            "close_reason": t.get("reason"),
            "open_ms": t.get("open_ms"),
            "close_ms": t.get("close_ms"),
            "dca_count": t.get("dca_count", 0),
        })
    return result


@app.get("/api/desk/bull/performance")
async def bull_performance(session=Depends(require_session)):
    """Statistiche aggregate del portafoglio Bull."""
    trades = _bull_trades_raw(last_n=5000)
    if not trades:
        return {
            "available": False,
            "total_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "equity_curve": [],
            "by_symbol": {},
            "by_type": {},
        }
    closed = [t for t in trades if t.get("net") is not None]
    total = len(closed)
    winners = [t for t in closed if (t.get("net") or 0) > 0]
    total_pnl = sum(t.get("net", 0) for t in closed)
    total_fees = sum(t.get("fees", 0) for t in closed)
    ordered = sorted(closed, key=lambda t: t.get("close_ms", 0))
    running = 0.0
    equity_curve = []
    for t in ordered:
        running += t.get("net", 0)
        equity_curve.append({"time": t.get("close_ms"), "equity": round(running, 2)})
    by_symbol: dict = {}
    for t in closed:
        sym = t.get("symbol", "?")
        d = by_symbol.setdefault(sym, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        d["trades"] += 1
        d["wins"] += 1 if (t.get("net") or 0) > 0 else 0
        d["net_pnl"] += t.get("net", 0)
    for d in by_symbol.values():
        d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
        d["net_pnl"] = round(d["net_pnl"], 2)
    by_type: dict = {}
    for t in closed:
        tp = t.get("type", "?")
        d = by_type.setdefault(tp, {"trades": 0, "wins": 0, "net_pnl": 0.0})
        d["trades"] += 1
        d["wins"] += 1 if (t.get("net") or 0) > 0 else 0
        d["net_pnl"] += t.get("net", 0)
    for d in by_type.values():
        d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
        d["net_pnl"] = round(d["net_pnl"], 2)
    gross_profit = sum(t.get("net", 0) for t in closed if (t.get("net") or 0) > 0)
    gross_loss = abs(sum(t.get("net", 0) for t in closed if (t.get("net") or 0) < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    return {
        "available": True,
        "portfolio": "bull",
        "total_trades": total,
        "winning_trades": len(winners),
        "losing_trades": total - len(winners),
        "win_rate": round(len(winners) / total * 100, 1) if total else 0,
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 2),
        "avg_pnl_per_trade": round(total_pnl / total, 2) if total else 0,
        "profit_factor": profit_factor,
        "equity_curve": equity_curve,
        "by_symbol": by_symbol,
        "by_type": by_type,
    }


@app.get("/api/desk/bull/diary")
async def bull_diary(session=Depends(require_session)):
    """Diario giornaliero del portafoglio Bull."""
    from datetime import datetime, timezone
    trades = _bull_trades_raw(last_n=5000)
    closed = [t for t in trades if t.get("net") is not None]
    days: dict = {}
    for t in closed:
        ms = t.get("close_ms", 0)
        day = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if ms else "?"
        days.setdefault(day, []).append(t)
    result = []
    for day in sorted(days.keys(), reverse=True):
        day_trades = sorted(days[day], key=lambda x: x.get("close_ms", 0))
        wins = [t for t in day_trades if (t.get("net") or 0) > 0]
        losses = [t for t in day_trades if (t.get("net") or 0) <= 0]
        total_pnl = sum(t.get("net", 0) for t in day_trades)
        by_sym: dict = {}
        for t in day_trades:
            sym = t.get("symbol", "?")
            s = by_sym.setdefault(sym, {"trades": 0, "wins": 0, "losses": 0,
                                        "total_pnl": 0.0, "best": 0.0, "worst": 0.0})
            net = t.get("net", 0)
            s["trades"] += 1
            s["total_pnl"] += net
            if net > 0:
                s["wins"] += 1
                s["best"] = max(s["best"], net)
            else:
                s["losses"] += 1
                s["worst"] = min(s["worst"], net)
        for s in by_sym.values():
            s["total_pnl"] = round(s["total_pnl"], 2)
            s["best"] = round(s["best"], 2)
            s["worst"] = round(s["worst"], 2)
        result.append({
            "day": day,
            "total_trades": len(day_trades),
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": round(total_pnl, 2),
            "by_symbol": by_sym,
            "trades": [
                {
                    "symbol": t.get("symbol"),
                    "side": t.get("side"),
                    "net": round(t.get("net", 0), 2),
                    "why": t.get("why", t.get("reason", "")),
                    "trade_type": t.get("trade_type", t.get("type", "?")),
                    "leverage": t.get("lev", t.get("leverage")),
                    "margin": t.get("margin"),
                    "close_ms": t.get("close_ms"),
                    "partial": t.get("partial", False),
                    "confidence": t.get("confidence"),
                }
                for t in day_trades
            ],
        })
    return {"days": result, "total_closed": len(closed)}


@app.get("/api/desk/bull/logs")
async def bull_logs(session=Depends(require_session)):
    """Lessons Bull."""
    content = _bull_lessons()
    return {"content": content, "available": bool(content)}


@app.post("/api/desk/bull/reset-budget")
async def bull_reset_budget(request: Request, session=Depends(require_session)):
    """Azzera il budget giornaliero AI del portafoglio Bull."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    equity_reset = bool(body.get("equity_reset", False))
    flag_path = os.path.join(_DESK_DATA_BULL, "budget_reset.flag")
    os.makedirs(_DESK_DATA_BULL, exist_ok=True)
    content = "equity_reset" if equity_reset else "budget_only"
    with open(flag_path, "w") as f:
        f.write(content)
    msg = "Bull — Budget AI azzerato + equity ripristinata a 1000$" if equity_reset else "Bull — Budget AI azzerato"
    return {"ok": True, "message": msg, "equity_reset": equity_reset}


@app.get("/api/desk/bull/health")
async def bull_health():
    """Health check per il portafoglio Bull (non richiede sessione)."""
    state = _bull_state()
    return {
        "available": bool(state),
        "portfolio": "bull",
        "cycle": state.get("cycle", 0),
        "day": state.get("day", ""),
        "halt": state.get("halt"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# LIVE DASHBOARD  (/api/desk/live/*)
# Endpoint per la dashboard live: saldo reale BitGet + P&L per portafoglio.
# Attivi sempre ma significativi solo quando DESK_MODE=live nei container desk.
# ──────────────────────────────────────────────────────────────────────────────

def _live_daily_pnl(trades_raw: list) -> float:
    """P&L realizzato oggi (dalla mezzanotte UTC) da una lista di trade chiusi."""
    import time as _time
    midnight_ms = int(_time.time() // 86400 * 86400 * 1000)
    return sum(
        t.get("net", 0.0)
        for t in trades_raw
        if (t.get("close_ms") or 0) >= midnight_ms and t.get("net") is not None
    )


def _live_total_pnl(trades_raw: list) -> float:
    """P&L realizzato totale da una lista di trade chiusi."""
    return sum(t.get("net", 0.0) for t in trades_raw if t.get("net") is not None)


def _fetch_bitget_wallet() -> dict:
    """
    Legge il saldo reale del futures wallet da BitGet via ccxt.
    Richiede BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE.
    Ritorna {"available": bool, "total_usdt": float, "available_usdt": float, "error": str|None}.
    """
    api_key    = os.environ.get("BITGET_API_KEY", "")
    secret_key = os.environ.get("BITGET_SECRET_KEY", "")
    passphrase = os.environ.get("BITGET_PASSPHRASE", "")
    desk_mode  = os.environ.get("DESK_MODE", "paper").strip().lower()

    if desk_mode != "live" or not all([api_key, secret_key, passphrase]):
        return {"available": False, "total_usdt": None, "available_usdt": None,
                "error": "DESK_MODE non è live o chiavi API mancanti"}
    try:
        import ccxt
        client = ccxt.bitget({
            "apiKey": api_key, "secret": secret_key, "password": passphrase,
            "options": {"defaultType": "swap"},
        })
        balance = client.fetch_balance()
        usdt = balance.get("USDT", {})
        return {
            "available": True,
            "total_usdt": round(float(usdt.get("total", 0) or 0), 2),
            "available_usdt": round(float(usdt.get("free", 0) or 0), 2),
            "used_usdt": round(float(usdt.get("used", 0) or 0), 2),
            "error": None,
        }
    except Exception as e:
        return {"available": False, "total_usdt": None, "available_usdt": None,
                "error": str(e)[:120]}


@app.get("/api/desk/live/wallet")
async def live_wallet(session=Depends(require_session)):
    """
    Saldo reale del futures wallet BitGet.
    In paper mode ritorna available=False senza errore — è il comportamento atteso.
    """
    return _fetch_bitget_wallet()


@app.get("/api/desk/live/overview")
async def live_overview(session=Depends(require_session)):
    """
    Vista consolidata live: saldo BitGet + P&L e stato di entrambi i portafogli.
    Aggrega /api/desk/status, /api/desk/bull/status e il wallet BitGet in una sola chiamata.
    """
    import time as _time

    # Saldo reale BitGet
    wallet = _fetch_bitget_wallet()

    # Configurazione capitali (letta dallo stesso env che usa il bot)
    hawk_capital    = float(os.environ.get("DESK_HAWK_CAPITAL", "1500"))
    bull_capital    = float(os.environ.get("DESK_BULL_CAPITAL", "1500"))
    daily_loss_pct  = float(os.environ.get("DESK_DAILY_LOSS_PCT", "25")) / 100.0
    hawk_loss_limit = hawk_capital * daily_loss_pct
    bull_loss_limit = bull_capital * daily_loss_pct

    # Dati Hawk
    hawk_state = _desk_state()
    hawk_trades = _desk_trades_raw(last_n=5000)
    hawk_main   = hawk_state.get("main", {}) if hawk_state else {}
    hawk_positions = hawk_main.get("positions", {})
    hawk_day_pnl   = _live_daily_pnl(hawk_trades)
    hawk_total_pnl = _live_total_pnl(hawk_trades)
    hawk_pos_list = [
        {
            "symbol": sym,
            "side": p.get("side"),
            "entry": p.get("entry"),
            "leverage": p.get("leverage"),
            "margin": p.get("total_margin"),
            "sl": p.get("sl"),
            "tp": p.get("tp"),
            "trade_type": p.get("trade_type"),
            "open_ms": p.get("open_ms"),
        }
        for sym, p in hawk_positions.items()
    ]

    # Dati Bull
    bull_state = _bull_state()
    bull_trades = _bull_trades_raw(last_n=5000)
    bull_main   = bull_state.get("main", {}) if bull_state else {}
    bull_positions = bull_main.get("positions", {})
    bull_day_pnl   = _live_daily_pnl(bull_trades)
    bull_total_pnl = _live_total_pnl(bull_trades)
    bull_pos_list = [
        {
            "symbol": sym,
            "side": p.get("side"),
            "entry": p.get("entry"),
            "leverage": p.get("leverage"),
            "margin": p.get("total_margin"),
            "sl": p.get("sl"),
            "tp": p.get("tp"),
            "trade_type": p.get("trade_type"),
            "open_ms": p.get("open_ms"),
        }
        for sym, p in bull_positions.items()
    ]

    # Limite raggiunto oggi?
    hawk_limit_hit = hawk_day_pnl <= -hawk_loss_limit
    bull_limit_hit = bull_day_pnl <= -bull_loss_limit

    desk_mode = os.environ.get("DESK_MODE", "paper").strip().lower()

    # Stato interruttore manuale (legge trading_enabled.json dal volume dati)
    def _read_trading_enabled(data_dir: str) -> bool:
        path = os.path.join(data_dir, "trading_enabled.json")
        try:
            with open(path) as f:
                return bool(json.load(f).get("enabled", False))
        except Exception:
            return False

    hawk_trading_enabled = _read_trading_enabled(_DESK_DATA)
    bull_trading_enabled = _read_trading_enabled(_DESK_DATA_BULL)

    return {
        "mode": desk_mode,
        "timestamp_ms": int(_time.time() * 1000),
        "wallet": wallet,
        "hawk": {
            "available": bool(hawk_state),
            "capital_usdt": hawk_capital,
            "daily_loss_limit_usdt": round(hawk_loss_limit, 2),
            "daily_pnl": round(hawk_day_pnl, 2),
            "total_pnl": round(hawk_total_pnl, 2),
            "daily_limit_hit": hawk_limit_hit,
            "open_positions": len(hawk_positions),
            "positions": hawk_pos_list,
            "total_closed": len([t for t in hawk_trades if t.get("net") is not None]),
            "cycle": hawk_state.get("cycle", 0) if hawk_state else 0,
            "halt": hawk_state.get("halt") if hawk_state else None,
            "trading_enabled": hawk_trading_enabled,
        },
        "bull": {
            "available": bool(bull_state),
            "capital_usdt": bull_capital,
            "daily_loss_limit_usdt": round(bull_loss_limit, 2),
            "daily_pnl": round(bull_day_pnl, 2),
            "total_pnl": round(bull_total_pnl, 2),
            "daily_limit_hit": bull_limit_hit,
            "open_positions": len(bull_positions),
            "positions": bull_pos_list,
            "total_closed": len([t for t in bull_trades if t.get("net") is not None]),
            "cycle": bull_state.get("cycle", 0) if bull_state else 0,
            "halt": bull_state.get("halt") if bull_state else None,
            "trading_enabled": bull_trading_enabled,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# INTERRUTTORE MANUALE TRADING  (/api/desk/{portfolio}/trading/*)
# Scrive trading_enabled.json nel volume dati del bot.
# Il bot (cli.py) legge questo file prima di ogni apertura.
# Attivo solo in live mode: in paper mode il flag non ha effetto sul bot
# ma l'endpoint risponde comunque (così il frontend non deve gestire casi speciali).
# ──────────────────────────────────────────────────────────────────────────────

def _write_trading_enabled(data_dir: str, enabled: bool) -> None:
    import time as _time
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "trading_enabled.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"enabled": enabled, "ts": int(_time.time() * 1000)}, f)
    os.replace(tmp, path)


@app.post("/api/desk/hawk/trading/enable")
async def hawk_trading_enable(session=Depends(require_session)):
    """Abilita il trading live per il portafoglio Hawk."""
    _write_trading_enabled(_DESK_DATA, True)
    return {"ok": True, "portfolio": "hawk", "trading_enabled": True}


@app.post("/api/desk/hawk/trading/disable")
async def hawk_trading_disable(session=Depends(require_session)):
    """Disabilita il trading live per il portafoglio Hawk (nessuna nuova apertura)."""
    _write_trading_enabled(_DESK_DATA, False)
    return {"ok": True, "portfolio": "hawk", "trading_enabled": False}


@app.post("/api/desk/bull/trading/enable")
async def bull_trading_enable(session=Depends(require_session)):
    """Abilita il trading live per il portafoglio Bull."""
    _write_trading_enabled(_DESK_DATA_BULL, True)
    return {"ok": True, "portfolio": "bull", "trading_enabled": True}


@app.post("/api/desk/bull/trading/disable")
async def bull_trading_disable(session=Depends(require_session)):
    """Disabilita il trading live per il portafoglio Bull (nessuna nuova apertura)."""
    _write_trading_enabled(_DESK_DATA_BULL, False)
    return {"ok": True, "portfolio": "bull", "trading_enabled": False}



# Capital V1 dashboard. PAPER-only handoff; the API never changes cash/vault.
# The bot is the only writer, with a durable receipt for retries.
def _capital_api_error(exc, *, transfer=False):
    if transfer and exc.code == "not_found":
        return HTTPException(status_code=404, detail=exc.message)
    code = 409 if exc.code in ("busy", "not_ready", "not_paper",
                              "stale_revision", "insufficient_vault") else 400
    return HTTPException(status_code=code, detail=exc.message)


@app.get("/api/desk/capital")
async def hawk_capital_status(session=Depends(require_session)):
    try:
        return capital_v1_view.status(_DESK_DATA, "hawk")
    except capital_v1_view.CapitalUnavailable as exc:
        raise _capital_api_error(exc)


@app.get("/api/desk/bull/capital")
async def bull_capital_status(session=Depends(require_session)):
    try:
        return capital_v1_view.status(_DESK_DATA_BULL, "bull")
    except capital_v1_view.CapitalUnavailable as exc:
        raise _capital_api_error(exc)


@app.post("/api/desk/capital/vault/withdraw")
async def hawk_capital_withdraw(request: Request, session=Depends(require_session)):
    try:
        return capital_v1_view.queue_manual_withdraw(
            _DESK_DATA, "hawk", await request.json())
    except capital_v1_view.CapitalUnavailable as exc:
        raise _capital_api_error(exc)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Richiesta non valida")
    except OSError:
        raise HTTPException(status_code=503, detail="Bot non raggiungibile")


@app.post("/api/desk/bull/capital/vault/withdraw")
async def bull_capital_withdraw(request: Request, session=Depends(require_session)):
    try:
        return capital_v1_view.queue_manual_withdraw(
            _DESK_DATA_BULL, "bull", await request.json())
    except capital_v1_view.CapitalUnavailable as exc:
        raise _capital_api_error(exc)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Richiesta non valida")
    except OSError:
        raise HTTPException(status_code=503, detail="Bot non raggiungibile")


@app.get("/api/desk/capital/vault/transfer/{event_id}")
async def hawk_capital_transfer_status(event_id: str, session=Depends(require_session)):
    try:
        return capital_v1_view.transfer_status(_DESK_DATA, event_id)
    except capital_v1_view.CapitalUnavailable as exc:
        raise _capital_api_error(exc, transfer=True)


@app.get("/api/desk/bull/capital/vault/transfer/{event_id}")
async def bull_capital_transfer_status(event_id: str, session=Depends(require_session)):
    try:
        return capital_v1_view.transfer_status(_DESK_DATA_BULL, event_id)
    except capital_v1_view.CapitalUnavailable as exc:
        raise _capital_api_error(exc, transfer=True)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.server:app', host='0.0.0.0', port=config.BACKEND_PORT, reload=True)
