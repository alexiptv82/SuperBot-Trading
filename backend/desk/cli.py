"""Loop principale V2: DCA, contesto di mercato, scalp vs medio, top-30 CMC.

Differenze chiave rispetto a V1:
- Simboli espansi (fino a 30 top-CMC + XAU/XAG)
- Contesto di mercato (funding/OI/notizie) aggiornato ogni 30 minuti
- Logica DCA: se Claude propone "dca" su una posizione aperta, si esegue
- Scalp vs medio: scalp ha cooldown ridotto e revisione più frequente
- Claude chiamato ogni ora (o prima per scalp)
- Budget giornaliero 0.70$ con DAILY_CAP dalla variabile d'ambiente
- Calendario di Claude (claude_schedule.json): se presente, Claude e' consultato solo nelle finestre indicate,
  ognuna con il suo budget; fuori finestra decidono le regole. Senza file vale il budget giornaliero di sempre.
- Dual portfolio: --portfolio hawk (default) | bull
"""
from __future__ import annotations

import json
import math
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
from desk import learning as _learning
from desk.learning import build_features, log_event
from desk.schedule import schedule_state, summary as schedule_summary
from desk.notifier import (notify_open, notify_close, notify_dca, notify_split,
                           notify_halt, notify_daily_report)
from desk.live_connector import LiveConnector


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


def _rc84_paper_classic_entry_policy(portfolio: str, source: str, decisions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Make PAPER classic entry origins/horizons independent without altering exits.

    Falco: scalp-only LONG or SHORT, including the rules fallback.
    Toro: AI-selected medium-term LONG or SHORT, never shared rules entries.
    Unrecognized sources/portfolios cannot create new PAPER exposure.
    Management (close/hold/partial/DCA) is preserved unchanged; normal risk,
    existing positions, stop and S25 time-exit handling remain separate.
    """
    entries = {"open_long", "open_short", "open_long_split", "open_short_split"}
    kept, rejected = [], []
    for decision in decisions:
        if decision.get("action") not in entries:
            kept.append(decision)
            continue
        horizon = decision.get("trade_type")
        allowed = (
            (portfolio == "hawk" and horizon == "scalp" and source in {"claude", "rules"})
            or (portfolio == "bull" and horizon == "medio" and source == "claude")
        )
        (kept if allowed else rejected).append(decision)
    return kept, rejected

# Tier A/B: BTC, ETH, XAU, XAG → soglia 60
# Tier C: tutti gli altri altcoin → soglia 70
_TIER_AB = {"BTC", "ETH", "XAU", "XAG"}


def tier_entry_score(symbol: str) -> int:
    """Restituisce la soglia di confidenza minima per aprire un trade su questo simbolo."""
    return 60 if symbol.upper() in _TIER_AB else 70


# Contratto dichiarato nei prompt (SYSTEM_HAWK/SYSTEM_BULL) che il motore NON applica oggi. Solo per il confronto
# in ombra (policy_shadow_violations): nessun valore qui cambia una decisione. Le modifiche di policy sono proposte a
# parte in docs/v3/RC84-FASE2-MOTORE-SEGNALI.md e richiedono l'approvazione dell'utente.
PROMPT_MIN_RR = 2.0
PROMPT_BULL_CONF = {"tier_a": 65, "altri": 75}
PROMPT_BULL_MIN_TP = 0.05


def policy_shadow_violations(dec: dict, portfolio, symbol: str) -> list:
    """Scostamenti di una decisione d'apertura dal contratto del prompt che il motore lascerebbe passare."""
    out = []
    sl, tp = float(dec.get("stop_loss_pct") or 0), float(dec.get("take_profit_pct") or 0)
    if tp <= 0:
        out.append("tp_assente: filtro R:R non applicato, nessun target")
    elif sl > 0 and tp / sl < PROMPT_MIN_RR:
        out.append("rr_%.2f_sotto_%.1f_del_prompt" % (tp / sl, PROMPT_MIN_RR))
    if sl <= 0:
        out.append("sl_assente: usato quello del segnale")
    name = getattr(portfolio, "name", "")
    if name == "bull":
        need = PROMPT_BULL_CONF["tier_a"] if symbol.upper() in _TIER_AB else PROMPT_BULL_CONF["altri"]
        if float(dec.get("confidence") or 0) < need:
            out.append("confidenza_%s_sotto_%d_del_prompt_toro" % (dec.get("confidence"), need))
        if 0 < tp < PROMPT_BULL_MIN_TP:
            out.append("tp_%.2f%%_sotto_5%%_del_prompt_toro" % (tp * 100))
    m, lev = float(dec.get("margin_usd") or 0), float(dec.get("leverage") or 0)
    if m < getattr(portfolio, "guardrail_min_margin", 0) or lev < getattr(portfolio, "guardrail_min_lev", 0):
        out.append("guardrail_alza_margine_leva: %.0f$/%gx -> %.0f$/%sx" % (
            m, lev, getattr(portfolio, "guardrail_margin_forced", 0), getattr(portfolio, "guardrail_lev_forced", "?")))
    return out
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
PAPER_BAR_MS = 900_000     # candele su cui Falco e Toro controllano stop, target e liquidazione
CODE_VERSION = os.getenv("DESK_CODE_VERSION", "dev")
CLOSE_POSITION_MAX_AGE_S = 600   # max age for PAPER close request

# Connettore live — no-op in paper mode, attivo se DESK_MODE=live
# Lancia ValueError all'avvio se le chiavi API mancano in modalità live
LIVE = LiveConnector(data_dir=DATA_DIR)

# ── Limite perdita giornaliero (solo in modalità live) ───────────────────────
# DESK_HAWK_CAPITAL / DESK_BULL_CAPITAL: capitale allocato a ogni portafoglio (USDT)
# DESK_DAILY_LOSS_PCT: percentuale massima di perdita giornaliera (default 25%)
# Esempio: capitale $1500, pct 25% → massima perdita $375/giorno
_PORTFOLIO_CAPITAL = float(os.getenv(
    f"DESK_{PORTFOLIO.name.upper()}_CAPITAL",
    os.getenv("DESK_PORTFOLIO_CAPITAL", "1500")
))
_DAILY_LOSS_PCT = float(os.getenv("DESK_DAILY_LOSS_PCT", "25")) / 100.0
_DAILY_LOSS_LIMIT = _PORTFOLIO_CAPITAL * _DAILY_LOSS_PCT

print(f"[CAPITAL] {PORTFOLIO.name.upper()} capitale={_PORTFOLIO_CAPITAL:.0f}$ "
      f"limite_perdita_giornaliero={_DAILY_LOSS_LIMIT:.0f}$ ({_DAILY_LOSS_PCT*100:.0f}%)", flush=True)


# ── Interruttore manuale trading (solo live) ──────────────────────────────────
# In live mode il bot parte con trading DISABILITATO: sei tu a premere "Avvia trading"
# nell'app. In paper mode l'interruttore non ha effetto (il paper gira sempre).
# Il flag viene persistito in trading_enabled.json nel volume dati del bot.
_TRADING_ENABLED_FILE = os.path.join(DATA_DIR, "trading_enabled.json")


def is_trading_enabled() -> bool:
    """True se l'interruttore manuale è attivo (o se siamo in paper mode)."""
    if not LIVE._live:
        return True   # paper mode: sempre abilitato
    try:
        with open(_TRADING_ENABLED_FILE) as f:
            return bool(json.load(f).get("enabled", False))
    except Exception:
        return False  # file assente o corrotto → disabilitato per sicurezza


def set_trading_enabled(enabled: bool) -> None:
    """Scrive il flag in modo atomico."""
    tmp = _TRADING_ENABLED_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"enabled": enabled, "ts": int(time.time() * 1000)}, f)
    os.replace(tmp, _TRADING_ENABLED_FILE)
    print(f"[TRADING] {PORTFOLIO.name.upper()} trading "
          f"{'ABILITATO ▶' if enabled else 'DISABILITATO ⏹'}", flush=True)


