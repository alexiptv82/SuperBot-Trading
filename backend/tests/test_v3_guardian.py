"""Smart Profit Guardian (backend/v3/guardian.py): stati dai numeri, sessione 08:00 Europe/Rome, floor mobile."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from backend.v3.guardian import (
    GuardianPolicy, evaluate_guardian, guardian_policy_from_config, session_start_ms,
)

M = 60_000
H = 3_600_000
POL = GuardianPolicy()
FEE = D("0")          # commissioni a zero nei casi numerici: si verificano i livelli esatti
COST = D("0")


@dataclass
class Ev:
    kind: str
    occurred_at_ms: int
    payload: dict


def utc(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


S = utc(2026, 11, 23, 7)          # 08:00 Europe/Rome (ora solare, UTC+1)


def opened(pid, t, side=1, fill="100", qty="1", stop="99", sym="BTCUSDT"):
    return Ev("paper_open", t, {"position_id": pid, "symbol": sym, "side": side, "fill_price": fill,
                                "quantity": qty, "stop_price": stop})


def closed(pid, t, pnl, sym="BTCUSDT"):
    return Ev("paper_close", t, {"position_id": pid, "symbol": sym, "realized_pnl": pnl})


def prices(path):
    """path: lista di (da_ms, prezzo): il prezzo vale da quell'istante in poi."""
    def close_at(symbol, minute_open_ms):
        px = None
        for t, p in path:
            if t <= minute_open_ms:
                px = D(p)
        return px
    return close_at


def run(events, path, now, equity="2000", **kw):
    return evaluate_guardian(events=events, initial_equity=D(equity), close_at=prices(path), now_ms=now, policy=POL,
                             max_loss_fraction=D("0.04"), fee_bps=FEE, roundtrip_cost_bp=COST, **kw)


def test_session_starts_at_08_rome_with_daylight_saving():
    assert session_start_ms(utc(2026, 11, 23, 9), POL) == utc(2026, 11, 23, 7)        # ora solare: 07:00 UTC
    assert session_start_ms(utc(2026, 7, 1, 9), POL) == utc(2026, 7, 1, 6)            # ora legale: 06:00 UTC
    assert session_start_ms(utc(2026, 7, 1, 5, 59), POL) == utc(2026, 6, 30, 6)       # prima delle 08:00: ieri
    # 29/03/2026 si passa all'ora legale: la sessione 28/03 08:00 -> 29/03 08:00 dura 23 ore
    a, b = session_start_ms(utc(2026, 3, 28, 12), POL), session_start_ms(utc(2026, 3, 29, 12), POL)
    assert b - a == 23 * H
    # 25/10/2026 si torna all'ora solare: 25 ore
    a, b = session_start_ms(utc(2026, 10, 24, 12), POL), session_start_ms(utc(2026, 10, 25, 12), POL)
    assert b - a == 25 * H


def test_flat_session_is_normal_without_extra_cap():
    g = run([], [], S + 3 * H)
    assert g.state == "NORMAL" and g.risk_cap is None and g.equity == D("2000") and not g.armed
    assert g.r_unit == D("80.00")


def test_profit_arms_the_floor_and_reduces_the_new_risk():
    # long 10 BTC da 100 (stop 99): +200 = +10 % -> floor armato a 2000 + 0,75 * 200 = 2150
    ev = [opened("p1", S - 2 * H, qty="10", stop="99")]
    path = [(S - 3 * H, "100"), (S + 30 * M, "120")]
    g = run(ev, path, S + 2 * H)
    assert g.armed and g.peak_equity == D("2200") and g.floor == D("2150.00")
    # budget = 2200 - 2150 - rischio aperto (10 * 1) = 40 < R (88) -> PROTECTED, tetto = 0,5 * 40
    assert g.open_risk == D("10") and g.budget == D("40.00")
    assert g.state == "PROTECTED" and g.risk_cap == D("20.000") and g.allow_reentry is False
    assert g.min_confidence == D("0.7")


def test_brain_example_250_of_profit_after_closing():
    # +250 realizzati (12,5 %): floor 2187,5; budget 62,5 -> PROTECTED, nuova apertura al massimo 31,25
    ev = [opened("p1", S + M, qty="12.5", stop="99"), closed("p1", S + 60 * M, "250")]
    path = [(S - H, "100"), (S + 30 * M, "120")]
    g = run(ev, path, S + 2 * H)
    assert g.equity == D("2250") and g.realized_session == D("250") and g.unrealized == 0
    assert g.floor == D("2187.50") and g.budget == D("62.50") and g.state == "PROTECTED"
    assert g.risk_cap == D("31.250")
    # un profitto piu' grande lascia piu' margine: +600 -> budget 150 >= R -> SELECTIVE, tetto = min(R, 75)
    ev = [opened("p1", S + M, qty="30", stop="99"), closed("p1", S + 60 * M, "600")]
    g = run(ev, path, S + 2 * H)
    assert g.state == "SELECTIVE" and g.risk_cap == D("75.000") and g.allow_reentry


