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
DEFAULT_CAPITAL = 1000.0       # uguale al default di cli.py (la base su cui ragiona il motore)
DEFAULT_LOSS_PCT = 25.0


WALLET_KEY_NAMES = ("BITGET_RO_API_KEY", "BITGET_RO_SECRET_KEY", "BITGET_RO_PASSPHRASE")   # conto unico (vecchio)
WALLET_BOTS = ("hawk", "bull")


def wallet_key_names(bot: Optional[str] = None) -> tuple:
    """Nomi delle tre variabili della chiave di SOLA LETTURA. Con `bot` ("hawk"/"bull") sono quelle del
    sub-account di quel bot (BITGET_RO_HAWK_API_KEY...); senza, quelle del vecchio conto unico."""
    if not bot:
        return WALLET_KEY_NAMES
    b = bot.strip().upper()
    return tuple(f"BITGET_RO_{b}_{part}" for part in ("API_KEY", "SECRET_KEY", "PASSPHRASE"))


def wallet_credentials(env, bot: Optional[str] = None) -> Optional[tuple]:
    """(api_key, secret, passphrase) della chiave BitGet di SOLA LETTURA usata dall'app per il saldo
    (di un bot, se indicato), oppure None se manca anche una sola delle tre. Le chiavi di trading
    (BITGET_API_KEY, BITGET_HAWK_API_KEY...) non si usano MAI qui: l'app non deve poterle avere, nemmeno per
    sbaglio. Con `bot` indicato non si ripiega mai sulla chiave di un altro conto: un saldo sbagliato e'
    peggio di nessun saldo."""
    vals = tuple((env.get(n) or "").strip() for n in wallet_key_names(bot))
    return vals if all(vals) else None


def combine_wallets(per_bot: dict) -> dict:
    """Mette insieme i saldi dei sub-account (uno per bot). I campi del totale (total_usdt, ...) sono la
    SOMMA e compaiono solo se TUTTI i bot sono leggibili: una somma parziale mostrerebbe un saldo sbagliato.
    Il dettaglio di ogni bot resta sempre in `per_bot`, errori compresi."""
    per_bot = {b: (w or {}) for b, w in per_bot.items()}
    bad = {b: (w.get("error") or "saldo non disponibile") for b, w in per_bot.items() if not w.get("available")}
    out = {"per_bot": per_bot}
    if not per_bot or bad:
        out["available"] = False
        out["error"] = "; ".join(f"{b}: {e}" for b, e in sorted(bad.items())) or "nessun saldo"
        return out
    out["available"] = True
    out["error"] = None
    for k in ("total_usdt", "available_usdt", "used_usdt"):
        out[k] = round(sum(float(w.get(k) or 0.0) for w in per_bot.values()), 2)
    return out


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


def _num(value, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v == v and abs(v) != float("inf") else default     # niente NaN / inf


def base_symbol(symbol) -> str:
    """'BTC/USDT:USDT' -> 'BTC'; 'BTCUSDT' -> 'BTC'; 'BTC' -> 'BTC' (stessa regola del connettore live)."""
    s = str(symbol or "").split("/")[0].split(":")[0].strip().upper()
    return s[:-4] if s.endswith("USDT") and len(s) > 4 else s


def _position_rows(state: dict, scale: float = 1.0) -> list:
    """Posizioni del motore, gia' portate nella scala reale (margine, quantita', P&L) e con il prezzo
    dell'ultimo ciclo del bot se c'e' (senza, il P&L non si puo' calcolare e resta None)."""
    positions = ((state.get("main") or {}).get("positions")) or {}
    last_prices = state.get("last_prices") or {}
    rows = []
    for sym, p in positions.items():
        if not isinstance(p, dict):
            continue
        side = 1 if _num(p.get("side")) >= 0 else -1
        entry, qty = _num(p.get("entry")), _num(p.get("qty")) * scale
        margin = _num(p.get("total_margin", p.get("margin"))) * scale
        price = _num(last_prices.get(sym))
        pnl = side * (price - entry) * qty if price and entry and qty else None
        rows.append({
            "symbol": sym, "side": side, "entry": entry or None, "price": price or None,
            "leverage": p.get("leverage"), "qty": qty or None, "margin": round(margin, 2),
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl / margin * 100, 2) if pnl is not None and margin else None,
            "sl": p.get("sl"), "tp": p.get("tp"), "liq": p.get("liq"),
            "trade_type": p.get("trade_type") or "medio", "dca_count": p.get("dca_count", 0),
            "open_ms": p.get("open_ms"), "source": "bot", "confirmed": None,
        })
    return rows


