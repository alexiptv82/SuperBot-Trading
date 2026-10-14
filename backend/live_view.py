"""Vista live dei portafogli desk: P&L del giorno, limite di perdita, interruttore manuale.

Solo lettura/scrittura di file nel volume dati del bot (stesso schema di desk_view.py): niente rete,
niente FastAPI, cosi' si testa a parte. Il saldo reale BitGet sta in server.py perche' usa ccxt.

Le regole qui DEVONO restare uguali a quelle del bot (backend/desk/cli.py):
- "oggi" = dalla mezzanotte UTC;
- il P&L del giorno e' quello REALIZZATO (net dei trade chiusi), non conta le posizioni ancora aperte;
- l'interruttore manuale e' il file trading_enabled.json: se manca o e' rovinato vale "spento".
"""
import json
import os
import time
from typing import Optional

import desk_view as dv

TRADING_FLAG = "trading_enabled.json"
DEFAULT_CAPITAL = 1500.0       # uguale al default di cli.py
DEFAULT_LOSS_PCT = 25.0


WALLET_KEY_NAMES = ("BITGET_RO_API_KEY", "BITGET_RO_SECRET_KEY", "BITGET_RO_PASSPHRASE")


def wallet_credentials(env) -> Optional[tuple]:
    """(api_key, secret, passphrase) della chiave BitGet di SOLA LETTURA usata dall'app per il saldo,
    oppure None se manca anche una sola delle tre. Le chiavi di trading (BITGET_API_KEY...) non si
    usano MAI qui: l'app non deve poterle avere, nemmeno per sbaglio."""
    vals = tuple((env.get(n) or "").strip() for n in WALLET_KEY_NAMES)
    return vals if all(vals) else None


def utc_midnight_ms(now: Optional[float] = None) -> int:
    now = time.time() if now is None else now
    return int(now // 86400 * 86400 * 1000)


def daily_pnl(trades: list, now: Optional[float] = None) -> float:
    """Somma del net dei trade chiusi da mezzanotte UTC (parziali inclusi, come fa il bot)."""
    start = utc_midnight_ms(now)
    return sum(float(t.get("net") or 0.0) for t in trades
               if t.get("net") is not None and (t.get("close_ms") or 0) >= start)


def total_pnl(trades: list) -> float:
    return sum(float(t.get("net") or 0.0) for t in trades if t.get("net") is not None)


def read_trading_enabled(data_dir: str) -> bool:
    """Spento di default: file assente, illeggibile o senza il campo 'enabled' = False."""
    try:
        with open(os.path.join(data_dir, TRADING_FLAG)) as f:
            return bool(json.load(f).get("enabled", False))
    except Exception:
        return False


def write_trading_enabled(data_dir: str, enabled: bool, now: Optional[float] = None) -> None:
    """Scrittura atomica (tmp + replace): il bot non legge mai un file a meta'."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, TRADING_FLAG)
    tmp = path + ".tmp"
    ts = int((time.time() if now is None else now) * 1000)
    with open(tmp, "w") as f:
        json.dump({"enabled": bool(enabled), "ts": ts}, f)
    os.replace(tmp, path)


def _position_rows(state: dict) -> list:
    positions = ((state.get("main") or {}).get("positions")) or {}
    return [{
        "symbol": sym, "side": p.get("side"), "entry": p.get("entry"),
        "leverage": p.get("leverage"), "margin": p.get("total_margin", p.get("margin")),
        "sl": p.get("sl"), "tp": p.get("tp"), "trade_type": p.get("trade_type"),
        "open_ms": p.get("open_ms"),
    } for sym, p in positions.items() if isinstance(p, dict)]


def _positive_float(value, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


def build_portfolio(data_dir: str, capital, loss_pct, now: Optional[float] = None) -> dict:
    """Un portafoglio come lo mostra la pagina Live."""
    capital = _positive_float(capital, DEFAULT_CAPITAL)
    loss_pct = _positive_float(loss_pct, DEFAULT_LOSS_PCT)
    limit = capital * loss_pct / 100.0
    state = dv.read_state(data_dir)
    trades = dv.closed_records(data_dir, state)
    day, tot = daily_pnl(trades, now), total_pnl(trades)
    rows = _position_rows(state)
    hb = dv.read_heartbeat(data_dir, now)
    return {
        "available": bool(state),
        "capital_usdt": capital,
        "daily_loss_limit_usdt": round(limit, 2),
        "daily_pnl": round(day, 2),
        "total_pnl": round(tot, 2),
        "daily_limit_hit": day <= -limit,
        "open_positions": len(rows),
        "positions": rows,
        "total_closed": len(trades),
        "cycle": state.get("cycle", 0) if state else 0,
        "halt": state.get("halt") if state else None,
        "trading_enabled": read_trading_enabled(data_dir),
        # Come gira DAVVERO il bot ("live"/"paper"), dal suo battito cardiaco. None = il bot non e'
        # raggiungibile oppure gira ancora con un codice precedente al live (container da ridistribuire).
        "bot_mode": (hb or {}).get("exec_mode"),
        "heartbeat_age_s": round(hb["age_s"], 1) if hb else None,
    }
