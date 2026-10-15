"""Endpoint HTTP dei portafogli desk. Un solo codice per Hawk e Bull: make_router() crea le rotte
per un portafoglio (stato, trade, performance, diario, run, comandi). Tutta la logica sta in
desk_view.py (testata a parte): qui c'e' solo il collegamento a FastAPI, volutamente sottile.
"""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import desk_view as dv

# prezzo live per simbolo: (istante monotonic, prezzo). Condiviso da /prices e da /status.
_ticker_cache: dict = {}
PRICE_MAX_AGE_S = 20.0      # sotto questa eta' non si richiede di nuovo all'exchange
PRICE_USABLE_S = 120.0      # oltre questa eta' il prezzo non si usa piu' per il P&L
TICKER_TIMEOUT_S = 4.0


def remember_price(symbol: str, price) -> None:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return
    if p > 0:
        _ticker_cache[symbol] = (time.monotonic(), p)


async def live_prices(symbols: list, get_ticker) -> dict:
    """Prezzi recenti per i simboli indicati, chiedendo all'exchange solo quelli scaduti.
    Se l'exchange non risponde si usano i prezzi ancora validi; mai un errore verso l'app."""
    now = time.monotonic()
    need = [s for s in symbols if s not in _ticker_cache or now - _ticker_cache[s][0] > PRICE_MAX_AGE_S]

    async def one(sym: str) -> None:
        for name in (sym + "USDT", sym + "/USDT"):
            try:
                t = await asyncio.wait_for(get_ticker(name), TICKER_TIMEOUT_S)
                price = float((t or {}).get("price") or 0)
            except Exception:
                continue
            if price > 0:
                remember_price(sym, price)
                return

    if need:
        await asyncio.gather(*(one(s) for s in need), return_exceptions=True)
    now = time.monotonic()
    return {s: _ticker_cache[s][1] for s in symbols
            if s in _ticker_cache and now - _ticker_cache[s][0] < PRICE_USABLE_S}


def make_router(portfolio: str, data_dir: str, require_session, get_ticker) -> APIRouter:
    r = APIRouter()
    name = portfolio.capitalize()

    def _flag_error(e: Exception) -> HTTPException:
        return HTTPException(status_code=500, detail=f"{name}: impossibile comunicare col bot ({e})")

    @r.get("/status")
    async def status(session=Depends(require_session)):
        prices = await live_prices(dv.open_symbols(data_dir), get_ticker)
        return dv.build_status(data_dir, portfolio, prices)

    @r.get("/trades")
    async def trades(limit: int = 100, session=Depends(require_session)):
        return dv.build_trades(data_dir, limit)

    @r.get("/performance")
    async def performance(session=Depends(require_session)):
        return dv.build_performance(data_dir, portfolio)

    @r.get("/diary")
    async def diary(session=Depends(require_session)):
        return dv.build_diary(data_dir)

    @r.get("/runs")
    async def runs(session=Depends(require_session)):
        return dv.list_runs(data_dir, portfolio)

    @r.get("/logs")
    async def logs(session=Depends(require_session)):
        content = dv.read_lessons(data_dir)
        return {"content": content, "available": bool(content)}

    @r.post("/pause")
    async def pause(session=Depends(require_session)):
        try:
            return dv.command_pause(data_dir)
        except OSError as e:
            raise _flag_error(e)

    @r.post("/resume")
    async def resume(session=Depends(require_session)):
        try:
            return dv.command_resume(data_dir)
        except OSError as e:
            raise _flag_error(e)

    @r.post("/close-all")
    async def close_all(session=Depends(require_session)):
        try:
            return dv.command_close_all(data_dir)
        except OSError as e:
            raise _flag_error(e)

    @r.post("/close-position")
    async def close_position(request: Request, session=Depends(require_session)):
        try:
            body = await request.json()
        except Exception:
            body = {}
        symbol = body.get("symbol") if isinstance(body, dict) else None
        try:
            ok, code, payload = dv.command_close_position(data_dir, symbol)
        except OSError as e:
            raise _flag_error(e)
        if not ok:
            raise HTTPException(status_code=code, detail=payload["message"])
        return payload

    @r.post("/reset-budget")
    async def reset_budget(session=Depends(require_session)):
        try:
            return dv.command_reset_budget(data_dir)
        except OSError as e:
            raise _flag_error(e)

    @r.post("/reset-portfolio")
    async def reset_portfolio(request: Request, session=Depends(require_session)):
        try:
            body = await request.json()
        except Exception:
            body = {}
        clear = bool(body.get("clear_lessons")) if isinstance(body, dict) else False
        try:
            ok, code, payload = dv.command_reset_portfolio(data_dir, clear)
        except OSError as e:
            raise _flag_error(e)
        if not ok:
            raise HTTPException(status_code=code, detail=payload["message"])
        return payload

    @r.get("/health")
    async def health():
        return dv.health(data_dir, portfolio)

    return r
