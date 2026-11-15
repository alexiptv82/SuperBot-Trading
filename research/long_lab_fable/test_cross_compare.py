"""Prove del confronto Toro-Brain su dati sintetici: viste corrette, journal aperto in sola lettura, livelli separati."""
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cross_compare as CC  # noqa: E402

RUN = "brain-test"


def _journal(path, events):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id TEXT, run_id TEXT, kind TEXT,"
                " occurred_at_ms INTEGER, payload_json TEXT, event_id TEXT)")
    for idx, (kind, ts, p) in enumerate(events):
        con.execute("INSERT INTO v3_events(portfolio_id, run_id, kind, occurred_at_ms, payload_json, event_id) "
                    "VALUES ('brain', ?, ?, ?, ?, ?)",
                    (RUN, kind, ts, json.dumps(p), f"synthetic-{idx}"))
    con.commit()
    con.close()


def _toro(path, rows):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "osservazioni.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_each_brain_view_is_classified_inside_the_24h_window(tmp_path):
    t = CC._day_close_ms("2026-12-01")
    ev = [("brain_decision", t + 60_000, {"symbol": "ETHUSDT", "kind": "OPEN", "status": "APPROVED"}),
          ("paper_open", t + 61_000, {"position_id": "p1", "symbol": "ETHUSDT", "side": 1}),
          ("paper_close", t + 9_000_000, {"position_id": "p1", "realized_pnl": "12.5", "reason": "take_profit"}),
          ("brain_decision", t + 60_000, {"symbol": "SOLUSDT", "kind": "NO_TRADE", "status": "RISK_REJECTED"}),
          ("brain_decision", t + 60_000, {"symbol": "XRPUSDT", "kind": "NO_TRADE", "status": "DRAFT"}),
          ("paper_open", t - 1, {"position_id": "p2", "symbol": "ADAUSDT", "side": 1}),         # prima della finestra
          ("paper_open", t + CC.WINDOW_MS, {"position_id": "p3", "symbol": "LINKUSDT", "side": -1})]  # subito dopo
    _journal(tmp_path / "j.db", ev)
    (tmp_path / "prop.jsonl").write_text(json.dumps({"ts_ms": t + 60_000, "symbol": "SOLUSDT", "kind": "OPEN", "side": 1}) + "\n")
    rows = [{"data_segnale": "2026-12-01", "simbolo": s, "esito": "eseguito_virtuale", "stato": "chiusa", "R": 1.0}
            for s in ("ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT")]
    _toro(tmp_path / "toro", rows)
    res = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN, tmp_path / "prop.jsonl")
    views = {f["simbolo"]: f["vista_brain"] for f in res["fatti"]}
    assert views == {"ETHUSDT": "LONG_aperto", "SOLUSDT": "LONG_proposto_respinto", "XRPUSDT": "NO_TRADE",
                     "ADAUSDT": "non_valutato", "LINKUSDT": "non_valutato"}
    eth = next(f for f in res["fatti"] if f["simbolo"] == "ETHUSDT")
    assert eth["esiti_brain"] == [{"lato": 1, "pnl_usdt": 12.5, "uscita": "take_profit"}]
    noprop = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN)
    assert {f["simbolo"]: f["vista_brain"] for f in noprop["fatti"]}["SOLUSDT"] == "RESPINTO_LATO_IGNOTO"


def test_journal_is_opened_read_only(tmp_path):
    _journal(tmp_path / "j.db", [])
    _toro(tmp_path / "toro", [])
    os.chmod(tmp_path / "j.db", 0o444)
    before = (tmp_path / "j.db").read_bytes()
    CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN)
    assert (tmp_path / "j.db").read_bytes() == before


def test_hypotheses_need_30_cases_and_rules_need_a_second_sample(tmp_path):
    rng = np.random.default_rng(1)
    rows, ev = [], []
    for k in range(160):
        d = str(np.datetime64("2026-01-01") + k)
        t = CC._day_close_ms(d)
        brain_long = k % 2 == 0
        ev.append(("brain_decision", t + 1000, {"symbol": "ETHUSDT", "kind": "OPEN" if brain_long else "NO_TRADE", "status": "APPROVED" if brain_long else "DRAFT"}))
        if brain_long:
            ev.append(("paper_open", t + 2000, {"position_id": f"p{k}", "symbol": "ETHUSDT", "side": 1}))
        r = rng.normal(1.0 if brain_long else -0.3, 0.8)
        rows.append({"data_segnale": d, "simbolo": "ETHUSDT", "esito": "eseguito_virtuale", "stato": "chiusa", "R": float(r)})
    _journal(tmp_path / "j.db", ev)
    _toro(tmp_path / "toro", rows)
    small = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN, validation_from="2026-01-31")
    assert small["ipotesi"] == {} and small["regole_validate"] == []          # 15 casi per vista: sotto soglia
    res = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN, validation_from="2026-04-01")
    assert set(res["ipotesi"]) == {"LONG_aperto", "NO_TRADE"}
    rules = {r["vista_brain"]: r for r in res["regole_validate"]}
    assert set(rules) == {"LONG_aperto", "NO_TRADE"}
    assert rules["LONG_aperto"]["validazione"]["ic95"][0] > 0 and rules["NO_TRADE"]["validazione"]["ic95"][1] < 0
    only_discovery = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN)
    assert only_discovery["regole_validate"] == [] and only_discovery["ipotesi"]   # senza secondo campione: solo ipotesi


