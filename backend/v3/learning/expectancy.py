"""Expectancy per cella con intervalli a blocchi di giorni (F7, passo P4).

Consuma ``TradeOutcome`` (backend/v3/outcomes.py) e dice, per ogni *cella*
(per default: simbolo, lato, regime della decisione, manuale/Brain), quanto
rende in media un trade **al netto dei costi**, in basis points dell'entry
notional, con un intervallo di confidenza onesto.

Perche' non il win rate
-----------------------
Con TP a 1,5R un win rate del 35% puo' essere un sistema redditizio o in
perdita: il win rate non dice nulla da solo. Qui e' solo informativo e non entra
mai in ``status``.

Perche' blocchi di giorni
-------------------------
I trade chiusi nello stesso giorno UTC condividono lo stesso mercato (stesso
crollo, stesso regime): non sono indipendenti. Un bootstrap sui trade singoli
darebbe intervalli troppo stretti. Si ricampionano quindi **giorni interi**
(``closed_at_ms // 86_400_000``) con reinserimento; una cella con pochi giorni
distinti resta ``insufficient`` anche se ha molti trade.

Regole esatte (contratto verificato dai test)
---------------------------------------------
* Modulo puro: nessuna I/O, rete, orologio, nessun import fuori dalla libreria
  standard. Nessuna soglia nel codice: ``min_trades``, ``min_days``,
  ``confidence``, ``n_boot`` sono argomenti obbligatori (li sceglie l'utente).
* Aritmetica in ``Decimal`` dentro un contesto LOCALE (60 cifre, half-even):
  il risultato non dipende dal contesto Decimal globale del chiamante.
  Risultati arrotondati a 4 decimali ``ROUND_HALF_EVEN``.
* Intervallo (metodo percentile): per ciascuna delle ``n_boot`` ripetizioni si
  estraggono ``n_days`` giorni con ``rng.randrange(n_days)``; la statistica e'
  ``somma(net_bp)/numero(trade)`` dei giorni estratti. Generatore
  ``random.Random(f"{seed}|{key!r}")`` (seme stringa: indipendente da
  ``PYTHONHASHSEED``). Con ``alpha = 1 - confidence`` e le medie ordinate ``m``:
  ``ci_low = m[floor(alpha/2 * n_boot)]``,
  ``ci_high = m[ceil((1 - alpha/2) * n_boot) - 1]``.
* ``status`` e' calcolato sui valori **riportati** (gia' arrotondati a 4
  decimali), cosi' quello che si legge e' coerente: ``positive`` se
  ``ci_low > 0``; ``negative`` se ``ci_high < 0``; altrimenti ``inconclusive``;
  ``insufficient`` (CI = ``None``) se ``n < min_trades`` o ``n_days < min_days``.
* Chiave di cella personalizzata: deve restituire una **tupla hashable** i cui
  elementi hanno un ``repr`` deterministico (niente oggetti col repr di default,
  che contiene l'indirizzo di memoria). Due chiavi sono la stessa cella solo se
  uguali **e** con lo stesso ``repr`` (cosi' ``(1,)`` e ``(True,)`` non si
  fondono a seconda di quale arriva per prima).
* Input ostili: tutto cio' che l'estrattore non produrrebbe mai (un
  ``TradeOutcome`` costruito a mano con NaN, float, ``closed_at_ms`` non intero)
  e' rifiutato con ``ValueError("invalid_outcome")`` invece di dare numeri
  falsi o eccezioni non tipizzate.

Cosa NON fa: non decide soglie, non apre o chiude trade, non legge il journal.
"""
from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal, localcontext,
)
from typing import Optional

from backend.v3.outcomes import LINK_STATUSES, TradeOutcome

_Q4 = Decimal("0.0001")
_MS_PER_DAY = 86_400_000
# Contesto locale: ampio abbastanza da rendere esatte medie e indici anche con
# valori molto grandi; indipendente da qualunque getcontext() del chiamante.
_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)


def _q4(d: Decimal) -> Decimal:
    """4 decimali half-even; mai uno zero negativo (``-0.0000`` nelle tabelle confonde)."""
    r = d.quantize(_Q4, rounding=ROUND_HALF_EVEN)
    return abs(r) if r == 0 else r


@dataclass(frozen=True)
class CellStats:
    key: tuple                      # valori della chiave di cella
    n: int                          # trade nella cella
    n_days: int                     # giorni UTC distinti (closed_at_ms // 86_400_000)
    mean_net_bp: Decimal
    median_net_bp: Decimal          # n pari: media dei due centrali
    mean_costs_bp: Decimal
    mean_r: Optional[Decimal]       # media di r_multiple dei trade che ce l'hanno; None se nessuno
    win_rate: Decimal               # SOLO informativa: non entra mai in `status`
    ci_low: Optional[Decimal]       # None se status == "insufficient"
    ci_high: Optional[Decimal]
    status: str                     # "insufficient" | "positive" | "negative" | "inconclusive"


