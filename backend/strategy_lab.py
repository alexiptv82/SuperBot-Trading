"""Laboratorio strategie (solo ricerca, nessun legame col bot in funzione).

Domanda: esiste un vantaggio LORDO misurabile e stabile nel tempo in strategie
con regole precise, su BTC/ETH (7 anni di storia BitGet), prima di toccare il
bot?

Disciplina anti-autoinganno (fissata PRIMA di guardare i risultati):
  * parametri fissi a priori, nessuna ottimizzazione;
  * una sola posizione alla volta per simbolo (campioni non sovrapposti);
  * ingresso all'apertura della barra SUCCESSIVA al segnale (nessun look-ahead);
    i timeframe superiori usano solo barre gia' chiuse;
  * stop prima del target se entrambi toccati nella stessa barra; il target
    conta solo se superato di 1 bp (non basta toccarlo), ma e' comunque un
    fill ottimistico per le strategie a target vicino (S3, S4, S5);
  * divisione cronologica: sviluppo 2020-2023, validazione 2024-giu 2025,
    test lug 2025-9 ago 2026; gli ultimi 60 giorni (dal 10 ago 2026) restano
    INTOCCATI e vengono calcolati solo per chi supera tutte le soglie;
  * soglie: STRICT = (BTC+ETH insieme) in dev, val e test: n>=20, lordo medio
    >=20 bp, netto taker/taker >0 (funding incluso) e lordo >0 su ciascun
    simbolo. COND = netto con ingresso maker >0 in tutti e tre i periodi.

Costi (round trip, in bp): A taker/taker 12 commissioni + 4 slippage = 16;
B ingresso maker + uscita taker 8 + 2 = 10 (assume fill sempre riuscito:
ottimistico); C maker/maker 4 (ideale). Funding: 1 bp ogni 8 ore pagato dai
soli long (i short ignorati: prudente).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np
import pandas as pd

M15 = 900_000
H1 = 3_600_000
H4 = 14_400_000
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
# D = stress da altcoin: 12 commissioni + 18 slippage (spread piu' larghi)
COSTS = {"A": 16.0, "B": 10.0, "C": 4.0, "D": 30.0}
FUND_BP_8H = 1.0
# Un target (ordine limite) si considera eseguito solo se il prezzo lo SUPERA di
# 1 bp (non basta toccarlo): prima approssimazione prudente del problema del fill.
TP_THROUGH = 1e-4
MIN_N = 20
STRICT_GROSS = 20.0


def ms(y, m, d) -> int:
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


DATA_START = ms(2019, 10, 1)
DATA_END = ms(2026, 10, 9)
PERIODS = {
    "dev": (ms(2020, 1, 1), ms(2024, 1, 1)),
    "val": (ms(2024, 1, 1), ms(2025, 7, 1)),
    "test": (ms(2025, 7, 1), ms(2026, 8, 10)),
    "fresh": (ms(2026, 8, 10), ms(2026, 10, 9)),
}


# --------------------------------------------------------------------- dati
@dataclass
class Bars:
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray

    def __len__(self) -> int:
        return len(self.t)

    def head(self, k: int) -> "Bars":
        return Bars(*(a[:k] for a in (self.t, self.o, self.h, self.l, self.c, self.v)))


def bars_from_array(a: np.ndarray) -> Bars:
    a = a[np.argsort(a[:, 0], kind="stable")]
    _, first = np.unique(a[:, 0], return_index=True)
    a = a[first]
    return Bars(a[:, 0].astype(np.int64), a[:, 1].copy(), a[:, 2].copy(),
                a[:, 3].copy(), a[:, 4].copy(), a[:, 5].copy())


def aggregate(b: Bars, tf_ms: int, base_ms: int = M15) -> Bars:
    """Aggrega barre base in barre piu' lunghe; scarta i gruppi incompleti."""
    key = b.t // tf_ms
    starts = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    counts = np.diff(np.r_[starts, len(key)])
    full = counts == tf_ms // base_ms
    ends = starts + counts - 1
    out = Bars(key[starts] * tf_ms, b.o[starts], np.maximum.reduceat(b.h, starts),
               np.minimum.reduceat(b.l, starts), b.c[ends], np.add.reduceat(b.v, starts))
    return Bars(*(a[full] for a in (out.t, out.o, out.h, out.l, out.c, out.v)))


