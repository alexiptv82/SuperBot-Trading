"""Validazione indipendente delle feature degli snapshot: dal ciclo REALE (motore, journal, snapshot) al Dataset Builder.

Il runtime scrive gli snapshot; le stesse candele vengono poi fornite come archivio attestato (un `candles_meta.json`
per timeframe) e il validatore del builder (`ops/brain-unico/training/snapshot_verify.py`, codice separato, nessun
import dal runtime) ricalcola digest e feature. Ogni manomissione deve lasciare lo snapshot NON verificato.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import STEP, NOW, _bars, _events, _journal
from backend.v3.decision_snapshot_v2 import SNAPSHOT_KIND
from backend.v3.runner.test_decision_trace import ScriptAnalyst, _run

D = Decimal
ROOT = Path(__file__).resolve().parents[3]
TRAINING = ROOT / "ops" / "brain-unico" / "training"
META = {"exchange": "bitget", "market": "usdt-futures", "price_basis": "last", "source": "synthetic-test"}


def _builder():
    sys.path.insert(0, str(TRAINING))
    try:
        import builder as B
        import snapshot_verify as SV
    finally:
        sys.path.remove(str(TRAINING))
    return B, SV


def _archive(root: Path, symbols=("AAAUSDT",), *, meta=True, edit=None, skip_tf=()):
    """Copia 'attestata' delle candele che il runtime ha visto (stesso generatore del FakeStore)."""
    for tf, ms in STEP.items():
        if tf in skip_tf:
            continue
        d = root / tf
        d.mkdir(parents=True)
        if meta:
            (d / "candles_meta.json").write_text(json.dumps({**META, "interval_ms": ms}))
        for sym in symbols:
            lines = []
            for b in _bars(tf):
                row = {"t": b.open_time_ms, "o": str(b.open), "h": str(b.high), "l": str(b.low), "c": str(b.close),
                       "v": str(b.volume)}
                if edit:
                    row = edit(tf, row)
                if row is not None:
                    lines.append(json.dumps(row))
            (d / f"{sym}.jsonl").write_text("\n".join(lines) + "\n")
    return root


def _snapshots(j):
    return [e.payload for e in _events(j, SNAPSHOT_KIND)]


def _decided(kind="NO_TRADE"):
    j = _journal()
    _run(j, ScriptAnalyst(kind=kind), symbols=("AAAUSDT",))
    return j


def test_runtime_snapshots_are_verified_against_attested_candles():
    B, SV = _builder()
    j = _decided("OPEN")
    root = _archive(Path(tempfile.mkdtemp()) / "dc")
    payload, = _snapshots(j)
    verdict, prov = SV.verify(payload, SV.DecisionCandles(str(root)))
    assert verdict == "verified", verdict
    assert set(prov["decision_market_dataset_ids"]) == {"15m", "1h", "4h"}


def test_an_archive_with_different_number_formatting_still_verifies():
    B, SV = _builder()
    j = _decided()
    root = _archive(Path(tempfile.mkdtemp()) / "dc", edit=lambda tf, r: {**r, "c": str(D(r["c"]).quantize(D("1.000000")))})
    assert SV.verify(_snapshots(j)[0], SV.DecisionCandles(str(root)))[0] == "verified"


def _verdict(edit=None, meta=True, skip_tf=(), payload_edit=None):
    B, SV = _builder()
    j = _decided()
    root = _archive(Path(tempfile.mkdtemp()) / "dc", meta=meta, edit=edit, skip_tf=skip_tf)
    p = dict(_snapshots(j)[0])
    if payload_edit:
        p = payload_edit(p)
    return SV.verify(p, SV.DecisionCandles(str(root)))[0]


LAST = {tf: _bars(tf)[-1].open_time_ms for tf in STEP}


@pytest.mark.parametrize("label, kwargs, expected", [
    ("candle changed", dict(edit=lambda tf, r: {**r, "h": str(D(r["h"]) + 1)} if r["t"] == LAST[tf] else r),
     "inputs_mismatch"),
    ("candle missing", dict(edit=lambda tf, r: None if tf == "1h" and r["t"] == LAST[tf] else r), "candles_missing"),
    ("no meta", dict(meta=False), "market_data_unattested"),
    ("timeframe missing", dict(skip_tf=("4h",)), "market_data_unattested"),
    ("feature changed", dict(payload_edit=lambda p: {**p, "features": {**p["features"], "t15m_rsi14": "12.5"}}),
     "features_mismatch"),
    ("feature dropped", dict(payload_edit=lambda p: {**p, "features": {k: v for k, v in p["features"].items()
                                                                        if k != "t1h_atr14_pct"}}),
     "features_incomplete"),
    ("feature not computable from the window", dict(payload_edit=lambda p: {**p, "features": {
        **p["features"], "t15m_ret_200": "0.01"}}), "features_mismatch"),
    ("feature added", dict(payload_edit=lambda p: {**p, "features": {**p["features"], "t15m_vol": "1"}}),
     "unknown_feature"),
    ("asof moved", dict(payload_edit=lambda p: {**p, "feature_asof_ms": p["feature_asof_ms"] - 1}), "asof_mismatch"),
    ("cut before last candle", dict(payload_edit=lambda p: {**p, "snapshot_captured_at_ms":
                                                            p["feature_asof_ms"] - 1}), "window_not_closed"),
    ("digest claimed falsely", dict(payload_edit=lambda p: {**p, "inputs_digest": "0" * 64}), "inputs_mismatch"),
    ("window shifted", dict(payload_edit=lambda p: {**p, "inputs_window": {**p["inputs_window"], "15m": [
        p["inputs_window"]["15m"][0] + 900_000, p["inputs_window"]["15m"][1]]}}), "candles_missing"),
    ("other feature set", dict(payload_edit=lambda p: {**p, "feature_set": "v0"}), "unsupported_feature_set"),
    ("no provenance", dict(payload_edit=lambda p: {**p, "inputs_digest": None}), "provenance_incomplete"),
])
def test_every_tampering_leaves_the_snapshot_unverified(label, kwargs, expected):
    assert _verdict(**kwargs) == expected, label


def test_conflicting_duplicate_candles_are_not_resolved_by_guessing():
    B, SV = _builder()
    j = _decided()
    root = _archive(Path(tempfile.mkdtemp()) / "dc")
    f = root / "15m" / "AAAUSDT.jsonl"
    last = json.loads(f.read_text().splitlines()[-1])
    with f.open("a") as fh:
        fh.write(json.dumps({**last, "v": str(D(last["v"]) + 1)}) + "\n")   # stessa candela, volume diverso
    assert SV.verify(_snapshots(j)[0], SV.DecisionCandles(str(root)))[0] == "candles_conflict"


def test_without_decision_candles_nothing_is_verified():
    B, SV = _builder()
    j = _decided()
    assert SV.verify(_snapshots(j)[0], None)[0] == "no_decision_candles"


def test_the_validator_does_not_import_the_runtime():
    import ast
    tree = ast.parse((TRAINING / "snapshot_verify.py").read_text())
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith("backend") for m in names)


# ------------------------------------------------------------------------------------------------ nel builder
# Quattro requisiti DISTINTI: coerenza delle feature, integrita' dell'archivio, provenienza verificabile delle candele
# (manifest + risposte grezze + ancora esterna) e attestazione del journal (Fase 0). Nessuno sostituisce gli altri.

MID = "candles-20261120T090000Z-e2e"


def _attested_archive(root: Path, symbols=("AAAUSDT",), edit=None):
    """Archivio come lo produce la procedura di acquisizione: risposte grezze della fonte pubblica -> file derivati."""
    B, SV = _builder()
    import candle_provenance as CP
    fetched, last = {}, 0
    for tf, ms in STEP.items():
        for sym in symbols:
            rows = []
            for b in _bars(tf):
                r = {"t": b.open_time_ms, "o": str(b.open), "h": str(b.high), "l": str(b.low), "c": str(b.close),
                     "v": str(b.volume)}
                rows.append(edit(tf, r) if edit else r)
            last = max(last, rows[-1]["t"] + ms)
            gran = CP.GRANULARITY[ms]
            url = (f"{CP.SOURCE['base_url']}{CP.SOURCE['path']}?symbol={sym}&productType=USDT-FUTURES"
                   f"&granularity={gran}&startTime={rows[0]['t']}&endTime={rows[-1]['t']}&limit=200")
            body = {"code": "00000", "data": [[str(r["t"]), r["o"], r["h"], r["l"], r["c"], r["v"], "0"]
                                              for r in rows]}
            fetched[f"{tf}/{sym}.jsonl"] = {"symbol": sym, "interval_ms": ms, "responses": [(url, body)]}
    sha = CP.write_archive(str(root), manifest_id=MID, acquired_at_ms=last, tool={"name": "test"},
                           fetched=fetched, meta=META)
    return root, {MID: sha}


def _build(j, dc_root, candle_anchors=None):
    B, SV = _builder()
    spec = {"inputs": [{"id": "brain-lab", "source_system": "brain_unico", "kind": "v3", "path": str(j.filename)}]}
    return B.build(spec, None, decision_candles_dir=str(dc_root) if dc_root else None, candle_anchors=candle_anchors)


def _rows_by_kind(res):
    return {r["record_kind"]: r for r in res["rows"]}


def test_without_decision_candles_nothing_is_promoted():
    j = _decided()
    plain = _rows_by_kind(_build(j, None))["no_trade"]
    assert "snapshot_unverified" in plain["quality_flags"] and "snapshot_unverified" in plain["ineligible_reasons"]
    assert plain["provenance"]["feature_consistency"] == "no_decision_candles"
    assert plain["provenance"]["candle_provenance"] == "archive_missing"


def test_all_three_market_requirements_promote_the_snapshot_but_not_the_row():
    j = _decided()
    root, anchors = _attested_archive(Path(tempfile.mkdtemp()) / "dc")
    res = _build(j, root, anchors)
    row = _rows_by_kind(res)["no_trade"]
    p = row["provenance"]
    assert (p["feature_consistency"], p["candle_archive_integrity"], p["candle_provenance"]) == (
        "verified", "intact", "attested")
    assert "snapshot_unverified" not in row["quality_flags"] and "snapshot_unverified" not in row["ineligible_reasons"]
    assert p["snapshot_risk_values"] == "excluded_unverified"
    assert not any(k.startswith("risk_") for k in (row["features"] or {}))
    # quarto requisito separato: journal e decisioni non attestati dalla Fase 0 => nessun training
    assert row["eligible_for_training"] is False and "input_not_attested" in row["ineligible_reasons"]
    assert res["decision_candles"]["provenance"] == "attested"


def test_consistent_features_on_a_merely_declared_archive_are_not_promoted():
    j = _decided()
    root = _archive(Path(tempfile.mkdtemp()) / "dc")            # solo candles_meta.json: provenienza dichiarata
    p = _rows_by_kind(_build(j, root))["no_trade"]["provenance"]
    assert (p["feature_consistency"], p["candle_provenance"]) == ("verified", "declared_only")
    assert "snapshot_unverified" in _rows_by_kind(_build(j, root))["no_trade"]["ineligible_reasons"]


def test_an_unanchored_or_broken_archive_is_not_promoted_even_with_consistent_features():
    j = _decided()
    root, anchors = _attested_archive(Path(tempfile.mkdtemp()) / "dc")
    row = _rows_by_kind(_build(j, root, {}))["no_trade"]                       # ancora non registrata
    assert row["provenance"]["feature_consistency"] == "verified"
    assert row["provenance"]["candle_provenance"] == "manifest_unanchored"
    assert "snapshot_unverified" in row["ineligible_reasons"]
    (root / "15m" / "NOTE.txt").write_text("aggiunto dopo")                    # integrita' rotta
    row = _rows_by_kind(_build(j, root, anchors))["no_trade"]
    assert row["provenance"]["candle_archive_integrity"] == "file_unlisted"
    assert "snapshot_unverified" in row["ineligible_reasons"]


def test_an_attested_archive_with_different_market_data_is_not_promoted():
    j = _decided()
    root, anchors = _attested_archive(
        Path(tempfile.mkdtemp()) / "dc",
        edit=lambda tf, r: {**r, "l": str(D(r["l"]) - D("0.01"))} if r["t"] == LAST[tf] else r)
    row = _rows_by_kind(_build(j, root, anchors))["no_trade"]
    assert row["provenance"]["candle_provenance"] == "attested"
    assert row["provenance"]["feature_consistency"] == "inputs_mismatch"   # il runtime ha visto altri dati
    assert "snapshot_unverified" in row["ineligible_reasons"]


def test_features_with_the_real_view_parameters_are_recognised():
    """Regressione trovata sui dati Bitget reali (20/11/2026): le finestre reali sono 2880/720/180 candele e i nomi
    `t15m_ret_2880` venivano rifiutati come `unknown_feature` dal validatore (che ne accettava al massimo 3 cifre)."""
    import tempfile as tf
    from backend.v3.brain_market.params import load_default_params
    from backend.v3.runner import decision_trace as dt
    B, SV = _builder()
    vp = load_default_params()
    assert {s.pct_window for s in vp.timeframes} >= {2880}
    now = NOW
    bars = {s.name: _bars(s.name, now, n=s.pct_window + 30) for s in vp.timeframes}
    cap = dt.capture_inputs(bars, vp.timeframes, now_ms=now)
    assert "t15m_ret_2880" in cap.features
    root = Path(tf.mkdtemp()) / "dc"
    for s in vp.timeframes:
        d = root / s.name
        d.mkdir(parents=True)
        (d / "candles_meta.json").write_text(json.dumps({**META, "interval_ms": s.candle_ms}))
        (d / "AAAUSDT.jsonl").write_text("".join(json.dumps({"t": b.open_time_ms, "o": str(b.open), "h": str(b.high),
                                                             "l": str(b.low), "c": str(b.close), "v": str(b.volume)}) + "\n"
                                                 for b in bars[s.name]))
    payload = {"feature_set": dt.FEATURE_SET, "inputs_window": {k: list(v) for k, v in cap.inputs_window.items()},
               "inputs_digest": cap.inputs_digest, "features": {k: format(v, "f") for k, v in cap.features.items()},
               "snapshot_captured_at_ms": now, "feature_asof_ms": cap.asof_ms, "symbol": "AAAUSDT"}
    assert SV.verify(payload, SV.DecisionCandles(str(root)))[0] == "verified"