def _daily_realized_pnl(acc) -> float:
    """Calcola il P&L realizzato oggi (dalla mezzanotte UTC)."""
    import time as _time
    midnight_ms = int(_time.time() // 86400 * 86400 * 1000)
    return sum(
        c.get("net", 0.0)
        for c in (acc.closed or [])
        if (c.get("close_ms") or 0) >= midnight_ms
    )


def _daily_loss_exceeded(acc) -> bool:
    """
    True se la perdita realizzata oggi supera il limite configurato.
    Attivo solo in modalità live — in paper mode non blocca mai.
    """
    if not LIVE._live:
        return False
    pnl = _daily_realized_pnl(acc)
    if pnl <= -_DAILY_LOSS_LIMIT:
        print(f"[DAILY LOSS LIMIT] {PORTFOLIO.name.upper()} perdita oggi={pnl:+.2f}$ "
              f"≥ limite {_DAILY_LOSS_LIMIT:.0f}$ — nessuna nuova apertura per oggi", flush=True)
        return True
    return False


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


# ---- barre native 4h e 1d (tendenze EMA50/EMA200 vere su barre chiuse; vedi desk/signals.py)
HTF_SPECS = (("4h", "4H", 14_400_000), ("1d", "1Dutc", 86_400_000))   # 1Dutc: giornata 00:00-24:00 UTC
_HTF_CACHE: dict = {}


def fetch_htf(sym: str, now_ms: int, fetch=None) -> dict:
    """{"4h": array|None, "1d": array|None}. Si riscarica un timeframe solo quando e' terminata una barra piu' recente
    di quella in cache: al massimo una richiesta ogni 4 ore (4h) e una al giorno (1d) per simbolo. Un errore di rete
    lascia None (o l'ultima serie buona, che signals.py dichiarera' UNKNOWN se ormai vecchia): mai dati inventati."""
    import numpy as np
    fetch = fetch or fetch_candles
    out = {}
    for key, gran, period in HTF_SPECS:
        cached = _HTF_CACHE.get((sym, key))
        expected_last_close = now_ms - now_ms % period            # fine dell'ultima barra che dovrebbe essere chiusa
        if cached is not None and cached[1] >= expected_last_close:
            out[key] = cached[0]
            continue
        rows = fetch(sym, gran, 1000)
        if rows:
            arr = np.array(rows, dtype=float)
            closed = arr[arr[:, 0] + period <= now_ms]
            newest_close = int(closed[-1, 0]) + period if len(closed) else 0
            _HTF_CACHE[(sym, key)] = (arr, newest_close)
            out[key] = arr
        else:
            out[key] = cached[0] if cached is not None else None
    return out


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
            "next_cycle_ms": 0,
            # Dice all'app che questa versione sa chiudere una singola posizione su richiesta dell'utente.
            # Con un bot piu' vecchio il tasto non appare (il comando resterebbe in attesa e scatterebbe dopo).
            "close_position": not LIVE._live}
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
    HB["trading_enabled"] = is_trading_enabled()
    HB["exec_mode"] = "live" if LIVE._live else "paper"   # come gira DAVVERO il bot (l'app lo mostra)
    try:
        HB["claude_schedule"] = schedule_summary(schedule_state(DATA_DIR, int(now * 1000)))
    except Exception:
        pass   # il calendario non deve mai fermare il bot
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


def _has_close_row(path: str, rec: dict, *, learning: bool, run_no) -> bool:
    """True se il registro contiene gia' ESATTAMENTE questa chiusura (finale o parziale). Sola lettura."""
    partial = bool(rec.get("partial"))
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if _close_row_matches(row, rec, learning=learning, run_no=run_no, partial=partial):
                    return True
    except OSError:
        return False
    return False


def record_close(state: dict, rec: dict) -> None:
    """Ogni chiusura (finale o parziale) va nello storico dei trade e nel registro di apprendimento."""
    append_trade_history(DATA_DIR, rec)
    row = dict(rec)
    row["reason"] = str(row.get("reason", ""))[:200]
    log_event(DATA_DIR, {"ev": "close", "ts": rec.get("close_ms"), "portfolio": PORTFOLIO.name,
                         "run_no": state.get("run_no", 1), **row})


# ---- Chiusure PAPER non protettive (regole/Claude, manuale, parziale, S25): commit in due fasi.
# 1) conto + claim (record esatto) salvati insieme; 2) storico e learning scritti DAL claim, mai ricalcolati;
# 3) claim rimosso e stato risalvato. Telegram solo dopo il passo 3. Un riavvio completa il claim con lo
# stesso record: nessun secondo fill della stessa posizione. Registri append-only, mai riscritti.
CLAIMS_KEY = "paper_close_claims"


def _close_claim_id(rec: dict, run_no) -> str:
    kind = f"partial:{rec.get('fraction')}" if rec.get("partial") else "terminal"
    return "|".join(str(x) for x in (run_no, rec.get("symbol"), rec.get("id"), rec.get("open_ms"),
                                       rec.get("close_ms"), kind, repr(_proof_value(rec, "net"))))


def _claim_paper_close(state: dict, rec: dict, notice=None) -> None:
    run_no = state.get("run_no", 1)
    claims = state.setdefault(CLAIMS_KEY, [])
    cid = _close_claim_id(rec, run_no)
    if not any(c.get("claim_id") == cid for c in claims):
        claims.append({"claim_id": cid, "run_no": run_no, "rec": dict(rec),
                       "notice": list(notice) if notice else None})


def _terminal_already_logged(state: dict, pos) -> bool:
    """Una chiusura terminale di QUESTA posizione (stessa run) e' gia' nei registri mentre il conto la tiene aperta."""
    if pos is None:
        return False
    run_no = state.get("run_no", 1)
    ident = {"symbol": getattr(pos, "symbol", None), "id": pos.id, "open_ms": pos.open_ms, "side": pos.side}
    for name, learning in (("trade_history.jsonl", False), ("learning_log.jsonl", True)):
        try:
            with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row, dict) or row.get("partial"):
                        continue
                    if learning and (row.get("ev") != "close" or row.get("run_no") != run_no):
                        continue
                    if "run_no" in row and row.get("run_no") != run_no:
                        continue
                    if all(row.get(k) == v for k, v in ident.items()):
                        return True
        except OSError:
            continue
    return False


