"""Falco Evoluto: analista a REGOLE per una run V3 (SHORT evoluto + LONG indipendente), AI solo consulente raro.

Origine: punteggio tecnico di Falco (``backend/desk/signals.py`` + soglie di ``brain.rules_decisions`` /
``cli.tier_entry_score``). Il desk V2 e il Falco storico NON sono toccati: qui c'e' una copia evoluta, separata.

Correzioni esplicite rispetto all'originale (audit 12/11/2026):
1. EMA calcolate con seme SMA (definite solo dopo ``n`` barre), non dal primo prezzo.
2. Trend 4h (EMA50 / EMA200): solo con almeno ``EMA200_MIN_BARS`` candele 4h chiuse; prima era una EMA200 su ~60
   barre ("EMA61"). Senza dati sufficienti il trend 4h e' "non disponibile" e non da' punti.
3. Trend 1d: solo da giorni UTC COMPLETI ricavati dalle candele 4h (6 per giorno), su EMA20 con pendenza confermata e
   almeno ``DAILY_MIN_DAYS`` giorni; prima EMA50/EMA200 giornaliere su pochi giorni. Senza dati: non disponibile.
4. Solo candele CHIUSE (il feed della run V3 fornisce gia' solo quelle).
La stagionalita' dell'originale (tabella non verificata) e la S25 non sono usate.

Regole
* Regime (classificatore P8 della vista di mercato, ``context.regime``): LONG solo in TREND_UP o EXPANSION, SHORT solo
  in TREND_DOWN o EXPANSION; RANGE, UNCERTAIN, SHOCK, UNKNOWN -> NO_TRADE (nessuna apertura obbligatoria).
* SHORT evoluto: punteggio originale lato short (trend 4h 20, 1h 15, 1d 15, prezzo sotto EMA50 8, momento 24h fino a
  12, rottura minimi 20h 10, RSI 30-50 8, volume ribassista 4, pattern ribassista 8, doji -5, ipervenduto -12) con
  soglia 60 (BTC, ETH) o 70 (altri) e veto se 4h e 1d sono entrambi rialzisti (apertura contro il mercato).
* LONG (nuovo, indipendente): TUTTE le conferme 4h rialzista, 1d rialzista, EMA20>EMA50 1h, prezzo sopra EMA50 1h,
  RSI 1h 50-70, volume >= media 24h, nessun incrocio ribassista sull'ultima 1h, nessun pattern ribassista; poi lo
  stesso punteggio simmetrico lato long con la stessa soglia.
* Conflitto: punteggi long e short entrambi vicini alla soglia (scarto < 10) -> consulto AI; pari -> NO_TRADE.
* Stop: 1,2 x ATR 1h, fra 0,3 % e 3,5 % (come l'originale). Non viene MAI stretto per far quadrare leva o margine: se
  il RiskManager non trova una leva 15-45x compatibile, la decisione diventa NO_TRADE.
* Leva proposta: il massimo del profilo; il motore scende fino alla prima leva che rispetta tutti i limiti.

AI (DeepSeek, budget proprio della run): chiamata SOLO per conflitto, inversione 1h contro il lato proposto o regime
EXPANSION. Puo' solo CONFERMARE il lato delle regole o dire NO_TRADE (mai simbolo, lato, leva o stop). AI non
disponibile, budget esaurito o risposta non valida -> NO_TRADE. La spesa resta nel registro della run.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Callable, Mapping, Optional, Sequence

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal
from backend.v3.brain_f3.providers import _call, _json_object

H4_MS = 14_400_000
DAY_MS = 86_400_000
EMA200_MIN_BARS = 220
DAILY_MIN_DAYS = 25
TIER_A = frozenset({"BTCUSDT", "ETHUSDT"})
ENTRY_TIER_A, ENTRY_TIER_C = 60, 70
CONFLICT_GAP = 10
LONG_REGIMES = frozenset({"TREND_UP", "EXPANSION"})
SHORT_REGIMES = frozenset({"TREND_DOWN", "EXPANSION"})
ORIGIN = "falco:rules"

SRC_SHORT, SRC_LONG, SRC_AI = "falco_evoluto:short_rules", "falco_evoluto:long_rules", "falco_evoluto:ai_confirmed"
# Motivi (codici chiusi, ammessi dal motore)
NT_REGIME, NT_SCORE, NT_CONFLICT = "falco_no_trade_regime", "falco_no_trade_score", "falco_no_trade_conflict"
NT_DATA, NT_AI_NO, NT_AI_DOWN = "falco_no_trade_data", "falco_ai_no_trade", "falco_ai_unavailable"
OPEN_SHORT, OPEN_LONG = "falco_short_signal", "falco_long_signal"
RATIONALES = frozenset({NT_REGIME, NT_SCORE, NT_CONFLICT, NT_DATA, NT_AI_NO, NT_AI_DOWN, OPEN_SHORT, OPEN_LONG})
SOURCES = frozenset({SRC_SHORT, SRC_LONG, SRC_AI})

AI_SYSTEM = ("You are a risk consultant for a PAPER trading rules engine. The rules already chose the symbol, side, "
             "stop and leverage. Given the JSON facts, answer ONLY with a JSON object {\"decision\":\"CONFIRM\"} or "
             "{\"decision\":\"NO_TRADE\"}. You cannot change side, leverage, size or stop. When in doubt: NO_TRADE.")


# ------------------------------------------------------------------ indicatori (float, solo candele chiuse)
def ema_sma_seeded(x: Sequence[float], n: int) -> list:
    """EMA con seme SMA: None per le prime n-1 barre (mai una media lunga su pochi dati)."""
    out = [None] * len(x)
    if len(x) < n:
        return out
    a = 2.0 / (n + 1)
    e = sum(x[:n]) / n
    out[n - 1] = e
    for i in range(n, len(x)):
        e = a * x[i] + (1 - a) * e
        out[i] = e
    return out


def rsi(c: Sequence[float], n: int = 14) -> Optional[float]:
    if len(c) < n + 1:
        return None
    d = [c[i] - c[i - 1] for i in range(1, len(c))]
    up = [max(v, 0.0) for v in d]
    dn = [max(-v, 0.0) for v in d]
    au, ad = sum(up[:n]) / n, sum(dn[:n]) / n
    for i in range(n, len(d)):
        au, ad = (au * (n - 1) + up[i]) / n, (ad * (n - 1) + dn[i]) / n
    return 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)


def atr(b: Sequence[tuple], n: int = 14) -> Optional[float]:
    if len(b) < n + 1:
        return None
    tr = [max(b[i][1] - b[i][2], abs(b[i][1] - b[i - 1][3]), abs(b[i][2] - b[i - 1][3])) for i in range(1, len(b))]
    return sum(tr[-n:]) / n


def candle_pattern(b: Sequence[tuple]) -> str:
    """Pattern dell'ultima candela 1h chiusa (stesse definizioni di desk/signals.doji_pattern)."""
    if len(b) < 3:
        return ""
    o, h, l, c = b[-1][0], b[-1][1], b[-1][2], b[-1][3]
    body, rng = abs(c - o), h - l
    if rng == 0:
        return ""
    upper, lower = h - max(o, c), min(o, c) - l
    if body / rng < 0.1:
        return "doji"
    if lower > body * 2 and upper < body * 0.5:
        return "hammer"
    if upper > body * 2 and lower < body * 0.5:
        return "shooting_star"
    po, pc = b[-2][0], b[-2][3]
    if c > o and pc < po and c > po and o < pc:
        return "bullish_engulfing"
    if c < o and pc > po and c < po and o > pc:
        return "bearish_engulfing"
    return ""