def test_giveback_below_the_floor_locks_until_the_next_session():
    ev = [opened("p1", S - 2 * H, qty="10", stop="90")]
    path = [(S - 3 * H, "100"), (S + 30 * M, "120"), (S + 60 * M, "113"), (S + 90 * M, "125")]
    # picco 2200 (floor 2150), poi 2130 < floor, poi risale a 2250: resta LOCKED fino al cambio di sessione
    g = run(ev, path, S + 3 * H)
    assert g.state == "LOCKED" and "below_floor" in g.reasons and g.risk_cap == 0
    assert g.peak_equity == D("2250") and g.giveback == 0
    # nuova sessione: la base e' il valore di mercato del cambio (2250), nessun blocco ereditato
    g2 = run(ev, path, S + 24 * H + H)
    assert g2.session_start_equity == D("2250") and g2.state == "NORMAL" and g2.realized_session == 0


def test_session_loss_locks_and_open_risk_alone_does_not_latch():
    ev = [opened("p1", S + M, qty="10", stop="80")]
    path = [(S - H, "100"), (S + 20 * M, "83"), (S + 40 * M, "100")]
    g = run(ev, path, S + 2 * H)                                   # -170 = -8,5 %: LOCKED anche dopo il recupero
    assert g.state == "LOCKED" and g.reasons == ("session_loss",)
    # armato e con molto rischio aperto: LOCKED per budget, ma si sblocca quando la posizione chiude in profitto
    # picco 2400 -> floor 2300; rischio aperto 10 + 100: budget -10 -> LOCKED (non bloccato fino al cambio)
    ev = [opened("p1", S - 2 * H, qty="10", stop="99"), opened("p2", S + M, qty="10", stop="90", sym="ETHUSDT")]
    path2 = [(S - 3 * H, "100"), (S + 30 * M, "120")]
    g = run(ev, path2, S + 2 * H)
    assert g.state == "LOCKED" and g.reasons == ("floor_budget",) and g.budget == D("-10.00")
    # p2 chiude al suo valore di mercato: l'equity non cambia, ma il suo rischio a stop si libera -> budget 90
    ev.append(closed("p2", S + 2 * H + M, "200", sym="ETHUSDT"))
    g = run(ev, path2, S + 3 * H)
    assert g.state == "PROTECTED" and g.budget == D("90.00")


def test_missing_price_fails_closed():
    ev = [opened("p1", S + M, sym="SOLUSDT")]
    g = run(ev, [], S + H)
    assert g.state == "LOCKED" and g.reasons == ("data_fault",) and g.risk_cap == 0


def test_position_crossing_the_session_change_is_not_double_counted():
    ev = [opened("p1", S - 3 * H, qty="10", stop="90"), closed("p1", S + 60 * M, "150")]
    path = [(S - 4 * H, "100"), (S - H, "110"), (S + 30 * M, "115")]
    g = run(ev, path, S + 2 * H)
    # base di sessione = 2000 + 10 * (110 - 100) = 2100; la chiusura a +150 vale +50 nella sessione
    assert g.session_start_equity == D("2100") and g.equity == D("2150")
    assert g.realized_session == D("150") and g.equity - g.session_start_equity == D("50")


def test_global_drawdown_halves_then_locks():
    ev = [opened("p1", S - 30 * H, qty="1", stop="99"), closed("p1", S - 29 * H, "-240")]
    g = run(ev, [], S + H)                                         # -12 %: R dimezzato
    assert g.state == "NORMAL" and g.reasons == ("drawdown_half",) and g.risk_cap == D("1760") * D("0.04") / 2
    ev = [opened("p1", S - 30 * H, qty="1", stop="99"), closed("p1", S - 29 * H, "-420")]
    g = run(ev, [], S + H)                                         # -21 %: LOCKED
    assert g.state == "LOCKED" and "global_drawdown" in g.reasons


def test_fees_reduce_the_mark_to_market():
    ev = [opened("p1", S + M, qty="10", stop="90")]
    g = evaluate_guardian(events=ev, initial_equity=D("1000"), close_at=prices([(S - H, "100")]), now_ms=S + H,
                          policy=POL, max_loss_fraction=D("0.04"), fee_bps=D("6"), roundtrip_cost_bp=D("16"))
    assert g.equity == D("1000") - (D("200") * 10 * D("0.0006"))
    assert g.open_risk == (D("10") + D("100") * D("0.0016")) * 10


def test_deterministic_and_journal_payload():
    ev = [opened("p1", S - 2 * H, qty="10", stop="99")]
    path = [(S - 3 * H, "100"), (S + 30 * M, "120")]
    a, b = run(ev, path, S + 2 * H), run(ev, path, S + 2 * H)
    assert a == b
    p = a.to_payload()
    assert p["state"] == "PROTECTED" and p["floor"] == "2150.00" and p["risk_cap"] == "20.000"


def test_policy_validation_and_config():
    raw = {"activation_fraction": "0.08", "keep_fraction": "0.75", "session_loss_fraction": "0.08",
           "spend_fraction": "0.5", "protected_below_r": "1", "locked_below_r": "0.25",
           "protected_min_confidence": "0.7", "global_drawdown_half": "0.10", "global_drawdown_lock": "0.20",
           "session_hour": 8, "session_tz": "Europe/Rome"}
    assert guardian_policy_from_config(raw) == POL
    for bad in (dict(raw, keep_fraction="1"), dict(raw, session_tz="Mars/Base"), dict(raw, session_hour=24),
                dict(raw, locked_below_r="2"), dict(raw, activation_fraction=0.08), {**raw, "extra": "1"}):
        with pytest.raises(ValueError, match="invalid_guardian_policy"):
            guardian_policy_from_config(bad)
