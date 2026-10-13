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
                        can_call, diagnose_reply, parse_decisions, record_spend, rules_decisions,
                        update_lessons, append_trade_history, load_symbol_stats, stats_summary,
                        SYSTEM as SYSTEM_HAWK, SYSTEM_BULL)
from desk.market_context import fetch_all_context
from desk.learning import build_features, log_event
from desk.notifier import (notify_open, notify_close, notify_dca, notify_split,
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

# ---- protocollo di controllo server <-> bot (file nella cartella dati)
#   pause.flag            PAUSA: il bot finisce le posizioni aperte e non ne apre di nuove
#   reset.flag            chiudi tutte le posizioni a prezzo di mercato
#   budget_reset.flag     azzera solo il budget giornaliero di Claude
#   reset_portfolio.flag  riparti da 1000$ (solo in pausa e senza posizioni); JSON {"clear_lessons": bool}
#   heartbeat.json        scritto dal bot: modalita', ultimo ciclo, prossimo ciclo, versione
# I percorsi si calcolano al momento dell'uso (DATA_DIR puo' cambiare, es. nei test).
def _flag(name: str) -> str:
    return os.path.join(DATA_DIR, name)


POLL_S = 5                 # ogni quanto il bot controlla i tasti dell'app
RETRY_S = 300              # dopo un ciclo fallito riprova dopo 5 minuti
CYCLE_S = 1800             # ciclo normale: 30 minuti
CYCLE_FAST_S = 900         # con scalp aperto o in svuotamento: 15 minuti
CODE_VERSION = os.getenv("DESK_CODE_VERSION", "dev")


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
        acc = PaperAccount.from_dict(state["main"])
        # I parametri vivono nel codice: i limiti salvati nello stato sarebbero rimasti quelli
        # del giorno in cui il conto e' nato e un cambio di parametri non avrebbe avuto effetto.
        acc.limits = PORTFOLIO.limits
        return acc
    return PaperAccount(PORTFOLIO.limits, "main")


# ---- heartbeat: dice all'app (e al healthcheck) che il bot e' vivo e cosa sta facendo
HB: dict = {"started_ms": int(time.time() * 1000), "version": CODE_VERSION, "pid": os.getpid(),
            "cycles": 0, "last_start_ms": 0, "last_end_ms": 0, "last_ok": None, "last_error": "",
            "next_cycle_ms": 0}
_hb_last_write = 0.0


def write_heartbeat(state: Optional[dict] = None, force: bool = True, **extra) -> None:
    """Scrive heartbeat.json (scrittura atomica). Con force=False al massimo una volta ogni 3 s."""
    global _hb_last_write
    now = time.time()
    if not force and now - _hb_last_write < 3:
        return
    _hb_last_write = now
    HB.update(extra)
    n_open = None
    if state is not None:
        n_open = len((state.get("main") or {}).get("positions") or {})
        paused = os.path.exists(_flag("pause.flag"))
        HB["pause_requested"] = paused
        HB["open_positions"] = n_open
        HB["mode"] = compute_mode(paused, n_open)
    HB["portfolio"] = PORTFOLIO.name
    HB["daily_cap_usd"] = DAILY_CAP
    if "params" not in HB:
        HB["params"] = run_params()   # i parametri veri, mostrati in Impostazioni
    HB["ts"] = now
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        path = _flag("heartbeat.json")
        with open(path + ".tmp", "w") as f:
            json.dump(HB, f, default=str)
        os.replace(path + ".tmp", path)
    except Exception:
        pass   # un heartbeat mancato non deve mai fermare il bot


def compute_mode(paused: bool, n_open: int) -> str:
    """running = lavora; draining = in pausa ma sta finendo le posizioni; paused = fermo e senza posizioni."""
    if not paused:
        return "running"
    return "draining" if n_open > 0 else "paused"


def save_account(acc: PaperAccount, state: dict) -> None:
    state["main"] = acc.to_dict()


def get_prices(symbols: list, candles_map: dict) -> dict:
    return {s: arr[-1][4] for s, arr in candles_map.items() if len(arr) > 0}


def record_close(state: dict, rec: dict) -> None:
    """Ogni chiusura (finale o parziale) va nello storico dei trade e nel registro di apprendimento."""
    append_trade_history(DATA_DIR, rec)
    row = dict(rec)
    row["reason"] = str(row.get("reason", ""))[:200]
    log_event(DATA_DIR, {"ev": "close", "ts": rec.get("close_ms"), "portfolio": PORTFOLIO.name,
                         "run_no": state.get("run_no", 1), **row})


REPLY_KEEP_CHARS = 6000   # una risposta scartata piu' lunga si salva accorciata (inizio e fine)


def log_claude_call(now_ms: int, state: dict, text: str, usage: dict, cost: float, parsed,
                    prompt_chars: int, n_positions: int, urgent: bool, max_tokens: int) -> None:
    """Registra ogni chiamata a Claude: esito, token, motivo di arresto. Se la risposta NON e' stata
    letta ne salva anche il testo, per capire perche' (es. tagliata dal limite di token).
    Solo registro: non influenza decisioni, budget o fallback, e non solleva mai."""
    try:
        u = usage if isinstance(usage, dict) else {}
        ev = {
            "ev": "claude_call", "ts": now_ms, "portfolio": PORTFOLIO.name, "run_no": state.get("run_no", 1),
            "ok": bool(parsed), "n_decisions": len(parsed["decisions"]) if parsed else None,
            "stop_reason": u.get("stop_reason"), "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"), "max_tokens": max_tokens, "cost_usd": round(cost, 5),
            "prompt_chars": prompt_chars, "reply_chars": len(text or ""), "n_positions": n_positions,
            "urgent_scalp": bool(urgent), "budget_spent": (state.get("budget") or {}).get("spent"),
        }
        if not parsed:
            ev["fail_reason"] = diagnose_reply(text)
            t = text or ""
            ev["reply"] = t if len(t) <= REPLY_KEEP_CHARS else t[:4000] + "\n[... omesso ...]\n" + t[-1500:]
        log_event(DATA_DIR, ev)
    except Exception:
        pass


