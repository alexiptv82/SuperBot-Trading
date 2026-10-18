"""Desk API only. No database, private exchange keys, engine or Telegram imports."""
import asyncio
import hmac
import os
import time
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request
from starlette.responses import JSONResponse

import desk_api
import desk_view as dv
import live_view

SYMBOLS = 'BTC ETH BNB XRP SOL ADA DOGE AVAX DOT LINK MATIC UNI ATOM LTC BCH APT ARB OP NEAR FIL INJ SUI TIA RUNE STX XAU XAG'.split()


def create_app(token, data_dirs, get_ticker):
    if len(token) < 32 or set(data_dirs) != {'hawk', 'bull'}:
        raise ValueError('Invalid gateway configuration')
    app = FastAPI(title='SuperBot PAPER desk gateway', docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def internal_auth(request, call_next):
        candidate = request.headers.get('x-superbot-gateway-token', '')
        if not hmac.compare_digest(candidate, token):
            return JSONResponse({'detail': 'Autenticazione interna richiesta'}, status_code=401)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            # Do not queue commands when the target engine is unavailable or no longer PAPER.
            portfolio = 'bull' if request.url.path.startswith('/api/desk/bull/') else 'hawk'
            hb = dv.read_heartbeat(data_dirs[portfolio])
            if not hb or hb.get('exec_mode') != 'paper' or hb['age_s'] >= dv.HEARTBEAT_FRESH_S:
                return JSONResponse({'detail': 'Bot PAPER non disponibile: comando non inviato'}, status_code=409)
        response = await call_next(request)
        response.headers['cache-control'] = 'no-store'
        return response

    async def authorized():
        return {'internal': True}

    app.include_router(desk_api.make_router('hawk', data_dirs['hawk'], authorized, get_ticker), prefix='/api/desk')
    app.include_router(desk_api.make_router('bull', data_dirs['bull'], authorized, get_ticker), prefix='/api/desk/bull')
    prices_cache, prices_ts = {}, 0.0

    @app.get('/api/desk/prices')
    async def prices(session=Depends(authorized)):
        nonlocal prices_cache, prices_ts
        if prices_cache and time.monotonic() - prices_ts < 30:
            return prices_cache
        async def one(sym):
            for name in (sym + 'USDT', sym + '/USDT'):
                try:
                    return sym, await asyncio.wait_for(get_ticker(name), 5)
                except Exception:
                    pass
            return sym, {'error': 'Prezzo temporaneamente non disponibile'}
        prices_cache = dict(await asyncio.gather(*(one(s) for s in SYMBOLS)))
        for sym, ticker in prices_cache.items():
            desk_api.remember_price(sym, ticker.get('price'))
        prices_ts = time.monotonic()
        return prices_cache

    def wallets():
        return live_view.combine_wallets({b: {'available': False,
            'error': "modalita' paper: nessun saldo reale da mostrare"} for b in data_dirs})

    @app.get('/api/desk/live/wallet')
    async def wallet(session=Depends(authorized)):
        return wallets()

    @app.get('/api/desk/live/overview')
    async def overview(session=Depends(authorized)):
        return {'mode': 'paper', 'timestamp_ms': int(time.time()*1000), 'wallet': wallets(),
            **{b: live_view.build_portfolio(p, os.environ.get('DESK_'+b.upper()+'_CAPITAL'),
                    os.environ.get('DESK_DAILY_LOSS_PCT', '25'), 'paper') for b, p in data_dirs.items()}}

    def switch_endpoint(bot, enabled):
        async def endpoint(session=Depends(authorized)):
            live_view.write_trading_enabled(data_dirs[bot], enabled)
            return {'ok': True, 'portfolio': bot, 'trading_enabled': enabled}
        return endpoint
    for bot in data_dirs:
        for enabled, action in [(True, 'enable'), (False, 'disable')]:
            app.add_api_route('/api/desk/'+bot+'/trading/'+action, switch_endpoint(bot, enabled), methods=['POST'])
    return app


def production_app():
    if os.environ.get('DESK_MODE') != 'paper':
        raise RuntimeError('Gateway requires PAPER')
    import ccxt
    import threading
    client = ccxt.bitget({'enableRateLimit': True, 'timeout': 5000, 'options': {'defaultType': 'swap'}})
    market_lock = threading.Lock()
    def public_ticker(symbol):
        if not client.markets:
            with market_lock:
                if not client.markets:
                    client.load_markets()
        t = client.fetch_ticker(symbol)
        return {'symbol': symbol, 'price': t['last'], 'bid': t['bid'], 'ask': t['ask'],
                'volume': t['quoteVolume'], 'change_24h': t['percentage']}
    async def get_ticker(symbol):
        return await asyncio.to_thread(public_ticker, symbol)
    dirs = {b: '/opt/superbot-desk-data/'+b for b in ('hawk','bull')}
    for b, p in dirs.items():
        hb = dv.read_heartbeat(p)
        if not hb or hb.get('exec_mode') != 'paper':
            raise RuntimeError('Expected PAPER heartbeat: '+b)
    return create_app(Path('/app/app_link/gateway.token').read_text().strip(), dirs, get_ticker)
