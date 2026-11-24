"""F0 CLI: local-only witness handling; no SSH, no secrets and no VPS access."""
import json
from hashlib import sha256
import shutil
import sqlite3

import pytest

from v3.f0_cli import main, run


def make_brain(tmp_path):
    p = tmp_path / "brain.sqlite3"
    with sqlite3.connect(p) as db:
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,"
                   "kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (
            json.dumps({"mode": "paper", "account_id": "brain-free-paper",
                        "cash": 2000, "positions": {}}),))
        db.execute("INSERT INTO events VALUES(1,'id1','ai_decision',1,'{}')")
    return p


def test_brain_cli_observe_capture_verify_with_offline_witness(tmp_path):
    db = make_brain(tmp_path)
    witness = run(["observe-brain", "--source", str(db)])
    assert witness["source_observation"]["event_count"] == 1
    witness_root = tmp_path / "external-evidence"
    witness_root.mkdir()
    witness_file = witness_root / "brain-source.json"
    witness_file.write_text(json.dumps(witness))
    captured = tmp_path / "captured"
    receipt = run(["capture-brain", "--source", str(db),
                   "--new-directory", str(captured)])
    assert receipt["externally_certified"] is False
    restored = tmp_path / "restored-on-other-volume-example"
    shutil.copytree(captured, restored)
    verified = run([
        "verify-brain", "--restored-directory", str(restored),
        "--external-witness", str(witness_file),
        "--external-manifest-sha256", receipt["manifest_sha256"],
    ])
    assert verified["verified"] is True
    assert verified["event_count"] == 1


def test_brain_cli_refuses_self_attested_witness_inside_restore(tmp_path):
    db = make_brain(tmp_path)
    witness = run(["observe-brain", "--source", str(db)])
    captured = tmp_path / "captured"
    receipt = run(["capture-brain", "--source", str(db),
                   "--new-directory", str(captured)])
    self_witness = captured / "witness.json"
    self_witness.write_text(json.dumps(witness))
    with pytest.raises(ValueError, match="witness_must_be_outside_restored_directory"):
        run(["verify-brain", "--restored-directory", str(captured),
             "--external-witness", str(self_witness),
             "--external-manifest-sha256", receipt["manifest_sha256"]])


def test_brain_cli_refuses_forged_external_witness(tmp_path):
    db = make_brain(tmp_path)
    witness = run(["observe-brain", "--source", str(db)])
    witness["source_observation"]["events_sha256"] = "0" * 64
    file = tmp_path / "independent.json"
    file.write_text(json.dumps(witness))
    captured = tmp_path / "captured"
    receipt = run(["capture-brain", "--source", str(db),
                   "--new-directory", str(captured)])
    with pytest.raises(ValueError, match="external_source_witness_mismatch"):
        run(["verify-brain", "--restored-directory", str(captured),
             "--external-witness", str(file),
             "--external-manifest-sha256", receipt["manifest_sha256"]])


def test_cli_fails_closed_without_tracebacks_or_source_content(tmp_path, capsys):
    missing = tmp_path / "missing.db"
    code = main(["observe-brain", "--source", str(missing)])
    response = json.loads(capsys.readouterr().out)
    assert code == 2
    assert response == {"error_code": "ValueError",
                        "status": "F0_BLOCKED", "verified": False}
    assert "missing.db" not in json.dumps(response)


def test_cli_refuses_missing_external_witness(tmp_path, capsys):
    db = make_brain(tmp_path)
    captured = tmp_path / "captured"
    receipt = run(["capture-brain", "--source", str(db),
                   "--new-directory", str(captured)])
    code = main(["verify-brain", "--restored-directory", str(captured),
                 "--external-witness", str(tmp_path / "absent.json"),
                 "--external-manifest-sha256", receipt["manifest_sha256"]])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "F0_BLOCKED"


def make_classic(tmp_path):
    base = tmp_path / "hawk"
    base.mkdir()
    trade = {"id": 1, "symbol": "ETH/USDT:USDT", "side": 1,
             "open_ms": 1793600000000, "close_ms": 1793600300000,
             "net": 4.0, "why": "time"}
    (base / "state_v2.json").write_text(json.dumps({
        "run_no": 1, "main": {"cash": 1004, "closed": [trade],
                             "positions": {}, "limits": {"start_equity": 1000}}
    }))
    (base / "trade_history.jsonl").write_text(json.dumps(trade) + "\n")
    (base / "learning_log.jsonl").write_text(
        json.dumps({"ev": "close", "run_no": 1, "portfolio": "hawk", **trade}) + "\n"
    )
    (base / "lessons.md").write_text("# Lessons preserved\n")
    return base


def test_classic_cli_witness_and_offline_verification(tmp_path):
    source = make_classic(tmp_path)
    evidence = run(["observe-classic", "--source", str(source),
                    "--portfolio", "hawk"])
    assert evidence["schema"] == "superbot-v3-f0-classic-source-v1"
    assert evidence["total_closed"] == 1
    proof = tmp_path / "external-source.json"
    proof.write_text(json.dumps(evidence))
    restored = tmp_path / "separate-restore"
    shutil.copytree(source, restored)
    verified = run(["verify-classic", "--restored-directory", str(restored),
                    "--external-witness", str(proof), "--portfolio", "hawk"])
    assert verified["verified"] is True
    assert verified["total_closed"] == 1


def test_classic_cli_rejects_wrong_account_witness(tmp_path):
    source = make_classic(tmp_path)
    evidence = run(["observe-classic", "--source", str(source),
                    "--portfolio", "hawk"])
    evidence["portfolio_id"] = "bull"
    proof = tmp_path / "external-source.json"
    proof.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="wrong_classic_witness_portfolio"):
        run(["verify-classic", "--restored-directory", str(source),
             "--external-witness", str(proof), "--portfolio", "hawk"])
