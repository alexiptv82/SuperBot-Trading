"""Punteggio tecnico V2: aggiunge timeframe 1d, pattern candele, stagionalità.

Dalle candele 15m CHIUSE si ricavano le barre 1h. Le tendenze 4h e 1d (EMA50 contro EMA200) si calcolano su barre
CHIUSE native (``bars_4h``/``bars_1d``, scaricate dall'exchange) oppure, se non fornite, su quelle ricavate dalle 15m,
ma SOLO con almeno ``TREND_MIN_BARS`` barre chiuse: una EMA200 non viene mai sostituita da una media piu' corta.
Senza storia sufficiente o con dati vecchi la tendenza e' ``UNKNOWN``: nessun punto a nessun lato e nessuna nuova
apertura su quel simbolo (vedi ``Reading.side``), mentre il punteggio resta disponibile per gestire le posizioni aperte.
Punteggio 0-100 per il lato indicato + bonus stagionalità da seasonal.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from desk.seasonal import get_seasonal

H1, H4, H1D = 3_600_000, 14_400_000, 86_400_000
M15 = 900_000
TREND_FAST, TREND_SLOW = 50, 200
TREND_MIN_BARS = TREND_SLOW          # una EMA200 vera richiede almeno 200 barre chiuse
TREND_4H_POINTS = 20
# Punti del trend giornaliero. Il disegno originale prevedeva 15, ma in RC84 il trend 1d non si e' mai attivato
# (storia di ~10 giorni): le soglie 60/70 sono state tarate SENZA di lui. Riattivarlo aggiungerebbe fino a 15 punti
# e quindi piu' aperture. Finche' la policy non lo decide, il trend 1d e' solo contesto (0 punti): e' riportato nei
# fatti, nella classificazione e nel prompt. Vedi docs/v3/RC84-FASE2-MOTORE-SEGNALI.md.
DAILY_TREND_POINTS = 0
MAX_GAP_MS = 3 * H1D                 # buco massimo tollerato in una serie 4h/1d (fine settimana dei metalli)
RANGE_GAP = 0.003                    # |EMA50-EMA200|/EMA200 sotto lo 0,3%: tendenza 4h piatta (laterale)


def resample(arr: np.ndarray, tf_ms: int, bar_ms: int = 900_000) -> np.ndarray:
    if len(arr) == 0:
        return np.empty((0, 6))
    per = tf_ms // bar_ms
    key = arr[:, 0].astype(np.int64) // tf_ms
    out = []
    for k in np.unique(key):
        g = arr[key == k]
        if len(g) != per or int(g[-1, 0]) - int(g[0, 0]) != (per - 1) * bar_ms:
            continue
        out.append([k * tf_ms, g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()])
    return np.array(out, dtype=float) if out else np.empty((0, 6))


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2 / (n + 1)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def rsi(c: np.ndarray, n: int = 14) -> float:
    d = np.diff(c)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = up[:n].mean(), dn[:n].mean()
    for i in range(n, len(d)):
        au, ad = (au * (n - 1) + up[i]) / n, (ad * (n - 1) + dn[i]) / n
    return 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)


def atr(b: np.ndarray, n: int = 14) -> float:
    h, l, c = b[:, 2], b[:, 3], b[:, 4]
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(tr[-n:].mean())


def doji_pattern(b: np.ndarray) -> str:
    """Identifica pattern di inversione sull'ultima candela 1h."""
    if len(b) < 3:
        return ""
    o, h, l, c = b[-1, 1], b[-1, 2], b[-1, 3], b[-1, 4]
    body = abs(c - o)
    candle_range = h - l
    if candle_range == 0:
        return ""
    body_ratio = body / candle_range
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    if body_ratio < 0.1:
        return "doji"  # indecisione
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return "hammer"  # potenziale inversione long
    if upper_shadow > body * 2 and lower_shadow < body * 0.5:
        return "shooting_star"  # potenziale inversione short
    # engulfing
    if len(b) >= 2:
        po, pc = b[-2, 1], b[-2, 4]
        if c > o and pc < po and c > po and o < pc:
            return "bullish_engulfing"
        if c < o and pc > po and c < po and o > pc:
            return "bearish_engulfing"
    return ""