def normalize_real_positions(raw: list) -> list:
    """Posizioni vere di BitGet (ccxt fetch_positions, sola lettura) nel formato della pagina Live.
    Campi come li compone ccxt per Bitget: info.holdSide, info.total (quantita' in coin), info.openPriceAvg,
    info.markPrice, info.unrealizedPL, info.marginSize, info.liquidationPrice, info.leverage, info.cTime.
    Le posizioni a quantita' zero si saltano."""
    rows = []
    for p in raw or []:
        if not isinstance(p, dict):
            continue
        info = p.get("info") if isinstance(p.get("info"), dict) else {}
        contracts = abs(_num(p.get("contracts"), _num(info.get("total"))))
        size = _num(p.get("contractSize"), 1.0) or 1.0
        qty = abs(_num(info.get("total"))) or contracts * size
        if qty <= 0:
            continue
        side_txt = str(p.get("side") or info.get("holdSide") or "").lower()
        side = 1 if side_txt == "long" else -1
        entry = _num(p.get("entryPrice"), _num(info.get("openPriceAvg")))
        mark = _num(p.get("markPrice"), _num(info.get("markPrice")))
        pnl = _num(p.get("unrealizedPnl"), _num(info.get("unrealizedPL")))
        margin = _num(info.get("marginSize")) or _num(p.get("initialMargin")) or _num(p.get("collateral"))
        liq = _num(p.get("liquidationPrice"), _num(info.get("liquidationPrice")))
        lev = int(_num(p.get("leverage"), _num(info.get("leverage")))) or None
        rows.append({
            "symbol": base_symbol(p.get("symbol") or info.get("symbol")), "side": side,
            "entry": entry or None, "price": mark or None, "leverage": lev, "qty": qty,
            "margin": round(margin, 2), "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / margin * 100, 2) if margin else None,
            "liq": liq or None, "open_ms": _positive_ms(p.get("timestamp") or info.get("cTime")) or None,
        })
    return rows


def merge_positions(real: Optional[dict], bot_rows: list) -> tuple:
    """Posizioni da mostrare: (righe, fonte, errore).

    Con BitGet leggibile le posizioni sono QUELLE VERE dell'exchange (prezzo, P&L, margine, liquidazione), a cui
    si aggiungono stop loss, take profit, tipo e DCA del bot. Una posizione che il bot ha in registro ma BitGet
    non mostra resta in lista, segnata `confirmed: False`; una che c'e' su BitGet e il bot non conosce e'
    segnata `in_bot: False`. Se BitGet non e' leggibile si mostrano i numeri del bot (`source: "bot"`) e si dice perche'."""
    real = real or {}
    if not real.get("available"):
        return list(bot_rows), "bot", real.get("error")
    bot_by = {base_symbol(r["symbol"]): r for r in bot_rows}
    out, seen = [], set()
    for r in real.get("positions") or []:
        b = bot_by.get(r["symbol"]) or {}
        seen.add(r["symbol"])
        out.append({**r, "sl": b.get("sl"), "tp": b.get("tp"), "trade_type": b.get("trade_type"),
                    "dca_count": b.get("dca_count", 0), "open_ms": b.get("open_ms") or r.get("open_ms"),
                    "source": "bitget", "confirmed": True, "in_bot": bool(b)})
    for key, b in bot_by.items():
        if key not in seen:
            out.append({**b, "source": "bot", "confirmed": False, "in_bot": True})
    out.sort(key=lambda x: x.get("open_ms") or 0)
    return out, "bitget", None


def _recent_trades(trades: list, scale: float, n: int = 5) -> list:
    """Gli ultimi n trade chiusi (piu' recenti prima), con il risultato nella scala reale."""
    last = sorted(trades, key=lambda t: _positive_ms(t.get("close_ms")), reverse=True)[:n]
    out = []
    for t in last:
        nt = dv.normalize_trade(t)
        pnl = nt.get("pnl")
        out.append({"symbol": nt["symbol"], "side": nt["side"], "leverage": nt["leverage"],
                    "pnl": round(_num(pnl) * scale, 2) if pnl is not None else None,
                    "close_ms": nt["close_ms"], "close_reason": nt["close_reason"],
                    "trade_type": nt["trade_type"], "partial": nt["partial"], "closed_by": nt.get("closed_by")})
    return out


