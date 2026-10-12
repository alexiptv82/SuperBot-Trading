"""Loop principale V2: DCA, contesto di mercato, scalp vs medio, top-30 CMC.

Differenze chiave rispetto a V1:
- Simboli espansi (fino a 30 top-CMC + XAU/XAG)
- Contesto di mercato (funding/OI/notizie) aggiornato ogni 30 minuti
- Logica DCA: se Claude propone "dca" su una posizione aperta, si esegue
- Scalp vs medio: scalp ha cooldown ridotto e revisione più frequente
- Claude chiamato ogni ora (o prima per scalp)
- Budget giornaliero 0.70$ con DAILY_CAP dalla variabile d'ambiente
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.request
from typing import Optional

from desk.engine import Limits, PaperAccount
from desk.signals import read_symbol
from desk.brain import (SYSTEM, DAILY_CAP, build_prompt, call_claude,
                        can_call, parse_decisions, record_spend, rules_decisions,
                        update_lessons)
from desk.market_context import fetch_all_context
from desk.notifier import (notify_open, notify_close, notify_dca,
                           notify_halt, notify_daily_report)

# ---- configurazione V2
DATA_DIR = os.getenv("DESK_DATA_DIR", "/data/desk")
ENTRY_SCORE = int(os.getenv("DESK_ENTRY_SCORE", "60"))   # V2: abbassato da 70 a 60
HOUR_MS = 3_600_000
HALF_HOUR_MS = 1_800_000
SCALP_REVIEW_MS = 900_000    # scalp revisionati ogni 15 minuti
SCALP_COOLDOWN_MS = 600_000  # cooldown per aprire scalp consecutivi (10 min)
MEDIO_COOLDOWN_MS = 3_600_000  # cooldown per medio (1h)

# Simboli V2: top-30 CMC + oro + argento (escludi stablecoin)
SYMBOLS = [
    "BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "AVAX",
    "DOT", "LINK", "MATIC", "UNI", "ATOM", "LTC", "BCH",
    "APT", "ARB", "OP", "NEAR", "FIL", "INJ", "SUI", "TIA",
    "RUNE", "STX", "XAU", "XAG",
]
BITGET_BASE = "https://api.bitget.com"
STATE_FILE = os.path.join(DATA_DIR, "state_v2.json")
LESSONS_FILE = os.path.join(DATA_DIR, "lessons.md")
ERRORS_FILE = os.path.join(DATA_DIR, "errors.md")


# ---- candles dal BitGet
def fetch_candles(symbol: str, bar: str = "15m", limit: int = 300) -> list:
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    url = (f"{BITGET_BASE}/api/v2/mix/market/candles"
           f"?symbol={sym}PERP&productType=USDT-FUTURES&granularity={bar}&limit={limit}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        if d.get("code") != "00000":
            return []
        raw = d.get("data", [])
        # BitGet: [ts, open, high, low, close, base_vol, quote_vol]
        return [[float(x) for x in row[:6]] for row in sorted(raw, key=lambda r: float(r[0]))]
    except Exception:
        return []


def load_state(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, default=str)
    os.replace(tmp, path)


def load_lessons() -> str:
    """Carica appunti giornalieri + errori ricorrenti (input per il prompt)."""
    parts = []
    if os.path.exists(ERRORS_FILE):
        with open(ERRORS_FILE) as f:
            parts.append(f.read()[-1000:])
    if os.path.exists(LESSONS_FILE):
        with open(LESSONS_FILE) as f:
            content = f.read()
            # ultimi 5 giorni di note
            parts.append(content[-1500:])
    return "\n---\n".join(parts)


def make_account(state: dict) -> PaperAccount:
    if state.get("main"):
        return PaperAccount.from_dict(state["main"])
    return PaperAccount(Limits(), "main")


def save_account(acc: PaperAccount, state: dict) -> None:
    state["main"] = acc.to_dict()


def get_prices(symbols: list, candles_map: dict) -> dict:
    return {s: arr[-1][4] for s, arr in candles_map.items() if len(arr) > 0}


def position_info(pos, price: float, readings: dict, now_ms: int) -> dict:
    r = readings.get(pos.symbol)
    return {
        "symbol": pos.symbol, "side": pos.side, "leverage": pos.leverage,
        "margin": pos.margin, "total_margin": pos.total_margin,
        "trade_type": pos.trade_type, "dca_count": pos.dca_count,
        "entry": pos.entry, "price": price, "sl": pos.sl,
        "pnl": pos.side * (price - pos.entry) * pos.qty,
        "hours": (now_ms - pos.open_ms) / 3_600_000,
        "score_now": r.score if r else 0,
        "reason": pos.reason,
    }


def render_report(acc: PaperAccount, prices: dict, now_ms: int) -> str:
    eq = acc.equity(prices)
    lines = [
        f"=== DESK V2 REPORT {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now_ms/1000))} ===",
        f"Equity: {eq:.2f}$  Cash: {acc.cash:.2f}$  Margin: {acc.margin_in_use():.2f}$",
        f"Posizioni: {len(acc.positions)}/{acc.limits.max_open}",
    ]
    for sym, pos in acc.positions.items():
        px = prices.get(sym, pos.entry)
        pnl = pos.side * (px - pos.entry) * pos.qty
        lines.append(
            f"  {sym} {'LONG' if pos.side == 1 else 'SHORT'} {pos.trade_type.upper()} "
            f"lev {pos.leverage}x  margin {pos.total_margin:.0f}$  DCA {pos.dca_count}/2  "
            f"P&L {pnl:+.2f}$  SL {pos.sl:.5g}"
        )
    if acc.closed:
        closed_today = [c for c in acc.closed
                        if now_ms - c["close_ms"] < 24 * 3_600_000]
        pnl_day = sum(c["net"] for c in closed_today)
        lines.append(f"Chiusi oggi: {len(closed_today)}  P&L netto: {pnl_day:+.2f}$")
    return "\n".join(lines)


def needs_scalp_review(pos, now_ms: int) -> bool:
    """Gli scalp vanno rivisti più spesso."""
    return pos.trade_type == "scalp" and (now_ms - pos.last_review_ms) >= SCALP_REVIEW_MS


# ---- ciclo principale
def run_cycle(state: dict, now_ms: int) -> None:
    import numpy as np

    acc = make_account(state)
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000))
    acc.roll_day(day, {})

    # carica candele per tutti i simboli
    candles_map: dict = {}
    for sym in SYMBOLS:
        arr = fetch_candles(sym)
        if arr:
            candles_map[sym] = np.array(arr)
        time.sleep(0.05)   # gentile con l'API

    prices = get_prices(SYMBOLS, candles_map)
    halt = acc.halted(prices)
    if halt:
        notify_halt(halt)

    # --- contesto di mercato (aggiornato ogni 30 minuti)
    last_ctx_ts = state.get("last_ctx_ts", 0)
    ctx = state.get("market_ctx")
    if ctx is None or (now_ms - last_ctx_ts) >= HALF_HOUR_MS:
        try:
            ctx = fetch_all_context(SYMBOLS, now_ms)
            # serializza FundingInfo/OIInfo in dict per JSON
            ctx_serial = {
                "funding": {k: vars(v) for k, v in ctx["funding"].items()},
                "oi": {k: vars(v) for k, v in ctx["oi"].items()},
                "news": ctx["news"], "ts": ctx["ts"],
            }
            state["market_ctx"] = ctx_serial
            state["last_ctx_ts"] = now_ms
        except Exception:
            pass

    # deserializza ctx per uso
    ctx_for_prompt: Optional[dict] = None
    if state.get("market_ctx"):
        ctx_for_prompt = state["market_ctx"]

    # segnali tecnici
    readings_list = []
    readings_map: dict = {}
    for sym in SYMBOLS:
        arr = candles_map.get(sym)
        if arr is None or len(arr) < 80:
            continue
        r = read_symbol(sym, arr, now_ms)
        if r is not None:
            readings_list.append(r)
            readings_map[sym] = r

    open_symbols = set(acc.positions)

    # snapshot conto per il prompt
    eq = acc.equity(prices)
    margin_used = acc.margin_in_use()
    snap = {
        "equity": eq, "cash": acc.cash, "margin": margin_used,
        "n_open": len(acc.positions), "day_pnl": eq - acc.day_start_equity,
        "halt": halt,
    }

    # posizioni aperte con info aggiornate
    pos_info = [position_info(pos, prices.get(sym, pos.entry), readings_map, now_ms)
                for sym, pos in acc.positions.items()]

    # notizie dal ctx
    headlines = ctx_for_prompt.get("news", []) if ctx_for_prompt else []

    lessons = load_lessons()

    last_call = state.get("last_call_ms", 0)
    # determina se qualche scalp richiede review urgente
    urgent_scalp = any(needs_scalp_review(pos, now_ms) for pos in acc.positions.values())
    call_due = (now_ms - last_call) >= HOUR_MS or urgent_scalp

    decisions = []
    source = "rules"
    if halt:
        print(f"[HALT] {halt}")
    elif call_due and can_call(state, day):
        try:
            prompt = build_prompt(snap, readings_list, pos_info, headlines, lessons, ctx_for_prompt)
            text, usage = call_claude(SYSTEM, prompt, max_tokens=1100)
            cost = record_spend(state, day, usage)
            state["last_call_ms"] = now_ms
            parsed = parse_decisions(text)
            if parsed:
                decisions = parsed["decisions"]
                source = "claude"
                print(f"[Claude] {len(decisions)} decisioni  costo {cost:.4f}$  "
                      f"budget usato {state['budget']['spent']:.3f}$ / {DAILY_CAP}$")
                if parsed.get("note"):
                    print(f"[Claude] Nota: {parsed['note']}")
        except Exception as e:
            print(f"[WARN] Claude non disponibile: {e}")

    if not decisions:
        decisions = rules_decisions(readings_list, pos_info, open_symbols, ENTRY_SCORE)
        source = "rules"

    # ---- esecuzione decisioni
    last_open_ms = state.get("last_open_ms", {})
    for dec in decisions:
        sym = dec["symbol"]
        act = dec["action"]
        px = prices.get(sym)
        if px is None:
            continue

        if act == "close":
            closed = acc.close(sym, px, now_ms, "chiusura Claude")
            if closed:
                print(f"[CLOSE] {sym} net {closed['net']:+.2f}$  motivo: {dec['reason'][:60]}")
                notify_close(sym, closed["net"], dec.get("reason", "")[:100], "chiusura Claude")

        elif act == "dca":
            # DCA su posizione esistente
            pos = acc.positions.get(sym)
            if pos is None:
                continue
            sl_pct = dec.get("dca_sl_pct") or dec.get("stop_loss_pct", 0)
            tp_pct = dec.get("dca_tp_pct") or dec.get("take_profit_pct", 0)
            if sl_pct <= 0:
                print(f"[DCA SKIP] {sym}: sl_pct mancante")
                continue
            new_sl = px * (1 - pos.side * sl_pct)
            new_tp = px * (1 + pos.side * tp_pct) if tp_pct > 0 else None
            result, msg = acc.add_dca(sym, new_sl, new_tp, now_ms, prices, dec.get("reason", "")[:80])
            if result:
                print(f"[DCA] {sym} DCA#{result.dca_count} @{px:.5g}  nuovo entry medio {result.entry:.5g}  "
                      f"SL {new_sl:.5g}  margine tot {result.total_margin:.0f}$")
                notify_dca(sym, result.dca_count, px, result.entry, result.total_margin)
            else:
                print(f"[DCA SKIP] {sym}: {msg}")

        elif act in ("open_long", "open_short"):
            # cooldown per tipo
            trade_type = dec.get("trade_type", "medio")
            cooldown = SCALP_COOLDOWN_MS if trade_type == "scalp" else MEDIO_COOLDOWN_MS
            last_ts = last_open_ms.get(sym, 0)
            if now_ms - last_ts < cooldown:
                print(f"[COOLDOWN] {sym} ({trade_type})")
                continue
            if sym in acc.positions:
                continue
            if dec["confidence"] < ENTRY_SCORE:
                continue
            side = 1 if act == "open_long" else -1
            sl_pct = dec.get("stop_loss_pct", 0)
            if sl_pct <= 0:
                r = readings_map.get(sym)
                sl_pct = r.sl_pct if r else 0.01
            sl = px * (1 - side * sl_pct)
            tp_pct = dec.get("take_profit_pct", 0)
            tp = px * (1 + side * tp_pct) if tp_pct > 0 else None
            pos, msg = acc.open(
                sym, side, dec["margin_usd"], dec["leverage"], px, sl, tp, now_ms, prices,
                confidence=dec["confidence"], reason=dec.get("reason", "")[:200],
                source=source, trade_type=trade_type,
            )
            if pos:
                last_open_ms[sym] = now_ms
                print(f"[OPEN] {sym} {'LONG' if side == 1 else 'SHORT'} {trade_type.upper()} "
                      f"lev {pos.leverage}x  margin {pos.total_margin:.0f}$  "
                      f"@{px:.5g}  SL {sl:.5g}  conf {dec['confidence']}  src {source}")
                notify_open(sym, side, px, pos.leverage, pos.total_margin,
                            trade_type, dec["confidence"], source,
                            dec.get("reason", "")[:120])
            else:
                print(f"[SKIP] {sym} {act}: {msg}")

        elif act == "hold":
            # aggiorna last_review_ms per lo scalp
            pos = acc.positions.get(sym)
            if pos:
                pos.last_review_ms = now_ms

    state["last_open_ms"] = last_open_ms

    # ---- processa barre (stop, liq, tp automatici)
    import numpy as np
    for sym, pos in list(acc.positions.items()):
        arr = candles_map.get(sym)
        if arr is None:
            continue
        bar_ms = 900_000  # 15m
        for row in arr:
            ts, o, h, l, c = int(row[0]), row[1], row[2], row[3], row[4]
            result = acc.on_bar(sym, ts, o, h, l, c, bar_ms)
            if result:
                print(f"[{result['why'].upper()}] {sym} net {result['net']:+.2f}$")
                notify_close(sym, result["net"], result.get("why", ""), result["why"])
                break

    # ---- lessons
    update_lessons(DATA_DIR, state, day)

    # ---- report giornaliero Telegram (inviato una volta all'inizio del nuovo giorno)
    _last_report_day = state.get("last_report_day", "")
    if _last_report_day and _last_report_day != day:
        # giorno appena cambiato → manda il report del giorno precedente
        closed_today = [c for c in acc.closed if now_ms - c["close_ms"] < 48 * 3_600_000
                        and c.get("close_ms", 0) > (now_ms - 48 * 3_600_000)]
        pnl_today = sum(c["net"] for c in closed_today)
        notify_daily_report(
            equity=acc.equity(prices),
            cash=acc.cash,
            day_pnl=acc.equity(prices) - acc.day_start_equity,
            n_open=len(acc.positions),
            n_closed_today=len(closed_today),
            pnl_closed_today=pnl_today,
            budget_spent=state.get("budget", {}).get("spent", 0.0),
        )
    state["last_report_day"] = day

    # ---- salva
    save_account(acc, state)
    save_state(state, STATE_FILE)

    # ---- report
    print(render_report(acc, prices, now_ms))


def iteration(state: dict) -> None:
    now_ms = int(time.time() * 1000)
    try:
        run_cycle(state, now_ms)
    except Exception:
        traceback.print_exc()


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    state = load_state(STATE_FILE)

    if "--once" in sys.argv:
        iteration(state)
        return

    print(f"[DESK V2] avvio — simboli: {len(SYMBOLS)}  entry_score={ENTRY_SCORE}  "
          f"daily_cap={DAILY_CAP}$  data={DATA_DIR}")
    while True:
        iteration(state)
        # sleep adattiva: scalp richiede attenzione ogni 15 min, default ogni 30 min
        sleep_s = 900 if any(p.trade_type == "scalp" for p in make_account(state).positions.values()) else 1800
        print(f"[SLEEP] {sleep_s//60} min")
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()
