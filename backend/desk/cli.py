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
from desk import macro_calendar
from desk import trading_hours
from desk.learning import build_features, log_event
from desk.schedule import schedule_state, summary as schedule_summary
from desk.notifier import (notify_open, notify_close, notify_dca, notify_split,
                           notify_halt, notify_daily_report, notify_live_alert, set_context)
from desk.live_connector import LiveConnector
from desk import live_sync


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
    # OPZIONE A (decisione di Alexander, 20/10/2026 16:30): se il margine realmente disponibile e' sotto
    # guardrail_min_margin l'apertura si RIFIUTA invece di essere ridimensionata dal motore (30-149 $). Solo Bull.
    refuse_below_min_margin: bool = False
    # OPZIONE B (decisione di Alexander, 20/10/2026 17:58): la leva proposta dal motore non puo' superare
    # max_leverage. Se supera, l'apertura si rifiuta. None = nessun limite (valore predefinito).
    max_leverage: Optional[int] = None


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
        max_leverage=None,   # nessun tetto del bot (utente, 21/10/2026: torna come all'inizio). Il cancello resta nel codice ma spento; restano i tetti per asset del motore (45x BTC/XAU/XAG, 30x ETH, 25x altri)
    )


def _make_bull_config() -> PortfolioConfig:
    data_dir = os.getenv("DESK_DATA_DIR", "/app/data/desk/bull")
    return PortfolioConfig(
        name="bull",
        data_dir=data_dir,
        limits=Limits(
            start_equity=1000.0,
            max_margin_trade=350.0,   # BULL: max $350 per trade
            max_margin_total=1050.0,  # budget 1050 = 3 x 350 (utente, 21/10/2026: torna come all'inizio; era 1000 dal 20/10 14:11); engine.open usa anche cash*0.95
            max_open=6,               # max 6 posizioni (utente, 21/10/2026; era 10 dal 20/10 13:56, 3 all'inizio). Non devono essere tutte piene
            kill_equity=450.0,
            daily_stop=0.12,
        ),
        system_prompt=SYSTEM_BULL,
        guardrail_min_margin=150.0,
        guardrail_min_lev=10,
        guardrail_margin_forced=200.0,
        guardrail_lev_forced=15,
        guardrail_type_forced="medio",
        description="Bull — max $350/trade, 6 posizioni, budget $1050, TP≥5%",
        refuse_below_min_margin=True,
        max_leverage=None,   # nessun tetto del bot (utente, 21/10/2026: torna come all'inizio). Il cancello resta nel codice ma spento; restano i tetti per asset del motore
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
# Tier C: tutti gli altri altcoin → soglia 63 (era 70; 65 la mattina del 20/10, poi 63 su decisione dell'utente,
# valida per Hawk e Bull)
_TIER_AB = {"BTC", "ETH", "XAU", "XAG"}
TIER_AB_ENTRY_SCORE = 60
TIER_C_ENTRY_SCORE = 63


def tier_entry_score(symbol: str) -> int:
    """Restituisce la soglia di confidenza minima per aprire un trade su questo simbolo."""
    return TIER_AB_ENTRY_SCORE if symbol.upper() in _TIER_AB else TIER_C_ENTRY_SCORE
HOUR_MS = 3_600_000
HALF_HOUR_MS = 1_800_000
SCALP_REVIEW_MS = 900_000    # scalp revisionati ogni 15 minuti
SCALP_COOLDOWN_MS = 600_000  # cooldown per aprire scalp consecutivi (10 min)
MEDIO_COOLDOWN_MS = 3_600_000  # cooldown per medio (1h)

# Simboli V2: top-30 CMC + oro + argento (escludi stablecoin)
SYMBOLS = [
    "BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "AVAX",
    "DOT", "LINK", "UNI", "ATOM", "LTC", "BCH",
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
#   close_position.flag   chiudi UNA o piu' posizioni scelte dall'utente, a prezzo di mercato:
#                         {"symbols": [...], "ts": ms}. Una richiesta piu' vecchia di CLOSE_POSITION_MAX_AGE_S
#                         si scarta (mai chiudere a distanza di ore per un clic dimenticato).
#   budget_reset.flag     azzera solo il budget giornaliero di Claude
#   reset_portfolio.flag  azzera il CONTO e riparti da 1000$ (solo in pausa e senza posizioni).
#                         Il "cervello" (trade_history.jsonl, lessons.md, errors.md, learning_log.jsonl)
#                         NON si tocca mai: il reset non lo cancella e l'opzione {"clear_lessons": true}
#                         (vecchia) viene ignorata.
#   trading_hours.json    ORARI DI TRADING (spento di default, lo attiva solo l'utente dall'app): fuori dalle fasce
#                         il bot si comporta come in pausa (niente nuove aperture, le aperte si chiudono da sole)
#   heartbeat.json        scritto dal bot: modalita', ultimo ciclo, prossimo ciclo, versione
# I percorsi si calcolano al momento dell'uso (DATA_DIR puo' cambiare, es. nei test).
def _flag(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def hours_blocked(now_ms: int) -> bool:
    """True se gli orari di trading sono attivi e adesso siamo FUORI dalle fasce (vedi trading_hours.py).
    Un errore imprevisto qui vale "non bloccato": il bot lavora come prima (gli errori sul file li gestisce
    trading_hours stesso, in modo prudente)."""
    try:
        return bool(trading_hours.hours_state(DATA_DIR, now_ms)["blocked"])
    except Exception:
        return False


def drain_reason(now_ms: int) -> str:
    """Perche' il bot non deve aprire nulla di nuovo adesso: "pausa" (tasto Pausa, vince su tutto), "orari"
    (fuori dalle fasce di trading) oppure "" (lavora)."""
    if os.path.exists(_flag("pause.flag")):
        return "pausa"
    return "orari" if hours_blocked(now_ms) else ""


def _sane_tp(sym: str, tp: Optional[float], where: str) -> Optional[float]:
    """Un take profit e' un PREZZO: se il calcolo da' <= 0 non e' raggiungibile (visto in app: short LTC con TP a
    -233$, cioe' take_profit_pct=4.72). Lo scartiamo = nessun nuovo TP. In APERTURA e' identico a prima (uno
    short non tocca mai un prezzo negativo: la posizione era di fatto senza TP). In DCA / chiusura parziale resta
    il TP che la posizione aveva gia', invece di essere sostituito da uno irraggiungibile. In live il prezzo
    assurdo non parte piu' verso l'exchange e l'app non mostra piu' un TP impossibile."""
    if tp is not None and not tp > 0:
        print(f"[TP_INVALIDO] {sym} ({where}): TP {tp:.5g} non e' un prezzo possibile -> scartato, "
              f"nessun TP impostato", flush=True)
        return None
    return tp


# Tetto di token della risposta di Claude. Con 1100 la risposta veniva TAGLIATA in 60 chiamate su 95 (registro
# 12-15 ott) e il bot la scartava: pagata e ignorata. In paper (test) l'utente ha deciso 3000 (15 ott), con
# timeout piu' lungo perche' la risposta e' piu' lunga; in LIVE resta 1100 finche' l'utente non decide, dopo
# aver confrontato i dati del test (il contabile conta le risposte ancora tagliate).
CLAUDE_MAX_TOKENS_PAPER, CLAUDE_TIMEOUT_PAPER_S = 3000, 120
CLAUDE_MAX_TOKENS_LIVE, CLAUDE_TIMEOUT_LIVE_S = 1100, 60


def claude_limits(live: bool) -> tuple:
    """(max_tokens, timeout in secondi) della chiamata a Claude. In live restano i valori di sempre."""
    if live:
        return CLAUDE_MAX_TOKENS_LIVE, CLAUDE_TIMEOUT_LIVE_S
    return CLAUDE_MAX_TOKENS_PAPER, CLAUDE_TIMEOUT_PAPER_S


POLL_S = 5                 # ogni quanto il bot controlla i tasti dell'app
RETRY_S = 300              # dopo un ciclo fallito riprova dopo 5 minuti
CYCLE_S = 1800             # ciclo normale: 30 minuti
CYCLE_FAST_S = 900         # con scalp aperto o in svuotamento: 15 minuti
CODE_VERSION = os.getenv("DESK_CODE_VERSION", "dev")
CLOSE_POSITION_MAX_AGE_S = 600   # una richiesta di chiusura singola piu' vecchia di 10 min non si esegue

# ── Capitale assegnato e scala degli ordini (solo live) ──────────────────────
# DESK_HAWK_CAPITAL / DESK_BULL_CAPITAL: capitale allocato a ogni portafoglio (USDT), scelto dall'utente.
# Il motore e il cervello ragionano SEMPRE su un conto di riferimento (start_equity = 1000$): non cambia
# nulla della strategia. In live ogni ORDINE verso Bitget e' moltiplicato per CAPITAL_SCALE = capitale /
# riferimento (con 500$ assegnati: meta' di quello che il motore ha deciso, cioe' le stesse percentuali del
# conto). Base FISSA: i profitti non si reinvestono e un calo non riduce le puntate. Con 1000$ la scala e' 1
# e tutto e' identico a prima. Se la variabile manca vale 1000 (prima 1500: ma 1500 sarebbe scala 1.5).
_PORTFOLIO_CAPITAL = float(
    os.getenv(f"DESK_{PORTFOLIO.name.upper()}_CAPITAL")
    or os.getenv("DESK_PORTFOLIO_CAPITAL")
    or "1000"
)
CAPITAL_REF = float(PORTFOLIO.limits.start_equity)
CAPITAL_SCALE = _PORTFOLIO_CAPITAL / CAPITAL_REF if CAPITAL_REF > 0 else 1.0

# Connettore live — no-op in paper mode, attivo se DESK_MODE=live
# Lancia ValueError all'avvio se le chiavi API mancano o la scala non e' valida in modalità live
LIVE = LiveConnector(data_dir=DATA_DIR, scale=CAPITAL_SCALE)
set_context(PORTFOLIO.name, LIVE._live, CAPITAL_SCALE)   # intestazione LIVE / NON REALE nei messaggi Telegram

# ── Limite perdita giornaliero (solo in modalità live) ───────────────────────
# DESK_DAILY_LOSS_PCT: percentuale massima di perdita giornaliera (default 25%) del capitale assegnato.
# Esempio: capitale $1000, pct 25% → massima perdita $250/giorno (reali: il confronto usa la scala).
_DAILY_LOSS_PCT = float(os.getenv("DESK_DAILY_LOSS_PCT", "25")) / 100.0
_DAILY_LOSS_LIMIT = _PORTFOLIO_CAPITAL * _DAILY_LOSS_PCT

print(f"[CAPITAL] {PORTFOLIO.name.upper()} capitale={_PORTFOLIO_CAPITAL:.0f}$ scala={CAPITAL_SCALE:g} "
      f"limite_perdita_giornaliero={_DAILY_LOSS_LIMIT:.0f}$ ({_DAILY_LOSS_PCT*100:.0f}%)", flush=True)

# ── Momento in cui il bot e' partito in live (persistito) ────────────────────
# Lo storico e le posizioni del simulatore stanno negli stessi file: l'app e il limite giornaliero contano
# come "veri" solo i trade APERTI dopo questo momento.
LIVE_SINCE_MS: Optional[int] = None
_LIVE_SINCE_FILE = os.path.join(DATA_DIR, "live_since.json")


def ensure_live_since(now_ms: Optional[int] = None) -> Optional[int]:
    """In live: legge (o crea alla prima partenza) live_since.json. In paper: None. Non lancia mai."""
    global LIVE_SINCE_MS
    if not LIVE._live:
        return None
    since = None
    try:
        with open(_LIVE_SINCE_FILE) as f:
            since = int(float(json.load(f).get("since_ms") or 0)) or None
    except Exception:
        since = None
    if not since:
        since = int(time.time() * 1000) if now_ms is None else int(now_ms)
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(_LIVE_SINCE_FILE + ".tmp", "w") as f:
                json.dump({"since_ms": since}, f)
            os.replace(_LIVE_SINCE_FILE + ".tmp", _LIVE_SINCE_FILE)
        except Exception as e:
            print(f"[LIVE] impossibile salvare live_since.json: {e}", flush=True)
    LIVE_SINCE_MS = since
    return since


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
    # in live contano solo i trade aperti DOPO la partenza del live: le chiusure di posizioni del simulatore
    # (aperte prima) non sono perdite vere e non devono bloccare le aperture
    since = LIVE_SINCE_MS if LIVE._live else None
    return sum(
        c.get("net", 0.0)
        for c in (acc.closed or [])
        if (c.get("close_ms") or 0) >= midnight_ms
        and (not since or (c.get("open_ms") or 0) >= since)
    )


def _daily_loss_exceeded(acc) -> bool:
    """
    True se la perdita realizzata oggi supera il limite configurato.
    Attivo solo in modalità live — in paper mode non blocca mai.
    """
    if not LIVE._live:
        return False
    pnl = _daily_realized_pnl(acc) * CAPITAL_SCALE      # dal conto del motore alla scala reale
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


BAR15_MS = 900_000
DAILY_LIMIT = 260
_DAILY_CACHE: dict = {}   # simbolo -> (giorno UTC dello scarico, barre 1d chiuse)


def closed_bars(arr, now_ms: int, bar_ms: int = BAR15_MS):
    """Solo barre CHIUSE: BitGet mette per ultima la barra ancora in formazione (massimo/minimo parziali).
    Indicatori e controlli di stop/TP usano solo barre definitive (difetto B)."""
    if arr is None or len(arr) == 0:
        return arr
    return arr[arr[:, 0] + bar_ms <= now_ms]


def daily_bars(symbol: str, now_ms: int):
    """Barre 1d chiuse per il trend di lungo (EMA50/EMA200 giornaliere). Un solo scarico per simbolo al giorno.
    Se lo scarico fallisce o la serie non e' regolare il trend 1d resta assente, come prima della correzione."""
    from desk.signals import closed_daily
    day = int(now_ms) // 86_400_000
    hit = _DAILY_CACHE.get(symbol)
    if hit is not None and hit[0] == day:
        return hit[1]
    arr = closed_daily(fetch_candles(symbol, "1D", DAILY_LIMIT), now_ms)
    if len(arr):
        _DAILY_CACHE[symbol] = (day, arr)
    return arr


def _capital_enabled() -> bool:
    # Off by default. HARD PAPER-only gate; no real exchange movements.
    return os.getenv("DESK_CAPITAL_V1", "").lower() == "paper" and not LIVE._live


def _capital_journal():
    from desk.capital_journal import PaperCapitalJournal
    return PaperCapitalJournal(DATA_DIR, PORTFOLIO.name)


def load_state(path: str) -> dict:
    if _capital_enabled() and path == STATE_FILE and os.path.exists(_capital_journal().journal_path):
        # Corrupt journal MUST fail closed, not silently recreate a $1000 account.
        return _capital_journal().recover()
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            if _capital_enabled() and path == STATE_FILE:
                raise
    return {}


def save_state(state: dict, path: str) -> None:
    if _capital_enabled() and path == STATE_FILE and (state.get("capital") or {}).get("schema_version")==1:
        from desk.capital_manager import dec
        disk=_capital_journal().recover()
        if disk == state:
            return
        before=disk.get("capital") or {}
        after=state["capital"]
        old_v=dec((before.get("vault") or {}).get("balance",0))
        new_v=dec((after.get("vault") or {}).get("balance",0))
        if old_v != new_v:
            if (before.get("day") or {}).get("utc_day") != (after.get("day") or {}).get("utc_day"):
                kind="rollover"
            elif len(after.get("receipts") or {}) > len(before.get("receipts") or {}):
                kind="withdraw"
            else:
                kind="settle"
            event_id=f"capital:{kind}:{time.time_ns()}"
        else:
            event_id=f"snapshot:{time.time_ns()}"
        result=_capital_journal().commit_snapshot(state,event_id=event_id)
        state.clear()
        state.update(result)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp=path+".tmp"
    with open(tmp,"w") as f:
        json.dump(state,f,default=str)
    os.replace(tmp,path)


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
        if _capital_enabled() and (state.get("capital") or {}).get("schema_version")==1:
            from desk.capital_manager import DayReference
            from dataclasses import replace
            cap=state["capital"]
            ref=DayReference.from_dict(cap["day"])
            if cap.get("status") != "READY":
                ref=replace(ref,day_budget=0,stop_latched=True)
            acc.set_capital_policy(PORTFOLIO.name,ref.day_budget,ref)
        return acc
    return PaperAccount(PORTFOLIO.limits, "main")


# ---- heartbeat: dice all'app (e al healthcheck) che il bot e' vivo e cosa sta facendo
HB: dict = {"started_ms": int(time.time() * 1000), "version": CODE_VERSION, "pid": os.getpid(),
            "cycles": 0, "last_start_ms": 0, "last_end_ms": 0, "last_ok": None, "last_error": "",
            "next_cycle_ms": 0,
            # Dice all'app che in questa versione il reset del portafoglio NON cancella il cervello (storico dei
            # trade, appunti, registro). Senza questo campo l'app tiene bloccato il pulsante di azzeramento.
            "reset_keeps_brain": True,
            # Dice all'app che questa versione sa chiudere una singola posizione su richiesta dell'utente.
            # Con un bot piu' vecchio il tasto non appare (il comando resterebbe in attesa e scatterebbe dopo).
            "close_position": True}
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
    HB["capital_usd"] = _PORTFOLIO_CAPITAL                 # capitale assegnato
    HB["capital_scale"] = CAPITAL_SCALE                    # ordini veri = importi del motore x scala
    HB["capital_v1"] = bool(_capital_enabled() and state and
                            (state.get("capital") or {}).get("status")=="READY")
    if LIVE._live:
        HB["live_since_ms"] = LIVE_SINCE_MS                # da quando i trade contano come veri
    if LIVE._live:   # stato del collegamento con l'exchange: l'app mostra il blocco aperture se c'e'
        HB["live_interlock"] = LIVE.interlock
        HB["live_pending_close"] = sorted(LIVE.pending_close)
        HB["live_stale_protection"] = sorted(LIVE.stale_protection)
    try:
        HB["claude_schedule"] = schedule_summary(schedule_state(DATA_DIR, int(now * 1000)))
    except Exception:
        pass   # il calendario non deve mai fermare il bot
    try:
        HB["hours"] = trading_hours.summary(trading_hours.hours_state(DATA_DIR, int(now * 1000)))
    except Exception:
        pass   # gli orari di trading non devono mai fermare il bot
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


def history_row(state: dict, rec: dict) -> dict:
    """Riga dello storico permanente: il trade del motore piu' la run e il capitale di partenza di quella run.
    Lo storico non si cancella mai (nemmeno con il reset del portafoglio): questi due campi dicono in quale
    fase e' nato ogni trade, cosi' si possono confrontare run con strategie o capitali diversi.
    Il record del motore resta com'e' (si lavora su una copia)."""
    row = dict(rec)
    row["run_no"] = state.get("run_no", 1)
    row["start_equity"] = PORTFOLIO.limits.start_equity
    return row


def record_close(state: dict, rec: dict) -> None:
    """Ogni chiusura (finale o parziale) va nello storico dei trade e nel registro di apprendimento."""
    append_trade_history(DATA_DIR, history_row(state, rec))
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


_FOUR_HOUR_CACHE = {}


def four_hour_bars(symbol, now_ms):
    from desk.signals import closed_four_hour, H4
    key = now_ms // H4
    cached = _FOUR_HOUR_CACHE.get(symbol)
    if cached and cached[0] == key:
        return cached[1]
    if cached and now_ms-cached[2] < 300000:
        return cached[1]
    try:
        result = closed_four_hour(fetch_candles(symbol, "4H", limit=300), now_ms)
    except (ValueError, TypeError):
        result = []
    if len(result) >= 200:
        _FOUR_HOUR_CACHE[symbol] = (key,result,now_ms)
        return result
    # Do not carry a stale trend forward as if it were a fresh 4h observation.
    _FOUR_HOUR_CACHE[symbol] = (None,None,now_ms)
    return None


def position_info(pos, price: float, readings: dict, now_ms: int, closed=(), limits=None) -> dict:
    from desk.position_card import metrics
    r = readings.get(pos.symbol)
    extra = metrics(pos, price, now_ms, closed, limits or Limits())
    return {
        **extra,
        "split_pending": pos.pending_split,
        "symbol": pos.symbol, "side": pos.side, "leverage": pos.leverage,
        "margin": pos.total_margin, "total_margin": pos.total_margin,
        "trade_type": pos.trade_type, "dca_count": pos.dca_count,
        "entry": pos.entry, "price": price, "sl": pos.sl,
        "pnl": pos.side * (price - pos.entry) * pos.qty,
        "hours": (now_ms - pos.open_ms) / 3_600_000,
        "score_now": (r.long_score if pos.side == 1 else r.short_score) if r else None,
        "score_opposite": (r.short_score if pos.side == 1 else r.long_score) if r else None,
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


def process_closed_bars(state: dict, acc, closed_map: dict, now_ms: int, bar_ms: int = BAR15_MS) -> None:
    """Stop, liquidazioni, take profit e seconda gamba al ritracciamento sulle barre CHIUSE non ancora giudicate.
    L'engine ricorda l'ultima barra elaborata per ogni posizione: ogni barra si giudica una volta sola, con i
    livelli in vigore in quel momento."""
    for sym, pos in list(acc.positions.items()):
        arr = closed_map.get(sym)
        if arr is None:
            continue
        for row in arr:
            ts, o, h, l, c = int(row[0]), row[1], row[2], row[3], row[4]
            # LIVE: con una seconda gamba in attesa la barra puo' farla scattare: serve poter tornare indietro
            before = None
            if LIVE._live and sym in acc.positions and acc.positions[sym].pending_split:
                before = live_sync.snapshot_position(acc, sym)
            # LIVE: la seconda gamba parte sull'exchange dopo la candela; se la candela chiude la posizione non esiste
            result = acc.on_bar(sym, ts, o, h, l, c, bar_ms, exit_first=bool(LIVE._live))
            if LIVE._live:
                note = live_sync.after_bar(LIVE, acc, sym, before, result, alert=notify_live_alert, now_ms=now_ms)
                if note:
                    print(f"[LIVE] {note}", flush=True)
            if result:
                print(f"[{result['why'].upper()}] {sym} net {result['net']:+.2f}$")
                notify_close(sym, result["net"], result.get("why", ""), result["why"])
                record_close(state, result)
                break
    flush_events(state, acc)


def margin_room(acc) -> float:
    """Margine che il motore concederebbe a una nuova apertura: STESSA formula di PaperAccount.open
    (engine.py: room = min(max_margin_trade, max_margin_total - margine in uso, cassa*0.95))."""
    L = acc.limits
    return min(L.max_margin_trade, L.max_margin_total - acc.margin_in_use(), acc.cash * 0.95)


MARGIN_EPS = 1e-9   # tolleranza in dollari per l'aritmetica in virgola mobile: esattamente 150,00 e' ammesso


def margin_gate(acc, pg) -> Optional[str]:
    """Opzione A di Alexander. Ritorna None se l'apertura puo' procedere, altrimenti il motivo del rifiuto.
    Si guarda il margine disponibile PRIMA di un eventuale split (la richiesta complessiva, non la prima gamba).
    Una taglia ridotta dal motore ma ancora >= minimo e' ammessa. Solo per i portafogli con
    refuse_below_min_margin (Bull); Hawk resta com'era.

    Difesa-in-profondita' (rilievo ChatGPT, audit e7c5f03): se cassa, margini in uso o limiti monetari
    contengono NaN o infiniti, Python min() restituisce risultati inaffidabili (NaN e' sempre 'non minore',
    inf altera il calcolo della room). Il controllo precede margin_room per evitare falsi 'ammesso'."""
    if not pg.refuse_below_min_margin:
        return None
    # ── guardia NaN/inf sui valori contabili usati da margin_room ────────────────────────────────
    import math as _math
    L = acc.limits
    _contabili = {
        "cassa":             acc.cash,
        "margine_in_uso":    acc.margin_in_use(),
        "limite_per_trade":  L.max_margin_trade,
        "limite_totale":     L.max_margin_total,
    }
    for nome, val in _contabili.items():
        if not _math.isfinite(val):
            return (f"stato contabile non finito ({nome}={val}): apertura Bull rifiutata per sicurezza")
    # ─────────────────────────────────────────────────────────────────────────────────────────────
    room = margin_room(acc)
    if room < pg.guardrail_min_margin - MARGIN_EPS:
        return (f"margine disponibile {room:.2f}$ sotto il minimo {pg.guardrail_min_margin:.0f}$ "
                f"di {pg.name}: nessun ridimensionamento sotto il minimo")
    return None


def leverage_gate(dec: dict, pg) -> Optional[str]:
    """Opzione B di Alexander. Ritorna None se la leva proposta e' ammessa, altrimenti il motivo del rifiuto.
    Si guarda la leva CHE IL MOTORE userebbe (quella nel dec, dopo il guardrail), non la raw di Claude.
    Se max_leverage e' None (default per un portfolio senza limite esplicito) il controllo non scatta mai."""
    if pg.max_leverage is None:
        return None
    lev = int(dec.get("leverage", 0))
    if lev > pg.max_leverage:
        return (f"leva proposta {lev}x supera il massimo {pg.max_leverage}x "
                f"di {pg.name}: nessuna apertura con leva eccessiva")
    return None


def account_snapshot(acc, equity: float, halt) -> dict:
    """Riassunto del conto per il prompt di Claude. Tetto di margine e numero di posizioni sono quelli VERI del
    portafoglio (Hawk e Bull hanno limiti diversi): prima il prompt diceva a tutti '/2000$' e '/10'."""
    return {
        "equity": equity, "cash": acc.cash, "margin": acc.margin_in_use(),
        "n_open": len(acc.positions), "day_pnl": equity - acc.day_start_equity,
        "halt": halt,
        "max_margin": acc.limits.max_margin_total, "max_open": acc.limits.max_open,
    }


def run_cycle(state: dict, now_ms: int, drain: bool = False) -> None:
    """Un ciclo di mercato.

    drain=True e' la PAUSA: le posizioni aperte continuano a essere gestite (stop loss,
    take profit, liquidazione e uscite decise da regole/Claude) ma non si apre nulla di
    nuovo e non si fanno DCA. Nessuna posizione viene chiusa a forza.
    """
    import numpy as np

    acc = make_account(state)
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000))
    claude_ok = apply_claude_schedule(state, now_ms, day)

    # ── LIVE: stato dell'exchange a inizio ciclo (decide se si possono aprire nuove posizioni) ──
    if LIVE._live:
        live_sync.sync(LIVE, acc, {}, now_ms, close_engine=False, alert=notify_live_alert)

    # carica candele per tutti i simboli
    candles_map: dict = {}
    for sym in SYMBOLS:
        arr = fetch_candles(sym)
        if arr:
            candles_map[sym] = np.array(arr)
        time.sleep(0.05)   # gentile con l'API
        write_heartbeat(state, force=False)   # il ciclo puo' durare un minuto: il bot resta "vivo"

    print(f"[DESK V2] candles ok: {len(candles_map)}/{len(SYMBOLS)} simboli", flush=True)
    prices = get_prices(SYMBOLS, candles_map)   # ultimo prezzo: la barra in formazione serve solo a questo
    closed_map = {s: closed_bars(a, now_ms) for s, a in candles_map.items()}
    # ultimi prezzi noti: la dashboard li usa come ripiego per il P&L live delle posizioni
    if prices:
        state["last_prices"] = {s: p for s, p in prices.items()}
        state["last_prices_ms"] = now_ms
    capital_mode = _capital_enabled() and (state.get("capital") or {}).get("schema_version")==1
    if capital_mode:
        from desk.capital_runtime import rollover_today
        if (state["capital"].get("day") or {}).get("utc_day") != day:
            # Apply all completed bars prior to the 00:00 UTC boundary FIRST.
            boundary_ms=(now_ms // 86400000)*86400000
            old_bars={sym:arr[arr[:,0]+BAR15_MS<=boundary_ms]
                      for sym,arr in closed_map.items()}
            process_closed_bars(state,acc,old_bars,now_ms)
            save_account(acc,state)
            save_state(state,STATE_FILE)
            rollover_today(state,now_ms,candles_map)
            save_state(state,STATE_FILE)
            acc=make_account(state)
            closed_map={sym:arr[arr[:,0]+BAR15_MS>boundary_ms]
                        for sym,arr in closed_map.items()}
        if state["capital"].get("status")!="READY":
            drain=True
    else:
        # Legacy 12% behavior remains intact with feature disabled.
        acc.roll_day(day,prices)

    # In pausa (o fuori orario) non entra nulla di nuovo: nemmeno la seconda gamba di un'entrata diversificata.
    early_why = drain_reason(now_ms)
    if drain or early_why:
        for s in list(acc.positions):
            acc.cancel_split(s, "fuori dagli orari di trading" if early_why == "orari" else "bot in pausa", now_ms)
    # Barre chiuse PRIMA delle decisioni (difetto A): stop, liquidazioni e TP scattati dall'ultimo ciclo si
    # contano con i livelli che erano in vigore; le decisioni di questo ciclo valgono solo per le barre future.
    process_closed_bars(state, acc, closed_map, now_ms)
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

    # calendario macro: regime del momento. NON solleva mai: se manca il dato o qualcosa va storto e' uno stato
    # neutro (nessun blocco, nessun bonus) e il bot lavora come prima.
    macro = macro_calendar.current(DATA_DIR, now_ms)
    HB["macro"] = macro_calendar.heartbeat_view(macro)
    macro_feats = macro_calendar.features(macro)
    if macro["regime"] in ("medio", "alto"):
        nxt = macro.get("next")
        print(f"[MACRO] regime {macro['regime'].upper()}  blocco nuove aperture={'SI' if macro['blackout'] else 'no'}  "
              f"bonus confidenza=+{macro['conf_bonus']}"
              + (f"  prossimo: {nxt['title']} tra {nxt['min']} min" if nxt else "")
              + ("" if macro.get("enforce", True) else "  [OSSERVAZIONE: registra, non frena]"), flush=True)
    elif macro["regime"] == "nd":
        print(f"[MACRO] calendario non disponibile ({macro.get('error') or 'nessun dato'}): il bot lavora come prima",
              flush=True)

    # segnali tecnici
    readings_list = []
    readings_map: dict = {}
    for sym in SYMBOLS:
        arr = closed_map.get(sym)
        if arr is None or len(arr) < 80:
            continue
        try:
            dly = daily_bars(sym, now_ms)
        except Exception:
            dly = None
        r = read_symbol(sym, arr, now_ms, daily=dly, price=prices.get(sym),
                        four_hour=four_hour_bars(sym, now_ms))
        if r is not None:
            readings_list.append(r)
            readings_map[sym] = r

    print(f"[DESK V2] readings validi: {len(readings_list)}/{len(SYMBOLS)} simboli", flush=True)
    open_symbols = set(acc.positions)

    # snapshot conto per il prompt
    eq = acc.equity(prices)
    snap = account_snapshot(acc, eq, halt)

    # posizioni aperte con info aggiornate
    pos_info = [position_info(pos, prices.get(sym, pos.entry), readings_map, now_ms, acc.closed, acc.limits)
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
    elif call_due and not claude_ok:
        print("[FINESTRA] fuori dal calendario: Claude non viene consultato, decidono le regole", flush=True)
    elif call_due and can_call(state, day):
        try:
            prompt = build_prompt(snap, readings_list, pos_info, headlines, lessons, ctx_for_prompt, sym_stats,
                                  macro_lines="\n".join(macro_calendar.prompt_lines(macro)))
            max_tok, timeout_s = claude_limits(LIVE._live)
            text, usage = call_claude(SYSTEM, prompt, max_tokens=max_tok, timeout=timeout_s)
            cost = record_spend(state, day, usage)
            state["last_call_ms"] = now_ms
            parsed = parse_decisions(text)
            log_claude_call(now_ms, state, text, usage, cost, parsed, len(prompt),
                            len(acc.positions), urgent_scalp, max_tok)
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

    why = drain_reason(now_ms)   # "pausa" | "orari" | "" ; la pausa premuta a ciclo in corso vale da subito
    if why:
        drain = True
    why_txt = "fuori dagli orari di trading" if why == "orari" else "bot in pausa"
    if drain:
        # PAUSA: solo gestione delle posizioni esistenti. Ingressi e DCA sono scartati qui,
        # prima dell'esecuzione, qualunque sia la loro origine (Claude o regole).
        skipped = [d for d in decisions if d["action"] not in MANAGE_ACTIONS]
        decisions = [d for d in decisions if d["action"] in MANAGE_ACTIONS]
        if skipped:
            print(f"[{'ORARI' if why == 'orari' else 'PAUSA'}] {len(skipped)} nuovi ingressi/DCA ignorati: {why_txt} "
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
                                           readings_map.get("BTC"), extra=macro_feats),
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
                if LIVE._live and LIVE.last_fill:
                    closed["live"] = dict(LIVE.last_fill)   # prezzo/quantita'/fee REALI accanto a quelli simulati
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
                new_tp = _sane_tp(sym, px * (1 + pos.side * tp2_pct), "chiusura parziale")
            # ── LIVE: riduci la posizione reale PRIMA di aggiornare il motore ────
            live_fill = None
            if LIVE._live:
                live_ok, live_detail = live_sync.partial_on_exchange(LIVE, pos, fraction)
                if not live_ok:
                    print(f"[LIVE PARTIAL FALLITA] {sym}: {live_detail} — posizione resta com'e'")
                    continue
                live_fill = dict(LIVE.last_fill)
            # ─────────────────────────────────────────────────────────────────
            partial = acc.partial_close(sym, px, now_ms, fraction, new_tp=new_tp,
                                        why=dec.get("reason", "TP parziale")[:80])
            if partial:
                if live_fill is not None:
                    partial["live"] = live_fill
                    if new_tp is not None:   # il nuovo take profit del motore va anche sull'exchange
                        LIVE.set_protection(sym, pos.side, pos.sl, pos.tp)
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
            new_tp = _sane_tp(sym, px * (1 + pos.side * tp_pct), "DCA") if tp_pct > 0 else None
            before = live_sync.snapshot_position(acc, sym) if LIVE._live else None
            result, msg = acc.add_dca(sym, new_sl, new_tp, now_ms, prices, dec.get("reason", "")[:80])
            if result and LIVE._live:
                # ── LIVE: i contratti aggiunti vanno sull'exchange; se rifiuta il DCA si annulla ────
                live_ok, live_detail = live_sync.dca_on_exchange(LIVE, acc, sym, before, px)
                if not live_ok:
                    print(f"[LIVE DCA FALLITO] {sym}: {live_detail} — DCA annullato nel motore")
                    result, msg = None, f"live: {live_detail}"
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
            # ── CALENDARIO MACRO: nessuna NUOVA apertura attorno a un evento ad alto impatto ──────────────
            # (le posizioni gia' aperte non vengono toccate: stop, take profit, DCA e chiusure restano come sempre)
            # soglia confidenza tier-aware, piu' il bonus del regime macro (0 se calmo o calendario non disponibile)
            base_thr = tier_entry_score(sym)
            # MODALITA' OSSERVAZIONE (predefinita): il calendario si legge e si registra ma non frena. Blocco e bonus
            # si applicano solo se l'utente ha acceso `macro_enforce.flag` (vedi macro_calendar).
            macro_on = bool(macro.get("enforce", True))
            m_block = bool(macro["blackout"]) and macro_on
            m_bonus = macro["conf_bonus"] if macro_on else 0
            # "macro_blocco" si registra solo per chi avrebbe superato la soglia NORMALE: chi non la supera si ferma
            # comunque piu' sotto per confidenza bassa, e contarlo come bloccato dalla macro gonfierebbe l'effetto.
            if m_block and dec["confidence"] >= base_thr:
                print(f"[MACRO_BLOCCO] {sym}: nuova apertura sospesa fino alle "
                      f"{macro_calendar.hm_utc(macro['blackout_until_ms'])} UTC (evento macro)", flush=True)
                _candidate("macro_blocco", dec, px)
                continue
            if macro["blackout"] and not macro_on and dec["confidence"] >= base_thr:
                print(f"[MACRO_OSSERVATO] {sym}: dentro una finestra a rischio (fino alle "
                      f"{macro_calendar.hm_utc(macro['blackout_until_ms'])} UTC) ma in osservazione: non frena", flush=True)
            thr = base_thr + m_bonus
            if dec["confidence"] < thr:
                print(f"[CONF_LOW] {sym} conf={dec['confidence']} < soglia={thr}"
                      + (f" ({base_thr}+{m_bonus} macro)" if m_bonus else ""))
                _candidate("conf_bassa_macro" if dec["confidence"] >= base_thr else "conf_bassa", dec, px)
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
            tp = _sane_tp(sym, px * (1 + side * tp_pct), "apertura") if tp_pct > 0 else None
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
                                       readings_map.get("BTC"), extra=macro_feats)
            except Exception:
                feats = {}   # la registrazione non deve mai impedire un'apertura
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
            # ── BLOCCO DI SICUREZZA LIVE (posizione estranea, lettura fallita, ...) ────────
            if LIVE._live and LIVE.open_blocked():
                print(f"[LIVE BLOCCO] {sym}: nuove aperture bloccate — {LIVE.open_blocked()}", flush=True)
                _candidate("live_bloccato", dec, px)
                continue
            # ─────────────────────────────────────────────────────────────────
            # ── OPZIONE A (Bull): margine disponibile sotto il minimo -> si rifiuta, non si ridimensiona ──
            why_margin = margin_gate(acc, pg)
            if why_margin:
                print(f"[SKIP:{pg.name.upper()}] {sym} {act}: {why_margin}", flush=True)
                _candidate("rifiutata:margine_sotto_minimo", dec, px)
                continue
            # ── OPZIONE B: leva proposta sopra il massimo -> si rifiuta ────────────────────────────────
            why_lev = leverage_gate(dec, pg)
            if why_lev:
                print(f"[SKIP:{pg.name.upper()}] {sym} {act}: {why_lev}", flush=True)
                _candidate("rifiutata:leva_sopra_massimo", dec, px)
                continue
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
                    live_ok, live_detail = live_sync.open_on_exchange(LIVE, pos, px)
                    if not live_ok:
                        # Bitget ha rifiutato: annulla la posizione in memoria
                        live_sync.rollback_open(acc, pos)
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
                    "live_fill": dict(LIVE.last_fill) if LIVE._live else None,
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
            acc.cancel_split(s, why_txt, now_ms)

    flush_events(state, acc)

    # ── LIVE: riallinea il motore all'exchange (la verita') e aggiorna il blocco aperture ──────
    if LIVE._live:
        res = live_sync.sync(LIVE, acc, prices, now_ms, close_engine=True, alert=notify_live_alert)
        for rec in res["closed"]:
            print(f"[CHIUSA SU BITGET] {rec['symbol']} net {rec['net']:+.2f}$ (stima del motore)", flush=True)
            notify_close(rec["symbol"], rec["net"], "chiusa su Bitget", rec["why"])
            record_close(state, rec)
        for n in res["notes"]:
            print(f"[LIVE SYNC] {n}", flush=True)
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

    # ---- salva in due transazioni distinte: prima tutti i trade, poi il vault
    save_account(acc,state)
    if capital_mode:
        from desk.capital_runtime import update_market_risk,settle_after_close
        update_market_risk(state,prices,now_ms=now_ms)
    save_state(state,STATE_FILE)
    if capital_mode and state["capital"].get("status")=="READY":
        try:
            if settle_after_close(state, {sym:prices[sym] for sym in acc.positions if sym in prices},
                                  event_id=f"settle:cycle:{now_ms}"):
                save_state(state,STATE_FILE)
        except Exception as exc:
            print(f"[CAPITAL] pending rinviato: {type(exc).__name__}",flush=True)

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


def _close_for_user(state: dict, acc: PaperAccount, sym: str, px: float, now_ms: int) -> tuple:
    """Chiude UNA posizione a prezzo di mercato perche' lo ha chiesto l'utente (Chiudi tutto o Chiudi singola).
    In live prima sull'exchange: se Bitget non chiude, la posizione resta aperta anche nel motore.
    Il trade entra nello storico e nel registro come tutti gli altri (vinto o perso secondo il profitto vero),
    con in piu' `closed_by: "utente"` per poter separare in analisi cio' che ha deciso il bot da cio' che ha
    deciso l'utente: non cambia l'esito, non e' un trade "falso".
    Ritorna (record, "") se chiusa, (None, motivo) se non e' stata chiusa."""
    # ── LIVE: chiudi su Bitget prima di aggiornare il motore ─────────
    if LIVE._live:
        pos_pre = acc.positions.get(sym)
        if pos_pre:
            live_ok, live_detail = LIVE.close(sym, pos_pre.side, pos_pre.qty)
            if not live_ok:
                print(f"[LIVE CLOSE FALLITA] {sym}: {live_detail} — skip chiusura manuale")
                return None, str(live_detail)[:160] or "chiusura su Bitget non riuscita"
    # ─────────────────────────────────────────────────────────────────
    rec = acc.close(sym, px, now_ms, "chiusura manuale")
    if rec is None:
        return None, "posizione non trovata"
    rec["closed_by"] = "utente"
    if LIVE._live and LIVE.last_fill:
        rec["live"] = dict(LIVE.last_fill)
    record_close(state, rec)
    return rec, ""


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
            rec, why_not = _close_for_user(state, acc, sym, px, now_ms)
            if why_not:
                skipped.append(sym)
                continue
            if rec:
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
        "entry_score_base": _ENTRY_SCORE_BASE, "entry_score_tier_ab": TIER_AB_ENTRY_SCORE,
        "entry_score_tier_c": TIER_C_ENTRY_SCORE,
        "guardrail": {"min_margin": p.guardrail_min_margin, "min_lev": p.guardrail_min_lev,
                      "margin_forced": p.guardrail_margin_forced, "lev_forced": p.guardrail_lev_forced,
                      "type_forced": p.guardrail_type_forced,
                      "max_leverage": p.max_leverage},   # OPZIONE B
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


def _check_close_position_flag(state: dict) -> bool:
    """close_position.flag = {"symbols": [...], "ts": ms}: l'utente vuole chiudere queste posizioni (non tutte) a
    prezzo di mercato. Stesse regole di 'Chiudi tutto': in live prima su Bitget, mai un'uscita inventata se
    manca il prezzo. Sicurezze: una richiesta vecchia (clic dimenticato) non si esegue; un simbolo gia' chiuso
    non e' un errore; il file si 'prende in carico' con un rinomina cosi' un secondo clic arrivato intanto
    non va perso. L'esito va in state['last_action'] e l'app lo mostra."""
    path = _flag("close_position.flag")
    if not os.path.exists(path):
        return False
    work = path + ".work"
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
        prices = _market_prices(present, state) if present else {}
        closed, failed, net = [], [], 0.0
        for sym in present:
            px = prices.get(sym)
            if px is None:
                failed.append((sym, "prezzo non disponibile"))
                continue
            rec, why_not = _close_for_user(state, acc, sym, px, now_ms)
            if why_not:
                failed.append((sym, why_not))
                continue
            closed.append(sym)
            net += rec["net"]
            try:
                notify_close(sym, rec["net"], "su tua richiesta", "chiusura manuale")
            except Exception:
                pass   # il messaggio Telegram non deve mai fermare la chiusura
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
        save_state(state, STATE_FILE)
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
    posizioni aperte. Dopo il reset resta in pausa: sei tu a premere Avvia.
    Il reset riguarda SOLO il conto. Il cervello (storico dei trade, appunti, errori ricorrenti, registro di
    apprendimento) resta dov'e' e continua a crescere: nessuna opzione lo cancella."""
    path = _flag("reset_portfolio.flag")
    if not os.path.exists(path):
        return False
    try:
        try:
            with open(path) as f:
                opts = json.loads(f.read() or "{}")
        except Exception:
            opts = {}
        if isinstance(opts, dict) and opts.get("clear_lessons"):
            print("[RESET PORTAFOGLIO] richiesta di cancellare gli appunti IGNORATA: il cervello non si cancella",
                  flush=True)
        clear_lessons = False        # mai: il cervello non si cancella da nessun comando
        if _capital_enabled() and (state.get("capital") or {}).get("schema_version")==1:
            _set_last_action(state,"reset_portfolio",False,
                             "rifiutato: salvadanaio V1 richiede procedura di migrazione separata")
            save_state(state,STATE_FILE)
            return False
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
        archive = _archive_run(state, acc, clear_lessons)   # se fallisce, il reset non parte
        # Nessun file del cervello viene rimosso o svuotato: trade_history.jsonl, lessons.md, errors.md e
        # learning_log.jsonl restano intatti. L'app mostra solo i trade della run attuale (run_started_ms).
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
                         f"portafoglio ripartito da {PORTFOLIO.limits.start_equity:.0f}$; run precedente archiviata; "
                         f"cervello (storico, appunti, registro) intatto",
                         archive=archive)
        save_state(state, STATE_FILE)
        print(f"[RESET PORTAFOGLIO] run archiviata in {archive}; conto a "
              f"{PORTFOLIO.limits.start_equity:.0f}$, bot in pausa; cervello intatto", flush=True)
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


def _process_vault_request(state: dict) -> bool:
    """Only the PAPER bot consumes the app's manual withdraw request.

    ACK and debit are committed in one journalled snapshot before unlinking
    the request. A crash after commit is recovered through the receipt.
    """
    from desk.capital_runtime import withdraw_request, utc_day
    from desk.capital_manager import CapitalInvariantError
    path=_flag("vault_transfer_request.json")
    if not os.path.exists(path):
        return False
    cap=state.get("capital") or {}
    if cap.get("status")!="READY" or (cap.get("day") or {}).get("utc_day")!=utc_day(int(time.time()*1000)):
        return False  # leave queued while midnight reconciliation is pending
    if LIVE._live:
        return False
    try:
        with open(path,encoding="utf8") as fh:
            request=json.load(fh)
        if not isinstance(request,dict):
            return False
        key=request.get("idempotency_key")
        if not isinstance(key,str) or len(key)>64:
            return False
        try:
            receipt=withdraw_request(state,request,bot=PORTFOLIO.name)
        except (CapitalInvariantError,KeyError,ValueError,TypeError) as e:
            receipt={"status":"rejected","amount":str(request.get("amount",0)),
                     "reason":type(e).__name__}
            state["capital"].setdefault("receipts",{})[key]=receipt
        save_state(state,STATE_FILE)
        os.unlink(path)
        print(f"[CAPITAL] trasferimento {receipt['status']} ({PORTFOLIO.name})",flush=True)
        return True
    except Exception as exc:
        print(f"[CAPITAL] richiesta rimane pendente per recovery: {type(exc).__name__}",flush=True)
        return False


def process_flags(state: dict) -> None:
    """Esegue comandi app; il bot PAPER e' l'unico autore dei saldi."""
    if _capital_enabled():
        _process_vault_request(state)
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
    if _capital_enabled() and (state.get("capital") or {}).get("schema_version")==1:
        from desk.capital_runtime import utc_day, rollover_today
        now_ms=int(time.time()*1000)
        day=utc_day(now_ms)
        if (state["capital"].get("day") or {}).get("utc_day")!=day:
            if not ((state.get("main") or {}).get("positions") or {}):
                if rollover_today(state,now_ms,{}):
                    save_state(state,STATE_FILE)
            else:
                ctl["next_cycle_ms"]=0  # resolve midnight using 15m historical bars
    process_flags(state)
    paused = os.path.exists(_flag("pause.flag"))
    if paused != ctl.get("prev_paused"):
        if ctl.get("prev_paused") is not None:
            print("[PAUSA] richiesta di pausa: finisco le posizioni aperte, nessun nuovo ingresso"
                  if paused else "[AVVIO] ripresa richiesta: il bot lavora", flush=True)
            ctl["next_cycle_ms"] = 0   # reagisce subito al tasto, senza aspettare il prossimo ciclo
        ctl["prev_paused"] = paused
    # orari di trading: fuori dalle fasce il bot si comporta come in pausa (ma la pausa dell'utente vince sempre)
    off_hours = hours_blocked(int(time.time() * 1000))
    if off_hours != ctl.get("prev_off_hours"):
        if ctl.get("prev_off_hours") is not None or off_hours:
            print("[ORARI] fuori dagli orari di trading: finisco le posizioni aperte, nessun nuovo ingresso"
                  if off_hours else "[ORARI] dentro gli orari di trading: il bot lavora", flush=True)
            ctl["next_cycle_ms"] = 0   # entrando in una fascia si parte subito, senza aspettare il prossimo ciclo
        ctl["prev_off_hours"] = off_hours
    drain = paused or off_hours
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
    if int(time.time() * 1000) >= ctl.get("next_cycle_ms", 0) and not (drain and n_open == 0):
        ok = iteration(state, drain=drain)
        wait = cycle_interval_s(state, drain) if ok else RETRY_S
        ctl["next_cycle_ms"] = int(time.time() * 1000) + wait * 1000
        print(f"[SLEEP] prossimo ciclo tra {wait // 60} min", flush=True)
        ran = True
    mode = sync_mode(state)
    write_heartbeat(state, next_cycle_ms=0 if mode == "paused" else ctl.get("next_cycle_ms", 0))
    return ran


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    ensure_live_since()          # solo in live: ricorda il momento della prima partenza
    state = load_state(STATE_FILE)
    if _capital_enabled() and state and "capital" not in state:
        from desk.capital_runtime import initial_capital,utc_day
        state["capital"]=initial_capital(state.get("main") or {},utc_day(int(time.time()*1000)))
        save_state(state,STATE_FILE)
        print("[CAPITAL] migrazione PAPER additiva; nessuna apertura fino al rollover validato",flush=True)

    # ── LIVE: riconciliazione posizioni al riavvio ────────────────────────────
    if LIVE._live:
        acc_check = make_account(state)
        warnings = LIVE.reconcile(acc_check.positions)
        for w in warnings:
            print(w, flush=True)
        if warnings:
            print("[RICONCILIAZIONE] controlla le posizioni su Bitget prima di procedere", flush=True)
        # blocca le nuove aperture finche' motore ed exchange non coincidono (nessuna azione automatica)
        live_sync.sync(LIVE, acc_check, {}, int(time.time() * 1000), close_engine=False,
                       alert=notify_live_alert)
    # ─────────────────────────────────────────────────────────────────────────

    if "--once" in sys.argv:
        process_flags(state)
        iteration(state, drain=bool(drain_reason(int(time.time() * 1000))))
        return

    # ogni riga del registro di apprendimento porta la versione del codice (short SHA del deploy) che l'ha scritta:
    # cosi' l'analista puo' separare i dati prima/dopo una modifica (es. max_tokens 1100 -> 2000 -> 3000)
    _learning.STAMP["code_version"] = CODE_VERSION
    print(f"[DESK V2] avvio [{PORTFOLIO.name.upper()}] versione {CODE_VERSION} — {PORTFOLIO.description}")
    print(f"[DESK V2] simboli: {len(SYMBOLS)}  "
          f"entry_score={TIER_AB_ENTRY_SCORE}(TIER_AB)/{TIER_C_ENTRY_SCORE}(TIER_C)  "
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