def align_htf(base_t: np.ndarray, base_ms: int, htf: Bars, htf_ms: int,
              values: np.ndarray) -> np.ndarray:
    """Per ogni barra base prende il valore dell'ultima barra HTF GIA' CHIUSA
    alla chiusura della barra base."""
    avail = htf.t + htf_ms
    k = np.searchsorted(avail, base_t + base_ms, side="right") - 1
    out = np.full(len(base_t), np.nan)
    ok = k >= 0
    out[ok] = values[k[ok]]
    return out


def fetch_15m(symbol: str, start_ms: int, end_ms: int, cache_dir: str) -> np.ndarray:
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{symbol.split('/')[0]}_15m_{start_ms}_{end_ms}.npy")
    if os.path.exists(path):
        print(f"[cache] {path}", flush=True)
        return np.load(path)
    import ccxt  # import locale: i test non richiedono ccxt
    client = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    since, got, calls, empties = start_ms, {}, 0, 0
    while since < end_ms:
        batch = None
        for attempt in range(5):
            try:
                batch = client.fetch_ohlcv(symbol, "15m", since=since, limit=200)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] {symbol} retry {attempt + 1}/5: {str(exc)[:80]}", file=sys.stderr)
                time.sleep(2 + 2 * attempt)
        calls += 1
        if batch is None:
            raise RuntimeError(f"{symbol}: download fallito dopo 5 tentativi (since={since})")
        if not batch:
            empties += 1
            if empties > 30:
                break
            since += 200 * M15
            continue
        empties = 0
        for c in batch:
            if c[0] < end_ms:
                got[int(c[0])] = [float(x) for x in c[:6]]
        last = int(max(c[0] for c in batch))
        since = last + M15 if last >= since else since + 200 * M15
        if calls % 100 == 0:
            print(f"  ...{symbol}: {len(got)} candele ({calls} chiamate)", flush=True)
        time.sleep(0.05)
    arr = np.array([got[k] for k in sorted(got)], dtype=float)
    if len(arr) == 0 or arr[-1, 0] < end_ms - 2 * 86_400_000:
        raise RuntimeError(f"{symbol}: copertura incompleta (ultima barra "
                           f"{arr[-1, 0] if len(arr) else None}); non salvo la cache")
    np.save(path, arr)
    return arr


# ---------------------------------------------------------------- indicatori
def _s(x) -> pd.Series:
    return pd.Series(np.asarray(x, dtype=float))


def sma(x, n):
    return _s(x).rolling(n).mean().to_numpy(dtype=float, copy=True)


def ema(x, n):
    return _s(x).ewm(span=n, adjust=False).mean().to_numpy(dtype=float, copy=True)


def rma(x, n):
    return _s(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy(dtype=float, copy=True)


def shift1(x):
    out = np.empty(len(x), dtype=float)
    out[0] = np.nan
    out[1:] = np.asarray(x, dtype=float)[:-1]
    return out


def rolling_max(x, n):
    return _s(x).rolling(n).max().to_numpy(dtype=float, copy=True)


def rolling_min(x, n):
    return _s(x).rolling(n).min().to_numpy(dtype=float, copy=True)


def true_range(h, l, c):
    pc = shift1(c)
    return np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))


def atr(h, l, c, n=14):
    return rma(true_range(h, l, c), n)