def _note_close_block(sym: str, why: str) -> None:
    blocked = HB.setdefault("paper_close_blocked", [])
    if sym not in blocked:
        blocked.append(sym)
    print(f"[CHIUSURA BLOCCATA] {sym}: {why}", flush=True)


def _learning_close_row(rec: dict, run_no) -> dict:
    row = dict(rec)
    row["reason"] = str(row.get("reason", ""))[:200]
    return {"ev": "close", "ts": rec.get("close_ms"), "portfolio": PORTFOLIO.name, "run_no": run_no, **row}


def _prove_claimed_close(rec: dict, run_no) -> str:
    """proven, pending (registro non scrivibile/leggibile) o conflict (terminale incompatibile gia' presente)."""
    history = os.path.join(DATA_DIR, "trade_history.jsonl")
    learning = os.path.join(DATA_DIR, "learning_log.jsonl")
    if rec.get("partial"):
        # Una parziale ha identita' propria (close_ms, fraction, net): un terminale successivo della stessa
        # posizione non la contraddice. Il terminale PRECEDENTE e' gia' rifiutato prima di eseguirla.
        if not _has_close_row(history, rec, learning=False, run_no=run_no):
            append_trade_history(DATA_DIR, rec)
        if not _has_close_row(learning, rec, learning=True, run_no=run_no):
            log_event(DATA_DIR, _learning_close_row(rec, run_no))
        ok = (_has_close_row(history, rec, learning=False, run_no=run_no)
              and _has_close_row(learning, rec, learning=True, run_no=run_no))
        return "proven" if ok else "pending"
    hist = _scan_close(history, rec, learning=False, run_no=run_no)
    learn = _scan_close(learning, rec, learning=True, run_no=run_no)
    if "conflict" in (hist, learn):
        return "conflict"
    if "unreadable" in (hist, learn):
        return "pending"
    if hist == "absent":
        append_trade_history(DATA_DIR, rec)
    if learn == "absent":
        log_event(DATA_DIR, _learning_close_row(rec, run_no))
    ok = (_scan_close(history, rec, learning=False, run_no=run_no) == "match"
          and _scan_close(learning, rec, learning=True, run_no=run_no) == "match")
    return "proven" if ok else "pending"


def _commit_paper_closes(state: dict) -> list:
    """Salva lo stato; se ci sono claim li prova nei registri, rimuove i provati e risalva; poi Telegram.
    Senza claim equivale a save_state (comportamento LIVE invariato)."""
    save_state(state, STATE_FILE)                       # fase 1: conto e claim insieme, o nulla
    claims = list(state.get(CLAIMS_KEY) or [])
    if not claims:
        if not LIVE._live:
            HB["paper_close_claims"] = {"pending": 0, "conflict": []}
        return []
    proven, conflict = [], []
    for claim in claims:
        status = _prove_claimed_close(claim["rec"], claim["run_no"])
        claim["status"] = status
        if status == "proven":
            proven.append(claim)
        elif status == "conflict":
            conflict.append(claim["claim_id"])
            print(f"[REGISTRO INCOERENTE] {claim['claim_id']}: terminale diverso gia' presente, nulla scritto",
                  flush=True)
    remaining = [c for c in claims if c not in proven]
    HB["paper_close_claims"] = {"pending": len(remaining) - len(conflict), "conflict": conflict}
    if proven:
        state[CLAIMS_KEY] = remaining
        try:
            save_state(state, STATE_FILE)               # fase 3: chiusure definitive
        except BaseException:
            state[CLAIMS_KEY] = claims                  # un salvataggio successivo non deve rendere definitivo cio' che non lo e'
            raise
        for claim in proven:                            # Telegram: informativo, al massimo una volta
            if claim.get("notice"):
                try:
                    notify_close(claim["rec"].get("symbol"), claim["rec"].get("net"), *claim["notice"])
                except Exception:
                    pass
    return proven


CLAIM_RECOVERY_S = 60   # tentativo di riconciliazione non aggressivo, indipendente dal mercato


def _unresolved_claims(state: dict) -> list:
    return list(state.get(CLAIMS_KEY) or []) if not LIVE._live else []


def _settle_claims_now(state: dict, acc) -> bool:
    """Subito dopo una chiusura PAPER non protettiva: checkpoint del conto + prova dei registri.
    True se nessun claim e' rimasto irrisolto (percorso sano: il ciclo prosegue come prima)."""
    if LIVE._live:
        return True
    save_account(acc, state)
    _commit_paper_closes(state)
    return not _unresolved_claims(state)


def _recover_paper_claims(state: dict, ctl: dict) -> bool:
    """Completa i claim sospesi anche con bot in pausa e senza posizioni. Nessun mercato, nessun trade.
    Al piu' un tentativo ogni CLAIM_RECOVERY_S secondi; un errore non ferma il ciclo principale."""
    if not _unresolved_claims(state):
        return False
    now = int(time.time() * 1000)
    if now < ctl.get("claims_retry_ms", 0):
        return False
    ctl["claims_retry_ms"] = now + CLAIM_RECOVERY_S * 1000
    try:
        _commit_paper_closes(state)
    except Exception as e:
        HB["paper_close_claims_error"] = type(e).__name__
        print(f"[CLAIM] riconciliazione rimandata: {type(e).__name__}", flush=True)
        return False
    HB.pop("paper_close_claims_error", None)
    return True


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


def apply_claude_schedule(state: dict, now_ms: int, day: str) -> bool:
    """Calendario di Claude: ritorna True se Claude puo' essere consultato adesso. Decide SOLO il quando.

    - senza calendario: True e nessuna modifica (budget giornaliero di sempre);
    - con calendario, dentro una finestra: all'inizio di OGNI finestra il budget riparte da zero e la prima
      chiamata e' subito possibile (come il tasto "Azzera budget"); durante la finestra il budget non si
      azzera a mezzanotte UTC;
    - fuori dalle finestre: False (decidono le regole, come quando il budget e' finito).
    Imposta anche l'etichetta passiva claude_win sulle righe del registro. Non solleva mai."""
    try:
        s = schedule_state(DATA_DIR, now_ms)
        if s["mode"] == "none":
            _learning.STAMP.pop("claude_win", None)
            return True
        _learning.STAMP["claude_win"] = 1 if s["allowed"] else 0
        w = s["window"]
        if w:
            bud = state.setdefault("budget", {})
            if state.get("claude_window") != w["id"]:
                state["claude_window"] = w["id"]
                state["budget"] = {"day": day, "spent": 0.0, "calls": 0, "total_spent": bud.get("total_spent", 0.0)}
                state["last_call_ms"] = 0
                print(f"[FINESTRA] inizia una finestra di Claude (fino alle "
                      f"{time.strftime('%d %H:%M UTC', time.gmtime(w['end_ms'] / 1000))}): budget azzerato", flush=True)
            else:
                bud["day"] = day   # il budget della finestra non si azzera al cambio di giorno UTC
        elif s["mode"] == "invalid":
            print(f"[FINESTRA] calendario di Claude non valido ({s['error']}): Claude resta spento", flush=True)
        return bool(s["allowed"])
    except Exception as e:
        print(f"[FINESTRA ERROR] {e}: Claude resta spento in questo ciclo", flush=True)
        return False


