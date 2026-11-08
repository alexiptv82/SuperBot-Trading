"""S25 - strategia LONG per Falco e Toro: EMA9 + VWAP giornaliero, candele da 1 ora. Modulo SEPARATO.

Specifica: ``claude/specifica-long-s25-falco-toro-2026-11-05.md`` (Project). Valori della fonte (G05), non provati da noi.

Interruttore ``DESK_LONG_S25=1`` (spento di default: senza, questo modulo non viene nemmeno importato da ``cli.py``
e il comportamento e' identico a prima). Nessun deploy senza OK esplicito dell'utente.

Regola (solo long, candele da 1 ora CHIUSE, ricavate dalle candele da 15 minuti scartando quelle in formazione):
* VWAP giornaliero: ancora 00:00 UTC, prezzo tipico (max + min + chiusura) / 3 per volume, sulle candele da 1 ora;
  EMA9 sulle chiusure; ATR(14) di Wilder. Stesse definizioni della vista di mercato V3 (prova con vettori fissi).
* Candela di segnale = ultima candela da 1 ora chiusa: EMA9 passa da sotto a sopra il VWAP (EMA9[t-1] <= VWAP[t-1] e
  EMA9[t] > VWAP[t]), chiusura sopra EMA9 e VWAP, volume > 0.
* Ingresso: nella candela da 1 ora successiva, quando il prezzo sta sopra il massimo della candela di segnale ma non
  oltre ``CHASE_ATR`` x ATR sopra di esso (niente inseguimento). Il segnale si ricalcola a ogni giro dalle candele
  (nessuna memoria): dopo un riavvio non si ripete un ingresso gia' fatto.
* Stop 1,5 x ATR, target 1,5 x ATR, chiusura a tempo dopo 12 ore. Un'apertura per simbolo. NESSUN tetto proprio di
  posizioni S25 (decisione dell'utente, 5/11): usa gli slot liberi del portafoglio come le altre aperture e non e'
  obbligatorio riempirli; il tetto resta quello del motore (``Limits.max_open``). Oro e argento INCLUSI (decisione dell'utente, 5/11): nei weekend le serie hanno
  buchi, ``closed_hours`` tiene solo la coda contigua e il VWAP della prima sessione incompleta e' indefinito, quindi
  li' i segnali sono semplicemente meno (nessun segnale falso).
* Dimensione (decisione dell'utente, 5/11): margine ``MARGIN`` per portafoglio (Falco 100 $, Toro 350 $: i tetti per
  trade dei portafogli). Leva: forbice dell'utente 15-35 (Falco) e 15-45 (Toro) in ``LEV_MIN``/``LEV_MAX``; il motore
  applica anche il tetto del simbolo (BTC, oro, argento 45x; ETH 30x; altri 25x), il controllo stop-contro-liquidazione,
  lo stop giornaliero e gli altri limiti. Regola di scelta della leva dentro la forbice: ``leverage_for`` = sempre la minima, 15x (decisione dell'utente, 5/11; si alza solo dopo le prime misure).

Le uscite di S25 sono SOLO stop, target e tempo: ``protect`` toglie le chiusure/DCA decise da regole o da Claude sulle
posizioni S25 (le regole chiuderebbero ogni long quando il punteggio long e' basso, cioe' nei mercati ribassisti).
Solo ``numpy``: l'immagine dei classici non contiene ``backend/v3``.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

import numpy as np

SWITCH = "DESK_LONG_S25"
SOURCE = "rules_long_s25"
STRATEGY_ID = "S25"
M15 = 900_000
H1 = 3_600_000
DAY = 86_400_000
EMA_N = 9
ATR_N = 14
STOP_ATR = 1.5
TARGET_ATR = 1.5
CHASE_ATR = 0.5                      # massimo scostamento sopra il trigger, in ATR (mia scelta, da confermare)
MAX_HOLD_MS = 12 * H1
COOLDOWN_MS = H1                     # come MEDIO_COOLDOWN_MS di cli.py
EXCLUDED: frozenset = frozenset()    # nessun simbolo escluso: oro e argento inclusi per decisione dell'utente
MARGIN = {"hawk": 100.0, "bull": 350.0}      # margine per posizione S25 ($), uguale al tetto per trade del portafoglio
LEV_MIN = 15
LEV_MAX = {"hawk": 35, "bull": 45}           # forbice dell'utente; il motore applica in piu' il tetto del simbolo
PROTECTED_ACTIONS = ("close", "partial_close", "dca")
MIN_HOURS = ATR_N + 2                # barre orarie contigue minime per calcolare il segnale


def enabled(env: Optional[dict] = None) -> bool:
    return (os.environ if env is None else env).get(SWITCH) == "1"


# ----------------------------------------------------------------------------------------------- candele
def closed_hours(arr15: np.ndarray, now_ms: int) -> np.ndarray:
    """Candele da 1 ora CHIUSE ``[apertura_ms, o, h, l, c, volume]``: 4 barre da 15 minuti contigue e tutte chiuse
    (``apertura + 15 minuti <= now``), righe non finite o non positive scartate; solo la coda contigua piu' recente."""
    empty = np.empty((0, 6))
    if arr15 is None or len(arr15) == 0:
        return empty
    a = np.asarray(arr15, dtype=float)
    if a.ndim != 2 or a.shape[1] < 6:
        return empty
    a = a[:, :6]
    ok = np.isfinite(a).all(axis=1) & (a[:, 1:5] > 0).all(axis=1) & (a[:, 5] >= 0)
    ok &= a[:, 0] + M15 <= now_ms
    a = a[ok]
    if len(a) == 0:
        return empty
    a = a[np.argsort(a[:, 0], kind="stable")]
    ts = a[:, 0].astype(np.int64)
    keys = ts // H1
    out = []
    for k in np.unique(keys):
        g = a[keys == k]
        t = g[:, 0].astype(np.int64)
        if len(g) == 4 and int(t[-1] - t[0]) == 3 * M15 and (np.diff(t) == M15).all():
            out.append([k * H1, g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()])
    if not out:
        return empty
    h = np.array(out, dtype=float)
    start = len(h) - 1
    while start > 0 and int(h[start, 0] - h[start - 1, 0]) == H1:
        start -= 1
    return h[start:]


