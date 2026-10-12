"""Loop principale V2: DCA, contesto di mercato, scalp vs medio, top-30 CMC.

Differenze chiave rispetto a V1:
- Simboli espansi (fino a 30 top-CMC + XAU/XAG)
- Contesto di mercato (funding/OI/notizie) aggiornato ogni 30 minuti
- Logica DCA: se Claude propone "dca" su una posizione aperta, si esegue
- Scalp vs medio: scalp ha cooldown ridotto e revisione più frequente
- Claude chiamato ogni ora (o prima per scalp)
- Budget giornaliero 0.70$ con DAILY_CAP dalla variabile d'ambiente
- Dual portfolio: --portfolio hawk (default) | bull
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.request
from dataclasses import dataclass
from typing import Optional

from desk.engine import Limits, PaperAccount
from desk.signals import read_symbol
from desk.brain import (DAILY_CAP, build_prompt, call_claude,
                        can_call, parse_decisions, record_spend, rules_decisions,
                        update_lessons, append_trade_history, load_symbol_stats, stats_summary,
                        SYSTEM as SYSTEM_HAWK, SYSTEM_BULL)
from desk.market_context import fetch_all_context
from desk.notifier import (notify_open, notify_close, notify_dca,
                           notify_halt, notify_daily_report)


# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE PORTAFOGLI
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class PortfolioConfig:
    name: str
    data_dir: str
    limits: Limits
    system_prompt: str
    # GUARDRAIL minimo margine (diverso per i due portafogli)
    guardrail_min_margin: float
    guardrail_min_lev: int
    guardrail_margin_forced: float
    guardrail_lev_forced: int
    guardrail_type_forced: str
    # max trade con cui il bot apre (superiore viene cappato al max_margin_trade del Limits)
    description: str


def _make_hawk_config() -> PortfolioConfig:
    data_dir = os.getenv("DESK_DATA_DIR", "/app/data/desk/hawk")
    return PortfolioConfig(
        name="hawk",
        data_dir=data_dir,
        limits=Limits(
            start_equity=1000.0,
            max_margin_trade=100.0,   # HAWK: max $100 per trade
            max_margin_total=1000.0,  # budget totale $1000
            max_open=10,              # max 10 posizioni
            kill_equity=450.0,
            daily_stop=0.12,
        ),
        system_prompt=SYSTEM_HAWK,
        guardrail_min_margin=50.0,
        guardrail_min_lev=10,
        guardrail_margin_forced=60.0,
        guardrail_lev_forced=15,
        guardrail_type_forced="scalp",
        description="Hawk — max $100/trade, 10 posizioni, budget $1000",
    )


def _make_bull_config() -> PortfolioConfig:
    data_dir = os.getenv("DESK_DATA_DIR", "/app/data/desk/bull")
    return PortfolioConfig(
        name="bull",
        data_dir=data_dir,
        limits=Limits(
            start_equity=1000.0,
            max_margin_trade=350.0,   # BULL: max $350 per trade
            max_margin_total=1050.0,  # max 3 × 350$
            max_open=3,               # max 3 posizioni
            kill_equity=450.0,
            daily_stop=0.12,
        ),
        system_prompt=SYSTEM_BULL,
        guardrail_min_margin=150.0,
        guardrail_min_lev=10,
        guardrail_margin_forced=200.0,
        guardrail_lev_forced=15,
        guardrail_type_forced="medio",
        description="Bull — max $350/trade, 3 posizioni, budget $1000, TP≥5%",
    )


# Selezione portfolio da env var o argomento CLI
def _select_portfolio() -> PortfolioConfig:
    pname = os.getenv("DESK_PORTFOLIO", "hawk").lower()
    for arg in sys.argv[1:]:
        if arg.startswith("--portfolio="):
            pname = arg.split("=", 1)[1].lower()
        elif arg == "--portfolio" and sys.argv.index(arg) + 1 < len(sys.argv):
            pname = sys.argv[sys.argv.index(arg) + 1].lower()
    if pname == "bull":
        return _make_bull_config()
    return _make_hawk_config()


PORTFOLIO = _select_portfolio()
DATA_DIR = PORTFOLIO.data_dir
SYSTEM = PORTFOLIO.system_prompt

# ENTRY_SCORE base (fallback) — il valore effettivo dipende dal tier dell'asset
_ENTRY_SCORE_BASE = int(os.getenv("DESK_ENTRY_SCORE", "60"))

# Tier A/B: BTC, ETH, XAU, XAG → soglia 60
# Tier C: tutti gli altri altcoin → soglia 70
_TIER_AB = {"BTC", "ETH", "XAU", "XAG"}


def tier_entry_score(symbol: str) -> int:
    """Restituisce la soglia di confidenza minima per aprire un trade su questo simbolo."""
    return 60 if symbol.upper() in _TIER_AB else 70
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

RESET_FLAG = os.path.join(DATA_DIR, "reset.flag")
BUDGET_RESET_FLAG = os.path.join(DATA_DIR, "budget_reset.flag")
PAUSE_FLAG = os.path.join(DATA_DIR, "pause.flag")


# ---- candles dal BitGet
def fetch_candles(symbol: str, bar: str = "15m", limit: int = 1000) -> list:
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    url = (f"{BITGET_BASE}/api/v2/mix/market/candles"
           f"?symbol={sym}&productType=USDT-FUTURES&granularity={bar}&limit={limit}")
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
    return PaperAccount(PORTFOLIO.limits, "main")


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

    print(f"[DESK V2] candles ok: {len(candles_map)}/{len(SYMBOLS)} simboli", flush=True)
    prices = get_prices(SYMBOLS, candles_map)
    halt = acc.halted(prices)
    if halt:
        # Invia l'alert HALT una sola volta per sessione (evita loop di messaggi)
        if not state.get("halt_notified"):
            notify_halt(halt)
            state["halt_notified"] = True
    else:
        # Reset flag quando il halt viene rimosso (es. nuovo giorno / resume)
        state.pop("halt_notified", None)

    # --- contesto di mercato (aggiornato ogni 30 minuti)
    last_ctx_ts = state.get("last_ctx_ts", 0)
    ctx = state.get("market_ctx")
    if ctx is None or (now_ms - last_ctx_ts) >= HALF_HOUR_MS:
        try:
            ctx = fetch_all_context(SYMBOLS, now_ms)
            # serializza FundingInfo/OIInfo/LSRatioInfo in dict per JSON
            ctx_serial = {
                "funding": {k: vars(v) for k, v in ctx["funding"].items()},
                "oi": {k: vars(v) for k, v in ctx["oi"].items()},
                "ls_ratio": {k: vars(v) for k, v in ctx.get("ls_ratio", {}).items()},
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

    print(f"[DESK V2] readings validi: {len(readings_list)}/{len(SYMBOLS)} simboli", flush=True)
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
    sym_stats = stats_summary(load_symbol_stats(DATA_DIR))

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
            prompt = build_prompt(snap, readings_list, pos_info, headlines, lessons, ctx_for_prompt, sym_stats)
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
        decisions = rules_decisions(readings_list, pos_info, open_symbols, _ENTRY_SCORE_BASE)
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
                append_trade_history(DATA_DIR, closed)

        elif act == "partial_close":
            fraction = float(dec.get("partial_close_fraction") or dec.get("partial_fraction") or 0.35)
            fraction = max(0.1, min(0.9, fraction))
            tp2_pct = dec.get("partial_close_tp2_pct") or dec.get("take_profit_pct") or 0
            pos = acc.positions.get(sym)
            if pos is None:
                print(f"[PARTIAL_CLOSE SKIP] {sym}: posizione non trovata")
                continue
            new_tp = None
            if tp2_pct and tp2_pct > 0:
                new_tp = px * (1 + pos.side * tp2_pct)
            partial = acc.partial_close(sym, px, now_ms, fraction, new_tp=new_tp,
                                        why=dec.get("reason", "TP parziale")[:80])
            if partial:
                print(f"[PARTIAL_CLOSE] {sym} chiuso {fraction*100:.0f}%  net {partial['net']:+.2f}$  "
                      f"TP2={'%.5g' % new_tp if new_tp else 'none'}")
                notify_close(sym, partial["net"],
                             f"TP parziale {fraction*100:.0f}% — {dec.get('reason','')[:80]}",
                             "partial_close")
                append_trade_history(DATA_DIR, partial)

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

        elif act in ("open_long", "open_short", "open_long_split", "open_short_split"):
            # normalizza: split → azione base (la seconda parte è gestita da pending_split)
            is_split = act.endswith("_split")
            base_act = act.replace("_split", "")
            # cooldown per tipo
            trade_type = dec.get("trade_type", "medio")
            cooldown = SCALP_COOLDOWN_MS if trade_type == "scalp" else MEDIO_COOLDOWN_MS
            last_ts = last_open_ms.get(sym, 0)
            if now_ms - last_ts < cooldown:
                print(f"[COOLDOWN] {sym} ({trade_type})")
                continue
            if sym in acc.positions:
                continue
            # soglia confidenza tier-aware
            if dec["confidence"] < tier_entry_score(sym):
                print(f"[CONF_LOW] {sym} conf={dec['confidence']} < soglia={tier_entry_score(sym)}")
                continue
            # filtro R:R minimo 1.5 — se SL e TP sono entrambi definiti
            sl_pct = dec.get("stop_loss_pct", 0)
            tp_pct = dec.get("take_profit_pct", 0)
            if sl_pct > 0 and tp_pct > 0:
                rr = tp_pct / sl_pct
                if rr < 1.5:
                    print(f"[RR_LOW] {sym} R:R={rr:.2f} < 1.5 (SL={sl_pct:.2%} TP={tp_pct:.2%})")
                    continue
            act = base_act  # usa open_long / open_short da qui in poi
            side = 1 if act == "open_long" else -1
            sl_pct = dec.get("stop_loss_pct", 0)
            if sl_pct <= 0:
                r = readings_map.get(sym)
                sl_pct = r.sl_pct if r else 0.01
            sl = px * (1 - side * sl_pct)
            tp_pct = dec.get("take_profit_pct", 0)
            tp = px * (1 + side * tp_pct) if tp_pct > 0 else None
            # ── GUARDRAIL portfolio-aware ────────────────────────────────────
            # Se Claude propone valori troppo bassi rispetto al portfolio corrente,
            # forziamo i minimi del portfolio selezionato.
            raw_margin = dec["margin_usd"]
            raw_lev    = dec["leverage"]
            pg = PORTFOLIO
            if raw_margin < pg.guardrail_min_margin or raw_lev < pg.guardrail_min_lev:
                print(f"[GUARDRAIL:{pg.name.upper()}] {sym} Claude proposto "
                      f"margin={raw_margin:.0f}$ lev={raw_lev}x "
                      f"→ forzato margin={pg.guardrail_margin_forced:.0f}$ "
                      f"lev={pg.guardrail_lev_forced}x {pg.guardrail_type_forced}")
                dec = dict(dec, margin_usd=pg.guardrail_margin_forced,
                           leverage=pg.guardrail_lev_forced,
                           trade_type=pg.guardrail_type_forced)
                trade_type = pg.guardrail_type_forced
            # Cappato al massimo margine del portfolio
            if dec["margin_usd"] > pg.limits.max_margin_trade:
                print(f"[CAP:{pg.name.upper()}] {sym} margin {dec['margin_usd']:.0f}$ "
                      f"→ cappato a {pg.limits.max_margin_trade:.0f}$")
                dec = dict(dec, margin_usd=pg.limits.max_margin_trade)
            # ─────────────────────────────────────────────────────────────────
            pos, msg = acc.open(
                sym, side, dec["margin_usd"], dec["leverage"], px, sl, tp, now_ms, prices,
                confidence=dec["confidence"], reason=dec.get("reason", "")[:200],
                source=source, trade_type=trade_type,
            )
            if pos:
                last_open_ms[sym] = now_ms
                rr_str = f"  R:R 1:{tp_pct/sl_pct:.1f}" if sl_pct > 0 and tp_pct > 0 else ""
                print(f"[OPEN] {sym} {'LONG' if side == 1 else 'SHORT'} {trade_type.upper()} "
                      f"lev {pos.leverage}x  margin {pos.total_margin:.0f}$  "
                      f"@{px:.5g}  SL {sl:.5g}  conf {dec['confidence']}  src {source}{rr_str}")
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
                append_trade_history(DATA_DIR, result)
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


def _check_budget_reset_flag(state: dict) -> bool:
    """Se esiste budget_reset.flag, azzera il budget giornaliero AI e opzionalmente
    ripristina l'equity a 1000$ (se il flag contiene 'equity_reset').
    Restituisce True se il reset è stato eseguito.
    """
    if not os.path.exists(BUDGET_RESET_FLAG):
        return False
    try:
        with open(BUDGET_RESET_FLAG) as f:
            content = f.read().strip()
        full_reset = "equity_reset" in content

        # azzera budget AI
        day = time.strftime("%Y-%m-%d", time.gmtime())
        state.setdefault("budget", {})
        state["budget"]["spent"] = 0.0
        state["budget"]["calls"] = 0
        state["budget"]["day"] = day
        state["last_call_ms"] = 0  # forza una nuova chiamata Claude al prossimo ciclo

        if full_reset:
            # ripristina equity e azzera posizioni (paper mode)
            acc = make_account(state)
            now_ms = int(time.time() * 1000)
            closed_count = 0
            for sym, pos in list(acc.positions.items()):
                rec = {
                    "id": pos.id, "symbol": sym, "side": pos.side,
                    "margin": pos.total_margin, "lev": pos.leverage,
                    "entry": pos.entry, "exit": pos.entry,
                    "open_ms": pos.open_ms, "close_ms": now_ms,
                    "net": 0.0, "gross": 0.0, "fees": 0.0, "funding": 0.0,
                    "reason": "budget_equity_reset", "type": pos.trade_type,
                    "dca_count": pos.dca_count, "source": "manual",
                }
                append_trade_history(DATA_DIR, [rec])
                closed_count += 1
            acc.positions.clear()
            acc.closed.clear()
            acc.cash = 1000.0
            # reset day tracking
            acc.day_start_equity = 1000.0
            save_account(acc, state)
            print(f"[BUDGET_RESET] Equity ripristinata a 1000$ — {closed_count} posizioni azzerate", flush=True)
        else:
            print(f"[BUDGET_RESET] Budget AI azzerato (equity invariata)", flush=True)

        save_state(state, STATE_FILE)
        os.remove(BUDGET_RESET_FLAG)
        return True
    except Exception as e:
        print(f"[BUDGET_RESET ERROR] {e}", flush=True)
        try:
            os.remove(BUDGET_RESET_FLAG)
        except Exception:
            pass
        return False


def _check_reset_flag(state: dict) -> bool:
    """Se esiste reset.flag, azzera tutte le posizioni aperte e rimuove il flag.
    Restituisce True se il reset è stato eseguito.
    """
    if not os.path.exists(RESET_FLAG):
        return False
    try:
        acc = make_account(state)
        prices = {}  # chiusura flat: usa prezzi di entrata
        now_ms = int(time.time() * 1000)
        closed_count = 0
        for sym, pos in list(acc.positions.items()):
            px = pos.entry  # chiusura flat al prezzo di entrata
            rec = {
                "id": pos.id, "symbol": sym, "side": pos.side,
                "margin": pos.total_margin, "lev": pos.leverage,
                "entry": pos.entry, "exit": px,
                "open_ms": pos.open_ms, "close_ms": now_ms,
                "net": 0.0, "gross": 0.0, "fees": 0.0, "funding": 0.0,
                "reason": "manual_reset", "type": pos.trade_type,
                "dca_count": pos.dca_count, "source": "manual",
            }
            append_trade_history(DATA_DIR, [rec])
            acc.cash += pos.total_margin
            closed_count += 1
        acc.positions.clear()
        save_account(acc, state)
        save_state(state, STATE_FILE)
        os.remove(RESET_FLAG)
        print(f"[RESET] Azzerate {closed_count} posizioni su richiesta manuale", flush=True)
        return True
    except Exception as e:
        print(f"[RESET ERROR] {e}", flush=True)
        try:
            os.remove(RESET_FLAG)
        except Exception:
            pass
        return False


def iteration(state: dict) -> None:
    now_ms = int(time.time() * 1000)
    _check_budget_reset_flag(state)
    _check_reset_flag(state)
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

    print(f"[DESK V2] avvio [{PORTFOLIO.name.upper()}] — {PORTFOLIO.description}")
    print(f"[DESK V2] simboli: {len(SYMBOLS)}  "
          f"entry_score=60(TIER_AB)/70(TIER_C)  "
          f"daily_cap={DAILY_CAP}$  data={DATA_DIR}")
    while True:
        # ── Pausa: se esiste pause.flag il bot aspetta senza fare nulla ──
        if os.path.exists(PAUSE_FLAG):
            print("[PAUSA] pause.flag trovato — bot in attesa. Rimuovi il file per riprendere.")
            # Segna paused nello stato così il server/frontend lo vede
            state["paused"] = True
            save_state(state, STATE_FILE)
            while os.path.exists(PAUSE_FLAG):
                time.sleep(15)
            print("[PAUSA] pause.flag rimosso — bot riprende.")
            state = load_state(STATE_FILE)  # ricarica stato fresco dopo la pausa
            state["paused"] = False
            save_state(state, STATE_FILE)
            continue

        iteration(state)
        # sleep adattiva: scalp richiede attenzione ogni 15 min, default ogni 30 min
        sleep_s = 900 if any(p.trade_type == "scalp" for p in make_account(state).positions.values()) else 1800
        print(f"[SLEEP] {sleep_s//60} min")
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()
