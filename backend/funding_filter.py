"""Filtro di sicurezza sul funding rate per i perpetual (dalla roadmap
consolidata + Qwen: "funding rate come feature standard per ciclo").

Logica: un funding rate molto positivo significa che i long pagano i
short -- il mercato e' "affollato" di posizioni long, spesso un segnale
di rischio di un repricing improvviso (squeeze) contro quella direzione.
Specularmente, un funding molto negativo e' un mercato affollato di
short. Quindi: non impedisce il segnale, ma lo PENALIZZA quando va nella
stessa direzione della folla (va CONTRO un eccesso di funding), perche'
è il caso con più rischio di una svolta improvvisa contro la posizione.

Soglie espresse come tasso per singolo intervallo di funding (su BitGet
tipicamente ogni 8h): sono valori di partenza ragionevoli (non una
calibrazione misurata su dati storici reali) e vanno rivisti osservando
la distribuzione reale dei funding rate su BTC/ETH una volta raccolti
abbastanza dati.
"""
from __future__ import annotations

FUNDING_ELEVATED = 0.0003   # 0.03% per intervallo: inizia la penalizzazione
FUNDING_EXTREME = 0.001     # 0.10% per intervallo: penalizzazione massima
MAX_PENALTY = 0.5           # il moltiplicatore di confidenza non scende
                            # mai sotto il 50% -- è un filtro di cautela,
                            # non un veto assoluto


def funding_penalty(funding_rate: float | None, direction: str) -> dict:
    """Ritorna {'multiplier': float in [MAX_PENALTY, 1.0], 'reason': str}.

    `direction` è 'long' o 'short' (la direzione del segnale da valutare).
    Un funding_rate None (simbolo senza funding, o fetch fallito) non
    penalizza nulla: multiplier=1.0.
    """
    if funding_rate is None or direction not in ('long', 'short'):
        return {'multiplier': 1.0, 'reason': 'funding rate non disponibile'}

    # Il segnale è "con la folla" se va nella stessa direzione dell'eccesso
    # di funding: funding positivo -> i long pagano -> la folla è long ->
    # un segnale long va con la folla (rischioso), uno short va contro.
    crowd_direction = 'long' if funding_rate > 0 else 'short'
    going_with_crowd = (direction == crowd_direction)

    magnitude = abs(funding_rate)
    if not going_with_crowd or magnitude < FUNDING_ELEVATED:
        return {'multiplier': 1.0, 'reason': 'funding normale o segnale contrarian'}

    # Interpolazione lineare tra FUNDING_ELEVATED (multiplier=1.0) e
    # FUNDING_EXTREME (multiplier=MAX_PENALTY), clampata oltre l'estremo.
    span = FUNDING_EXTREME - FUNDING_ELEVATED
    t = min(1.0, (magnitude - FUNDING_ELEVATED) / span) if span > 0 else 1.0
    multiplier = 1.0 - t * (1.0 - MAX_PENALTY)
    return {
        'multiplier': round(multiplier, 3),
        'reason': f'segnale {direction} con funding {funding_rate:+.4%} (folla {crowd_direction})',
    }