def _bar_usable(o, h, l, c) -> bool:
    """OHLC utilizzabile per uno stop: numeri finiti, positivi, e il range contiene apertura e chiusura."""
    try:
        vals = (float(o), float(h), float(l), float(c))
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(v) and v > 0 for v in vals):
        return False
    oo, hh, ll, cc = vals
    return ll <= min(oo, cc) and max(oo, cc) <= hh


_CLOSE_PROOF = ("symbol", "id", "open_ms", "close_ms", "why", "net")


def _proof_value(row: dict, key: str):
    value = row.get(key)
    if key == "net" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def _close_row_matches(row, rec: dict, *, learning: bool, run_no, partial: bool = False) -> bool:
    """La riga e' questa chiusura: identita' esatta, senza riscrivere un fill gia' completo."""
    if not isinstance(row, dict) or bool(row.get("partial")) != partial:
        return False
    if partial and _proof_value(row, "fraction") != _proof_value(rec, "fraction"):
        return False
    if learning and row.get("ev") != "close":
        return False
    for key in _CLOSE_PROOF:
        if _proof_value(row, key) != _proof_value(rec, key):
            return False
    if "run_no" in row and row.get("run_no") != run_no:
        return False
    if learning and row.get("run_no") != run_no:
        return False
    return True


def _scan_close(path: str, rec: dict, *, learning: bool, run_no) -> str:
    """match, absent, conflict o unreadable. Una riga troncata non conta e non si cancella.

    conflict: esiste già una chiusura terminale della stessa posizione con un netto o un motivo diverso.
    Non si aggiunge un secondo fill e non si sceglie un match arbitrario.
    """
    match = False
    conflict = False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or row.get("partial"):
                    continue
                if learning and row.get("ev") != "close":
                    continue
                if (row.get("symbol") != rec.get("symbol") or row.get("id") != rec.get("id")
                        or row.get("open_ms") != rec.get("open_ms") or row.get("side") != rec.get("side")):
                    continue
                if "run_no" in row and row.get("run_no") != run_no:
                    continue
                if learning and row.get("run_no") != run_no:
                    continue
                if _close_row_matches(row, rec, learning=learning, run_no=run_no):
                    match = True
                else:
                    conflict = True
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unreadable"
    if conflict:
        return "conflict"
    return "match" if match else "absent"


def _prove_protective_close(state: dict, rec: dict) -> bool:
    """Scrive e rilegge storico e learning. Non riscrive un fill gia' provato e non cancella righe.

    Ritorna True solo se entrambi i registri contengono la stessa chiusura. Un fill terminale diverso
    per la stessa posizione blocca la scrittura. Se la prova manca, il conto non va salvato come chiuso.
    """
    run_no = state.get("run_no", 1)
    history = os.path.join(DATA_DIR, "trade_history.jsonl")
    learning = os.path.join(DATA_DIR, "learning_log.jsonl")
    hist = _scan_close(history, rec, learning=False, run_no=run_no)
    learn = _scan_close(learning, rec, learning=True, run_no=run_no)
    if "conflict" in (hist, learn) or "unreadable" in (hist, learn):
        return False
    if hist == "absent":
        append_trade_history(DATA_DIR, rec)
    if learn == "absent":
        row = dict(rec)
        row["reason"] = str(row.get("reason", ""))[:200]
        log_event(DATA_DIR, {"ev": "close", "ts": rec.get("close_ms"), "portfolio": PORTFOLIO.name,
                             "run_no": run_no, **row})
    return (_scan_close(history, rec, learning=False, run_no=run_no) == "match"
            and _scan_close(learning, rec, learning=True, run_no=run_no) == "match")


def _quote_fresh(ts: int, now_ms: int) -> bool:
    """La barra può prezzare un ingresso solo se non è più vecchia di due candele da 15 minuti."""
    return ts <= now_ms and not ts + 2 * PAPER_BAR_MS < now_ms


def operational_prices(symbols: list, candles_map: dict, now_ms: int) -> dict:
    """Prezzo per aperture e DCA. L'ultima riga deve essere fresca e OHLC valido.

    Non si torna a una barra più vecchia se l'ultima è futura, invalida o stale. Gli stop
    continuano a usare le barre storiche valide in apply_paper_protective_exits.
    """
    out = {}
    for sym in symbols:
        arr = candles_map.get(sym)
        if arr is None or len(arr) == 0:
            continue
        last = list(arr)[-1]
        try:
            ts, o, h, l, c = int(last[0]), last[1], last[2], last[3], last[4]
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
        if not _quote_fresh(ts, now_ms) or not _bar_usable(o, h, l, c):
            continue
        close = float(c)
        if math.isfinite(close) and close > 0:
            out[sym] = close
    return out


def apply_paper_protective_exits(acc: PaperAccount, candles_map: dict, now_ms: int, state: dict,
                                 report: Optional[dict] = None) -> dict:
    """Applica stop, take-profit e liquidazione sulle candele da 15 minuti gia' ricevute.

    Non inventa un prezzo. Una barra nel futuro, con numeri non validi o con high/low incoerenti non chiude
    la posizione. Una barra valida chiude anche se il feed e' rimasto indietro: lo stop gia' stampato resta.
    Il heartbeat riceve stop_feed e stop_certified=false. L'allarme non significa che il processo sia morto:
    significa che il controllo degli stop non ha un prezzo utilizzabile fino all'ultima candela attesa.
    """
    if report is None:
        report = {}
    try:
        for sym in list(acc.positions):
            arr = candles_map.get(sym)
            info = {"checked": False, "status": "missing", "bad": 0, "future": 0,
                    "newest_open_ms": None, "exit": None}
            rows = [] if arr is None else list(arr)
            valid = []
            last_ok = False
            for i, row in enumerate(rows):
                try:
                    ts, o, h, l, c = int(row[0]), row[1], row[2], row[3], row[4]
                except (TypeError, ValueError, IndexError, OverflowError):
                    info["bad"] += 1
                    continue
                if ts > now_ms:
                    info["future"] += 1
                    continue
                if not _bar_usable(o, h, l, c):
                    info["bad"] += 1
                    continue
                valid.append((ts, float(o), float(h), float(l), float(c)))
                last_ok = i == len(rows) - 1
            if not valid:
                info["status"] = "future" if info["future"] else ("missing" if not rows else "unusable")
                report[sym] = info
                continue
            newest = valid[-1][0]
            info["newest_open_ms"] = newest
            info["checked"] = True
            if info["future"]:
                info["status"] = "future"
            elif newest + 2 * PAPER_BAR_MS < now_ms:
                info["status"] = "stale"
            elif not last_ok:
                info["status"] = "latest_rejected"
            else:
                info["status"] = "ok"
            report[sym] = info
            for ts, o, h, l, c in valid:
                result = acc.on_bar(sym, ts, o, h, l, c, PAPER_BAR_MS)
                if not result:
                    continue
                info["exit"] = result["why"]
                print(f"[{result['why'].upper()}] {sym} net {result['net']:+.2f}$")
                if not _prove_protective_close(state, result):
                    info["status"] = "close_not_durable"
                    raise RuntimeError("close_not_durable")
                save_account(acc, state)
                save_state(state, STATE_FILE)
                # Telegram is informational, never evidence of a durable close.
                # A failed journal proof or state save must not send a false "CHIUSO".
                try:
                    notify_close(sym, result["net"], result.get("why", ""), result["why"])
                except Exception:
                    pass
                break
    finally:
        alarm = any(item.get("status") != "ok" for item in report.values())
        HB["stop_feed"] = {"timeframe": "15m", "bar_ms": PAPER_BAR_MS, "alarm": alarm,
                           "stop_certified": False, "symbols": report}
        HB["stop_certified"] = False
    return report