def log_claude_error(now_ms: int, state: dict, exc: Exception, n_positions: int, urgent: bool) -> None:
    """Registra una chiamata a Claude fallita prima di avere una risposta (rete, errore API, bug nel prompt)."""
    try:
        log_event(DATA_DIR, {
            "ev": "claude_call", "ts": now_ms, "portfolio": PORTFOLIO.name, "run_no": state.get("run_no", 1),
            "ok": False, "fail_reason": "errore:" + type(exc).__name__, "error": str(exc)[:160],
            "n_positions": n_positions, "urgent_scalp": bool(urgent),
        })
    except Exception:
        pass


def flush_events(state: dict, acc: PaperAccount) -> None:
    """Scrive nel registro e notifica gli eventi del motore (seconda gamba eseguita o annullata)."""
    evs, acc.events = acc.events, []
    for ev in evs:
        log_event(DATA_DIR, {**ev, "portfolio": PORTFOLIO.name, "run_no": state.get("run_no", 1)})
        if ev.get("ev") == "split_fill":
            print(f"[SPLIT] {ev['symbol']} 2a gamba @{ev['price']:.5g}  entry medio {ev['entry_avg']:.5g}  "
                  f"margine tot {ev['total_margin']:.0f}$", flush=True)
            notify_split(ev["symbol"], ev["side"], ev["price"], ev["entry_avg"], ev["total_margin"])
        else:
            print(f"[SPLIT ANNULLATO] {ev.get('symbol')}: {ev.get('reason')}", flush=True)