def _positive_float(value, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


def _positive_ms(value) -> int:
    """Millisecondi epoch > 0, altrimenti 0 (campo assente o rovinato)."""
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def _opened_ms(trade: dict) -> int:
    """Quando e' stato aperto un trade chiuso (se manca, vale la chiusura)."""
    return _positive_ms(trade.get("open_ms")) or _positive_ms(trade.get("close_ms"))


def build_portfolio(data_dir: str, capital, loss_pct, desk_mode: str = "paper",
                    now: Optional[float] = None, real_positions: Optional[dict] = None) -> dict:
    """Un portafoglio come lo mostra la pagina Live.

    I numeri (P&L, posizioni, trade chiusi) si leggono dai file del bot SOLO se il server e' in live
    (DESK_MODE=live) E il bot sta girando davvero in live (heartbeat exec_mode == "live"). Negli altri
    casi - server in paper, bot ancora la versione vecchia senza live, bot in paper, bot fermo - quei
    file sono i dati del simulatore: mostrarli nella pagina Live le farebbe passare per soldi veri.
    Si restituisce quindi uno scheletro a zero (`real_data: False`); lo stato del bot (heartbeat,
    interruttore) resta leggibile perche' serve a spiegare perche' non ci sono numeri.

    `real_positions` ({"available", "positions": [normalize_real_positions(...)], "error"}) sono le posizioni lette
    da BitGet con la chiave di sola lettura: se ci sono, la lista delle posizioni e' quella vera (vedi merge_positions).
    """
    capital = _positive_float(capital, DEFAULT_CAPITAL)
    loss_pct = _positive_float(loss_pct, DEFAULT_LOSS_PCT)
    limit = round(capital * loss_pct / 100.0, 2)
    hb = dv.read_heartbeat(data_dir, now)
    server_live = (desk_mode or "").strip().lower() == "live"
    bot_mode = (hb or {}).get("exec_mode")
    base = {
        "capital_usdt": capital,
        "daily_loss_limit_usdt": limit,
        "paper_mode": not server_live,       # il server non e' in live (DESK_MODE != live)
        "trading_enabled": read_trading_enabled(data_dir),
        "bot_mode": bot_mode,
        "heartbeat_age_s": round(hb["age_s"], 1) if hb else None,
        "bot_online": bool(hb and hb["age_s"] < dv.HEARTBEAT_FRESH_S),
        # il tasto Chiudi della singola posizione c'e' solo se il bot di adesso lo sa fare (vedi desk_view)
        "can_close_position": dv.can_close_position(hb),
        "close_pending": dv.close_pending(data_dir),
        "cycle_info": {"last_end_ms": _positive_ms((hb or {}).get("last_end_ms")) or None,
                       "next_cycle_ms": _positive_ms((hb or {}).get("next_cycle_ms")) or None,
                       "last_ok": (hb or {}).get("last_ok"), "last_error": (hb or {}).get("last_error") or ""},
    }

    if not (server_live and bot_mode == "live"):
        return {**base, "available": False, "real_data": False,
                "daily_pnl": 0.0, "total_pnl": 0.0, "daily_limit_hit": False,
                "open_positions": 0, "positions": [], "positions_source": "none", "positions_error": None,
                "unrealized_pnl": 0.0, "recent_trades": [], "total_closed": 0, "cycle": 0, "halt": None,
                "live_interlock": None, "live_pending_close": []}

    state = dv.read_state(data_dir)
    # Solo cio' che e' stato APERTO dopo la partenza del live: lo storico e le posizioni del simulatore
    # (aperti prima) stanno negli stessi file ma non sono soldi veri. Senza il momento di partenza non si
    # puo' distinguere: si mostra zero piuttosto che numeri incerti.
    since = _positive_ms((hb or {}).get("live_since_ms"))
    # Il motore ragiona su un conto da 1000$; sull'exchange ogni ordine e' in scala (capitale / 1000):
    # gli importi del motore si portano nella scala reale prima di mostrarli.
    scale = _positive_float((hb or {}).get("capital_scale"), 1.0)
    trades = [t for t in dv.closed_records(data_dir, state) if since and _opened_ms(t) >= since]
    bot_rows = [r for r in _position_rows(state, scale) if since and _positive_ms(r.get("open_ms")) >= since]
    rows, source, pos_error = merge_positions(real_positions, bot_rows)
    day, tot = daily_pnl(trades, now) * scale, total_pnl(trades) * scale
    return {
        **base,
        "available": bool(state), "real_data": True,
        "live_since_ms": since or None, "scale": scale,
        "daily_pnl": round(day, 2), "total_pnl": round(tot, 2),
        "daily_limit_hit": day <= -limit,
        "open_positions": len(rows), "positions": rows,
        "positions_source": source, "positions_error": pos_error,
        "unrealized_pnl": round(sum(_num(r.get("pnl")) for r in rows), 2),
        "recent_trades": _recent_trades(trades, scale),
        "total_closed": len(trades),
        "cycle": state.get("cycle", 0) if state else 0,
        "halt": state.get("halt") if state else None,
        "live_interlock": (hb or {}).get("live_interlock"),
        "live_pending_close": (hb or {}).get("live_pending_close") or [],
        "last_action": state.get("last_action") if state else None,
    }
