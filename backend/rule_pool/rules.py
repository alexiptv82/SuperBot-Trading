"""Regole del pool: una regola e' un dato con parametri CONGELATI.

Cambiare un parametro (uscite, simboli, costi, codice del segnale) cambia
`params_hash`. Il giornale rifiuta di registrare lo stesso id/versione con un
hash diverso: per cambiare una regola si alza `version` e i contatori ripartono.

Limite noto: l'hash copre il codice della funzione-segnale (e delle funzioni che
incapsula), non gli indicatori condivisi (ema, adx, ...): quelli sono coperti
dai test di strategy_lab.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import math
from dataclasses import dataclass
from typing import Optional

import strategy_lab as sl

KINDS = ("promotable", "control")

# Elenco PROVVISORIO delle coppie piu' liquide: da riconfermare sulla liquidita'
# reale di BitGet prima della fase 2 (e' parte della regola: cambiarlo = nuova versione).
TOP10 = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "BNB/USDT:USDT",
         "DOGE/USDT:USDT", "ADA/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT", "LTC/USDT:USDT")
MAJORS = ("BTC/USDT:USDT", "ETH/USDT:USDT")


def _src(fn, seen: Optional[set] = None) -> str:
    seen = seen if seen is not None else set()
    if fn in seen:
        return ""
    seen.add(fn)
    try:
        text = inspect.getsource(fn)
    except (OSError, TypeError):
        text = getattr(fn, "__qualname__", repr(fn))
    for cell in getattr(fn, "__closure__", None) or ():
        try:
            inner = cell.cell_contents
        except ValueError:
            continue
        if callable(inner):
            text += _src(inner, seen)
    return text


def _clean(v):
    return "nan" if isinstance(v, float) and math.isnan(v) else v


@dataclass(frozen=True)
class Rule:
    rule_id: str
    strategy: str                      # nome in strategy_lab.STRATEGIES
    symbols: tuple
    kind: str = "promotable"           # 'promotable' | 'control'
    cost_profile: str = "A"            # chiave di strategy_lab.COSTS
    version: int = 1
    base_rule: Optional[str] = None    # solo per i controlli

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"kind sconosciuto: {self.kind}")
        if self.cost_profile not in sl.COSTS:
            raise ValueError(f"profilo costi sconosciuto: {self.cost_profile}")
        if not self.symbols:
            raise ValueError("serve almeno un simbolo")
        if self.kind == "control" and not self.base_rule:
            raise ValueError("un controllo deve indicare la regola di base")
        self.strat()  # KeyError se la strategia non esiste

    def strat(self) -> "sl.Strategy":
        for s in sl.STRATEGIES:
            if s.name == self.strategy:
                return s
        raise KeyError(f"strategia sconosciuta: {self.strategy}")

    @property
    def cost_bp(self) -> float:
        return sl.COSTS[self.cost_profile]

    @property
    def tf_ms(self) -> int:
        return {"15m": sl.M15, "1h": sl.H1, "4h": sl.H4}[self.strat().tf]

    def params(self) -> dict:
        s = self.strat()
        return {
            "strategy": s.name, "tf": s.tf, "symbols": list(self.symbols), "kind": self.kind,
            "cost_profile": self.cost_profile, "cost_bp": self.cost_bp, "fund_bp_8h": sl.FUND_BP_8H,
            "tp_through": sl.TP_THROUGH, "base_rule": self.base_rule,
            "exit": {k: _clean(v) for k, v in dataclasses.asdict(s.cfg).items()},
            "signal_source": _src(s.build),
        }

    def params_hash(self) -> str:
        blob = json.dumps(self.params(), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def initial_rules() -> list:
    """Regole iniziali: quelle del laboratorio con i risultati meno peggiori, congelate,
    piu' un controllo con ingressi casuali per ciascuna."""
    base = [
        Rule("R_S1_majors", "S1_donchian_4h", MAJORS),
        Rule("R_S2_majors", "S2_donchian_1h", MAJORS),
        Rule("R_S2_top10", "S2_donchian_1h", TOP10),
    ]
    ctl = [Rule("CTL_" + r.rule_id[2:], r.strategy, r.symbols, kind="control", base_rule=r.rule_id)
           for r in base]
    return base + ctl


def promotable_count(rules) -> int:
    """K: numero di regole promuovibili, base della correzione per test multipli."""
    return sum(1 for r in rules if r.kind == "promotable")