def closed_bars(arr: np.ndarray, now_ms: int, period_ms: int) -> np.ndarray:
    """Solo barre CHIUSE (apertura + durata <= now), finite, con prezzi positivi, ordinate e senza duplicati."""
    if arr is None or len(arr) == 0:
        return np.empty((0, 6))
    a = np.asarray(arr, dtype=float)
    if a.ndim != 2 or a.shape[1] < 6:
        return np.empty((0, 6))
    a = a[:, :6]
    ok = np.isfinite(a).all(axis=1) & (a[:, 1:5] > 0).all(axis=1) & (a[:, 5] >= 0)
    ok &= a[:, 0] + period_ms <= now_ms
    a = a[ok]
    if len(a) == 0:
        return np.empty((0, 6))
    a = a[np.argsort(a[:, 0], kind="stable")]
    keep = np.r_[True, np.diff(a[:, 0]) > 0]
    return a[keep]


def htf_trend(bars: np.ndarray, now_ms: int, period_ms: int) -> dict:
    """Tendenza EMA50/EMA200 su barre CHIUSE di un timeframe superiore. Mai una media sostituita da una piu' corta.

    ``state``: ``UP``/``DOWN``/``UNKNOWN``; ``why`` spiega un UNKNOWN; ``gap`` = (EMA50-EMA200)/EMA200;
    ``close_vs_ema50`` = +1/-1 se l'ultima chiusura e' sopra/sotto la EMA50; ``ema50_slope`` = segno della EMA50 su 3 barre."""
    out = {"state": "UNKNOWN", "why": "", "bars": 0, "gaps": 0, "gap": None, "close_vs_ema50": 0, "ema50_slope": 0,
           "closes_above_ema50": 0, "asof_ms": None}
    c = closed_bars(bars, now_ms, period_ms)
    out["bars"] = int(len(c))
    # barre davvero di questo timeframe: aperture allineate al periodo e distanti almeno un periodo
    # (una serie con un'altra granularita' non diventa una tendenza 4h/1d)
    if len(c) and (np.any(c[:, 0].astype(np.int64) % period_ms != 0) or np.any(np.diff(c[:, 0]) < period_ms)):
        out["why"] = "barre non coerenti con il timeframe"
        out["bars"] = 0
        return out
    # interruzioni: si usa solo la coda piu' recente senza buchi oltre MAX_GAP_MS (es. un fine settimana dei metalli);
    # oltre quel buco la serie precedente non si incolla, e se la coda e' corta la tendenza resta UNKNOWN
    if len(c) > 1:
        gaps = np.flatnonzero(np.diff(c[:, 0]) > max(MAX_GAP_MS, period_ms))
        out["gaps"] = int(np.sum(np.diff(c[:, 0]) > period_ms))
        if len(gaps):
            c = c[gaps[-1] + 1:]
            out["bars"] = int(len(c))
    if len(c) < TREND_MIN_BARS:
        out["why"] = "storia insufficiente: %d barre chiuse < %d" % (len(c), TREND_MIN_BARS)
        return out
    last_end = int(c[-1, 0]) + period_ms
    # dati vecchi: l'ultima barra chiusa non e' quella appena terminata (oltre una barra di ritardo)
    if now_ms - last_end >= period_ms:
        out["why"] = "dati vecchi: ultima barra chiusa terminata %d min fa" % ((now_ms - last_end) // 60_000)
        return out
    closes = c[:, 4]
    e50, e200 = ema(closes, TREND_FAST), ema(closes, TREND_SLOW)
    if not (np.isfinite(e50[-1]) and np.isfinite(e200[-1]) and e200[-1] > 0):
        out["why"] = "medie non calcolabili"
        return out
    gap = float((e50[-1] - e200[-1]) / e200[-1])
    above = 0
    for k in range(1, min(6, len(c)) + 1):           # chiusure consecutive sopra(+)/sotto(-) la EMA50, dall'ultima
        sgn = 1 if closes[-k] > e50[-k] else -1
        if k == 1:
            above = sgn
        elif sgn == (1 if above > 0 else -1):
            above += sgn
        else:
            break
    out.update(state="UP" if gap > 0 else "DOWN" if gap < 0 else "UNKNOWN", gap=round(gap, 6),
               close_vs_ema50=1 if closes[-1] > e50[-1] else -1,
               ema50_slope=1 if e50[-1] > e50[-4] else -1 if e50[-1] < e50[-4] else 0,
               closes_above_ema50=int(above), asof_ms=last_end)
    if out["state"] == "UNKNOWN":
        out["why"] = "EMA50 e EMA200 coincidenti"
    return out


def classify_trend(t4: dict, t1d: dict, ltf_up: bool) -> tuple[str, str]:
    """Classificazione CONSULTIVA (nessuna apertura dipende da essa): distingue continuazione, inversione confermata
    e rimbalzo non confermato, per direzione. Regola verificabile, da validare nel replay prima di farne un filtro:
      - UNKNOWN: tendenza 4h sconosciuta;
      - RANGE: 4h quasi piatta (|gap| < RANGE_GAP);
      - CONTINUATION_<dir>: il movimento 1h va nella direzione della tendenza 4h;
      - REVERSAL_CONFIRMED_<dir>: il movimento 1h va contro la tendenza 4h E il 4h lo conferma: almeno 2 chiusure 4h
        consecutive oltre la EMA50 4h e EMA50 4h gia' girata nella nuova direzione, senza tendenza 1d contraria;
      - BOUNCE_UNCONFIRMED_<dir>: il movimento 1h va contro la tendenza 4h senza quella conferma."""
    s4 = t4.get("state")
    if s4 not in ("UP", "DOWN"):
        return "UNKNOWN", "tendenza 4h sconosciuta (%s)" % (t4.get("why") or "?")
    if t4.get("gap") is not None and abs(t4["gap"]) < RANGE_GAP:
        return "RANGE", "EMA50 e EMA200 4h a meno dello %.1f%%" % (RANGE_GAP * 100)
    move = "UP" if ltf_up else "DOWN"
    if move == s4:
        return "CONTINUATION_" + move, "1h e 4h nella stessa direzione"
    want = 1 if move == "UP" else -1
    d1 = t1d.get("state")
    confirmed = (t4.get("closes_above_ema50", 0) * want >= 2 and t4.get("ema50_slope") == want
                 and not (d1 in ("UP", "DOWN") and (1 if d1 == "UP" else -1) != want))
    if confirmed:
        return "REVERSAL_CONFIRMED_" + move, "2+ chiusure 4h oltre la EMA50 4h e EMA50 4h girata, 1d non contrario"
    return "BOUNCE_UNCONFIRMED_" + move, "movimento 1h contro la tendenza 4h, senza conferma 4h"


@dataclass
class Reading:
    symbol: str
    price: float
    side: int = 0
    score: int = 0
    long_score: int = 0
    short_score: int = 0
    atr_pct: float = 0.0
    sl_pct: float = 0.01
    tp_pct: float = 0.02
    facts: dict = field(default_factory=dict)
    why: list = field(default_factory=list)
    seasonal_note: str = ""
    pattern: str = ""
    trade_type: str = "medio"   # "scalp" se segnale su 15m/1h, "medio" se su 4h/1d


def read_symbol(symbol: str, arr15: np.ndarray, now_ms: int | None = None, *,
                bars_4h: np.ndarray | None = None, bars_1d: np.ndarray | None = None) -> Reading | None:
    """Lettura del simbolo sulle sole candele CHIUSE.

    ``arr15`` puo' contenere l'ultima candela da 15 minuti in formazione (come la restituisce l'exchange): viene
    esclusa da ogni indicatore. ``now_ms`` assente = tutte le candele ricevute sono considerate chiuse (solo prove).
    ``bars_4h``/``bars_1d``: barre native dell'exchange (anche con quella in formazione, che viene esclusa); se mancano,
    si usano quelle ricavate dalle 15m chiuse, valide solo con almeno 200 barre."""
    if arr15 is None or len(arr15) == 0:
        return None
    arr15 = np.asarray(arr15, dtype=float)
    if now_ms is None:
        now_ms = int(arr15[-1, 0]) + M15
    closed15 = closed_bars(arr15, now_ms, M15)
    b1 = resample(closed15, H1)
    if len(b1) < 60:
        return None
    c1 = b1[:, 4]
    price = float(arr15[-1, 4])            # ultimo prezzo ricevuto: solo informativo, nessun indicatore lo usa
    ref = float(c1[-1])                    # chiusura dell'ultima ora CHIUSA: base di tutti i confronti
    e20, e50 = ema(c1, 20)[-1], ema(c1, 50)[-1]
    src4 = bars_4h if bars_4h is not None else resample(closed15, H4)
    t4 = htf_trend(src4, now_ms, H4)
    t1d = htf_trend(bars_1d if bars_1d is not None else resample(closed15, H1D), now_ms, H1D)
    r1h = rsi(c1)
    roc24 = float(c1[-1] / c1[-25] - 1) if len(c1) > 25 else 0.0
    hi20, lo20 = float(b1[-21:-1, 2].max()), float(b1[-21:-1, 3].min())
    vol_ratio = float(b1[-1, 5] / max(1e-9, b1[-25:-1, 5].mean()))
    a_pct = atr(b1) / ref

    # --- timeframe 1d (contesto di lungo): EMA50/EMA200 vere su barre giornaliere chiuse, altrimenti UNKNOWN
    daily_trend = 1 if t1d["state"] == "UP" else -1 if t1d["state"] == "DOWN" else 0
    daily_note = ("trend 1d %s" % ("bull" if daily_trend == 1 else "bear")) if daily_trend else \
        "trend 1d UNKNOWN (%s)" % t1d["why"]
    trend_state, trend_state_why = classify_trend(t4, t1d, e20 > e50)

    # Advisory-only: an actual EMA20/50 crossover on the last CLOSED 1h bar.
    # Scores, SHORT logic and the existing 1h/4h/1d trend readings are unchanged.
    from desk.trend_change import advisory as trend_change_advisory
    trend_change = trend_change_advisory(b1, np.asarray(src4, dtype=float)[:, :6] if len(src4) else np.empty((0, 6)),
                                         now_ms, ema_fn=ema)

    # --- pattern candele
    pat = doji_pattern(b1)

    # --- stagionalità
    sea = get_seasonal(symbol, now_ms)

    comp = {"long": [], "short": []}
    sc = {"long": 0, "short": 0}

    def add(side_name, pts, why):
        sc[side_name] += pts
        comp[side_name].append(f"{why} (+{pts})")

    # trend 4h: 20 punti, solo con EMA50/EMA200 vere su barre 4h chiuse (UNKNOWN = nessun punto)
    if t4["state"] in ("UP", "DOWN"):
        add("long" if t4["state"] == "UP" else "short", TREND_4H_POINTS, "trend 4h")
    else:
        comp["long"].append("trend 4h UNKNOWN (0)")
        comp["short"].append("trend 4h UNKNOWN (0)")
    # trend 1h: 15 punti
    add("long" if e20 > e50 else "short", 15, "trend 1h")
    # trend 1d: solo se noto, punti secondo la policy (DAILY_TREND_POINTS, oggi 0 = solo contesto)
    if daily_trend != 0 and DAILY_TREND_POINTS > 0:
        add("long" if daily_trend == 1 else "short", DAILY_TREND_POINTS, "trend 1d")
    # prezzo (chiusura dell'ultima ora chiusa) vs EMA50 1h: 8 punti
    add("long" if ref > e50 else "short", 8, "prezzo vs EMA50")
    # momentum 24h: fino a 12 punti
    m = int(round(min(abs(roc24) / 0.03, 1.0) * 12))
    if m:
        add("long" if roc24 > 0 else "short", m, f"momento 24h {roc24:+.1%}")
    # rottura massimi/minimi: 10 punti
    if c1[-1] > hi20:
        add("long", 10, "rottura massimi 20h")
    elif c1[-1] < lo20:
        add("short", 10, "rottura minimi 20h")
    # RSI 1h: 8 punti
    if 50 <= r1h <= 70:
        add("long", 8, f"RSI {r1h:.0f}")
    elif 30 <= r1h < 50:
        add("short", 8, f"RSI {r1h:.0f}")
    # volume: 4 punti
    if vol_ratio > 1.3:
        add("long" if c1[-1] >= b1[-1, 1] else "short", 4, f"volumi x{vol_ratio:.1f}")

    # --- pattern candele: fino a 8 punti
    if pat == "hammer":
        add("long", 8, "hammer")
    elif pat == "bullish_engulfing":
        add("long", 8, "bullish engulfing")
    elif pat == "shooting_star":
        add("short", 8, "shooting star")
    elif pat == "bearish_engulfing":
        add("short", 8, "bearish engulfing")
    # doji = indecisione: riduce entrambi i lati
    elif pat == "doji":
        sc["long"] = max(0, sc["long"] - 5)
        sc["short"] = max(0, sc["short"] - 5)

    # overbought/oversold
    if r1h > 78:
        sc["long"] = max(0, sc["long"] - 12)
        comp["long"].append(f"ipercomprato RSI {r1h:.0f} (-12)")
    if r1h < 22:
        sc["short"] = max(0, sc["short"] - 12)
        comp["short"].append(f"ipervenduto RSI {r1h:.0f} (-12)")

    # --- stagionalità: bonus fino a 15 punti per lato
    if sea.long_bonus > 0:
        sc["long"] = min(100, sc["long"] + sea.long_bonus)
        comp["long"].append(f"stagionalità long +{sea.long_bonus}")
    if sea.short_bonus > 0:
        sc["short"] = min(100, sc["short"] + sea.short_bonus)
        comp["short"].append(f"stagionalità short +{sea.short_bonus}")

    ls, ss = min(100, sc["long"]), min(100, sc["short"])
    side = 1 if ls > ss else -1 if ss > ls else 0
    score = max(ls, ss)
    # Politica prudente: senza una tendenza 4h verificabile nessun lato e' "segnalato" (side 0 = nessuna apertura
    # dalle regole). I punteggi restano: servono a gestire le posizioni gia' aperte.
    if t4["state"] not in ("UP", "DOWN"):
        side = 0

    # sl più morbido in V2: 1.2x ATR (era 1.5x)
    sl = float(min(0.035, max(0.003, 1.2 * a_pct)))
    # trade_type: scalp se segnale deciso su TF basso con volume sopra media.
    # Soglia abbassata da 75→68 e vol_ratio da 1.5→1.2 per permettere scalp reali
    # ad alta leva (15-45x) come previsto dalla roadmap V2.
    # V2 aggressivo: quasi sempre scalp. Solo se segnale debolissimo o trend 4h
    # contrario e volume piatto si usa medio (setup multi-TF molto lento).
    trade_type = "scalp" if score >= 55 else "medio"

    return Reading(
        symbol=symbol, price=price, side=side, score=score, long_score=ls, short_score=ss,
        atr_pct=a_pct, sl_pct=sl, tp_pct=round(sl * 1.8, 5),
        facts={"rsi1h": round(r1h, 1), "ema20_50_1h": "su" if e20 > e50 else "giu",
               "ema50_200_4h": {"UP": "su", "DOWN": "giu"}.get(t4["state"], "UNKNOWN"), "roc24h": round(roc24, 4),
               "trend4h_state": t4["state"], "trend4h_why": t4["why"], "trend4h_bars": t4["bars"],
               "trend1d_state": t1d["state"], "trend1d_why": t1d["why"], "trend1d_bars": t1d["bars"],
               "trend_state": trend_state, "trend_state_why": trend_state_why,
               "closed_asof_ms": int(b1[-1, 0]) + H1,
               "atr1h_pct": round(a_pct, 4), "vol_ratio": round(vol_ratio, 2),
               "daily_trend": daily_note,
               "trend_change": trend_change["event"],
               "trend_change_h4": trend_change["h4_bias"],
               "trend_change_asof_ms": trend_change["asof_ms"]},
        why=comp["long" if side == 1 else "short"],
        seasonal_note=sea.note,
        pattern=pat,
        trade_type=trade_type,
    )
