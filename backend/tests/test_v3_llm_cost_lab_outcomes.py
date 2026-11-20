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
    assert g["no_trade"]["avoided_unfavorable"] == 1 and g["no_trade"]["missed_favorable"] == 0
    assert g["ev_net_r"] is None
    assert l["ev_net_r"] == d["ev_net_r"] == D("-1.16") and l["losses"] == 1
    assert sc["agreement_is_correctness"] is False and sc["basis"] == "market_outcomes"
    assert sc["sample_size_warning"] is True


def test_a_no_trade_that_skips_a_winner_is_a_missed_opportunity():
    win = [(D("102.5"), D("99.9"), D("102.2"))] + FLAT[:9]
    records = [_rec("deepseek-flash"), _rec("gemini", action="NO_TRADE")]
    sc = score(records, _label(records, _candles(win)), reference_model="deepseek-flash")
    nt = sc["arms"]["gemini"]["no_trade"]
    assert nt["missed_favorable"] == 1 and nt["avoided_unfavorable"] == 0


def test_score_refuses_misaligned_labels():
    records = [_rec("gemini"), _rec("llama")]
    labs = _label(records, _candles(FLAT))
    with pytest.raises(ValueError, match="labels_mismatch"):
        score(records, list(reversed(labs)), reference_model="deepseek-flash")
    with pytest.raises(ValueError, match="labels_mismatch"):
        score(records, labs[:1], reference_model="deepseek-flash")


# ------------------------------------------------------------------------------------------------ limiti e incertezza

def test_abstaining_together_with_the_reference_is_not_counted_as_avoiding_anything():
    records = [_rec("deepseek-flash", action="NO_TRADE"), _rec("gemini", action="NO_TRADE")]
    nt = score(records, _label(records, _candles(FLAT)), reference_model="deepseek-flash")["arms"]["gemini"]["no_trade"]
    assert nt == {"total": 1, "avoided_unfavorable": 0, "missed_favorable": 0, "reference_flat": 0,
                  "reference_also_abstained": 1, "unjudged": 0}


def test_a_no_trade_without_a_usable_reference_is_unjudged():
    c = _candles(FLAT)
    del c["BTCUSDT"][4]
    records = [_rec("deepseek-flash"), _rec("gemini", action="NO_TRADE"), _rec("llama", action="NO_TRADE", sample="s9")]
    arms = score(records, _label(records, c), reference_model="deepseek-flash")["arms"]
    assert arms["gemini"]["no_trade"]["unjudged"] == 1 and arms["llama"]["no_trade"]["unjudged"] == 1


DAY = 86_400_000


def _multi(paths_by_sample, models, days=None):
    """Un campione per percorso; ogni modello apre LONG con stop 99 su ogni campione (giorno ``days[i]``)."""
    records, candles = [], {}
    for i, path in enumerate(paths_by_sample):
        sym = f"S{i}USDT"
        start = T0 + (days[i] if days else 0) * DAY + i * M          # istanti diversi anche nello stesso giorno
        candles.update(_candles(path, start=start, symbol=sym))
        for m in models:
            r = _rec(m, sample=f"s{i}", decision=start)
            r["symbol"] = sym
            records.append(r)
    return records, candles


WIN = [(D("102.5"), D("99.9"), D("102.2"))] + FLAT[:9]
LOSS = [(D("100.2"), D("98.9"), D("99"))] + FLAT[:9]


def test_uncertainty_days_and_sample_flag_are_reported():
    records, candles = _multi([WIN, LOSS, WIN, LOSS], ["gemini"], days=[0, 0, 1, 3])
    a = score(records, _label(records, candles), reference_model="deepseek-flash")["arms"]["gemini"]
    assert a["labelled"] == 4 and a["ev_net_r"] == D("0.34")             # (1,84 - 1,16) / 2
    # scarti +-1,5: varianza campionaria 9/3 = 3, sd 1,7321, se 0,8660, 95 % = 0,34 +- 1,96 * 0,8660
    assert (a["sd_net_r"], a["se"]) == (D("1.7321"), D("0.8660"))
    assert a["ci95_approx"] == [D("-1.3574"), D("2.0374")]
    assert a["distinct_days"] == 3 and a["sample"] == "insufficient" and a["label_kind"] == "simulated_counterfactual"


def test_paired_difference_uses_only_samples_where_both_opened():
    records, candles = _multi([WIN, LOSS], ["deepseek-flash", "gemini"])
    records[3] = dict(records[3], action="NO_TRADE", direction=None)      # gemini si astiene sul secondo
    records[3].pop("proposal")
    sc = score(records, _label(records, candles), reference_model="deepseek-flash")
    assert sc["paired_vs_reference"]["gemini"]["pairs"] == 1 and sc["paired_vs_reference"]["gemini"]["mean_diff_r"] == 0
    assert sc["arms"]["gemini"]["no_trade"]["avoided_unfavorable"] == 1


def test_observed_paper_trades_stay_separate_from_simulations():
    records, candles = _multi([WIN, LOSS], ["deepseek-flash", "gemini"])
    sc = score(records, _label(records, candles), reference_model="deepseek-flash",
               observed={"s0": D("1.2"), "s1": D("-1.0")})
    obs = sc["reference_observed"]
    assert obs["label_kind"] == "observed_paper_trade" and obs["comparable_with_simulated_arms"] is False
    assert obs["n"] == 2 and obs["ev_net_r"] == D("0.1")
    assert obs["simulated_minus_observed"]["mean_r"] == D("0.24")        # ((1,84-1,2) + (-1,16+1,0)) / 2
    assert sc["arms"]["deepseek-flash"]["ev_net_r"] == D("0.34")         # le simulazioni non cambiano


def test_every_report_declares_its_limits():
    records = [_rec("gemini")]
    sc = score(records, _label(records, _candles(FLAT)), reference_model="deepseek-flash")
    assert {"simulated_labels_are_counterfactual", "no_trade_judged_relative_to_reference",
            "bracket_exit_not_production_exit_policy", "samples_not_independent"} <= set(sc["limits"])
    assert sc["reference_observed"] is None