def position_info(pos, price: float, readings: dict, now_ms: int) -> dict:
    r = readings.get(pos.symbol)
    return {
        "split_pending": pos.pending_split,
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
MANAGE_ACTIONS = ("close", "partial_close", "hold")   # unico che resta ammesso in pausa


def run_cycle(state: dict, now_ms: int, drain: bool = False) -> None:
    """Un ciclo di mercato.

    drain=True e' la PAUSA: le posizioni aperte continuano a essere gestite (stop loss,
    take profit, liquidazione e uscite decise da regole/Claude) ma non si apre nulla di
    nuovo e non si fanno DCA. Nessuna posizione viene chiusa a forza.
    """
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
        write_heartbeat(state, force=False)   # il ciclo puo' durare un minuto: il bot resta "vivo"

    print(f"[DESK V2] candles ok: {len(candles_map)}/{len(SYMBOLS)} simboli", flush=True)
    prices = get_prices(SYMBOLS, candles_map)
    # ultimi prezzi noti: la dashboard li usa come ripiego per il P&L live delle posizioni
    if prices:
        state["last_prices"] = {s: p for s, p in prices.items()}
        state["last_prices_ms"] = now_ms
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
    elif drain and not acc.positions:
        pass   # in pausa e senza posizioni non c'e' nulla da gestire: niente chiamate a Claude
    elif call_due and can_call(state, day):
        try:
            prompt = build_prompt(snap, readings_list, pos_info, headlines, lessons, ctx_for_prompt, sym_stats)
            text, usage = call_claude(SYSTEM, prompt, max_tokens=1100)
            cost = record_spend(state, day, usage)
            state["last_call_ms"] = now_ms
            parsed = parse_decisions(text)
            log_claude_call(now_ms, state, text, usage, cost, parsed, len(prompt),
                            len(acc.positions), urgent_scalp, 1100)
            if parsed:
                decisions = parsed["decisions"]
                source = "claude"
                print(f"[Claude] {len(decisions)} decisioni  costo {cost:.4f}$  "
                      f"budget usato {state['budget']['spent']:.3f}$ / {DAILY_CAP}$")
                if parsed.get("note"):
                    print(f"[Claude] Nota: {parsed['note']}")
        except Exception as e:
            print(f"[WARN] Claude non disponibile: {e}")
            log_claude_error(now_ms, state, e, len(acc.positions), urgent_scalp)

    if not decisions:
        decisions = rules_decisions(readings_list, pos_info, open_symbols, _ENTRY_SCORE_BASE)
        source = "rules"

    if not drain and os.path.exists(_flag("pause.flag")):
        drain = True   # pausa premuta mentre il ciclo era in corso: vale da subito
    if drain:
        # PAUSA: solo gestione delle posizioni esistenti. Ingressi e DCA sono scartati qui,
        # prima dell'esecuzione, qualunque sia la loro origine (Claude o regole).
        skipped = [d for d in decisions if d["action"] not in MANAGE_ACTIONS]
        decisions = [d for d in decisions if d["action"] in MANAGE_ACTIONS]
        if skipped:
            print(f"[PAUSA] {len(skipped)} nuovi ingressi/DCA ignorati: bot in pausa "
                  f"({len(acc.positions)} posizioni ancora da completare)", flush=True)

    # ---- esecuzione decisioni
    last_open_ms = state.get("last_open_ms", {})

    def _candidate(status: str, d: dict, price: float) -> None:
        """Registra un'apertura decisa ma NON eseguita, con le stesse feature di un'apertura vera:
        servono per etichettarne l'esito in seguito (come sarebbe andata). Mai bloccante."""
        try:
            s = d["symbol"]
            log_event(DATA_DIR, {
                "ev": "candidate", "status": status, "ts": now_ms, "portfolio": PORTFOLIO.name,
                "run_no": state.get("run_no", 1), "symbol": s, "price": price, "source": source,
                "side": 1 if str(d.get("action", "")).startswith("open_long") else -1,
                "features": build_features(s, readings_map.get(s), ctx_for_prompt, d, now_ms,
                                           readings_map.get("BTC")),
            }, candidate=True)
        except Exception:
            pass

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
                record_close(state, closed)

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
                record_close(state, partial)

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
            # normalizza: split -> azione base. Con _split il motore apre la prima gamba (50% del margine)
            # e tiene in attesa la seconda al ritracciamento (vedi PaperAccount.open / on_bar).
            is_split = act.endswith("_split")
            base_act = act.replace("_split", "")
            # cooldown per tipo
            trade_type = dec.get("trade_type", "medio")
            cooldown = SCALP_COOLDOWN_MS if trade_type == "scalp" else MEDIO_COOLDOWN_MS
            last_ts = last_open_ms.get(sym, 0)
            if now_ms - last_ts < cooldown:
                print(f"[COOLDOWN] {sym} ({trade_type})")
                _candidate("cooldown", dec, px)
                continue
            if sym in acc.positions:
                continue
            # soglia confidenza tier-aware
            if dec["confidence"] < tier_entry_score(sym):
                print(f"[CONF_LOW] {sym} conf={dec['confidence']} < soglia={tier_entry_score(sym)}")
                _candidate("conf_bassa", dec, px)
                continue
            # filtro R:R minimo 1.5 — se SL e TP sono entrambi definiti
            sl_pct = dec.get("stop_loss_pct", 0)
            tp_pct = dec.get("take_profit_pct", 0)
            if sl_pct > 0 and tp_pct > 0:
                rr = tp_pct / sl_pct
                if rr < 1.5:
                    print(f"[RR_LOW] {sym} R:R={rr:.2f} < 1.5 (SL={sl_pct:.2%} TP={tp_pct:.2%})")
                    _candidate("rr_basso", dec, px)
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
            # valori su cui si decide, registrati con l'apertura (e con i candidati scartati)
            try:
                feats = build_features(sym, readings_map.get(sym), ctx_for_prompt, dec, now_ms,
                                       readings_map.get("BTC"))
            except Exception:
                feats = {}   # la registrazione non deve mai impedire un'apertura
            feats.update(proposed_margin=raw_margin, proposed_lev=raw_lev, split_requested=is_split,
                          guardrail_forced=bool(raw_margin != dec["margin_usd"] or raw_lev != dec["leverage"]))
            split_cfg = None
            if is_split:
                retr = float(dec.get("split_retrace_pct") or 0.0)   # frazione (0.005 = 0,5%)
                if not 0.002 <= retr <= 0.012:
                    retr = 0.005                                    # valore predefinito: 0,5%
                split_cfg = {"retrace_pct": retr, "first_frac": 0.5}
            pos, msg = acc.open(
                sym, side, dec["margin_usd"], dec["leverage"], px, sl, tp, now_ms, prices,
                confidence=dec["confidence"], reason=dec.get("reason", "")[:200],
                source=source, trade_type=trade_type, features=feats, split=split_cfg,
            )
            if pos:
                last_open_ms[sym] = now_ms
                rr_str = f"  R:R 1:{tp_pct/sl_pct:.1f}" if sl_pct > 0 and tp_pct > 0 else ""
                ps = pos.pending_split
                split_str = ""
                if is_split and ps:
                    split_str = f"  [1a gamba, 2a @{ps['trigger']:.5g} {ps['margin']:.0f}$]"
                elif is_split:
                    split_str = "  [split non applicato: ingresso unico]"
                print(f"[OPEN] {sym} {'LONG' if side == 1 else 'SHORT'} {trade_type.upper()} "
                      f"lev {pos.leverage}x  margin {pos.total_margin:.0f}$  "
                      f"@{px:.5g}  SL {sl:.5g}  conf {dec['confidence']}  src {source}{rr_str}{split_str}")
                notify_open(sym, side, px, pos.leverage, pos.total_margin,
                            trade_type, dec["confidence"], source,
                            ("[1ª gamba] " if ps else "") + dec.get("reason", "")[:110])
                log_event(DATA_DIR, {
                    "ev": "open", "ts": now_ms, "id": pos.id, "portfolio": PORTFOLIO.name,
                    "run_no": state.get("run_no", 1), "symbol": sym, "side": side, "price": px,
                    "entry": pos.entry, "sl": pos.sl, "tp": pos.tp, "leverage": pos.leverage,
                    "margin_first": pos.total_margin, "risk_plan_usd": pos.risk_plan_usd,
                    "r_dist": pos.r_dist, "trade_type": trade_type, "source": source,
                    "confidence": dec["confidence"], "split_plan": ps, "features": feats,
                })
            else:
                print(f"[SKIP] {sym} {act}: {msg}")
                _candidate("rifiutata:" + str(msg)[:60], dec, px)

        elif act == "hold":
            # aggiorna last_review_ms per lo scalp
            pos = acc.positions.get(sym)
            if pos:
                pos.last_review_ms = now_ms

    state["last_open_ms"] = last_open_ms
    flush_events(state, acc)

    # In pausa non entra nulla di nuovo: nemmeno la seconda gamba di un'entrata diversificata.
    if drain:
        for s in list(acc.positions):
            acc.cancel_split(s, "bot in pausa", now_ms)

    # ---- processa barre (stop, liq, tp automatici; seconda gamba al ritracciamento)
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
                record_close(state, result)
                break
    flush_events(state, acc)

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


# ──────────────────────────────────────────────────────────────────────────────
# COMANDI DALL'APP (file-flag) E CICLO PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────
def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _set_last_action(state: dict, kind: str, ok: bool, detail: str = "", **extra) -> None:
    """Esito dell'ultimo comando ricevuto dall'app: l'app lo mostra all'utente."""
    state["last_action"] = {"type": kind, "ok": ok, "detail": detail,
                            "ts": int(time.time() * 1000), **extra}


def _check_budget_reset_flag(state: dict) -> bool:
    """budget_reset.flag: azzera SOLO il budget giornaliero di Claude (il conto non si tocca).
    Il vecchio contenuto 'equity_reset' viene ignorato: azzerare il conto ha un comando suo."""
    path = _flag("budget_reset.flag")
    if not os.path.exists(path):
        return False
    try:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        state["budget"] = {"day": day, "spent": 0.0, "calls": 0}
        state["last_call_ms"] = 0   # permette una nuova chiamata a Claude al prossimo ciclo
        save_state(state, STATE_FILE)
        print("[BUDGET_RESET] budget giornaliero di Claude azzerato (conto invariato)", flush=True)
        return True
    except Exception as e:
        print(f"[BUDGET_RESET ERROR] {e}", flush=True)
        return False
    finally:
        _remove(path)


def _market_prices(symbols: list, state: dict) -> dict:
    """Ultimo prezzo di mercato per i simboli indicati (candela 15m piu' recente)."""
    px: dict = {}
    for s in symbols:
        arr = fetch_candles(s, "15m", 3)
        if arr:
            px[s] = arr[-1][4]
    for s in symbols:
        if s not in px and (state.get("last_prices") or {}).get(s):
            px[s] = state["last_prices"][s]
    return px


def _check_close_all_flag(state: dict) -> bool:
    """reset.flag = 'chiudi tutto': chiude ogni posizione al PREZZO DI MERCATO, con commissioni,
    slippage e funding reali, e registra i trade nello storico. Se per un simbolo non c'e' un
    prezzo la posizione resta aperta (meglio che inventare un'uscita) e l'esito lo dice."""
    path = _flag("reset.flag")
    if not os.path.exists(path):
        return False
    try:
        acc = make_account(state)
        if not acc.positions:
            _set_last_action(state, "close_all", True, "nessuna posizione aperta")
            save_state(state, STATE_FILE)
            return True
        now_ms = int(time.time() * 1000)
        prices = _market_prices(list(acc.positions), state)
        closed_n, skipped, net = 0, [], 0.0
        for sym in list(acc.positions):
            px = prices.get(sym)
            if px is None:
                skipped.append(sym)
                continue
            rec = acc.close(sym, px, now_ms, "chiusura manuale")
            if rec:
                record_close(state, rec)
                closed_n += 1
                net += rec["net"]
        flush_events(state, acc)
        save_account(acc, state)
        detail = f"chiuse {closed_n} posizioni (netto {net:+.2f}$)"
        if skipped:
            detail += f"; prezzo non disponibile per {', '.join(skipped)}: ancora aperte, riprova"
        _set_last_action(state, "close_all", not skipped, detail, closed=closed_n, skipped=skipped)
        save_state(state, STATE_FILE)
        print(f"[CHIUDI TUTTO] {detail}", flush=True)
        return True
    except Exception as e:
        print(f"[CHIUDI TUTTO ERROR] {e}", flush=True)
        traceback.print_exc()
        return False
    finally:
        _remove(path)


def run_params() -> dict:
    """I parametri con cui gira questo portafoglio (finiscono nel riepilogo di ogni run archiviata)."""
    from dataclasses import asdict
    p = PORTFOLIO
    return {
        "portfolio": p.name, "code_version": CODE_VERSION, "limits": asdict(p.limits),
        "entry_score_base": _ENTRY_SCORE_BASE, "entry_score_tier_ab": 60, "entry_score_tier_c": 70,
        "guardrail": {"min_margin": p.guardrail_min_margin, "min_lev": p.guardrail_min_lev,
                      "margin_forced": p.guardrail_margin_forced, "lev_forced": p.guardrail_lev_forced,
                      "type_forced": p.guardrail_type_forced},
        "daily_cap_usd": DAILY_CAP,
        "split": {"first_frac": 0.5, "default_retrace_pct": 0.5, "min_retrace_pct": 0.15,
                  "max_of_stop_distance": 0.6, "ttl_scalp_h": 3, "ttl_medio_h": 12},
    }


def summarize_run(state: dict, acc: PaperAccount, now_ms: int) -> dict:
    closed = list(acc.closed)
    nets = [float(c.get("net", 0)) for c in closed]
    wins = [n for n in nets if n > 0]
    by_type: dict = {}
    for c in closed:
        t = by_type.setdefault(c.get("trade_type", "?"), {"n": 0, "net": 0.0})
        t["n"] += 1
        t["net"] = round(t["net"] + float(c.get("net", 0)), 4)
    start = float(acc.limits.start_equity)
    return {
        "run_no": state.get("run_no", 1),
        "portfolio": PORTFOLIO.name,
        "started_ms": state.get("run_started_ms") or (min((c["open_ms"] for c in closed), default=now_ms)),
        "ended_ms": now_ms,
        "start_equity": start,
        "end_equity": round(acc.cash, 2),
        "pnl": round(acc.cash - start, 2),
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(nets) - len(wins),
        "win_rate": round(len(wins) / len(nets) * 100, 1) if nets else 0.0,
        "net_total": round(sum(nets), 2),
        "fees_total": round(sum(float(c.get("fees", 0)) for c in closed), 2),
        "best": round(max(nets), 2) if nets else 0.0,
        "worst": round(min(nets), 2) if nets else 0.0,
        "by_type": by_type,
        "params": run_params(),
    }


def _archive_run(state: dict, acc: PaperAccount, clear_lessons: bool) -> str:
    """Salva la run corrente in archive/<data-ora>/ (storico trade, stato, appunti, riepilogo,
    parametri). Ritorna il nome della cartella. Se qualcosa fallisce solleva: il reset NON parte."""
    import shutil
    now_ms = int(time.time() * 1000)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now_ms / 1000))
    root = os.path.join(DATA_DIR, "archive")
    name, n = stamp, 1
    while os.path.exists(os.path.join(root, name)):
        n += 1
        name = f"{stamp}-{n}"
    dest = os.path.join(root, name)
    os.makedirs(dest)
    with open(os.path.join(dest, "state_v2.json"), "w") as f:
        json.dump(state, f, default=str)
    hist = os.path.join(DATA_DIR, "trade_history.jsonl")
    if os.path.exists(hist):
        shutil.copy2(hist, os.path.join(dest, "trade_history.jsonl"))
    for fn in ("lessons.md", "errors.md"):
        src = os.path.join(DATA_DIR, fn)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, fn))
    summary = summarize_run(state, acc, now_ms)
    summary["archive"] = name
    summary["lessons_cleared"] = clear_lessons
    with open(os.path.join(dest, "summary.json"), "w") as f:
        json.dump(summary, f, default=str, indent=1)
    return name