# ------------------------------------------------------------------------------------------ indicatori
def _smooth(x: np.ndarray, alpha: float, n: int) -> np.ndarray:
    """Media esponenziale con il primo valore come seme; indefinita (NaN) prima della barra ``n``-esima."""
    out = np.empty(len(x), dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + alpha * (x[i] - out[i - 1])
    out[: n - 1] = np.nan
    return out


def ema(values: np.ndarray, n: int) -> np.ndarray:
    return _smooth(np.asarray(values, dtype=float), 2.0 / (n + 1), n)


def atr(h: np.ndarray, n: int = ATR_N) -> np.ndarray:
    hi, lo, cl = h[:, 2], h[:, 3], h[:, 4]
    tr = np.empty(len(h), dtype=float)
    tr[0] = hi[0] - lo[0]
    if len(h) > 1:
        tr[1:] = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    return _smooth(tr, 1.0 / n, n)


def vwap_day(h: np.ndarray) -> np.ndarray:
    """VWAP della sessione UTC (00:00): prezzo tipico x volume cumulato da inizio giorno. NaN se il volume cumulato
    e' zero e per la prima sessione della serie se la serie non comincia alle 00:00 (sessione incompleta)."""
    out = np.full(len(h), np.nan)
    if len(h) == 0:
        return out
    sess = (h[:, 0].astype(np.int64) // DAY)
    partial = int(h[0, 0]) % DAY != 0
    cur, cum_pv, cum_v = None, 0.0, 0.0
    for i in range(len(h)):
        if sess[i] != cur:
            cur, cum_pv, cum_v = sess[i], 0.0, 0.0
        if partial and sess[i] == sess[0]:
            continue
        tp = (h[i, 2] + h[i, 3] + h[i, 4]) / 3.0
        cum_pv += tp * h[i, 5]
        cum_v += h[i, 5]
        if cum_v > 0:
            out[i] = cum_pv / cum_v
    return out


def signal(h: np.ndarray) -> Optional[dict]:
    """Segnale sull'ULTIMA candela da 1 ora chiusa (indice -1), oppure ``None``."""
    n = len(h)
    if n < MIN_HOURS:
        return None
    c = h[:, 4]
    e, v, a = ema(c, EMA_N), vwap_day(h), atr(h)
    i = n - 1
    vals = (e[i - 1], e[i], v[i - 1], v[i], a[i])
    if not all(np.isfinite(x) for x in vals) or a[i] <= 0 or h[i, 5] <= 0:
        return None
    if e[i - 1] <= v[i - 1] and e[i] > v[i] and c[i] > e[i] and c[i] > v[i]:
        return {"signal_open_ms": int(h[i, 0]), "trigger": float(h[i, 2]), "ema9": float(e[i]),
                "vwap": float(v[i]), "atr": float(a[i]), "close": float(c[i])}
    return None


def entry_plan(sig: dict, price: float, now_ms: int) -> tuple[Optional[dict], str]:
    """Il prezzo ha rotto il massimo della candela di segnale, nella candela da 1 ora successiva, senza inseguire?"""
    sig_end = sig["signal_open_ms"] + H1
    if not sig_end <= now_ms < sig_end + H1:
        return None, "segnale_scaduto"
    if not (price > 0 and np.isfinite(price)):
        return None, "prezzo_non_valido"
    if price <= sig["trigger"]:
        return None, "nessuna_rottura"
    if price - sig["trigger"] > CHASE_ATR * sig["atr"]:
        return None, "troppo_lontano"
    sl, tp = price - STOP_ATR * sig["atr"], price + TARGET_ATR * sig["atr"]
    if sl <= 0:
        return None, "stop_non_valido"
    return {"sl": sl, "tp": tp}, "ok"


# ------------------------------------------------------------------------------------- aggancio al ciclo
def owned(positions: dict) -> set:
    return {s for s, p in positions.items() if getattr(p, "source", "") == SOURCE}


def protect(decisions: list, positions: dict) -> list:
    """Toglie chiusure, chiusure parziali e DCA decise da regole o Claude sulle posizioni S25."""
    mine = owned(positions)
    if not mine:
        return decisions
    return [d for d in decisions if not (d.get("symbol") in mine and d.get("action") in PROTECTED_ACTIONS)]


def leverage_for(name: str, sig: dict, price: float) -> int:
    """Leva di un ingresso S25 dentro la forbice ``LEV_MIN``..``LEV_MAX[name]``. Per ora fissa al minimo (15x): la regola
    che la fa salire va ancora decisa con l'utente. Il tetto del simbolo lo applica il motore."""
    return min(LEV_MIN, LEV_MAX.get(name, LEV_MIN))


def _base(symbol: str) -> str:
    return symbol.upper().replace("USDT", "").replace("PERP", "").strip("/:")


def step(acc, state: dict, candles_map: dict, prices: dict, now_ms: int, portfolio, *, halt, drain: bool,
         record_close: Callable, notify_open: Callable, notify_close: Callable,
         log_event: Callable[[dict], None], echo: Callable[[str], None] = print,
         can_close: Optional[Callable[[str], bool]] = None) -> dict:
    """Un giro di S25: chiusura a tempo delle posizioni S25 (sempre) e nuove aperture (non in pausa, non con blocco).
    Mai solleva per un simbolo: l'errore di un simbolo non ferma gli altri ne' il ciclo classico."""
    report = {"opened": [], "closed": [], "skipped": {}}
    for sym, pos in list(acc.positions.items()):
        if getattr(pos, "source", "") != SOURCE or now_ms - pos.open_ms < MAX_HOLD_MS:
            continue
        px = prices.get(sym)
        if px is None:
            report["skipped"][sym] = "prezzo_assente"
            continue
        if can_close is not None and not can_close(sym):
            report["skipped"][sym] = "registro_incoerente"
            continue
        rec = acc.close(sym, px, now_ms, "chiusura a tempo S25")
        if rec:
            report["closed"].append(sym)
            echo(f"[S25 TEMPO] {sym} net {rec['net']:+.2f}$")
            _safe(notify_close, sym, rec["net"], "S25: 12 ore trascorse", rec["why"])
            record_close(state, rec)
    if halt or drain:
        return report
    last_open = state.setdefault("last_open_ms", {})
    name = getattr(portfolio, "name", "")
    for sym, arr in candles_map.items():
        if _base(sym) in EXCLUDED or sym in acc.positions:
            continue
        try:
            sig = signal(closed_hours(arr, now_ms))
            if sig is None:
                continue
            px = prices.get(sym)
            plan, why = entry_plan(sig, float(px) if px is not None else 0.0, now_ms)
            if plan is None:
                report["skipped"][sym] = why
                continue
            if now_ms - last_open.get(sym, 0) < COOLDOWN_MS:
                report["skipped"][sym] = "cooldown"
                continue
            if name not in MARGIN:
                report["skipped"][sym] = "portafoglio_sconosciuto"
                continue
            margin = min(MARGIN[name], portfolio.limits.max_margin_trade)
            lev = leverage_for(name, sig, float(px))
            feats = {"strategy": STRATEGY_ID, "ema9": round(sig["ema9"], 8), "vwap": round(sig["vwap"], 8),
                     "atr1h": round(sig["atr"], 8), "trigger": sig["trigger"], "signal_open_ms": sig["signal_open_ms"]}
            reason = (f"S25 EMA9 sopra VWAP 1h, rottura {sig['trigger']:.5g}; stop {STOP_ATR} ATR, "
                      f"target {TARGET_ATR} ATR, max 12 h")
            pos, msg = acc.open(sym, 1, margin, lev, float(px), plan["sl"], plan["tp"],
                                now_ms, prices, confidence=0, reason=reason, source=SOURCE, trade_type="medio",
                                features=feats)
            if not pos:
                report["skipped"][sym] = "rifiutata:" + str(msg)[:60]
                echo(f"[S25 SKIP] {sym}: {msg}")
                continue
            last_open[sym] = now_ms
            report["opened"].append(sym)
            echo(f"[S25 OPEN] {sym} LONG lev {pos.leverage}x margin {pos.total_margin:.0f}$ @{float(px):.5g} "
                 f"SL {pos.sl:.5g} TP {pos.tp:.5g}")
            _safe(notify_open, sym, 1, float(px), pos.leverage, pos.total_margin, "medio", 0, SOURCE, reason)
            _safe(log_event, {"ev": "open", "ts": now_ms, "id": pos.id, "portfolio": name,
                              "run_no": state.get("run_no", 1), "symbol": sym, "side": 1, "price": float(px),
                              "entry": pos.entry, "sl": pos.sl, "tp": pos.tp, "leverage": pos.leverage,
                              "margin_first": pos.total_margin, "risk_plan_usd": pos.risk_plan_usd,
                              "r_dist": pos.r_dist, "trade_type": "medio", "source": SOURCE, "confidence": 0,
                              "split_plan": None, "features": feats})
        except Exception as exc:          # un simbolo storto non ferma il ciclo classico
            report["skipped"][sym] = "errore:" + type(exc).__name__
    return report


def _safe(fn: Callable, *args) -> None:
    try:
        fn(*args)
    except Exception:
        pass                              # notifiche e registro non devono mai impedire un'operazione