def test_risk_rejection_without_proposal_is_not_model_no_trade(tmp_path):
    t = CC._day_close_ms("2026-12-01")
    events = [("brain_decision", t + 100, {"symbol": "SOLUSDT", "kind": "NO_TRADE",
                                               "status": "RISK_REJECTED", "rationale": "risk_rejected"}),
              ("brain_decision", t + 300, {"symbol": "XRPUSDT", "kind": "NO_TRADE",
                                               "status": "DRAFT", "rationale": "deepseek:analysis"}),
              ("brain_decision", t + 400, {"symbol": "LINKUSDT", "kind": "OPEN",
                                               "status": "APPROVED", "rationale": "risk_quote_ok"})]
    _journal(tmp_path / "j.db", events)
    _toro(tmp_path / "toro", [{"data_segnale": "2026-12-01", "simbolo": s, "esito": "eseguito_virtuale",
                              "stato": "aperta"} for s in ("SOLUSDT", "XRPUSDT", "LINKUSDT", "ADAUSDT")])
    r = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN)
    views = {f["simbolo"]: f["vista_brain"] for f in r["fatti"]}
    assert views == {"SOLUSDT": "RESPINTO_LATO_IGNOTO", "XRPUSDT": "NO_TRADE",
                     "LINKUSDT": "APPROVATO_NON_ESEGUITO", "ADAUSDT": "non_valutato"}


def test_unlinked_proposal_is_not_a_confirmed_rejection_and_mixed_fills_visible(tmp_path):
    t = CC._day_close_ms("2026-12-02")
    events = [("brain_decision", t + 100, {"symbol": "SOLUSDT", "kind": "NO_TRADE",
                                               "status": "RISK_REJECTED", "rationale": "risk_rejected"}),
              ("paper_open", t + 200, {"symbol": "ETHUSDT", "side": 1, "position_id": "p1"}),
              ("paper_open", t + 300, {"symbol": "ETHUSDT", "side": -1, "position_id": "p2"})]
    _journal(tmp_path / "j.db", events)
    _toro(tmp_path / "toro", [{"data_segnale": "2026-12-02", "simbolo": s, "esito": "eseguito_virtuale",
                              "stato": "aperta"} for s in ("SOLUSDT", "ETHUSDT")])
    props = tmp_path / "props.jsonl"
    props.write_text(json.dumps({"ts_ms": t + 101, "symbol": "SOLUSDT", "kind": "OPEN", "side": 1}) + "\n")
    r = CC.compare(tmp_path / "toro", tmp_path / "j.db", RUN, props)
    by_sym = {f["simbolo"]: f for f in r["fatti"]}
    assert by_sym["SOLUSDT"]["vista_brain"] == "PROPOSTA_ESITO_IGNOTO"
    assert by_sym["SOLUSDT"]["rifiuti_confermati"] == 0
    assert by_sym["SOLUSDT"]["proposte_senza_decisione"] == 1
    assert by_sym["ETHUSDT"]["vista_brain"] == "MISTO_aperto"


def test_observation_only_closed_executed_trades_enter_statistics():
    good = {"vista_brain": "NO_TRADE", "toro": {"esito": "eseguito_virtuale", "stato": "chiusa", "R": 1.0}}
    rejected = {"vista_brain": "NO_TRADE", "toro": {"esito": "rifiutato_slot_pieni", "stato": "chiusa", "R": -2.0}}
    open_ = {"vista_brain": "NO_TRADE", "toro": {"esito": "eseguito_virtuale", "stato": "aperta", "R": -3.0}}
    result = CC.groups([good, rejected, open_, good])
    assert result["NO_TRADE"]["n"] == 2
    assert result["NO_TRADE"]["R_medio"] == 1.0
