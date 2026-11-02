"""Offline classic source-vs-restored archive checks; fully synthetic."""
import json
import shutil

import pytest

from v3.f0_classic_certificate import (
    observe_classic_source_readonly, verify_classic_offhost
)


def make_hawk(tmp_path):
    root = tmp_path / "source-hawk"
    root.mkdir()
    old = {"id":1, "symbol":"BTC/USDT:USDT", "side":-1,
           "open_ms":1793600000000, "close_ms":1793600300000,
           "net":-4.5, "why":"time"}
    now = {"id":2, "symbol":"ETH/USDT:USDT", "side":1,
           "open_ms":1793620000000, "close_ms":1793620300000,
           "net":7.0, "why":"time"}
    (root/"state_v2.json").write_text(json.dumps({
        "run_no":8, "main":{"cash":1007, "closed":[now],
                            "positions":{}, "limits":{"start_equity":1000}}
    }))
    (root/"trade_history.jsonl").write_text(
        json.dumps(old)+"\n"+json.dumps(now)+"\n"
    )
    (root/"learning_log.jsonl").write_text(
        json.dumps({"ev":"close","run_no":7,"portfolio":"hawk",**old})+"\n"+
        json.dumps({"ev":"close","run_no":8,"portfolio":"hawk",**now})+"\n"
    )
    folder = root/"archive"/"run-7"
    folder.mkdir(parents=True)
    (folder/"state_v2.json").write_text(json.dumps({
        "run_no":7,"main":{"closed":[old],"positions":{}}
    }))
    (folder/"trade_history.jsonl").write_text(json.dumps(old)+"\n")
    (folder/"summary.json").write_text(json.dumps({
        "run_no":7, "portfolio":"hawk", "start_equity":1000,
        "end_equity":995.5, "pnl":-4.5, "net_total":-4.5, "trades":1
    }))
    return root


def kw(w):
    return {
        "expected_files_sha256":w.files_sha256,
        "expected_total_closed":w.total_closed,
        "expected_historical_runs":w.historical_run_count,
        "expected_current_run":w.current_run,
    }


def test_classic_archive_restored_offhost_matches_independent_witness(tmp_path):
    source = make_hawk(tmp_path)
    witness = observe_classic_source_readonly(source, "hawk")
    assert witness.total_closed == 2
    assert witness.historical_run_count == 1
    assert witness.current_run == 8
    dest = tmp_path/"separate-restore"
    shutil.copytree(source, dest)
    assert verify_classic_offhost(dest, "hawk", **kw(witness)) == witness


def test_forged_archive_summary_fails_closed(tmp_path):
    source = make_hawk(tmp_path)
    witness = observe_classic_source_readonly(source, "hawk")
    dest = tmp_path/"restore"
    shutil.copytree(source, dest)
    file = dest/"archive"/"run-7"/"summary.json"
    obj = json.loads(file.read_text())
    obj["end_equity"] = 9999
    file.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="classic_archive_or_accounting_failed"):
        verify_classic_offhost(dest, "hawk", **kw(witness))


def test_self_consistent_but_different_source_rejected_by_independent_digest(tmp_path):
    source = make_hawk(tmp_path)
    witness = observe_classic_source_readonly(source, "hawk")
    dest = tmp_path/"restore"
    shutil.copytree(source, dest)
    # Add a non-close learning event: audit remains economically coherent but
    # byte-for-byte provenance must no longer match the original observation.
    with (dest/"learning_log.jsonl").open("a") as out:
        out.write(json.dumps({"ev":"observer_note","note":"changed"})+"\n")
    with pytest.raises(ValueError, match="classic_external_source_witness_mismatch"):
        verify_classic_offhost(dest, "hawk", **kw(witness))


def test_missing_archive_rejected_before_any_import(tmp_path):
    source = make_hawk(tmp_path)
    shutil.rmtree(source/"archive")
    with pytest.raises(ValueError, match="classic_archive_or_accounting_failed"):
        observe_classic_source_readonly(source, "hawk")


def test_missing_or_invalid_external_witness_rejected(tmp_path):
    source = make_hawk(tmp_path)
    with pytest.raises(TypeError):
        verify_classic_offhost(source, "hawk")
    with pytest.raises(ValueError, match="invalid_classic_external_witness"):
        verify_classic_offhost(source,"hawk", expected_files_sha256="bad",
            expected_total_closed=2,expected_historical_runs=1,
            expected_current_run=8)