def default_cell_key(o: TradeOutcome) -> tuple:
    """Manuale e Brain non si mischiano mai: ``is_manual`` fa parte della chiave."""
    return (o.symbol, o.side, o.decision_regime, o.is_manual)


# ---------------------------------------------------------------------------
# validazione
# ---------------------------------------------------------------------------

def _finite(v: object) -> bool:
    return isinstance(v, Decimal) and v.is_finite()


def _usable(o: object) -> bool:
    """Un TradeOutcome che cell_stats puo' leggere senza produrre numeri falsi.

    ``TradeOutcome`` e' un dataclass pubblico senza validazione: costruito a mano
    puo' contenere valori che l'estrattore non produrrebbe mai.
    """
    return (
        isinstance(o, TradeOutcome)
        and _finite(o.net_bp) and _finite(o.costs_bp) and _finite(o.realized_pnl)
        and (o.r_multiple is None or _finite(o.r_multiple))
        and type(o.closed_at_ms) is int and o.closed_at_ms > 0
        and isinstance(o.link_status, str)
    )


def _validate(outcomes, min_trades, min_days, confidence, n_boot, seed, key, link_statuses) -> None:
    """Solleva ValueError(codice) PRIMA di qualunque calcolo, nell'ordine del contratto."""
    if not isinstance(outcomes, Sequence) or not all(_usable(o) for o in outcomes):
        raise ValueError("invalid_outcome")
    if type(min_trades) is not int or min_trades < 1:
        raise ValueError("invalid_min_trades")
    if type(min_days) is not int or min_days < 2:
        raise ValueError("invalid_min_days")
    if (not isinstance(confidence, Decimal) or not confidence.is_finite()
            or not (Decimal(0) < confidence < Decimal(1))):
        raise ValueError("invalid_confidence")
    if type(n_boot) is not int or n_boot < 200:
        raise ValueError("invalid_n_boot")
    if type(seed) is not int:
        raise ValueError("invalid_seed")
    if not callable(key):
        raise ValueError("invalid_key")
    if not isinstance(link_statuses, frozenset) or not link_statuses <= frozenset(LINK_STATUSES):
        raise ValueError("invalid_link_statuses")


def _cell_id(key: Callable[[TradeOutcome], tuple], o: TradeOutcome) -> tuple[tuple, str, tuple]:
    """(chiave, repr, chiave di ordinamento) oppure ValueError("invalid_key").

    La chiave viene valutata UNA volta per trade e deve dare una tupla hashable.
    Qualunque eccezione della funzione utente (anche un ValueError suo) diventa
    ``invalid_key``: il codice del contratto non si confonde con un messaggio altrui.
    """
    try:
        k = key(o)
        if not isinstance(k, tuple):
            raise ValueError("invalid_key")
        hash(k)
        return k, repr(k), tuple(str(v) for v in k)
    except Exception:
        raise ValueError("invalid_key") from None


def _percentile_indexes(confidence: Decimal, n_boot: int) -> tuple[int, int]:
    """Indici (basso, alto) nell'elenco ordinato delle ``n_boot`` medie.

    ``lo = floor(alpha/2 * n_boot)``, ``hi = ceil((1 - alpha/2) * n_boot) - 1``,
    calcolati in Decimal (mai float). Per costruzione ``hi == n_boot - 1 - lo``
    e ``0 <= lo <= hi < n_boot``.
    """
    with localcontext(_CTX):
        alpha = Decimal(1) - confidence
        lo = int((alpha / 2 * n_boot).to_integral_value(rounding=ROUND_FLOOR))
        hi = int(((1 - alpha / 2) * n_boot).to_integral_value(rounding=ROUND_CEILING)) - 1
    return lo, hi


# ---------------------------------------------------------------------------
# calcolo
# ---------------------------------------------------------------------------

