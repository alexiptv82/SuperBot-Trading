"""Analisi stagionale e ciclica — dati statici calcolati offline.

Fonte: medie mensili storiche BTC/ETH/XAU dal 2017 a luglio 2025.
Ciclo BTC: halving aprile 2024 → fase bull post-halving.
Nessuna chiamata di rete, nessuna dipendenza esterna.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

# Rendimento medio mensile storico (%) per asset.
# BTC: dati dal 2017 ad agosto 2025 (media geometrica delle variazioni mensili)
# ETH: dal 2018 ad agosto 2025
# XAU (oro): dal 2017 ad agosto 2025
# Valori approssimativi basati su storici pubblici CoinGecko/TradingView
MONTHLY_BIAS: dict[str, list[float]] = {
    # mese:              gen    feb    mar    apr    mag    giu    lug    ago    set    ott    nov    dic
    "BTC": [           +14.5, +13.2, +7.0,  +9.0,  -8.5,  -5.0,  +4.5,  -7.0, -6.5, +22.0, +38.0, +12.0],
    "ETH": [           +20.0, +16.0, +8.0,  +6.0, -12.0,  -8.0,  +6.0,  -9.0, -5.0, +18.0, +42.0, +10.0],
    "XAU": [            +1.5,  -0.5, +0.8,  +0.5,  -0.3,  +0.2,  +1.8,  +1.2, +0.8,  -0.5,  -0.8,  +1.0],
    "XAG": [            +1.2,  -0.8, +1.0,  +0.3,  -0.5,  +0.4,  +2.5,  +1.0, +0.5,  -0.8,  -1.0,  +0.8],
    "DEFAULT": [        +5.0,  +4.0, +3.0,  +3.0,  -3.0,  -2.0,  +2.0,  -3.0, -2.5,  +8.0, +12.0,  +4.0],
}

# Ciclo BTC post-halving (aprile 2024)
# Mesi dal halving → fase tipica → bias moltiplicatore
# Fonte: pattern storici halving 2012, 2016, 2020
HALVING_MS = 1_713_571_200_000  # 2024-04-20 00:00 UTC in ms

HALVING_CYCLE: list[tuple[int, int, str, float]] = [
    # (mese_inizio, mese_fine, fase, moltiplicatore_bias)
    (0,   3,  "consolidamento post-halving",  0.5),
    (3,   9,  "accumulo lento",               0.8),
    (9,  18,  "bull run primario",             1.8),
    (18, 24,  "distribuzione",                 0.9),
    (24, 30,  "correzione",                   -0.5),
    (30, 36,  "bear market",                  -1.0),
    (36, 42,  "capitolazione/bottom",         -0.3),
    (42, 48,  "accumulazione pre-halving",     0.6),
]


@dataclass
class SeasonalContext:
    month: int               # 1-12
    asset: str
    monthly_bias_pct: float  # rendimento medio storico del mese corrente
    halving_phase: str       # descrizione fase del ciclo
    halving_months: int      # mesi dal halving
    cycle_mult: float        # moltiplicatore (positivo = bull, negativo = bear)
    long_bonus: int          # punti bonus per long (0-15)
    short_bonus: int         # punti bonus per short (0-15)
    note: str                # testo per il prompt


def get_seasonal(symbol: str, now_ms: int | None = None) -> SeasonalContext:
    """Ritorna il contesto stagionale e ciclico per il simbolo al momento now_ms."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    tm = time.gmtime(now_ms / 1000)
    month = tm.tm_mon  # 1-12

    # asset base (rimuove USDT, :USDT ecc.)
    base = symbol.upper().replace("USDT", "").replace(":", "").strip("/")
    biases = MONTHLY_BIAS.get(base, MONTHLY_BIAS["DEFAULT"])
    monthly_bias = biases[month - 1]

    # fase del ciclo BTC (applicata a tutti gli asset crypto con fattore ridotto per altcoin)
    months_since = max(0, (now_ms - HALVING_MS) // (30 * 24 * 3_600_000))
    phase_name, cycle_mult = "sconosciuta", 1.0
    for (s, e, name, mult) in HALVING_CYCLE:
        if s <= months_since < e:
            phase_name, cycle_mult = name, mult
            break

    # per oro/argento il ciclo BTC non si applica
    is_crypto = base not in ("XAU", "XAG")
    if not is_crypto:
        cycle_mult = 1.0
        phase_name = "commodity indipendente da ciclo BTC"

    # calcola bonus punti (max 15 per lato)
    effective = monthly_bias * (cycle_mult if is_crypto else 1.0)
    if effective > 0:
        long_bonus = min(15, int(effective / 4))
        short_bonus = 0
    else:
        long_bonus = 0
        short_bonus = min(15, int(abs(effective) / 4))

    note = (f"Stagionalità {month}/{tm.tm_year}: storicamente {monthly_bias:+.1f}% per {base}. "
            f"Ciclo BTC: {phase_name} ({months_since} mesi dal halving, mult {cycle_mult:+.1f}x).")

    return SeasonalContext(month, base, monthly_bias, phase_name, months_since,
                           cycle_mult, long_bonus, short_bonus, note)
