"""Feature point-in-time da candele CHIUSE. Funzioni pure, deterministiche, nessuna rete, nessun orologio.

Garanzia anti-leakage: `compute_features(store, symbol, ts)` legge solo `store.closed_before(symbol, ts, ...)`, quindi
modificare qualunque candela con t + intervallo > ts NON cambia l'output (verificato da test).
Le feature sono INDICATIVE e versionate (FEATURE_SET): non riproducono quelle dei prompt storici.
"""
from __future__ import annotations

import math
import time
from typing import Optional

FEATURE_SET = "ohlcv15m_v1"
BARS_1H, BARS_4H, BARS_24H = 4, 16, 96
NEED = BARS_24H + 20


def _r(x: Optional[float], nd: int = 6) -> Optional[float]:
    return None if x is None or not math.isfinite(x) else round(x, nd)


def _ema(vals: list, n: int) -> float:
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _rsi(closes: list, n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


def _atr_pct(cs: list, n: int = 14) -> Optional[float]:
    if len(cs) < n + 1:
        return None
    trs = []
    for prev, c in zip(cs[-n - 1:-1], cs[-n:]):
        trs.append(max(c.h - c.l, abs(c.h - prev.c), abs(c.l - prev.c)))
    return sum(trs) / n / cs[-1].c


def compute_features(store, symbol: str, ts: int, btc_symbol: Optional[str] = "BTCUSDT") -> Optional[dict]:
    cs = store.closed_before(symbol, ts, NEED)
    if len(cs) < NEED or not store.contiguous(cs):
        return None                                      # dati insufficienti o con buchi: nessuna feature inventata
    closes = [c.c for c in cs]
    last = cs[-1]
    ret = lambda n: closes[-1] / closes[-1 - n] - 1  # noqa: E731
    rets15 = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - BARS_24H, len(closes))]
    mean = sum(rets15) / len(rets15)
    vol24 = math.sqrt(sum((x - mean) ** 2 for x in rets15) / len(rets15)) * math.sqrt(BARS_24H)
    hi24, lo24 = max(c.h for c in cs[-BARS_24H:]), min(c.l for c in cs[-BARS_24H:])
    vols = [c.v for c in cs]
    prior = vols[-BARS_24H - 4:-4]
    vol_ratio = (sum(vols[-4:]) / 4) / (sum(prior) / len(prior)) if prior and sum(prior) > 0 else None
    f = {"feature_set": FEATURE_SET, "asof_candle_open_ms": last.t, "price": _r(last.c, 8),
         "ret_1h": _r(ret(BARS_1H)), "ret_4h": _r(ret(BARS_4H)), "ret_24h": _r(ret(BARS_24H)),
         "atr_pct14": _r(_atr_pct(cs)), "vol24_pct": _r(vol24), "vol_ratio": _r(vol_ratio, 4),
         "rsi14": _r(_rsi(closes), 2), "ema20_50": 1 if _ema(closes[-60:], 20) > _ema(closes[-60:], 50) else -1,
         "dist_high_24h": _r(last.c / hi24 - 1), "dist_low_24h": _r(last.c / lo24 - 1),
         "hour_utc": time.gmtime(ts / 1000).tm_hour, "dow": time.gmtime(ts / 1000).tm_wday}
    if btc_symbol and symbol != btc_symbol:
        b = store.closed_before(btc_symbol, ts, BARS_24H + 1)
        f["btc_ret_24h"] = _r(b[-1].c / b[0].c - 1) if len(b) == BARS_24H + 1 and store.contiguous(b) else None
    return f