def daily_from_4h(bars4h) -> list:
    """Chiusure giornaliere dei SOLI giorni UTC completi (6 candele 4h contigue)."""
    days: dict = {}
    for b in bars4h:
        days.setdefault(b.open_time_ms // DAY_MS, []).append(b)
    out = []
    for k in sorted(days):
        g = sorted(days[k], key=lambda b: b.open_time_ms)
        if len(g) == 6 and all(g[i].open_time_ms == k * DAY_MS + i * H4_MS for i in range(6)):
            out.append(float(g[-1].close))
    return out


def _rows(bars) -> list:
    return [(float(b.open), float(b.high), float(b.low), float(b.close), float(b.volume)) for b in bars]


# ------------------------------------------------------------------ valutazione delle regole
@dataclass(frozen=True)
class Evaluation:
    side: int                         # +1 / -1 proposto dalle regole, 0 = nessuno
    code: str                         # motivo (RATIONALES)
    long_score: int
    short_score: int
    stop_fraction: Optional[float]
    consult: tuple = ()               # motivi del consulto AI (vuoto = nessun consulto)
    facts: dict = field(default_factory=dict)


def evaluate(symbol: str, regime: str, price: float, bars1h, bars4h) -> Evaluation:
    b1, b4 = _rows(bars1h), _rows(bars4h)
    if len(b1) < 60 or len(b4) < 60 or not price > 0:
        return Evaluation(0, NT_DATA, 0, 0, None)
    c1, c4 = [r[3] for r in b1], [r[3] for r in b4]
    e20, e50 = ema_sma_seeded(c1, 20), ema_sma_seeded(c1, 50)
    trend1h = 1 if e20[-1] > e50[-1] else -1
    trend4h = None
    if len(c4) >= EMA200_MIN_BARS:                                   # correzione 2
        e50_4, e200_4 = ema_sma_seeded(c4, 50)[-1], ema_sma_seeded(c4, 200)[-1]
        trend4h = 1 if e50_4 > e200_4 else -1
    daily = daily_from_4h(bars4h)
    trend1d = None
    if len(daily) >= DAILY_MIN_DAYS:                                 # correzione 3
        ed = ema_sma_seeded(daily, 20)
        if ed[-1] is not None and ed[-4] is not None:
            if daily[-1] > ed[-1] and ed[-1] > ed[-4]:
                trend1d = 1
            elif daily[-1] < ed[-1] and ed[-1] < ed[-4]:
                trend1d = -1
            else:
                trend1d = 0
    r1h = rsi(c1)
    roc24 = c1[-1] / c1[-25] - 1
    hi20, lo20 = max(r[1] for r in b1[-21:-1]), min(r[2] for r in b1[-21:-1])
    vol_ratio = b1[-1][4] / max(1e-12, sum(r[4] for r in b1[-25:-1]) / 24)
    a = atr(b1)
    a_pct = a / c1[-1] if a else None
    pat = candle_pattern(b1)
    cross = ("up" if e20[-2] <= e50[-2] and e20[-1] > e50[-1]
             else "down" if e20[-2] >= e50[-2] and e20[-1] < e50[-1] else "")

    sc = {1: 0, -1: 0}

    def add(side, pts):
        sc[side] += pts

    if trend4h is not None:
        add(trend4h, 20)
    add(trend1h, 15)
    if trend1d in (1, -1):
        add(trend1d, 15)
    add(1 if price > e50[-1] else -1, 8)
    m = int(round(min(abs(roc24) / 0.03, 1.0) * 12))
    if m:
        add(1 if roc24 > 0 else -1, m)
    if c1[-1] > hi20:
        add(1, 10)
    elif c1[-1] < lo20:
        add(-1, 10)
    if r1h is not None and 50 <= r1h <= 70:
        add(1, 8)
    elif r1h is not None and 30 <= r1h < 50:
        add(-1, 8)
    if vol_ratio > 1.3:
        add(1 if c1[-1] >= b1[-1][0] else -1, 4)
    if pat in ("hammer", "bullish_engulfing"):
        add(1, 8)
    elif pat in ("shooting_star", "bearish_engulfing"):
        add(-1, 8)
    elif pat == "doji":
        sc[1], sc[-1] = max(0, sc[1] - 5), max(0, sc[-1] - 5)
    if r1h is not None and r1h > 78:
        sc[1] = max(0, sc[1] - 12)
    if r1h is not None and r1h < 22:
        sc[-1] = max(0, sc[-1] - 12)
    ls, ss = min(100, sc[1]), min(100, sc[-1])
    threshold = ENTRY_TIER_A if symbol in TIER_A else ENTRY_TIER_C
    stop = None if a_pct is None else min(0.035, max(0.003, 1.2 * a_pct))
    facts = {"regime": regime, "trend_4h": trend4h, "trend_1h": trend1h, "trend_1d": trend1d,
             "rsi_1h": None if r1h is None else round(r1h, 1), "roc_24h": round(roc24, 4),
             "vol_ratio": round(vol_ratio, 2), "atr_1h_pct": None if a_pct is None else round(a_pct, 5),
             "pattern": pat, "ema_cross_1h": cross, "long_score": ls, "short_score": ss, "threshold": threshold,
             "bars_4h": len(c4), "days_1d": len(daily)}
    if regime not in LONG_REGIMES | SHORT_REGIMES:
        return Evaluation(0, NT_REGIME, ls, ss, stop, facts=facts)
    if stop is None:
        return Evaluation(0, NT_DATA, ls, ss, None, facts=facts)

    long_ok = (regime in LONG_REGIMES and trend4h == 1 and trend1d == 1 and trend1h == 1 and price > e50[-1]
               and r1h is not None and 50 <= r1h <= 70 and vol_ratio >= 1.0 and cross != "down"
               and pat not in ("shooting_star", "bearish_engulfing") and ls >= threshold)
    short_ok = (regime in SHORT_REGIMES and ss >= threshold and not (trend4h == 1 and trend1d == 1))
    near = ls >= threshold - CONFLICT_GAP and ss >= threshold - CONFLICT_GAP and abs(ls - ss) < CONFLICT_GAP
    if near:
        if ls == ss or not (long_ok or short_ok):
            return Evaluation(0, NT_CONFLICT, ls, ss, stop, facts=facts)
        side = 1 if long_ok and (not short_ok or ls > ss) else -1
        return Evaluation(side, OPEN_LONG if side == 1 else OPEN_SHORT, ls, ss, stop, ("conflict",), facts)
    if long_ok and not short_ok:
        side = 1
    elif short_ok and not long_ok:
        side = -1
    elif long_ok and short_ok:                                       # entrambi validi: impossibile senza conflitto
        return Evaluation(0, NT_CONFLICT, ls, ss, stop, facts=facts)
    else:
        return Evaluation(0, NT_SCORE, ls, ss, stop, facts=facts)
    consult = []
    if (side == 1 and cross == "down") or (side == -1 and cross == "up"):
        consult.append("reversal_against")
    if regime == "EXPANSION":
        consult.append("regime_expansion")
    return Evaluation(side, OPEN_LONG if side == 1 else OPEN_SHORT, ls, ss, stop, tuple(consult), facts)


# ------------------------------------------------------------------ analista
class FalcoEvolutoAnalyst(Analyst):
    def __init__(self, *, bars_source: Callable[[str], Mapping], max_leverage: int,
                 transport=None, model: str = "", spending_gate=None, ai_enabled: bool = False,
                 max_tokens: int = 2000):
        if type(max_leverage) is not int or not 1 <= max_leverage <= 125:
            raise ValueError("invalid_leverage")
        self.bars_source, self.max_leverage = bars_source, max_leverage
        self.transport, self.model, self.spending_gate = transport, model, spending_gate
        self.ai_enabled, self.max_tokens = ai_enabled, max_tokens
        self.consults = 0

    def _ask_ai(self, symbol: str, side: int, ev: Evaluation) -> Optional[bool]:
        """True = confermato, False = NO_TRADE dell'AI, None = AI non disponibile o risposta non valida."""
        self.consults += 1
        payload = {"model": self.model, "stream": False, "max_tokens": self.max_tokens,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": AI_SYSTEM},
                                {"role": "user", "content": json.dumps(
                                    {"symbol": symbol, "proposed_side": "LONG" if side == 1 else "SHORT",
                                     "consult_reasons": list(ev.consult), "facts": ev.facts}, sort_keys=True)}]}
        try:
            body = _call(self.transport, self.spending_gate, "deepseek", self.model, self.ai_enabled, payload)
            choice = body["choices"][0]
            if choice["finish_reason"] != "stop":
                return None
            obj = _json_object(choice["message"]["content"])
            if set(obj) != {"decision"} or obj["decision"] not in ("CONFIRM", "NO_TRADE"):
                return None
            return obj["decision"] == "CONFIRM"
        except Exception:
            return None

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        def no_trade(code, sources=()):
            return BrainDecision(kind=DecisionKind.NO_TRADE, rationale=code, sources=list(sources),
                                 occurred_at_ms=context.timestamp_ms)
        try:
            bars = self.bars_source(context.symbol)
            price = float(context.price)
            if not math.isfinite(price):
                return no_trade(NT_DATA)
            ev = evaluate(context.symbol, str(context.regime), price, bars["1h"], bars["4h"])
        except Exception:
            return no_trade(NT_DATA)
        if ev.side == 0:
            return no_trade(ev.code)
        src = [SRC_LONG if ev.side == 1 else SRC_SHORT]
        if ev.consult:
            verdict = self._ask_ai(context.symbol, ev.side, ev)
            if verdict is None:
                return no_trade(NT_AI_DOWN, src)
            if verdict is False:
                return no_trade(NT_AI_NO, src)
            src.append(SRC_AI)
        entry = context.price
        stop = (entry * (Decimal(1) - ev.side * Decimal(str(ev.stop_fraction)))).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
        digest = hashlib.sha256(json.dumps(ev.facts, sort_keys=True).encode()).hexdigest()[:32]
        prop = OpenProposal(context.symbol, ev.side, entry, stop, self.max_leverage, ev.code,
                            max(0.0, min(1.0, (ev.long_score if ev.side == 1 else ev.short_score) / 100)),
                            ORIGIN, digest)
        return BrainDecision(kind=DecisionKind.OPEN, proposal=prop, rationale=ev.code, sources=src,
                             occurred_at_ms=context.timestamp_ms)