def _check_portfolio_reset_flag(state: dict) -> bool:
    """reset_portfolio.flag: archivia la run e riparte da 1000$ con i parametri del codice.
    Regole (controllate anche qui, non solo dall'app): il bot deve essere IN PAUSA e senza
    posizioni aperte. Dopo il reset resta in pausa: sei tu a premere Avvia."""
    path = _flag("reset_portfolio.flag")
    if not os.path.exists(path):
        return False
    try:
        try:
            with open(path) as f:
                opts = json.loads(f.read() or "{}")
        except Exception:
            opts = {}
        clear_lessons = bool(opts.get("clear_lessons")) if isinstance(opts, dict) else False
        if not os.path.exists(_flag("pause.flag")):
            _set_last_action(state, "reset_portfolio", False, "rifiutato: il bot non e' in pausa")
            save_state(state, STATE_FILE)
            print("[RESET PORTAFOGLIO] rifiutato: bot non in pausa", flush=True)
            return False
        acc = make_account(state)
        if acc.positions:
            _set_last_action(state, "reset_portfolio", False,
                             f"rifiutato: {len(acc.positions)} posizioni ancora aperte")
            save_state(state, STATE_FILE)
            print("[RESET PORTAFOGLIO] rifiutato: posizioni aperte", flush=True)
            return False
        archive = _archive_run(state, acc, clear_lessons)   # se fallisce, non si cancella nulla
        # solo ora lo storico della run corrente si sposta (la copia e' gia' in archivio)
        _remove(os.path.join(DATA_DIR, "trade_history.jsonl"))
        if clear_lessons:
            _remove(os.path.join(DATA_DIR, "lessons.md"))
            _remove(os.path.join(DATA_DIR, "errors.md"))
        now_ms = int(time.time() * 1000)
        keep = {k: state[k] for k in ("budget", "last_call_ms", "market_ctx", "last_ctx_ts",
                                      "last_report_day", "last_prices", "last_prices_ms")
                if k in state}
        if not clear_lessons and "lessons_day" in state:
            keep["lessons_day"] = state["lessons_day"]
        run_no = int(state.get("run_no", 1)) + 1
        state.clear()
        state.update(keep)
        state["main"] = PaperAccount(PORTFOLIO.limits, "main").to_dict()
        state.update(run_no=run_no, run_started_ms=now_ms, paused=True, mode="paused")
        _set_last_action(state, "reset_portfolio", True,
                         f"portafoglio ripartito da {PORTFOLIO.limits.start_equity:.0f}$; run precedente archiviata",
                         archive=archive)
        save_state(state, STATE_FILE)
        print(f"[RESET PORTAFOGLIO] run archiviata in {archive}; conto a "
              f"{PORTFOLIO.limits.start_equity:.0f}$, bot in pausa", flush=True)
        return True
    except Exception as e:
        print(f"[RESET PORTAFOGLIO ERROR] {e}", flush=True)
        traceback.print_exc()
        _set_last_action(state, "reset_portfolio", False, f"errore: {e}")
        try:
            save_state(state, STATE_FILE)
        except Exception:
            pass
        return False
    finally:
        _remove(path)


