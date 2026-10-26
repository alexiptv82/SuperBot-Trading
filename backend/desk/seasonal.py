"""Analisi stagionale e ciclica — dati statici + curva halving smoothed.

Modifiche V2:
- Formula additiva (non moltiplicativa): 0.60×monthly + 0.40×cycle.
  Ottobre BTC (+22% storico) non viene più ribaltato dal ciclo bear.
- Curva ciclo interpolata: mese 30 (ottobre 2026) = −0.40 invece di −1.0.
- market_factor opzionale: se btc_return_3d va forte contro il prior, bonus ridotto/azzerato.
- Retrocompatibile: get_seasonal(symbol, now_ms) → SeasonalContext invariato.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

# Rendimento medio mensile storico (%) per asset.
MONTHLY_BIAS: dict[str, list[float]] = {
    # mese:              gen    feb    mar    apr    mag    giu    lug    ago    set    ott    nov    dic
    "BTC": [           +14.5, +13.2, +7.0,  +9.0,  -8.5,  -5.0,  +4.5,  -7.0, -6.5, +22.0, +38.0, +12.0],
    "ETH": [           +20.0, +16.0, +8.0,  +6.0, -12.0,  -8.0,  +6.0,  -9.0, -5.0, +18.0, +42.0, +10.0],
    "XAU": [            +1.5,  -0.5, +0.8,  +0.5,  -0.3,  +0.2,  +1.8,  +1.2, +0.8,  -0.5,  -0.8,  +1.0],
    "XAG": [            +1.2,  -0.8, +1.0,  +0.3,  -0.5,  +0.4,  +2.5,  +1.0, +0.5,  -0.8,  -1.0,  +0.8],
    "DEFAULT": [        +5.0,  +4.0, +3.0,  +3.0,  -3.0,  -2.0,  +2.0,  -3.0, -2.5,  +8.0, +12.0,  +4.0],
}

HALVING_MS = 1_713_571_200_000  # 2024-04-20 00:00 UTC in ms

# Curva ciclo halving interpolata linearmente.
# Valori range ~[−0.60, +0.85]; mese 30 = −0.40 (era −1.0 nella tabella discreta).
# Basata su pattern storici 2012/2016/2020 — prior probabilistico, n=3 cicli.
_CYCLE_ANCHORS: list[tuple[float, float]] = [
    (0.0,  0.15),
    (6.0,  0.55),
    (12.0, 0.85),
    (18.0, 0.45),
    (24.0, 0.10),
    (28.0, 0.00),
    (30.0, -0.40),
    (33.0, -0.60),
    (36.0, -0.45),
    (42.0, -0.15),
    (48.0, 0.25),
    (54.0, 0.45),
]

_MONTHLY_NORM_SCALE = 22.0   # tanh(22/22) ≈ 0.76, calibrato su ottobre BTC
_WEIGHT_MONTHLY = 0.60       # peso stagionalità mensile storica
_WEIGHT_CYCLE = 0.40         # peso ciclo halvings (ipotesi n=3)
_MAX_COMBINED = 0.91         # valore massimo raggiungibile: 0.60×0.76 + 0.40×0.85
_MAX_BONUS = 15              # punti massimi per lato (invariato)

_PHASE_NAMES: list[tuple[int, int, str]] = [
    (0,  6,  "consolidamento post-halving"),
    (6,  12, "accumulo lento"),
    (12, 18, "bull run primario"),
    (18, 24, "distribuzione"),
    (24, 30, "correzione"),
    (30, 36, "bear market"),
    (36, 42, "capitolazione/bottom"),
    (42, 48, "accumulazione pre-halving"),
]


def _smooth_cycle_mult(months_since: float) -> float:
    """Curva interpolata del ciclo halvings. Valori in [−0.60, +0.85]."""
    if months_since <= _CYCLE_ANCHORS[0][0]:
        return _CYCLE_ANCHORS[0][1]
    if months_since >= _CYCLE_ANCHORS[-1][0]:
        return _CYCLE_ANCHORS[-1][1]
    for (m0, v0), (m1, v1) in zip(_CYCLE_ANCHORS, _CYCLE_ANCHORS[1:]):
        if m0 <= months_since <= m1:
            t = (months_since - m0) / (m1 - m0)
            return v0 + t * (v1 - v0)
    return 0.0


@dataclass
class SeasonalContext:
    month: int
    asset: str
    monthly_bias_pct: float
    halving_phase: str
    halving_months: int
    cycle_mult: float        # valore smooth dalla curva interpolata
    long_bonus: int
    short_bonus: int
    note: str


def get_seasonal(symbol: str, now_ms: int | None = None,
                 btc_return_3d: float | None = None) -> SeasonalContext:
    """Ritorna il contesto stagionale per il simbolo.

    btc_return_3d: rendimento BTC degli ultimi 3 giorni (es. −0.04 = −4%).
    Se fornito e opposto al prior, applica market_factor (riduce/azzera il bonus).
    Retrocompatibile: chiamate con 1 o 2 argomenti funzionano invariate.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    tm = time.gmtime(now_ms / 1000)
    month = tm.tm_mon

    base = symbol.upper().replace("USDT", "").replace(":", "").strip("/")
    biases = MONTHLY_BIAS.get(base, MONTHLY_BIAS["DEFAULT"])
    monthly_bias_pct = biases[month - 1]

    months_since = max(0.0, (now_ms - HALVING_MS) / (30 * 24 * 3_600_000))
    months_int = int(months_since)

    is_crypto = base not in ("XAU", "XAG")

    if is_crypto:
        cycle_mult = _smooth_cycle_mult(months_since)
        # formula additiva: monthly e ciclo sono contributi separati con pesi fissi
        monthly_norm = math.tanh(monthly_bias_pct / _MONTHLY_NORM_SCALE)
        combined = _WEIGHT_MONTHLY * monthly_norm + _WEIGHT_CYCLE * cycle_mult
    else:
        cycle_mult = 1.0
        monthly_norm = math.tanh(monthly_bias_pct / _MONTHLY_NORM_SCALE)
        combined = monthly_norm  # XAU/XAG: solo bias mensile

    # market_factor: se il tape va forte contro il prior, riduce/azzera il bonus
    if combined != 0.0 and btc_return_3d is not None:
        favored_long = combined > 0
        market_against = (favored_long and btc_return_3d < 0) or (not favored_long and btc_return_3d > 0)
        if market_against:
            if abs(btc_return_3d) >= 0.03:
                combined = 0.0        # rimbalzo forte contro il prior: bonus azzerato
            elif abs(btc_return_3d) >= 0.015:
                combined *= 0.50      # contro-movimento moderato: bonus dimezzato

    bonus_pts = min(_MAX_BONUS, round(abs(combined) * _MAX_BONUS / _MAX_COMBINED))
    if combined > 0:
        long_bonus, short_bonus = bonus_pts, 0
        dir_label = f"LONG +{bonus_pts}"
    elif combined < 0:
        long_bonus, short_bonus = 0, bonus_pts
        dir_label = f"SHORT +{bonus_pts}"
    else:
        long_bonus, short_bonus = 0, 0
        dir_label = "neutro"

    phase_name = "ciclo avanzato"
    for s, e, name in _PHASE_NAMES:
        if s <= months_int < e:
            phase_name = name
            break
    if not is_crypto:
        phase_name = "commodity indipendente da ciclo BTC"

    note = (
        f"Stagionalità {month}/{tm.tm_year}: storicamente {monthly_bias_pct:+.1f}% per {base}. "
        f"Ciclo BTC: {phase_name} ({months_int} mesi dal halving, curva {cycle_mult:+.2f}). "
        f"Bias netto: {dir_label}."
    )

    return SeasonalContext(
        month=month, asset=base, monthly_bias_pct=monthly_bias_pct,
        halving_phase=phase_name, halving_months=months_int,
        cycle_mult=cycle_mult, long_bonus=long_bonus, short_bonus=short_bonus,
        note=note,
    )
