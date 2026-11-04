"""Deterministic closed-bar indicators for Brain V3.

No I/O, network, clock, or randomness. Decimal arithmetic in a local
60-digit ROUND_HALF_EVEN context. Values are not rounded.

Known limits: early EMA/RMA values depend on first-value initialization;
gaps are rejected (never interpolated); volume is validated but unused;
no real market data was used.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, Context, localcontext
from typing import Optional, Sequence

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class Bar:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class MacdSeries:
    line: tuple[Optional[Decimal], ...]
    signal: tuple[Optional[Decimal], ...]
    hist: tuple[Optional[Decimal], ...]


@dataclass(frozen=True)
class BollingerSeries:
    mid: tuple[Optional[Decimal], ...]
    upper: tuple[Optional[Decimal], ...]
    lower: tuple[Optional[Decimal], ...]
    percent_b: tuple[Optional[Decimal], ...]
    bandwidth: tuple[Optional[Decimal], ...]


@dataclass(frozen=True)
class DonchianSeries:
    high: tuple[Optional[Decimal], ...]
    low: tuple[Optional[Decimal], ...]


@dataclass(frozen=True)
class AdxSeries:
    plus_di: tuple[Optional[Decimal], ...]
    minus_di: tuple[Optional[Decimal], ...]
    adx: tuple[Optional[Decimal], ...]


def _nz(d: Decimal) -> Decimal:
    return Decimal(0) if d == 0 else d


def check_bars(bars, *, candle_ms) -> None:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    if not isinstance(bars, (list, tuple)):
        raise ValueError("invalid_bars")
    prev = None
    for b in bars:
        if type(b) is not Bar:
            raise ValueError("invalid_bars")
        if type(b.open_time_ms) is not int or b.open_time_ms < 0 or b.open_time_ms % candle_ms != 0:
            raise ValueError("invalid_bars")
        for p in (b.open, b.high, b.low, b.close):
            if not isinstance(p, Decimal) or not p.is_finite() or p <= 0:
                raise ValueError("invalid_bars")
        if not isinstance(b.volume, Decimal) or not b.volume.is_finite() or b.volume < 0:
            raise ValueError("invalid_bars")
        if not (b.low <= b.open <= b.high and b.low <= b.close <= b.high):
            raise ValueError("invalid_bars")
        if prev is not None and b.open_time_ms != prev + candle_ms:
            raise ValueError("invalid_bars")
        prev = b.open_time_ms


def _check_period(n) -> None:
    if type(n) is not int or n < 1:
        raise ValueError("invalid_period")


def _check_values(values) -> None:
    if not isinstance(values, (list, tuple)):
        raise ValueError("invalid_values")
    for v in values:
        if not isinstance(v, Decimal) or not v.is_finite():
            raise ValueError("invalid_values")


def sma(values, n) -> tuple[Optional[Decimal], ...]:
    _check_period(n)
    _check_values(values)
    with localcontext(_CTX):
        out = []
        for i in range(len(values)):
            if i < n - 1:
                out.append(None)
            else:
                s = sum(values[i - n + 1:i + 1])
                out.append(_nz(s / Decimal(n)))
        return tuple(out)


def ema(values, n) -> tuple[Optional[Decimal], ...]:
    _check_period(n)
    _check_values(values)
    with localcontext(_CTX):
        alpha = Decimal(2) / Decimal(n + 1)
        e = []
        for i, v in enumerate(values):
            if i == 0:
                e.append(v)
            else:
                e.append(e[-1] + alpha * (v - e[-1]))
        return tuple(None if i < n - 1 else _nz(e[i]) for i in range(len(values)))


def rma(values, n) -> tuple[Optional[Decimal], ...]:
    _check_period(n)
    _check_values(values)
    with localcontext(_CTX):
        alpha = Decimal(1) / Decimal(n)
        e = []
        for i, v in enumerate(values):
            if i == 0:
                e.append(v)
            else:
                e.append(e[-1] + alpha * (v - e[-1]))
        return tuple(None if i < n - 1 else _nz(e[i]) for i in range(len(values)))


def true_range(bars, *, candle_ms) -> tuple[Decimal, ...]:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    check_bars(bars, candle_ms=candle_ms)
    with localcontext(_CTX):
        out = []
        for i, b in enumerate(bars):
            if i == 0:
                out.append(_nz(b.high - b.low))
            else:
                prev = bars[i - 1].close
                tr = max(b.high - b.low, abs(b.high - prev), abs(b.low - prev))
                out.append(_nz(tr))
        return tuple(out)


def atr(bars, n, *, candle_ms) -> tuple[Optional[Decimal], ...]:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_period(n)
    check_bars(bars, candle_ms=candle_ms)
    return rma(list(true_range(bars, candle_ms=candle_ms)), n)


def rsi(bars, n, *, candle_ms) -> tuple[Optional[Decimal], ...]:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_period(n)
    check_bars(bars, candle_ms=candle_ms)
    with localcontext(_CTX):
        closes = [b.close for b in bars]
        out = [None] * len(bars)
        if len(bars) < 2:
            return tuple(out)
        gains = [Decimal(0)]
        losses = [Decimal(0)]
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, Decimal(0)))
            losses.append(max(-d, Decimal(0)))
        alpha = Decimal(1) / Decimal(n)
        ag = gains[1]
        al = losses[1]
        for i in range(1, len(bars)):
            if i > 1:
                ag = ag + alpha * (gains[i] - ag)
                al = al + alpha * (losses[i] - al)
            if i >= n:
                if al == 0 and ag == 0:
                    out[i] = Decimal(50)
                elif al == 0:
                    out[i] = Decimal(100)
                else:
                    rs = ag / al
                    out[i] = _nz(Decimal(100) - Decimal(100) / (Decimal(1) + rs))
        return tuple(out)


def macd(bars, fast, slow, signal, *, candle_ms) -> MacdSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_period(fast)
    _check_period(slow)
    _check_period(signal)
    if fast >= slow:
        raise ValueError("invalid_period")
    check_bars(bars, candle_ms=candle_ms)
    closes = [b.close for b in bars]
    with localcontext(_CTX):
        alpha_f = Decimal(2) / Decimal(fast + 1)
        alpha_s = Decimal(2) / Decimal(slow + 1)
        ef, es = [], []
        for i, v in enumerate(closes):
            if i == 0:
                ef.append(v)
                es.append(v)
            else:
                ef.append(ef[-1] + alpha_f * (v - ef[-1]))
                es.append(es[-1] + alpha_s * (v - es[-1]))
        line_full = [ef[i] - es[i] for i in range(len(closes))]
        alpha_sig = Decimal(2) / Decimal(signal + 1)
        sig_full = []
        for i, v in enumerate(line_full):
            if i == 0:
                sig_full.append(v)
            else:
                sig_full.append(sig_full[-1] + alpha_sig * (v - sig_full[-1]))
        hist_full = [line_full[i] - sig_full[i] for i in range(len(closes))]
        line = tuple(None if i < slow - 1 else _nz(line_full[i]) for i in range(len(closes)))
        sig = tuple(None if i < slow + signal - 2 else _nz(sig_full[i]) for i in range(len(closes)))
        hist = tuple(None if i < slow + signal - 2 else _nz(hist_full[i]) for i in range(len(closes)))
        return MacdSeries(line, sig, hist)


def bollinger(bars, n, k, *, candle_ms) -> BollingerSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_period(n)
    if n < 2:
        raise ValueError("invalid_period")
    if not isinstance(k, Decimal) or not k.is_finite() or k <= 0:
        raise ValueError("invalid_period")
    check_bars(bars, candle_ms=candle_ms)
    closes = [b.close for b in bars]
    with localcontext(_CTX):
        mid, upper, lower, pb, bw = [], [], [], [], []
        for i in range(len(closes)):
            if i < n - 1:
                mid.append(None)
                upper.append(None)
                lower.append(None)
                pb.append(None)
                bw.append(None)
            else:
                window = closes[i - n + 1:i + 1]
                m = sum(window) / Decimal(n)
                var = sum((c - m) ** 2 for c in window) / Decimal(n)
                sd = var.sqrt()
                u = m + k * sd
                lo = m - k * sd
                mid.append(_nz(m))
                upper.append(_nz(u))
                lower.append(_nz(lo))
                if u == lo:
                    pb.append(None)
                else:
                    pb.append(_nz((closes[i] - lo) / (u - lo)))
                bw.append(_nz((u - lo) / m))
        return BollingerSeries(tuple(mid), tuple(upper), tuple(lower), tuple(pb), tuple(bw))


def donchian(bars, n, *, candle_ms) -> DonchianSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_period(n)
    check_bars(bars, candle_ms=candle_ms)
    with localcontext(_CTX):
        hi, lo = [], []
        for i in range(len(bars)):
            if i < n - 1:
                hi.append(None)
                lo.append(None)
            else:
                window = bars[i - n + 1:i + 1]
                hi.append(_nz(max(b.high for b in window)))
                lo.append(_nz(min(b.low for b in window)))
        return DonchianSeries(tuple(hi), tuple(lo))


def adx(bars, n, *, candle_ms) -> AdxSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_period(n)
    check_bars(bars, candle_ms=candle_ms)
    with localcontext(_CTX):
        plus_dm = [Decimal(0)]
        minus_dm = [Decimal(0)]
        for i in range(1, len(bars)):
            up = bars[i].high - bars[i - 1].high
            dn = bars[i - 1].low - bars[i].low
            plus_dm.append(up if up > dn and up > 0 else Decimal(0))
            minus_dm.append(dn if dn > up and dn > 0 else Decimal(0))
        tr = list(true_range(bars, candle_ms=candle_ms))
        alpha = Decimal(1) / Decimal(n)
        def rma_nm(vals):
            e = []
            for i, v in enumerate(vals):
                if i == 0:
                    e.append(v)
                else:
                    e.append(e[-1] + alpha * (v - e[-1]))
            return e
        a = rma_nm(tr)
        pdi_full = []
        mdi_full = []
        for i in range(len(bars)):
            if a[i] == 0:
                pdi_full.append(Decimal(0))
                mdi_full.append(Decimal(0))
            else:
                pdi_full.append(Decimal(100) * rma_nm(plus_dm)[i] / a[i])
                mdi_full.append(Decimal(100) * rma_nm(minus_dm)[i] / a[i])
        dx = []
        for i in range(len(bars)):
            s = pdi_full[i] + mdi_full[i]
            if s > 0:
                dx.append(Decimal(100) * abs(pdi_full[i] - mdi_full[i]) / s)
            else:
                dx.append(Decimal(0))
        adx_full = rma_nm(dx)
        pdi = tuple(None if i < n - 1 else _nz(pdi_full[i]) for i in range(len(bars)))
        mdi = tuple(None if i < n - 1 else _nz(mdi_full[i]) for i in range(len(bars)))
        adx_out = tuple(None if i < 2 * n - 2 else _nz(adx_full[i]) for i in range(len(bars)))
        return AdxSeries(pdi, mdi, adx_out)