def process_flags(state: dict) -> None:
    """Esegue i comandi arrivati dall'app. L'ordine conta: budget, chiudi tutto, reset conto."""
    _check_budget_reset_flag(state)
    _check_close_all_flag(state)
    _check_portfolio_reset_flag(state)


def iteration(state: dict, drain: bool = False) -> bool:
    """Un ciclo di mercato. Ritorna True se e' andato a buon fine."""
    now_ms = int(time.time() * 1000)
    HB.update(last_start_ms=now_ms)
    write_heartbeat(state, cycle_running=True)
    ok = True
    try:
        run_cycle(state, now_ms, drain=drain)
        HB.update(last_ok=True, last_error="")
    except Exception as e:
        ok = False
        traceback.print_exc()
        HB.update(last_ok=False, last_error=f"{type(e).__name__}: {e}"[:300])
    HB.update(last_end_ms=int(time.time() * 1000), cycles=HB.get("cycles", 0) + 1)
    write_heartbeat(state, cycle_running=False)
    return ok


def cycle_interval_s(state: dict, paused: bool) -> int:
    """Pausa con posizioni aperte (svuotamento) o scalp aperto: si guarda piu' spesso."""
    acc = make_account(state)
    if any(p.trade_type == "scalp" for p in acc.positions.values()):
        return CYCLE_FAST_S
    if paused and acc.positions:
        return CYCLE_FAST_S
    return CYCLE_S