def _one_cell(k: tuple, rep: str, trades: list[TradeOutcome], *, min_trades: int, min_days: int,
              lo_idx: int, hi_idx: int, n_boot: int, seed: int) -> CellStats:
    nets = [t.net_bp for t in trades]
    rs = [t.r_multiple for t in trades if t.r_multiple is not None]
    n = len(trades)

    by_day: dict[int, list[Decimal]] = {}
    for t in trades:
        by_day.setdefault(t.closed_at_ms // _MS_PER_DAY, []).append(t.net_bp)
    day_keys = sorted(by_day)                       # giorni in ordine crescente
    n_days = len(day_keys)

    mean_net = _q4(sum(nets) / Decimal(n))
    mean_costs = _q4(sum(t.costs_bp for t in trades) / Decimal(n))
    mean_r = _q4(sum(rs) / Decimal(len(rs))) if rs else None
    win_rate = _q4(Decimal(sum(1 for t in trades if t.is_win)) / Decimal(n))
    ordered = sorted(nets)
    if n % 2 == 1:
        median = _q4(ordered[n // 2])
    else:
        median = _q4((ordered[n // 2 - 1] + ordered[n // 2]) / Decimal(2))

    if n < min_trades or n_days < min_days:
        return CellStats(key=k, n=n, n_days=n_days, mean_net_bp=mean_net, median_net_bp=median,
                         mean_costs_bp=mean_costs, mean_r=mean_r, win_rate=win_rate,
                         ci_low=None, ci_high=None, status="insufficient")

    # somma e numero di trade per giorno: la media di un campione di giorni e'
    # somma(somme)/somma(conteggi), identica alla media dei trade dei giorni estratti
    day_sum = [sum(by_day[d]) for d in day_keys]
    day_cnt = [len(by_day[d]) for d in day_keys]
    rng = random.Random(f"{seed}|{rep}")
    means: list[Decimal] = []
    for _ in range(n_boot):
        picks = [rng.randrange(n_days) for _ in range(n_days)]
        means.append(sum(day_sum[i] for i in picks) / Decimal(sum(day_cnt[i] for i in picks)))
    means.sort()
    ci_low, ci_high = _q4(means[lo_idx]), _q4(means[hi_idx])

    if ci_low > 0:
        status = "positive"
    elif ci_high < 0:
        status = "negative"
    else:
        status = "inconclusive"
    return CellStats(key=k, n=n, n_days=n_days, mean_net_bp=mean_net, median_net_bp=median,
                     mean_costs_bp=mean_costs, mean_r=mean_r, win_rate=win_rate,
                     ci_low=ci_low, ci_high=ci_high, status=status)


def cell_stats(
    outcomes: Sequence[TradeOutcome],
    *,
    min_trades: int,
    min_days: int,
    confidence: Decimal,
    n_boot: int,
    seed: int,
    key: Callable[[TradeOutcome], tuple] = default_cell_key,
    link_statuses: frozenset[str] = frozenset({"linked"}),
) -> tuple[CellStats, ...]:
    """Statistiche per cella (vedi la docstring del modulo per le regole esatte).

    Raises
    ------
    ValueError
        Con uno di questi codici come messaggio, prima di qualunque calcolo:
        ``invalid_outcome`` (non e' una sequenza di ``TradeOutcome`` utilizzabili),
        ``invalid_min_trades`` (int >= 1, no bool), ``invalid_min_days`` (int >= 2,
        no bool), ``invalid_confidence`` (Decimal finito, 0 < c < 1),
        ``invalid_n_boot`` (int >= 200, no bool), ``invalid_seed`` (int, no bool),
        ``invalid_key`` (non chiamabile; oppure, su un trade che passa il filtro,
        non restituisce una tupla hashable o solleva), ``invalid_link_statuses``
        (non un frozenset di valori in ``LINK_STATUSES``).
    """
    _validate(outcomes, min_trades, min_days, confidence, n_boot, seed, key, link_statuses)

    # filtro: gli altri trade non contano ne' in n ne' altrove
    groups: dict[tuple[tuple, str], list[TradeOutcome]] = {}
    order_keys: dict[tuple[tuple, str], tuple] = {}
    for o in outcomes:
        if o.link_status not in link_statuses:
            continue
        k, rep, sort_key = _cell_id(key, o)
        groups.setdefault((k, rep), []).append(o)
        order_keys[(k, rep)] = sort_key

    lo_idx, hi_idx = _percentile_indexes(confidence, n_boot)
    results: list[CellStats] = []
    try:
        with localcontext(_CTX):
            # ordine deterministico: tuple(str(x)) come da contratto; a parita' il repr
            for cid in sorted(groups, key=lambda g: (order_keys[g], g[1])):
                results.append(_one_cell(
                    cid[0], cid[1], groups[cid], min_trades=min_trades, min_days=min_days,
                    lo_idx=lo_idx, hi_idx=hi_idx, n_boot=n_boot, seed=seed))
    except ArithmeticError:
        # valori finiti ma oltre ogni scala ragionevole: non si inventano numeri
        raise ValueError("invalid_outcome") from None
    return tuple(results)


def format_cells(cells: Sequence[CellStats]) -> str:
    """Tabella di testo deterministica: una riga per cella, ``-`` dove il dato manca."""
    def f(v: object) -> str:
        return "-" if v is None else str(v)

    lines = ["key | n | n_days | mean_net_bp | median_net_bp | mean_costs_bp | mean_r | "
             "win_rate | ci_low | ci_high | status"]
    for c in cells:
        lines.append(" | ".join([
            repr(c.key), str(c.n), str(c.n_days), f(c.mean_net_bp), f(c.median_net_bp),
            f(c.mean_costs_bp), f(c.mean_r), f(c.win_rate), f(c.ci_low), f(c.ci_high), c.status,
        ]))
    return "\n".join(lines)
