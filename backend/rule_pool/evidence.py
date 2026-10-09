"""Statistiche di evidenza per regola. Funzioni pure (numpy), nessun I/O.

Tutto in bp AL NETTO dei costi. Il t-stat usato per decidere e' il minimo tra
quello sulle singole operazioni e quello sulle medie mensili (le operazioni dello
stesso mese sono correlate): una scelta prudente, non un test esatto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Optional

import numpy as np

import strategy_lab as sl


@dataclass(frozen=True)
class Gate:
    min_trades: int = 300
    min_months: int = 6
    alpha: float = 0.05           # errore complessivo, diviso per K (Bonferroni, unilaterale)
    futility_n: int = 100
    futility_t: float = -1.0
    demote_n: int = 50
    demote_t: float = 0.0
    max_live: int = 2
    alarm_z: float = 3.0          # allarme dei controlli: solo per effetti enormi (errori di sistema)


@dataclass(frozen=True)
class Summary:
    n: int
    mean: float
    sd: float
    t_iid: float
    t_month: float
    n_months: int
    ci_low: float
    ci_high: float

    @property
    def t_gate(self) -> float:
        """Minimo tra t sulle operazioni e t mensile (se definito)."""
        if not math.isfinite(self.t_iid):
            return float("nan")
        return min(self.t_iid, self.t_month) if math.isfinite(self.t_month) else self.t_iid


def net_bp(gross: float, side: int, hold_h: float, cost_bp: float) -> float:
    """Lordo - costi a giro - funding (1 bp/8h, solo sui long: come nel laboratorio)."""
    fund = sl.FUND_BP_8H * hold_h / 8.0 if side == 1 else 0.0
    return gross - cost_bp - fund


def month_key(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m")


def summarize(times, net) -> Optional[Summary]:
    net = np.asarray(net, dtype=float)
    n = len(net)
    if n == 0:
        return None
    times = np.asarray(times, dtype=np.int64)
    mean = float(net.mean())
    sd = float(net.std(ddof=1)) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    t_iid = mean / se if n > 1 and sd > 0 else float("nan")
    by: dict = {}
    for t, x in zip(times, net):
        by.setdefault(month_key(int(t)), []).append(x)
    m = np.array([np.mean(v) for v in by.values()])
    t_month = float("nan")
    if len(m) >= 3 and m.std(ddof=1) > 0:
        t_month = float(m.mean() / (m.std(ddof=1) / math.sqrt(len(m))))
    ci = 1.96 * se if math.isfinite(se) else float("nan")
    return Summary(n, mean, sd, t_iid, t_month, len(by), mean - ci, mean + ci)


def bonferroni_z(k: int, alpha: float = 0.05) -> float:
    """Soglia z unilaterale (si promuovono solo vantaggi positivi) corretta per K regole."""
    return NormalDist().inv_cdf(1.0 - alpha / max(1, k))


def required_n(sd_bp: float, edge_bp: float, z: float) -> int:
    """Operazioni necessarie perche' un vantaggio netto `edge_bp` raggiunga t = z."""
    return int(math.ceil((z * sd_bp / edge_bp) ** 2))


def halves_positive(times, net) -> bool:
    """La media netta e' positiva in entrambe le meta' cronologiche."""
    order = np.argsort(np.asarray(times), kind="stable")
    x = np.asarray(net, dtype=float)[order]
    h = len(x) // 2
    return bool(h > 0 and x[:h].mean() > 0 and x[h:].mean() > 0)


def check_gate(s: Optional[Summary], k: int, gate: Gate, halves_ok: bool,
               excess: Optional[float]) -> dict:
    """Soglia di idoneita'. `excess` = media netta della regola - media netta del
    controllo casuale sullo stesso periodo (None = controllo non disponibile: non passa)."""
    z = bonferroni_z(k, gate.alpha)
    if s is None:
        return {"pass": False, "z": z, "checks": {"dati": False}}
    checks = {
        "trade": s.n >= gate.min_trades,
        "mesi": s.n_months >= gate.min_months,
        "t": bool(math.isfinite(s.t_gate) and s.t_gate >= z),
        "meta": bool(halves_ok),
        "controllo": bool(excess is not None and math.isfinite(excess) and excess > 0),
    }
    return {"pass": all(checks.values()), "z": z, "checks": checks}


def futility(s: Optional[Summary], gate: Gate) -> bool:
    """Regola da ritirare in fretta: abbastanza trade e t chiaramente negativo."""
    return bool(s is not None and s.n >= gate.futility_n and math.isfinite(s.t_gate)
                and s.t_gate <= gate.futility_t)


def control_alarm(control_summaries, k: int, gate: Gate) -> bool:
    """Un controllo casuale con un vantaggio molto netto indica un errore nel sistema.
    Soglia piu' severa di quella di promozione (alarm_z, almeno quella corretta per K):
    un falso allarme blocca le decisioni, quindi deve essere raro."""
    z = max(bonferroni_z(k, gate.alpha), gate.alarm_z)
    for s in control_summaries:
        if s is not None and s.n >= gate.min_trades and math.isfinite(s.t_gate) and s.t_gate >= z:
            return True
    return False