def adx(h, l, c, n=14):
    up = h - shift1(h)
    dn = shift1(l) - l
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = rma(true_range(h, l, c), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * rma(plus, n) / a
        mdi = 100.0 * rma(minus, n) / a
        dx = np.where(pdi + mdi > 0, 100.0 * np.abs(pdi - mdi) / (pdi + mdi), 0.0)
    return rma(dx, n)


def bollinger(c, n=20, k=2.0):
    mid = sma(c, n)
    sd = _s(c).rolling(n).std(ddof=0).to_numpy(dtype=float, copy=True)
    return mid, mid + k * sd, mid - k * sd


# ------------------------------------------------------------------ segnali
@dataclass
class Sig:
    side: np.ndarray   # +1 / -1 / 0, noto alla chiusura della barra i
    atr: np.ndarray    # ATR della barra i
    tgt: np.ndarray    # target assoluto (nan se assente)


@dataclass
class ExitCfg:
    stop_mult: float
    trail_mult: float = float("nan")
    target_r: float = float("nan")
    abs_target: bool = False
    donch_exit: int = 0
    max_hold: int = 48


def _finish(long_, short_, atr_arr, tgt=None) -> Sig:
    side = np.where(long_ & ~short_, 1, np.where(short_ & ~long_, -1, 0)).astype(np.int8)
    return Sig(side, atr_arr, tgt if tgt is not None else np.full(len(side), np.nan))


def sig_donch4h(a: dict) -> Sig:
    b = a["4h"]
    dh, dl = shift1(rolling_max(b.h, 20)), shift1(rolling_min(b.l, 20))
    e20, e50, ad, at = ema(b.c, 20), ema(b.c, 50), adx(b.h, b.l, b.c), atr(b.h, b.l, b.c)
    return _finish((b.c > dh) & (ad >= 25) & (e20 > e50),
                   (b.c < dl) & (ad >= 25) & (e20 < e50), at)


def sig_donch1h(a: dict) -> Sig:
    b, b4 = a["1h"], a["4h"]
    dh, dl = shift1(rolling_max(b.h, 20)), shift1(rolling_min(b.l, 20))
    at = atr(b.h, b.l, b.c)
    expansion = at >= sma(at, 50)
    e200 = align_htf(b.t, H1, b4, H4, ema(b4.c, 200))
    return _finish((b.c > dh) & expansion & (b.c > e200),
                   (b.c < dl) & expansion & (b.c < e200), at)


def _mean_reversion(b: Bars, adx_arr: np.ndarray) -> Sig:
    mid, up, lo = bollinger(b.c, 20, 2.5)
    pc, pu, pl = shift1(b.c), shift1(up), shift1(lo)
    calm = adx_arr < 20
    long_ = (pc < pl) & (b.c > lo) & (b.c < mid) & calm
    short_ = (pc > pu) & (b.c < up) & (b.c > mid) & calm
    return _finish(long_, short_, atr(b.h, b.l, b.c), mid)


def sig_mr1h(a: dict) -> Sig:
    b = a["1h"]
    return _mean_reversion(b, adx(b.h, b.l, b.c))


def sig_mr15m(a: dict) -> Sig:
    b, b1 = a["15m"], a["1h"]
    return _mean_reversion(b, align_htf(b.t, M15, b1, H1, adx(b1.h, b1.l, b1.c)))


def sig_pullback15m(a: dict) -> Sig:
    b, b1 = a["15m"], a["1h"]
    e20h, e50h = ema(b1.c, 20), ema(b1.c, 50)
    al = lambda v: align_htf(b.t, M15, b1, H1, v)  # noqa: E731
    e20h, e50h, c1, ad1 = al(e20h), al(e50h), al(b1.c), al(adx(b1.h, b1.l, b1.c))
    e20 = ema(b.c, 20)
    up = (e20h > e50h) & (c1 > e50h) & (ad1 >= 20)
    dn = (e20h < e50h) & (c1 < e50h) & (ad1 >= 20)
    return _finish(up & (b.l <= e20) & (b.c > e20) & (b.c > b.o),
                   dn & (b.h >= e20) & (b.c < e20) & (b.c < b.o), atr(b.h, b.l, b.c))


def sig_squeeze15m(a: dict) -> Sig:
    b = a["15m"]
    mid, up, lo = bollinger(b.c, 20, 2.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        width = (up - lo) / mid
    q20 = _s(width).rolling(200).quantile(0.2).to_numpy(dtype=float, copy=True)
    squeezed = shift1(width) <= shift1(q20)
    vol = b.v > 1.5 * sma(b.v, 20)
    return _finish(squeezed & vol & (b.c > up), squeezed & vol & (b.c < lo), atr(b.h, b.l, b.c))


def _inverse(fn: Callable) -> Callable:
    def inner(a: dict) -> Sig:
        s = fn(a)
        return Sig((-s.side).astype(np.int8), s.atr, s.tgt)
    return inner


@dataclass
class Strategy:
    name: str
    tf: str
    build: Callable
    cfg: ExitCfg


STRATEGIES = [
    Strategy("S1_donchian_4h", "4h", sig_donch4h,
             ExitCfg(stop_mult=2.0, trail_mult=3.0, max_hold=60)),
    Strategy("S2_donchian_1h", "1h", sig_donch1h,
             ExitCfg(stop_mult=2.5, donch_exit=10, max_hold=48)),
    Strategy("S3_meanrev_1h", "1h", sig_mr1h,
             ExitCfg(stop_mult=2.0, abs_target=True, max_hold=24)),
    Strategy("S3_meanrev_15m", "15m", sig_mr15m,
             ExitCfg(stop_mult=2.0, abs_target=True, max_hold=16)),
    Strategy("S4_pullback_15m", "15m", sig_pullback15m,
             ExitCfg(stop_mult=1.5, target_r=2.0, max_hold=16)),
    Strategy("S4_pullback_15m_inv", "15m", _inverse(sig_pullback15m),
             ExitCfg(stop_mult=1.5, target_r=2.0, max_hold=16)),
    Strategy("S5_squeeze_15m", "15m", sig_squeeze15m,
             ExitCfg(stop_mult=1.5, target_r=2.0, max_hold=16)),
    Strategy("S5_squeeze_15m_inv", "15m", _inverse(sig_squeeze15m),
             ExitCfg(stop_mult=1.5, target_r=2.0, max_hold=16)),
]


def build_frames(b15: Bars) -> dict:
    return {"15m": b15, "1h": aggregate(b15, H1), "4h": aggregate(b15, H4)}


# ------------------------------------------------------------------- motore
def simulate_exit(b: Bars, e: int, side: int, d: float, cfg: ExitCfg, sig: Sig,
                  tgt: float, dlow: Optional[np.ndarray], dhigh: Optional[np.ndarray]):
    """Entra all'apertura della barra e. Ritorna (idx_uscita, prezzo, motivo)."""
    n = len(b)
    p = b.o[e]
    stop = p - side * d
    hh = -np.inf
    ll = np.inf
    last = min(e + cfg.max_hold - 1, n - 1)
    for j in range(e, last + 1):
        o, h, l, c = b.o[j], b.h[j], b.l[j], b.c[j]
        if side == 1:
            if o <= stop:
                return j, o, "stop"
            if l <= stop:
                return j, stop, "stop"
            if np.isfinite(tgt) and h >= tgt * (1.0 + TP_THROUGH):
                return j, tgt, "target"
        else:
            if o >= stop:
                return j, o, "stop"
            if h >= stop:
                return j, stop, "stop"
            if np.isfinite(tgt) and l <= tgt * (1.0 - TP_THROUGH):
                return j, tgt, "target"
        hh, ll = max(hh, h), min(ll, l)
        if np.isfinite(cfg.trail_mult) and np.isfinite(sig.atr[j]):
            if side == 1:
                stop = max(stop, hh - cfg.trail_mult * sig.atr[j])
            else:
                stop = min(stop, ll + cfg.trail_mult * sig.atr[j])
        if cfg.donch_exit and j + 1 < n:
            if side == 1 and np.isfinite(dlow[j]) and c < dlow[j]:
                return j + 1, b.o[j + 1], "donchian"
            if side == -1 and np.isfinite(dhigh[j]) and c > dhigh[j]:
                return j + 1, b.o[j + 1], "donchian"
    return last, b.c[last], ("time" if last == e + cfg.max_hold - 1 else "end")


def donch_arrays(b: Bars, cfg: ExitCfg):
    if not cfg.donch_exit:
        return None, None
    return shift1(rolling_min(b.l, cfg.donch_exit)), shift1(rolling_max(b.h, cfg.donch_exit))


def run_strategy(b: Bars, sig: Sig, cfg: ExitCfg, tf_ms: int) -> list:
    n = len(b)
    dlow, dhigh = donch_arrays(b, cfg)
    trades, free_from = [], 0
    for i in np.flatnonzero(sig.side != 0):
        if i < free_from or i + 1 >= n:
            continue
        side, e = int(sig.side[i]), i + 1
        a = sig.atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        p = b.o[e]
        d = cfg.stop_mult * a
        if cfg.abs_target:
            tgt = sig.tgt[i]
            if not np.isfinite(tgt) or (tgt - p) * side <= 0:
                continue
        elif np.isfinite(cfg.target_r):
            tgt = p + side * cfg.target_r * d
        else:
            tgt = float("nan")
        j, px, why = simulate_exit(b, e, side, d, cfg, sig, tgt, dlow, dhigh)
        hold_h = (j - e + 1) * tf_ms / H1
        trades.append({"t": int(b.t[e]), "e": int(e), "side": side, "entry": float(p), "exit": float(px),
                       "why": why, "hold_h": hold_h,
                       "gross": side * (px / p - 1.0) * 1e4})
        free_from = j
    return trades


# ------------------------------------------------------------- statistiche
def stats(trades: list) -> Optional[dict]:
    n = len(trades)
    if n == 0:
        return None
    g = np.array([t["gross"] for t in trades])
    fund = np.array([FUND_BP_8H * t["hold_h"] / 8.0 if t["side"] == 1 else 0.0 for t in trades])
    sd = g.std(ddof=1) if n > 1 else float("nan")
    longs = np.array([t["side"] == 1 for t in trades])
    out = {"n": n, "gross": float(g.mean()), "sd": float(sd),
           "t": float(g.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
           "win": float((g > 0).mean()), "hold_h": float(np.mean([t["hold_h"] for t in trades])),
           "nL": int(longs.sum()), "nS": int((~longs).sum()),
           "gL": float(g[longs].mean()) if longs.any() else float("nan"),
           "gS": float(g[~longs].mean()) if (~longs).any() else float("nan"),
           "fund": float(fund.mean())}
    for k, cst in COSTS.items():
        out[k] = float((g - cst - fund).mean())
    return out


def in_period(trades: list, name: str) -> list:
    lo, hi = PERIODS[name]
    return [t for t in trades if lo <= t["t"] < hi]


def evaluate_tiers(per_pool: dict, per_sym: dict) -> dict:
    ps = [per_pool.get(p) for p in ("dev", "val", "test")]
    have = all(s is not None and s["n"] >= MIN_N for s in ps)
    sym_pos = all(per_sym[sym].get(p) is not None and per_sym[sym][p]["gross"] > 0
                  for sym in per_sym for p in ("dev", "val", "test"))
    strict = have and sym_pos and all(s["gross"] >= STRICT_GROSS and s["A"] > 0 for s in ps)
    cond = have and sym_pos and all(s["B"] > 0 for s in ps)
    return {"strict": bool(strict), "cond": bool(cond), "enough_n": bool(have), "sym_pos": bool(sym_pos)}


def fmt(tag: str, s: Optional[dict]) -> str:
    if s is None:
        return f"{tag}: nessuna operazione"
    return (f"{tag} n={s['n']} lordo={s['gross']:+.1f}bp t={s['t']:+.1f} win={100 * s['win']:.0f}% "
            f"netA={s['A']:+.1f} B={s['B']:+.1f} C={s['C']:+.1f} "
            f"L/S={s['gL']:+.0f}({s['nL']})/{s['gS']:+.0f}({s['nS']}) tenuta={s['hold_h']:.0f}h")


# --------------------------------------------------------------------- main
def load_frames(symbols: list, cache_dir: str, start: int, end: int) -> dict:
    return {sym: build_frames(bars_from_array(fetch_15m(sym, start, end, cache_dir)))
            for sym in symbols}


def run(args) -> dict:
    t0 = time.time()
    frames = load_frames(SYMBOLS, args.cache_dir, DATA_START, DATA_END)
    lines: dict[str, list] = {}

    def add(title: str, text: str):
        print(text, flush=True)
        lines.setdefault(title, []).append(text[:230])

    for sym, fr in frames.items():
        b = fr["15m"]
        gaps = np.diff(b.t)
        add("Dati", f"{sym[:3]} 15m: {len(b)} barre {datetime.fromtimestamp(b.t[0] / 1000, timezone.utc):%Y-%m-%d}"
                    f" -> {datetime.fromtimestamp(b.t[-1] / 1000, timezone.utc):%Y-%m-%d}, buchi>15m={int((gaps > M15).sum())},"
                    f" max={int(gaps.max() // M15)} barre; 1h={len(fr['1h'])} 4h={len(fr['4h'])}")
        for p in ("dev", "val", "test", "fresh"):
            if p == "fresh":
                continue  # ultimi 60 giorni intoccati: non si guardano
            lo, hi = PERIODS[p]
            m = (b.t >= lo) & (b.t < hi)
            if m.any():
                add("Dati", f"{sym[:3]} {p}: mercato {100 * (b.c[m][-1] / b.o[m][0] - 1):+.0f}%")

    results, summary = {}, []
    for st in STRATEGIES:
        if args.only and st.name not in args.only.split(","):
            continue
        per_sym_tr = {}
        for sym, fr in frames.items():
            base = fr[st.tf]
            sig = st.build(fr)
            tf_ms = {"15m": M15, "1h": H1, "4h": H4}[st.tf]
            per_sym_tr[sym] = run_strategy(base, sig, st.cfg, tf_ms)
        per_sym = {s: {p: stats(in_period(tr, p)) for p in ("dev", "val", "test")}
                   for s, tr in per_sym_tr.items()}
        pooled = {p: stats([t for tr in per_sym_tr.values() for t in in_period(tr, p)])
                  for p in ("dev", "val", "test")}
        tiers = evaluate_tiers(pooled, per_sym)
        results[st.name] = {"tiers": tiers, "pooled": pooled, "per_symbol": per_sym}
        add(f"Strategia {st.name}", f"== {st.name} == STRICT={tiers['strict']} COND={tiers['cond']} "
                                    f"(n>=20 tutti i periodi={tiers['enough_n']}, lordo>0 su ogni simbolo={tiers['sym_pos']})")
        for p in ("dev", "val", "test"):
            add(f"Strategia {st.name}", fmt(f"BTC+ETH {p}", pooled[p]))
        for sym in SYMBOLS:
            for p in ("dev", "val", "test"):
                add(f"Strategia {st.name}", fmt(f"{sym[:3]} {p}", per_sym[sym][p]))
        if tiers["strict"] or tiers["cond"]:
            fresh = stats([t for tr in per_sym_tr.values() for t in in_period(tr, "fresh")])
            results[st.name]["fresh"] = fresh
            add(f"Strategia {st.name}", fmt("ULTIMI 60 GG (intoccati)", fresh))
        summary.append(f"{st.name}: STRICT={tiers['strict']} COND={tiers['cond']} "
                       f"lordo dev/val/test = " + "/".join(
                           f"{pooled[p]['gross']:+.1f}" if pooled[p] else "n/d" for p in ("dev", "val", "test")))
    add("Riepilogo", f"Soglie fissate in anticipo: STRICT = lordo>=20bp e netto A>0 in dev, val e test con n>=20")
    for s in summary:
        add("Riepilogo", s)
    add("Riepilogo", f"durata {time.time() - t0:.0f}s")

    with open(args.out, "w") as f:
        json.dump({"results": results, "lines": lines}, f, indent=1, default=float)
    if args.annotate:
        for title, ls in lines.items():
            for i in range(0, len(ls), 14):
                msg = "%0A".join(x.replace("%", "%25") for x in ls[i:i + 14])
                suffix = f" ({i // 14 + 1})" if len(ls) > 14 else ""
                print(f"::notice title=Lab - {title}{suffix}::{msg}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="lab_cache")
    ap.add_argument("--out", default="strategy_lab_results.json")
    ap.add_argument("--only", default="")
    ap.add_argument("--annotate", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
