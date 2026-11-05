"""L4 — verifica indipendente di Claude sul tabellone (``build_scoreboard``).

Oracolo scritto dal contratto del prompt, senza riusare il codice di ``view.py`` ne' gli helper dei test
di ChatGPT: regola dell'etichetta riscritta (regex + prefisso), selezione, raggruppamento, media con
``Fraction`` arrotondata half-even a 4 decimali, ordine e taglio. Solo intervallo e stato arrivano da
``cell_stats`` (gia' collaudato da P4 con il suo oracolo) chiamato su una selezione fatta qui.
Scenari casuali ripetibili (seme fisso), nessun dato di mercato reale.
"""
from __future__ import annotations

import json
import random
import re
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction

import pytest

from backend.v3.brain_view.params import ViewParams
from backend.v3.brain_view.view import build_scoreboard
from backend.v3.learning.expectancy import cell_stats
from backend.v3.outcomes import LINK_STATUSES, REGIMES, TradeOutcome

D = Decimal
DAY = 86_400_000
T0 = 1_700_000_000_000
TOKEN = re.compile(r"[A-Z][A-Z0-9_]{0,31}")

STRATS = [("S01", "library"), ("S02", "library"), ("S05", "library"), ("S07", "library"),
          ("AI_TREND_X", "ai_proposed"), ("AI_FADE", "ai_proposed")]
BAD_LABELS = [("s07", "library"), ("S07", "ai_proposed"), ("AI_", "ai_proposed"), ("AI_X", "library"),
              ("S07", "Library"), ("S 07", "library"), ("", ""), ("S07", ""), ("", "library"),
              ("X" * 33, "library")]


def _valid_label(sid, origin) -> bool:
    """Riscritta dal contratto L1 (senza elenco ammesso)."""
    if origin not in ("library", "ai_proposed") or not isinstance(sid, str) or not TOKEN.fullmatch(sid):
        return False
    if origin == "ai_proposed":
        return sid.startswith("AI_") and len(sid) > 3
    return not sid.startswith("AI_")


def _outcome(i, *, sid, origin, side, regime, link, manual, day, net, symbol):
    costs = D("12")
    return TradeOutcome(
        schema_version=2, position_id=f"p{i}", portfolio_id="brain", run_id="r", symbol=symbol,
        side=side, originating_ai="deepseek", leverage=2,
        opened_at_ms=T0 + day * DAY, closed_at_ms=T0 + day * DAY + 60_000, hold_ms=60_000,
        entry_price=D("100"), exit_price=D("101"), quantity=D("1"), notional_entry=D("100"),
        margin_used=D("50"), gross_pnl=D("1"), fees=D("0.12"), realized_pnl=net / D(100),
        gross_bp=net + costs, costs_bp=costs, net_bp=net, stop_distance_bp=D("200"),
        r_multiple=D("0.5"), exit_reason="manual" if manual else "brain_close",
        loss_exceeds_margin=False, decision_event_id=f"d{i}", link_status=link,
        decision_regime=regime, strategy_id=sid, strategy_origin=origin,
    )


def _scenario(seed):
    rnd = random.Random(seed)
    regimes = ["TRENDING", "TREND_UP", "RANGE", "SHOCK"]
    links = sorted(LINK_STATUSES)
    rows = []
    for i in range(rnd.randint(30, 140)):
        sid, origin = rnd.choice(STRATS) if rnd.random() < 0.8 else rnd.choice(BAD_LABELS)
        rows.append(_outcome(
            i, sid=sid, origin=origin, side=rnd.choice((1, -1)), regime=rnd.choice(regimes),
            link="linked" if rnd.random() < 0.8 else rnd.choice(links), manual=rnd.random() < 0.1,
            day=rnd.randint(0, 9), net=D(rnd.randint(-6000, 6000)) / D(100),
            symbol=rnd.choice(("BTCUSDT", "ETHUSDT", "SOLUSDT"))))
    return rows, rnd


