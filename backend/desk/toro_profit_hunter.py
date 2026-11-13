"""Toro LONG Profit Hunter V1 — deterministic PAPER research core.

Separate from Falcon SHORT and from autonomous Brain. No Bitget write API, no
network, no exchange orders, no inherited strategy changes. All signals use
ONLY candles closed as of asof_ms; entry fills require later 1m market evidence.

Specification: docs/v3/TORO-LONG-PROFIT-HUNTER-rapporto-indipendente.md.
This is a candidate, NOT a proven profitable strategy or a live trading engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import floor, isfinite, sqrt
from statistics import mean, pstdev
from typing import Sequence

HOUR = 3_600_000
FOUR_HOURS = 4 * HOUR
MINUTE = 60_000


@dataclass(frozen=True)
class Candle:
    ts: int                      # UTC opening time, milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    def valid(self) -> bool:
        x = (self.open, self.high, self.low, self.close, self.volume)
        return (all(isfinite(float(v)) for v in x) and self.low > 0 and
                self.low <= min(self.open, self.close) and
                max(self.open, self.close) <= self.high and self.volume >= 0)


@dataclass(frozen=True)
class Policy:
    equity_start: float = 1000.0
    slots: int = 5
    max_margin: float = 200.0
    max_total_margin: float = 800.0
    cash_reserve: float = 200.0
    max_notional_total: float = 10000.0
    risk_per_trade: float = 16.0
    max_open_risk: float = 40.0
    max_daily_loss: float = 30.0
    max_drawdown: float = 0.15
    kill_equity: float = 450.0
    max_leverage: int = 20
    maker_fee: float = 0.0002
    taker_fee: float = 0.0006
    stop_slippage: float = 0.0002
    funding_reserve: float = 0.0000
    min_margin: float = 30.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    asof_ms: int
    entry_limit: float
    stop: float
    target: float
    atr: float
    regime: str
    reason: str = "bb100_confirmed_reentry"


@dataclass(frozen=True)
class Quote:
    symbol: str
    margin: float
    leverage: int
    notional: float
    worst_case_loss: float
    entry_limit: float
    stop: float
    target: float


@dataclass(frozen=True)
class Decision:
    action: str               # NO_TRADE, PLACE_MAKER, CLOSE, PARTIAL, HOLD, RAISE_STOP
    why: str
    quote: Quote | None = None
    new_stop: float | None = None
    fraction: float = 0.0


@dataclass
class Guardian:
    """Persistent per-position audit state. All figures are USDT, net of costs."""
    max_net_total: float = 0.0
    ratchet_floor: float = float("-inf")
    realized_net: float = 0.0
    partial_done: bool = False
    max_price: float = 0.0
    last_observed_ms: int = 0


def _bars(bars: Sequence[Candle], asof_ms: int, interval: int, required: int) -> list[Candle]:
    b = sorted((bar for bar in bars if bar.ts + interval <= asof_ms), key=lambda bar: bar.ts)
    if len(b) < required:
        return []
    b = b[-required:]
    if (any(not x.valid() or x.ts % interval for x in b) or
            any(b[i].ts + interval != b[i+1].ts for i in range(len(b)-1)) or
            len(set(x.ts for x in b)) != len(b)):
        return []
    return b


def _ema(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    result = [float(values[0])]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def _atr(c: Sequence[Candle], period: int = 14) -> float:
    if len(c) < period + 1:
        return 0.0
    tr = [max(c[i].high - c[i].low,
              abs(c[i].high - c[i-1].close),
              abs(c[i].low - c[i-1].close)) for i in range(1, len(c))]
    return mean(tr[-period:])


def _adx(c: Sequence[Candle], period: int = 14) -> float:
    """ADX approximation with Wilder smoothing; only for the strong-down veto."""
    if len(c) < 3 * period:
        return 0.0
    trs, plus, minus = [], [], []
    for a, b in zip(c[:-1], c[1:]):
        up, down = b.high - a.high, a.low - b.low
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
        trs.append(max(b.high-b.low, abs(b.high-a.close), abs(b.low-a.close)))
    def wilder(z):
        v = sum(z[:period])
        out = []
        for x in z[period:]:
            v = v - v / period + x
            out.append(v)
        return out
    tr_s, p_s, m_s = map(wilder, (trs, plus, minus))
    dx = [100 * abs(p-m) / (p+m) if p+m else 0 for t, p, m in zip(tr_s,p_s,m_s)
          if t > 0]
    if len(dx) < period:
        return 0.0
    result = mean(dx[:period])
    for val in dx[period:]:
        result = (result * (period-1) + val) / period
    return result


def _lower(c: Sequence[Candle], idx: int, period: int = 100) -> float:
    if idx < period - 1:
        return float("nan")
    close = [x.close for x in c[idx-period+1:idx+1]]
    return mean(close) - 2 * pstdev(close)


def entry_signal(symbol: str, hourly: Sequence[Candle], four_hour: Sequence[Candle],
                 asof_ms: int) -> tuple[Signal | None, str]:
    """Exactly one proposal after the last CLOSED 1H bar, with CLOSED 4H regime."""
    h = _bars(hourly, asof_ms, HOUR, 750)   # 30-day ATR percentile, EMA history
    f = _bars(four_hour, asof_ms, FOUR_HOURS, 240)
    if not h or not f:
        return None, "missing_or_gapped_closed_history"
    if h[-1].ts + HOUR != asof_ms:
        return None, "latest_1h_not_closed_at_decision"
    if asof_ms - (f[-1].ts + FOUR_HOURS) >= FOUR_HOURS:
        return None, "4h_stale"
    h_close, f_close = [x.close for x in h], [x.close for x in f]
    e50, e200 = _ema(f_close, 50), _ema(f_close, 200)
    strong_down = (f[-1].close < e200[-1] and
                   all(e50[-j] < e50[-j-1] for j in range(1, 6)) and
                   _adx(f) >= 25)
    if strong_down:
        return None, "strong_4h_downtrend"
    last = h[-1]
    atr = _atr(h)
    if not atr or last.close <= 0:
        return None, "atr_invalid"
    hist_atr = [_atr(h[:i]) for i in range(15, len(h)+1)]
    recent = sorted(x for x in hist_atr[-720:] if x > 0)
    if len(recent) < 500 or atr > recent[int(0.9 * (len(recent)-1))]:
        return None, "excessive_volatility"
    if not (last.close > last.open and last.close >= (last.high+last.low)/2
            and last.close > _lower(h, len(h)-1)):
        return None, "no_closed_reentry_confirmation"
    touches = [i for i in range(len(h)-4, len(h)-1)
               if h[i].low <= _lower(h, i)]
    if not touches:
        return None, "no_lower_band_touch"
    if any((h[i].high - h[i].low) > 3*atr for i in touches):
        return None, "violent_dump_wick"
    touch_idx = touches[-1]
    below_streak = sum(1 for i in range(touch_idx, len(h)-1)
                       if h[i].close < _lower(h, i))
    if below_streak > 3:
        return None, "persistent_breakdown"
    # Stop distance must be between 0.8 and 2.0 ATR, respecting actual structure.
    stop = min(h[touch_idx].low, last.low) - 0.25*atr
    dist = last.close - stop
    if not 0.8*atr <= dist <= 2.0*atr:
        return None, "technical_stop_out_of_range"
    mid = mean(x.close for x in h[-100:])
    if mid <= last.close:
        return None, "no_reversion_room"
    return Signal(symbol, asof_ms, last.close, stop, mid, atr,
                  "neutral_or_up"), "signal"


def quote_entry(s: Signal, *, equity: float, cash: float, margin_used: float,
                notional_used: float, open_risk: float, n_positions: int,
                daily_pnl: float, equity_peak: float, exchange_max_leverage: int,
                policy: Policy = Policy()) -> tuple[Quote | None, str]:
    if n_positions >= policy.slots or equity <= policy.kill_equity:
        return None, "slots_or_equity_halt"
    if daily_pnl <= -policy.max_daily_loss or (
        equity_peak > 0 and (equity_peak-equity)/equity_peak >= policy.max_drawdown
    ):
        return None, "circuit_breaker"
    budget = min(policy.risk_per_trade, policy.max_open_risk-open_risk,
                 policy.max_daily_loss + daily_pnl)
    if budget <= 0:
        return None, "no_remaining_risk_budget"
    available_margin = min(policy.max_margin, policy.max_total_margin-margin_used,
                           cash-policy.cash_reserve)
    if available_margin < policy.min_margin:
        return None, "margin_or_reserve_exhausted"
    stop_distance = (s.entry_limit-s.stop)/s.entry_limit
    cost = policy.maker_fee+policy.taker_fee+policy.stop_slippage+policy.funding_reserve
    target_distance = (s.target-s.entry_limit)/s.entry_limit
    if (not isfinite(stop_distance) or not (0 < stop_distance < 1) or
            (target_distance-cost)/(stop_distance+cost) < 1.3):
        return None, "economic_gate"
    max_notional = min(budget/(stop_distance+cost),
                       policy.max_notional_total-notional_used,
                       available_margin*min(exchange_max_leverage,policy.max_leverage))
    # Reduce MARGIN if the remaining risk budget cannot even support 1x
    # at a full 200 USDT ticket. Do not force slots or over-risk a small order.
    # Always round margin DOWN to the nearest cent: nearest rounding can
    # exceed the remaining daily risk budget by a fractional cent.
    margin = floor(min(available_margin, max_notional)*100)/100
    if margin < policy.min_margin:
        return None, "notional_too_small"
    lev = floor(max_notional/margin)
    if lev < 1:
        return None, "notional_too_small"
    notional = margin*lev
    risk = notional*(stop_distance+cost)
    if risk > budget+1e-7:
        return None, "risk_exceeded"
    return Quote(s.symbol, margin, lev, notional, risk, s.entry_limit,
                 s.stop, s.target), "accepted"


@dataclass
class MakerPending:
    quote: Quote
    placed_ms: int
    expires_ms: int
    status: str = "PENDING"
    atr: float = 0.0
    invalid_below: float = 0.0

    def on_minute(self, bar: Candle, *, price_gap: bool = False) -> str:
        if self.status != "PENDING":
            return self.status
        if not bar.valid() or price_gap or bar.ts < self.placed_ms:
            return self.status
        if bar.ts >= self.expires_ms:
            self.status = "EXPIRED"
        elif bar.open < self.quote.entry_limit:
            # Post-only marketable on open: would cancel rather than cross spread.
            self.status = "CANCELLED_POST_ONLY"
        elif ((self.atr > 0 and bar.high >= self.quote.entry_limit + 0.25*self.atr)
                or (self.invalid_below > 0 and bar.low <= self.invalid_below)):
            # Ambiguous OHLC crossing/cancel sequence: conservative NO FILL.
            self.status = "CANCELLED_INVALIDATED"
        elif bar.low < self.quote.entry_limit:
            self.status = "FILLED"
        return self.status


def momentum_score(five_min: Sequence[Candle], asof_ms: int) -> int | None:
    """Closed 5m bars only. None => data unavailable, never treated as strong."""
    bars = _bars(five_min, asof_ms, 5*MINUTE, 30)
    if not bars:
        return None
    closes = [x.close for x in bars]
    e9 = _ema(closes, 9)
    points = 0
    if closes[-1] > e9[-1] and e9[-1] > e9[-2]:
        points += 1
    if closes[-1] > min(x.low for x in bars[-4:-1]):
        points += 1
    if mean(x.volume for x in bars[-3:]) >= 0.8 * mean(x.volume for x in bars[-15:-3]):
        points += 1
    return points


def estimated_net_long(*, entry: float, last_bid: float, quantity: float,
                       maker_fee: float, taker_fee: float, stop_slippage: float,
                       funding: float = 0.0) -> float:
    """Net liquidation PnL on the RESIDUAL open quantity, all costs applied once."""
    if not (entry > 0 and last_bid > 0 and quantity > 0):
        raise ValueError("invalid_pnl_inputs")
    return (quantity*(last_bid*(1-stop_slippage)-entry)
            - quantity*entry*maker_fee
            - quantity*last_bid*taker_fee - funding)


def profit_guardian(state: Guardian, *, now_ms: int, opened_ms: int,
                    net_open_now: float, atr_price: float, entry_price: float,
                    remaining_notional: float, momentum_score: int,
                    structural_room_net: float, funding_soon: bool = False,
                    risk_halt: bool = False, waiting_higher_quality: bool = False,
                    profit_target_hit: bool = False) -> Decision:
    """Compute advisory action; caller MUST persist state before executing once.

    net_open_now is residual liquidation PnL plus state.realized_net only if the
    caller has subtracted all fees/funding; max is monitored from CLOSED 1m bars.
    Stop loss is independent and always takes priority over guardian.
    """
    if now_ms < opened_ms or not all(map(isfinite, (
            net_open_now, atr_price, entry_price, remaining_notional))):
        return Decision("NO_TRADE","invalid_time_or_mark")
    combined = state.realized_net + net_open_now
    if now_ms <= state.last_observed_ms:
        return Decision("HOLD","out_of_order_observation")
    state.last_observed_ms = now_ms
    state.max_net_total = max(state.max_net_total, combined)
    m = state.max_net_total
    age = now_ms-opened_ms
    if age >= 24*HOUR or (age >= 12*HOUR and combined < 5):
        return Decision("CLOSE","time_exit")
    if m >= 12:
        # Convert ATR in price units into USDT variation of current notional.
        atr_money = 0.25*(atr_price/entry_price)*remaining_notional
        giveback = max(5.0, atr_money, m*(0.4 if m<20 else
                            0.3 if m<30 else 0.25 if m<40 else 0.2))
        # Report Claude section D: between +12 and +15 net the floor is
        # BREAK-EVEN, not an aggressive +7 USDT trailing target.
        new_floor = 0.0 if m < 15 else max(0.0, m-giveback)
        state.ratchet_floor = max(state.ratchet_floor, new_floor)
        if combined <= state.ratchet_floor:
            return Decision("CLOSE","ratchet_profit_floor")
    strong = (momentum_score == 3 and
              structural_room_net >= 1.5*max(0.0, m-state.ratchet_floor) and
              not funding_soon and not risk_halt and not waiting_higher_quality)
    if profit_target_hit and not strong:
        return Decision("CLOSE","reached_bb_midline")
    if combined >= 40 and not strong:
        return Decision("CLOSE","profit_40_take")
    if combined >= 30 and strong and not state.partial_done:
        return Decision("PARTIAL","strong_trend_protect_half",fraction=0.5)
    if combined >= 25 and not strong:
        return Decision("CLOSE","profit_25_take")
    if combined >= 20 and momentum_score <= 2:
        return Decision("CLOSE","momentum_weak_profit")
    if combined >= 15 and momentum_score <= 1:
        return Decision("CLOSE","momentum_weak_safety")
    return Decision("HOLD","trailing_protection" if m>=12 else "waiting_for_setup")


def daily_summary(closed: Sequence[dict]) -> dict:
    nets = [float(x["net"]) for x in closed]
    if not nets:
        return {"trades":0,"win_rate":None,"net":0.0,"max_drawdown":0.0}
    equity, peak, dd = 0.0, 0.0, 0.0
    for pnl in nets:
        equity += pnl
        peak = max(peak,equity)
        dd = max(dd,peak-equity)
    return {"trades":len(nets),"win_rate":sum(x>0 for x in nets)/len(nets),
            "net":round(sum(nets),2),"max_drawdown":round(dd,2)}