def run_cycle(state: dict, now_ms: int, drain: bool = False) -> None:
    """Un ciclo di mercato.

    drain=True e' la PAUSA: le posizioni aperte continuano a essere gestite (stop loss,
    take profit, liquidazione e uscite decise da regole/Claude) ma non si apre nulla di
    nuovo e non si fanno DCA. Nessuna posizione viene chiusa a forza.
    """
    import numpy as np

    HB.pop("paper_close_blocked", None)
    if not LIVE._live and state.get(CLAIMS_KEY):
        _commit_paper_closes(state)       # ripresa: completa i claim con il record gia' salvato
    claim_block = bool(_unresolved_claims(state))   # chiusure contabili ancora da riconciliare
    acc = make_account(state)
    if claim_block:
        # Come in pausa: nessuna nuova esposizione (aperture, DCA, seconde gambe, S25); le uscite restano attive.
        for s_ in list(acc.positions):
            acc.cancel_split(s_, "chiusure contabili da riconciliare", now_ms)
        print(f"[CLAIM] {len(state[CLAIMS_KEY])} chiusure da riconciliare: nuove aperture e DCA bloccate", flush=True)
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000))
    acc.roll_day(day, {})
    claude_ok = apply_claude_schedule(state, now_ms, day)

    # carica candele per tutti i simboli
    candles_map: dict = {}
    for sym in SYMBOLS:
        arr = fetch_candles(sym)
        if arr:
            candles_map[sym] = np.array(arr)
        time.sleep(0.05)   # gentile con l'API
        write_heartbeat(state, force=False)   # il ciclo puo' durare un minuto: il bot resta "vivo"

    print(f"[DESK V2] candles ok: {len(candles_map)}/{len(SYMBOLS)} simboli", flush=True)
    prices = operational_prices(SYMBOLS, candles_map, now_ms)
    HB["new_exposure"] = {
        "blocked_symbols": sorted(sym for sym, arr in candles_map.items() if len(arr) and sym not in prices),
        "stop_certified": False,
    }
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

    # Prima di Claude, del DCA e di qualunque spostamento dello stop: uno stop gia' stampato
    # su una candela valida non deve poter essere allargato nello stesso ciclo.
    stop_report: dict = {}
    apply_paper_protective_exits(acc, candles_map, now_ms, state, stop_report)

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
        htf = fetch_htf(sym, now_ms)
        r = read_symbol(sym, arr, now_ms, bars_4h=htf.get("4h"), bars_1d=htf.get("1d"))
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
    valid_claude_reply = False
    explicit_claude_no_trade = False
    if halt:
        print(f"[HALT] {halt}")
    elif drain and not acc.positions:
        pass   # in pausa e senza posizioni non c'e' nulla da gestire: niente chiamate a Claude
    elif call_due and not claude_ok:
        print("[FINESTRA] fuori dal calendario: Claude non viene consultato, decidono le regole", flush=True)
    elif call_due and can_call(state, day):
        try:
            prompt = build_prompt(snap, readings_list, pos_info, headlines, lessons, ctx_for_prompt, sym_stats)
            text, usage = call_claude(SYSTEM, prompt, max_tokens=1100)
            cost = record_spend(state, day, usage)
            state["last_call_ms"] = now_ms
            parsed = parse_decisions(text)
            log_claude_call(now_ms, state, text, usage, cost, parsed, len(prompt),
                            len(acc.positions), urgent_scalp, 1100)
            if parsed is not None:
                # An explicitly valid empty decision list means NO_TRADE, not
                # "Claude failed": never silently replace it with rules entries.
                valid_claude_reply = True
                explicit_claude_no_trade = not parsed["decisions"]
                decisions = parsed["decisions"]
                source = "claude"
                print(f"[Claude] {len(decisions)} decisioni  costo {cost:.4f}$  "
                      f"budget usato {state['budget']['spent']:.3f}$ / {DAILY_CAP}$")
                if parsed.get("note"):
                    print(f"[Claude] Nota: {parsed['note']}")
        except Exception as e:
            print(f"[WARN] Claude non disponibile: {e}")
            log_claude_error(now_ms, state, e, len(acc.positions), urgent_scalp)

    if not decisions and not valid_claude_reply:
        decisions = rules_decisions(readings_list, pos_info, open_symbols, _ENTRY_SCORE_BASE)
        source = "rules"

    if not LIVE._live and os.environ.get("DESK_LONG_S25") == "1":   # strategia long S25: le sue uscite sono solo stop, target, tempo
        try:
            from desk import long_s25
            decisions = long_s25.protect(decisions, acc.positions)
        except Exception as e:
            print(f"[S25] errore ignorato: {e}", flush=True)

    if not LIVE._live and PORTFOLIO.name in ("hawk", "bull"):
        decisions, excluded = _rc84_paper_classic_entry_policy(PORTFOLIO.name, source, decisions)
        if excluded:
            for dec in excluded:
                # Rejections are visible without using any exchange API and
                # do not create fake trade or learning outcomes.
                print(f"[RC84_POLICY:{PORTFOLIO.name.upper()}] ingresso {source} rifiutato "
                      f"{dec.get('symbol', '?')} {dec.get('action', '?')} "
                      f"tipo={dec.get('trade_type', '?')}", flush=True)
            HB["rc84_policy_rejected"] = len(excluded)
        else:
            HB["rc84_policy_rejected"] = 0

    if not drain and os.path.exists(_flag("pause.flag")):
        drain = True   # pausa premuta mentre il ciclo era in corso: vale da subito
    no_new = drain or claim_block
    if no_new:
        # PAUSA: solo gestione delle posizioni esistenti. Ingressi e DCA sono scartati qui,
        # prima dell'esecuzione, qualunque sia la loro origine (Claude o regole).
        skipped = [d for d in decisions if d["action"] not in MANAGE_ACTIONS]
        decisions = [d for d in decisions if d["action"] in MANAGE_ACTIONS]
        if skipped:
            print(f"[{'PAUSA' if drain else 'CLAIM'}] {len(skipped)} nuovi ingressi/DCA ignorati: "
                  f"{'bot in pausa ' if drain else 'chiusure da riconciliare '}"
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
        if claim_block and act not in MANAGE_ACTIONS:
            print(f"[CLAIM] {sym} {act} ignorata: chiusure da riconciliare", flush=True)
            continue

        if act == "close":
            if not LIVE._live and _terminal_already_logged(state, acc.positions.get(sym)):
                _note_close_block(sym, "chiusura terminale gia' nei registri: verifica necessaria")
                continue
            # ── LIVE: chiudi su Bitget prima di aggiornare il motore ─────────
            if LIVE._live:
                pos_pre = acc.positions.get(sym)
                if pos_pre:
                    qty = pos_pre.qty
                    live_ok, live_detail = LIVE.close(sym, pos_pre.side, qty)
                    if not live_ok:
                        print(f"[LIVE CLOSE FALLITA] {sym}: {live_detail} — posizione resta aperta")
                        continue   # non chiudere in memoria se Bitget ha fallito
            # ─────────────────────────────────────────────────────────────────
            closed = acc.close(sym, px, now_ms, "chiusura Claude")
            if closed:
                print(f"[CLOSE] {sym} net {closed['net']:+.2f}$  motivo: {dec['reason'][:60]}")
                if LIVE._live:
                    notify_close(sym, closed["net"], dec.get("reason", "")[:100], "chiusura Claude")
                    record_close(state, closed)
                else:
                    _claim_paper_close(state, closed, (dec.get("reason", "")[:100], "chiusura Claude"))
                    claim_block = claim_block or not _settle_claims_now(state, acc)

        elif act == "partial_close":
            fraction = float(dec.get("partial_close_fraction") or dec.get("partial_fraction") or 0.35)
            fraction = max(0.1, min(0.9, fraction))
            tp2_pct = dec.get("partial_close_tp2_pct") or dec.get("take_profit_pct") or 0
            pos = acc.positions.get(sym)
            if pos is None:
                print(f"[PARTIAL_CLOSE SKIP] {sym}: posizione non trovata")
                continue
            if not LIVE._live and _terminal_already_logged(state, pos):
                _note_close_block(sym, "chiusura terminale gia' nei registri: parziale rifiutata")
                continue
            new_tp = None
            if tp2_pct and tp2_pct > 0:
                new_tp = px * (1 + pos.side * tp2_pct)
            partial = acc.partial_close(sym, px, now_ms, fraction, new_tp=new_tp,
                                        why=dec.get("reason", "TP parziale")[:80])
            if partial:
                print(f"[PARTIAL_CLOSE] {sym} chiuso {fraction*100:.0f}%  net {partial['net']:+.2f}$  "
                      f"TP2={'%.5g' % new_tp if new_tp else 'none'}")
                partial_reason = f"TP parziale {fraction*100:.0f}% — {dec.get('reason','')[:80]}"
                if LIVE._live:
                    notify_close(sym, partial["net"], partial_reason, "partial_close")
                    record_close(state, partial)
                else:
                    _claim_paper_close(state, partial, (partial_reason, "partial_close"))
                    claim_block = claim_block or not _settle_claims_now(state, acc)

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
            # RC84 fase 2: senza una tendenza 4h VERIFICABILE (EMA50/EMA200 su barre 4h chiuse) nessuna nuova
            # esposizione su quel simbolo, qualunque sia l'origine (regole o Claude). Gestione e uscite invariate.
            rd_ = readings_map.get(sym)
            if rd_ is None or (rd_.facts or {}).get("trend4h_state") not in ("UP", "DOWN"):
                print(f"[TREND_UNKNOWN] {sym}: tendenza 4h non verificabile "
                      f"({(rd_.facts or {}).get('trend4h_why', 'nessuna lettura') if rd_ else 'nessuna lettura'}): "
                      f"nessuna nuova apertura", flush=True)
                _candidate("trend_sconosciuto", dec, px)
                continue
            shadow = policy_shadow_violations(dec, PORTFOLIO, sym)
            if shadow:
                # SOLO REGISTRAZIONE: confronto tra il contratto del prompt e i controlli del motore. Non blocca.
                print(f"[POLICY_SHADOW:{PORTFOLIO.name.upper()}] {sym} {act}: {', '.join(shadow)}", flush=True)
                HB["policy_shadow_last"] = {"symbol": sym, "ts": now_ms, "violations": shadow}
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
            feats.update(policy_shadow=shadow)
            feats.update(proposed_margin=raw_margin, proposed_lev=raw_lev, split_requested=is_split,
                          guardrail_forced=bool(raw_margin != dec["margin_usd"] or raw_lev != dec["leverage"]))
            # ── INTERRUTTORE MANUALE (solo live) ────────────────────────────
            if not is_trading_enabled():
                print(f"[TRADING DISABILITATO] {sym}: trading live disabilitato — premi 'Avvia trading' nell'app",
                      flush=True)
                _candidate("trading_disabilitato", dec, px)
                continue
            # ── DAILY LOSS LIMIT (solo live) ────────────────────────────────
            if _daily_loss_exceeded(acc):
                _candidate("daily_loss_limit", dec, px)
                continue
            # ─────────────────────────────────────────────────────────────────
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
                # ── LIVE: invia ordine reale a Bitget ───────────────────────
                live_ok, live_detail = True, "paper"
                if LIVE._live:
                    qty = LIVE.qty_from_margin(sym, pos.total_margin, pos.leverage, px)
                    live_ok, live_detail = LIVE.open(sym, side, qty, pos.leverage, sl, tp)
                    if not live_ok:
                        # Bitget ha rifiutato: annulla la posizione in memoria
                        acc.positions.pop(sym, None)
                        acc.cash += pos.total_margin + pos.fee_open
                        print(f"[LIVE ROLLBACK] {sym}: ordine rifiutato da Bitget — posizione annullata")
                        _candidate("live_rifiutata:" + live_detail[:60], dec, px)
                        continue
                # ─────────────────────────────────────────────────────────────
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
                    "live_order_id": live_detail,
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
    if drain or claim_block:
        for s in list(acc.positions):
            acc.cancel_split(s, "bot in pausa" if drain else "chiusure contabili da riconciliare", now_ms)

    # ---- strategia long S25 (spenta di default): chiusura a tempo e nuovi ingressi, prima della lettura delle barre
    if not LIVE._live and os.environ.get("DESK_LONG_S25") == "1":
        try:
            from desk import long_s25
            s25_notice: dict = {}

            def s25_record(st, rec):
                _claim_paper_close(st, rec, s25_notice.pop(rec["symbol"], None))
                try:
                    _settle_claims_now(st, acc)
                except Exception as exc:
                    # Nessun errore di salvataggio nascosto: il claim resta irrisolto (entries_blocked lo vede)
                    # e il commit finale del ciclo ritenta e solleva come per ogni altra chiusura.
                    print(f"[CLAIM] S25: riconciliazione immediata rimandata: {type(exc).__name__}", flush=True)

            # RC84: keep S25 STOP/TP/TIME EXIT management for old trades.
            # New S25 entries (same symbols/stops on BOTH portfolios, R:R=1:1)
            # are DISABLED until separate signal-quality tests and approval.
            # Original Claude/rule LONG+SHORT decisions continue as before.
            # Only Toro may later opt in explicitly after verification.
            s25_new_entries = (PORTFOLIO.name == "bull" and
                               os.getenv("DESK_S25_TORO_ENTRY_APPROVED") == "1"
                               and not explicit_claude_no_trade)
            long_s25.step(acc, state, candles_map, prices, now_ms, PORTFOLIO, halt=halt, drain=no_new,
                          allow_new_entries=s25_new_entries,
                          record_close=s25_record,
                          entries_blocked=lambda: bool(_unresolved_claims(state)),
                          notify_open=notify_open,
                          notify_close=lambda sym, net, reason, why: s25_notice.__setitem__(sym, (reason, why)),
                          can_close=lambda sym: not _terminal_already_logged(state, acc.positions.get(sym)),
                          log_event=lambda ev: log_event(DATA_DIR, ev))
        except Exception as e:
            print(f"[S25] errore ignorato: {e}", flush=True)
    if _unresolved_claims(state):          # claim nato in questo ciclo e ancora irrisolto: niente seconde gambe
        for s in list(acc.positions):
            acc.cancel_split(s, "chiusure contabili da riconciliare", now_ms)

    # Il DCA e le altre modifiche sono solo in memoria. Si scrivono prima del secondo passaggio:
    # se la chiusura non si puo' provare, il disco resta su questa posizione e il netto del giro dopo coincide.
    save_account(acc, state)
    _commit_paper_closes(state)
    # Secondo passaggio: uno stop stretto da Claude o dalle regole nello stesso ciclo vale subito,
    # sulle stesse candele gia' filtrate. Una posizione chiusa dal primo passaggio non c'e' piu'.
    apply_paper_protective_exits(acc, candles_map, now_ms, state, stop_report)
    if HB.get("new_exposure", {}).get("blocked_symbols"):
        HB["stop_feed"]["alarm"] = True
        HB["stop_feed"]["stop_certified"] = False
    flush_events(state, acc)

    # ---- lessons (una chiamata a Claude: segue il calendario come le altre)
    if claude_ok:
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


MANUAL_CLOSE_CANDLE_MAX_AGE_MS = 1_800_000  # 30 minuti
MANUAL_CLOSE_CACHE_MAX_AGE_MS = 120_000  # 2 minuti: bloccare prezzi vecchi di giorni


def _market_prices(symbols: list, state: dict, now_ms: int | None = None) -> dict:
    """Chiusure manuali: usare solo prezzi recenti e finiti (PAPER)."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    prices: dict = {}
    for sym in symbols:
        arr = fetch_candles(sym, "15m", 3)
        if not arr:
            continue
        try:
            candle = arr[-1]
            ts, mark = int(candle[0]), float(candle[4])
            if (0 <= now_ms - ts <= MANUAL_CLOSE_CANDLE_MAX_AGE_MS
                    and math.isfinite(mark) and mark > 0):
                prices[sym] = mark
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
    cache_ms = state.get("last_prices_ms")
    if (type(cache_ms) is int
            and 0 <= now_ms - cache_ms <= MANUAL_CLOSE_CACHE_MAX_AGE_MS):
        cached = state.get("last_prices") or {}
        for sym in symbols:
            if sym in prices:
                continue
            try:
                mark = float(cached.get(sym))
                if math.isfinite(mark) and mark > 0:
                    prices[sym] = mark
            except (TypeError, ValueError, OverflowError):
                continue
    return prices


def _close_for_user(state: dict, acc: PaperAccount, sym: str, px: float, now_ms: int, notice=None) -> tuple:
    """Chiude UNA posizione a prezzo di mercato perche' lo ha chiesto l'utente (Chiudi tutto o Chiudi singola).
    Il trade entra nello storico e nel registro come tutti gli altri (vinto o perso secondo il profitto vero),
    con in piu' `closed_by: "utente"` per poter separare in analisi cio' che ha deciso il bot da cio' che ha
    deciso l'utente: non cambia l'esito, non e' un trade "falso". Non passa dalle decisioni di regole o di Claude:
    vale per qualunque posizione, anche una aperta da una strategia che le regole non possono chiudere.
    Ritorna (record, "") se chiusa, (None, motivo) se non e' stata chiusa."""
    if _terminal_already_logged(state, acc.positions.get(sym)):
        _note_close_block(sym, "chiusura terminale gia' nei registri: verifica necessaria")
        return None, "chiusura gia' presente nello storico: verifica necessaria"
    rec = acc.close(sym, px, now_ms, "chiusura manuale")
    if rec is None:
        return None, "posizione non trovata"
    rec["closed_by"] = "utente"
    # Esempio per l'analisi del profitto, non una strategia automatica convalidata.
    rec["manual_learning"] = (
        "profit_protection_example" if rec["net"] > 0
        else "loss_reduction_example" if rec["net"] < 0
        else "break_even_example"
    )
    _claim_paper_close(state, rec, notice)
    return rec, ""


CLOSE_ALL_MAX_AGE_S = 600  # anche il comando legacy senza timestamp non puo' svegliarsi giorni dopo


def _check_close_all_flag(state: dict, price_provider=None) -> bool:
    """reset.flag: chiusura PAPER a prezzo di mercato, mai su richiesta dimenticata.
    Il protocollo storico non contiene un timestamp. Per le sole richieste PAPER,
    usare l'mtime del flag; se troppo vecchio si scarta senza toccare le posizioni.
    LIVE conserva il percorso precedente, senza cambiare l'esecuzione exchange.
    """
    path = _flag("reset.flag")
    if not os.path.exists(path):
        return False
    # PAPER: atomically claim a request before fetching prices. A crash leaves
    # .work visible for manual reconciliation rather than executing it twice.
    work = path if LIVE._live else path + ".work"
    if not LIVE._live:
        if os.path.exists(work):
            return False
        try:
            os.replace(path, work)
        except OSError:
            return False
    try:
        if not LIVE._live:
            try:
                age_s = time.time() - os.path.getmtime(work)
            except OSError:
                return False
            if not (-60 <= age_s <= CLOSE_ALL_MAX_AGE_S):
                _set_last_action(state, "close_all", False,
                                 "richiesta di chiusura totale scaduta: ignorata; riprova dall'app")
                save_state(state, STATE_FILE)
                return False
        acc = make_account(state)
        if not acc.positions:
            _set_last_action(state, "close_all", True, "nessuna posizione aperta")
            save_state(state, STATE_FILE)
            return True
        now_ms = int(time.time() * 1000)
        prices = (price_provider or _market_prices)(list(acc.positions), state, now_ms)
        closed_n, skipped, net = 0, [], 0.0
        blocked: list = []
        for sym in list(acc.positions):
            px = prices.get(sym)
            if px is None:
                skipped.append(sym)
                continue
            # ── LIVE: chiudi su Bitget prima di aggiornare il motore ─────────
            if LIVE._live:
                pos_pre = acc.positions.get(sym)
                if pos_pre:
                    live_ok, live_detail = LIVE.close(sym, pos_pre.side, pos_pre.qty)
                    if not live_ok:
                        print(f"[LIVE CLOSE FALLITA] {sym}: {live_detail} — skip chiusura manuale")
                        skipped.append(sym)
                        continue
            # ─────────────────────────────────────────────────────────────────
            if LIVE._live:
                rec = acc.close(sym, px, now_ms, "chiusura manuale")
                if rec:
                    record_close(state, rec)
            else:
                rec, why_not = _close_for_user(state, acc, sym, px, now_ms)
                if why_not and rec is None:
                    blocked.append(sym)
            if rec:
                closed_n += 1
                net += rec["net"]
        flush_events(state, acc)
        save_account(acc, state)
        detail = f"chiuse {closed_n} posizioni (netto {net:+.2f}$)"
        if skipped:
            detail += f"; prezzo non disponibile per {', '.join(skipped)}: ancora aperte, riprova"
        if blocked:
            detail += f"; {', '.join(blocked)}: chiusura gia' presente nello storico, verifica necessaria"
        _set_last_action(state, "close_all", not (skipped or blocked), detail, closed=closed_n,
                         skipped=skipped + blocked)
        _commit_paper_closes(state)
        print(f"[CHIUDI TUTTO] {detail}", flush=True)
        return True
    except Exception as e:
        print(f"[CHIUDI TUTTO ERROR] {e}", flush=True)
        traceback.print_exc()
        return False
    finally:
        _remove(work)


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


def _check_close_position_flag(state: dict, price_provider=None) -> bool:
    """close_position.flag = {"symbols": [...], "ts": ms}: l'utente vuole chiudere queste posizioni (non tutte) a
    prezzo di mercato. Stesse regole di 'Chiudi tutto': mai un'uscita inventata se manca il prezzo. Sicurezze: una
    richiesta vecchia (clic dimenticato) non si esegue; un simbolo gia' chiuso non e' un errore; il file si 'prende
    in carico' con un rinomina cosi' un secondo clic arrivato intanto non va perso. Funziona anche in pausa. L'esito
    va in state['last_action'] e l'app lo mostra."""
    path = _flag("close_position.flag")
    if LIVE._live:
        # This new request protocol is PAPER-only. The existing LIVE close-all
        # path above remains unchanged and still calls the exchange first.
        return False
    if not os.path.exists(path):
        return False
    work = path + ".work"
    if os.path.exists(work):  # incomplete prior close must be reconciled, never overwritten
        return False
    try:
        os.replace(path, work)
    except OSError:
        return False
    try:
        try:
            with open(work) as f:
                req = json.loads(f.read() or "{}")
        except Exception:
            req = {}
        if not isinstance(req, dict):
            req = {}
        wanted = [str(x) for x in (req.get("symbols") or []) if x]
        wanted = list(dict.fromkeys(wanted))
        now_ms = int(time.time() * 1000)
        try:
            age_s = (now_ms - int(req.get("ts"))) / 1000.0
        except (TypeError, ValueError):
            age_s = None
        if not wanted:
            _set_last_action(state, "close_position", False, "richiesta di chiusura senza simbolo: ignorata")
            save_state(state, STATE_FILE)
            return False
        if age_s is None or age_s > CLOSE_POSITION_MAX_AGE_S or age_s < -60:
            _set_last_action(state, "close_position", False,
                             f"richiesta di chiusura scaduta ({', '.join(wanted)}): non eseguita, riprova")
            save_state(state, STATE_FILE)
            print(f"[CHIUDI POSIZIONE] richiesta scaduta o senza ora ({', '.join(wanted)}): non eseguita", flush=True)
            return False
        acc = make_account(state)
        present = [s for s in wanted if s in acc.positions]
        gone = [s for s in wanted if s not in acc.positions]
        prices = (price_provider or _market_prices)(present, state, now_ms) if present else {}
        closed, failed, net = [], [], 0.0
        for sym in present:
            px = prices.get(sym)
            if px is None:
                failed.append((sym, "prezzo non disponibile"))
                continue
            rec, why_not = _close_for_user(state, acc, sym, px, now_ms,
                                           notice=("su tua richiesta", "chiusura manuale"))
            if why_not:
                failed.append((sym, why_not))
                continue
            closed.append(sym)
            net += rec["net"]
        flush_events(state, acc)
        save_account(acc, state)
        parts = []
        if closed:
            parts.append(f"chiusa {', '.join(closed)} (netto {net:+.2f}$)" if len(closed) == 1
                         else f"chiuse {', '.join(closed)} (netto {net:+.2f}$)")
        if gone:
            parts.append(f"{', '.join(gone)}: gia' chiusa")
        for sym, why in failed:
            parts.append(f"{sym}: NON chiusa ({why}), resta aperta: riprova")
        detail = "; ".join(parts) or "nessuna posizione da chiudere"
        _set_last_action(state, "close_position", not failed, detail, closed=closed,
                         skipped=[s for s, _ in failed])
        _commit_paper_closes(state)
        print(f"[CHIUDI POSIZIONE] {detail}", flush=True)
        return True
    except Exception as e:
        print(f"[CHIUDI POSIZIONE ERROR] {e}", flush=True)
        traceback.print_exc()
        return False
    finally:
        _remove(work)


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
        claims = _unresolved_claims(state)
        if claims:
            conflict = sum(1 for c in claims if c.get("status") == "conflict")
            _set_last_action(state, "reset_portfolio", False,
                             f"rifiutato: {len(claims)} chiusure contabili da riconciliare"
                             f"{f' ({conflict} in conflitto)' if conflict else ''}; "
                             "storico e learning non toccati")
            save_state(state, STATE_FILE)
            print("[RESET PORTAFOGLIO] rifiutato: chiusure contabili da riconciliare", flush=True)
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
    """Esegue i comandi arrivati dall'app. L'ordine conta: budget, chiudi tutto, chiudi singola, reset conto."""
    _check_budget_reset_flag(state)
    _check_close_all_flag(state)
    _check_close_position_flag(state)
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
    _recover_paper_claims(state, ctl)
    paused = os.path.exists(_flag("pause.flag"))
    if paused != ctl.get("prev_paused"):
        if ctl.get("prev_paused") is not None:
            print("[PAUSA] richiesta di pausa: finisco le posizioni aperte, nessun nuovo ingresso"
                  if paused else "[AVVIO] ripresa richiesta: il bot lavora", flush=True)
            ctl["next_cycle_ms"] = 0   # reagisce subito al tasto, senza aspettare il prossimo ciclo
        ctl["prev_paused"] = paused
    try:   # all'inizio di una finestra di Claude il ciclo parte subito (non si aspetta il prossimo giro)
        w = schedule_state(DATA_DIR, int(time.time() * 1000)).get("window")
        wid = w["id"] if w else None
        if wid != ctl.get("window_id"):
            ctl["window_id"] = wid
            if wid is not None:
                ctl["next_cycle_ms"] = 0
    except Exception:
        pass
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

    # ── LIVE: riconciliazione posizioni al riavvio ────────────────────────────
    if LIVE._live:
        acc_check = make_account(state)
        warnings = LIVE.reconcile(acc_check.positions)
        for w in warnings:
            print(w, flush=True)
        if warnings:
            print("[RICONCILIAZIONE] controlla le posizioni su Bitget prima di procedere", flush=True)
    # ─────────────────────────────────────────────────────────────────────────

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