def _expected(rows, regime, params):
    linked = [o for o in rows if o.link_status == "linked" and o.exit_reason != "manual"]
    labelled = [o for o in linked if _valid_label(o.strategy_id, o.strategy_origin)]
    chosen = [o for o in labelled if o.decision_regime == regime]
    groups = {}
    for o in chosen:
        groups.setdefault((o.strategy_id, o.strategy_origin, o.side), []).append(o)
    stats = {}
    if chosen:
        for c in cell_stats(chosen, min_trades=params.min_trades, min_days=params.min_days,
                            confidence=params.confidence, n_boot=params.n_boot, seed=params.seed,
                            key=lambda o: (o.strategy_id, o.strategy_origin, o.side)):
            stats[c.key] = c
    cells = []
    for key, g in groups.items():
        total = sum(Fraction(str(o.net_bp)) for o in g)
        mean = (D(total.numerator) / D(total.denominator) / D(len(g))).quantize(
            D("0.0001"), rounding=ROUND_HALF_EVEN)
        s = stats[key]
        assert (s.n, s.n_days) == (len(g), len({o.closed_at_ms // DAY for o in g}))
        assert s.mean_net_bp == mean            # P4 e oracolo a mano concordano sulla media
        cells.append({"strategy_id": key[0], "origin": key[1], "side": key[2], "n": len(g),
                      "n_days": s.n_days, "mean_net_bp": str(mean),
                      "ci_low": None if s.ci_low is None else str(s.ci_low),
                      "ci_high": None if s.ci_high is None else str(s.ci_high), "status": s.status})
    rank = {"positive": 0, "negative": 1, "inconclusive": 2, "insufficient": 3}
    cells.sort(key=lambda c: (rank[c["status"]], -D(c["mean_net_bp"]), c["strategy_id"], -c["side"]))
    return {"regime": regime, "n_closed_linked": len(linked), "n_labelled": len(labelled),
            "n_cells": len(cells), "truncated": len(cells) > params.max_cells,
            "cells": cells[:params.max_cells]}


@pytest.mark.parametrize("seed", range(40))
def test_scoreboard_matches_independent_oracle(seed):
    rows, rnd = _scenario(seed)
    params = ViewParams(3, 2, D("0.90"), 200, 20261105, rnd.randint(1, 8))
    before = list(rows)
    for regime in ("TRENDING", "TREND_UP", "RANGE", "SHOCK", "UNKNOWN"):
        got = build_scoreboard(rows, regime=regime, params=params)
        assert got == _expected(rows, regime, params)
        assert json.loads(json.dumps(got)) == got           # serializzabile, nessun float nascosto
    assert rows == before                                    # input invariato


def test_oracle_scenarios_really_exercise_every_branch():
    """Guardia: gli scenari casuali contengono davvero tutti gli stati, il taglio e le esclusioni."""
    seen_status, truncated, excluded = set(), False, False
    for seed in range(40):
        rows, rnd = _scenario(seed)
        params = ViewParams(3, 2, D("0.90"), 200, 20261105, 2)
        for regime in ("TRENDING", "TREND_UP", "RANGE", "SHOCK"):
            out = build_scoreboard(rows, regime=regime, params=params)
            seen_status |= {c["status"] for c in out["cells"]}
            truncated |= out["truncated"]
            excluded |= out["n_labelled"] < out["n_closed_linked"]
    assert {"insufficient", "inconclusive"} <= seen_status
    assert truncated and excluded
    # le cartelle di prova non hanno regimi fuori dal vocabolario
    assert {"TRENDING", "TREND_UP", "RANGE", "SHOCK", "UNKNOWN"} <= set(REGIMES)


def test_tie_order_is_id_ascending_then_long_before_short():
    # stesso stato (insufficient) e stessa media: decide l'id crescente, poi +1 prima di -1
    rows = [_outcome(i, sid=sid, origin="library", side=side, regime="TRENDING", link="linked",
                     manual=False, day=i, net=D("5"), symbol="BTCUSDT")
            for i, (sid, side) in enumerate([("S02", -1), ("S02", 1), ("S01", -1)])]
    out = build_scoreboard(rows, regime="TRENDING", params=ViewParams(3, 2, D("0.90"), 200, 1, 12))
    assert [(c["strategy_id"], c["side"]) for c in out["cells"]] == [("S01", -1), ("S02", 1), ("S02", -1)]
    assert {c["status"] for c in out["cells"]} == {"insufficient"}
