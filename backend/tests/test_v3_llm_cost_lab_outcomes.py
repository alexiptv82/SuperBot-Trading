"""Etichette degli esiti del laboratorio LLM: utilita' misurata sul mercato, stesse regole per ogni modello.

Candele sintetiche costruite a mano (nessuna rete). Si verifica: ingresso a mercato e non quello dichiarato, stop
dal lato sbagliato non eseguibile, obiettivo in R, costi, nessuna candela precedente o contenente la decisione,
candela mancante => incompleto, NO_TRADE giudicate contro il riferimento, accordo mai usato come criterio.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.v3.learning.opportunity import Candle
from backend.v3.llm_cost_lab.outcomes import label_records, score

D = Decimal
M = 60_000
T0 = 1_800_000_000_000 - (1_800_000_000_000 % M)           # decisione allineata al minuto
ENTRY = D("100")


def _candles(path, start=T0, symbol="BTCUSDT"):
    """path: (high, low, close) per minuto a partire da ``start`` (la prima candela apre a ``start``)."""
    out, prev = [], ENTRY
    for i, (h, l, c) in enumerate(path):
        out.append(Candle(start + i * M, min(max(prev, l), h), h, l, c))   # apertura dentro il range
        prev = c
    return {symbol: out}


FLAT = [(D("100.1"), D("99.9"), D("100"))] * 10


def _rec(model, action="LONG", stop="99", sample="s1", entry="123", valid=True, decision=T0):
    r = {"sample_id": sample, "model_id": model, "symbol": "BTCUSDT", "action": action, "valid": valid,
         "direction": action if action != "NO_TRADE" else None, "decision_ms": decision}
    if action != "NO_TRADE":
        r["proposal"] = {"entry_price": entry, "stop_price": stop, "leverage": 20}
    return r


def _label(records, candles, **kw):
    args = dict(entry_of=lambda sid: ENTRY, candle_ms=M, horizon_ms=10 * M, target_r=D("2"), cost_bp=D("16"),
                ambiguous_policy="stop_first")
    args.update(kw)
    return label_records(records, candles, **args)


def test_target_reached_is_two_r_minus_costs_and_the_declared_entry_is_ignored():
    path = [(D("100.5"), D("99.9"), D("100.4")), (D("102.1"), D("100.3"), D("102"))] + FLAT[:8]
    lab, = _label([_rec("gemini", stop="99", entry="123")], _candles(path))   # entry 123 dichiarato: ignorato
    assert lab["status"] == "labelled" and lab["barrier"] == "target"
    # 2R = +200 bp lordi, costi 16 bp, R = 100 bp => 1,84 R
    assert lab["net_bp"] == D("184") and lab["net_r"] == D("1.84")


def test_stop_hit_is_minus_one_r_minus_costs():
    path = [(D("100.2"), D("98.9"), D("99"))] + FLAT[:9]
    lab, = _label([_rec("llama", stop="99")], _candles(path))
    assert lab["barrier"] == "stop" and lab["net_r"] == D("-1.16")


def test_short_side_and_timeout():
    lab, = _label([_rec("gemini", action="SHORT", stop="101")], _candles(FLAT))
    assert lab["barrier"] == "timeout" and lab["net_r"] == D("-0.16")


def test_a_stop_on_the_wrong_side_of_the_market_entry_is_not_executable():
    labs = _label([_rec("gemini", stop="100.5"), _rec("gemini", action="SHORT", stop="99", sample="s2"),
                   _rec("gemini", stop="100", sample="s3")], _candles(FLAT))
    assert [x["status"] for x in labs] == ["not_executable"] * 3


def test_the_candle_containing_the_decision_and_earlier_ones_are_never_used():
    # decisione 30 s dentro la prima candela: quella candela (con un crollo) non conta
    crash_first = [(D("100.1"), D("90"), D("100"))] + [(D("102.5"), D("99.9"), D("102.2"))] + FLAT[:9]
    lab, = _label([_rec("gemini", decision=T0 + 30_000)], _candles(crash_first))
    assert lab["barrier"] == "target"


def test_a_missing_candle_makes_the_label_incomplete():
    c = _candles(FLAT)
    del c["BTCUSDT"][4]
    lab, = _label([_rec("gemini")], c)
    assert lab["status"] == "incomplete" and lab["net_r"] is None


def test_no_trade_and_invalid_records_are_not_simulated():
    labs = _label([_rec("gemini", action="NO_TRADE"), _rec("llama", valid=False)], _candles(FLAT))
    assert [x["status"] for x in labs] == ["no_trade", "invalid"]


def test_target_r_must_be_fixed_and_positive():
    for bad in (D("0"), D("-1"), 2, D("NaN")):
        with pytest.raises(ValueError, match="invalid_target_r"):
            _label([_rec("gemini")], _candles(FLAT), target_r=bad)


def test_score_measures_market_outcome_not_agreement():
    stop_path = [(D("100.2"), D("98.9"), D("99"))] + FLAT[:9]
    records = [
        _rec("deepseek-flash", sample="s1"),                 # riferimento: perde
        _rec("gemini", action="NO_TRADE", sample="s1"),      # evita un ingresso sfavorevole
        _rec("llama", sample="s1"),                          # concorda con DeepSeek: perde lo stesso
    ]
    labs = _label(records, _candles(stop_path))
    sc = score(records, labs, reference_model="deepseek-flash")
    g, l, d = sc["arms"]["gemini"], sc["arms"]["llama"], sc["arms"]["deepseek-flash"]
    assert g["avoided_unfavorable"] == 1 and g["missed_favorable"] == 0 and g["ev_net_r"] is None
    assert l["ev_net_r"] == d["ev_net_r"] == D("-1.16") and l["losses"] == 1
    assert sc["agreement_is_correctness"] is False and sc["basis"] == "market_outcomes"
    assert sc["sample_size_warning"] is True


def test_a_no_trade_that_skips_a_winner_is_a_missed_opportunity():
    win = [(D("102.5"), D("99.9"), D("102.2"))] + FLAT[:9]
    records = [_rec("deepseek-flash"), _rec("gemini", action="NO_TRADE")]
    sc = score(records, _label(records, _candles(win)), reference_model="deepseek-flash")
    assert sc["arms"]["gemini"]["missed_favorable"] == 1 and sc["arms"]["gemini"]["avoided_unfavorable"] == 0


def test_score_refuses_misaligned_labels():
    records = [_rec("gemini"), _rec("llama")]
    labs = _label(records, _candles(FLAT))
    with pytest.raises(ValueError, match="labels_mismatch"):
        score(records, list(reversed(labs)), reference_model="deepseek-flash")
    with pytest.raises(ValueError, match="labels_mismatch"):
        score(records, labs[:1], reference_model="deepseek-flash")