def sync_mode(state: dict) -> str:
    """Tiene state['paused'/'mode'] allineati a pause.flag + posizioni; salva solo se cambia."""
    paused = os.path.exists(_flag("pause.flag"))
    mode = compute_mode(paused, len((state.get("main") or {}).get("positions") or {}))
    if state.get("paused") != paused or state.get("mode") != mode:
        state["paused"], state["mode"] = paused, mode
        save_state(state, STATE_FILE)
        print(f"[MODO] {mode}", flush=True)
    return mode


def loop_step(state: dict, ctl: dict) -> bool:
    """Un giro del ciclo principale (ogni POLL_S secondi). ctl tiene la memoria tra un giro e l'altro:
    {'next_cycle_ms': int, 'prev_paused': bool|None}. Ritorna True se in questo giro e' girato un ciclo
    di mercato.

    - i comandi dell'app (chiudi tutto, azzera budget, azzera portafoglio) si eseguono subito;
    - premere Pausa o Avvia fa partire un ciclo immediato (non si aspetta il prossimo giro);
    - in pausa il bot continua a girare finche' ha posizioni aperte (svuotamento), poi si ferma da solo.
    """
    process_flags(state)
    paused = os.path.exists(_flag("pause.flag"))
    if paused != ctl.get("prev_paused"):
        if ctl.get("prev_paused") is not None:
            print("[PAUSA] richiesta di pausa: finisco le posizioni aperte, nessun nuovo ingresso"
                  if paused else "[AVVIO] ripresa richiesta: il bot lavora", flush=True)
            ctl["next_cycle_ms"] = 0   # reagisce subito al tasto, senza aspettare il prossimo ciclo
        ctl["prev_paused"] = paused
    n_open = len((state.get("main") or {}).get("positions") or {})
    ran = False
    if int(time.time() * 1000) >= ctl.get("next_cycle_ms", 0) and not (paused and n_open == 0):
        ok = iteration(state, drain=paused)
        wait = cycle_interval_s(state, paused) if ok else RETRY_S
        ctl["next_cycle_ms"] = int(time.time() * 1000) + wait * 1000
        print(f"[SLEEP] prossimo ciclo tra {wait // 60} min", flush=True)
        ran = True
    mode = sync_mode(state)
    write_heartbeat(state, next_cycle_ms=0 if mode == "paused" else ctl.get("next_cycle_ms", 0))
    return ran


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    state = load_state(STATE_FILE)

    if "--once" in sys.argv:
        process_flags(state)
        iteration(state, drain=os.path.exists(_flag("pause.flag")))
        return

    print(f"[DESK V2] avvio [{PORTFOLIO.name.upper()}] versione {CODE_VERSION} — {PORTFOLIO.description}")
    print(f"[DESK V2] simboli: {len(SYMBOLS)}  "
          f"entry_score=60(TIER_AB)/70(TIER_C)  "
          f"daily_cap={DAILY_CAP}$  data={DATA_DIR}")
    ctl = {"next_cycle_ms": 0, "prev_paused": None}
    while True:
        try:
            loop_step(state, ctl)
        except Exception:
            traceback.print_exc()
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
