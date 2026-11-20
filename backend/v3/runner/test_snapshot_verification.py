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

def _build(j, dc_root):
    B, SV = _builder()
    spec = {"inputs": [{"id": "brain-lab", "source_system": "brain_unico", "kind": "v3", "path": str(j.filename)}]}
    return B.build(spec, None, decision_candles_dir=str(dc_root) if dc_root else None)


def _rows_by_kind(res):
    return {r["record_kind"]: r for r in res["rows"]}


def test_the_builder_lifts_snapshot_unverified_only_after_verification():
    j = _decided()
    plain = _rows_by_kind(_build(j, None))["no_trade"]
    assert "snapshot_unverified" in plain["quality_flags"]
    assert plain["provenance"]["snapshot_verification"] == "no_decision_candles"
    assert "snapshot_unverified" in plain["ineligible_reasons"]

    verified = _rows_by_kind(_build(j, _archive(Path(tempfile.mkdtemp()) / "dc")))["no_trade"]
    assert "snapshot_unverified" not in verified["quality_flags"]
    assert verified["provenance"]["snapshot_verification"] == "verified"
    assert verified["provenance"]["snapshot_risk_values"] == "excluded_unverified"
    assert not any(k.startswith("risk_") for k in (verified["features"] or {}))
    assert "snapshot_unverified" not in verified["ineligible_reasons"]
    # resta comunque escluso finche' l'input (journal) non e' attestato dalla Fase 0: nessuna scorciatoia
    assert verified["eligible_for_training"] is False and "input_not_attested" in verified["ineligible_reasons"]


def test_a_tampered_archive_keeps_the_row_out_of_training():
    j = _decided()
    root = _archive(Path(tempfile.mkdtemp()) / "dc",
                    edit=lambda tf, r: {**r, "l": str(D(r["l"]) - D("0.01"))} if r["t"] == LAST[tf] else r)
    row = _rows_by_kind(_build(j, root))["no_trade"]
    assert row["provenance"]["snapshot_verification"] == "inputs_mismatch"
    assert "snapshot_unverified" in row["ineligible_reasons"]
