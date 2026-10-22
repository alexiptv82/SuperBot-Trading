"""
Test per deploy/scripts/learning_log_manifest.py (step 3 ricerca).

Verifica:
- file mancante → exists=False, nessun crash
- file vuoto → lines_valid=0
- JSON invalido contato correttamente
- campi mancanti contati separatamente
- sha256 deterministico e corretto
- NESSUN valore di trade grezzo in output (solo conteggi/hash)
- lati e simboli aggregati correttamente
- ts_min/ts_max calcolati
- versione schema ignota segnalata
"""
import hashlib
import importlib.util
import json
import sys
import os
import types
import pytest

# Carica il modulo senza installarlo
_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "deploy", "scripts", "learning_log_manifest.py",
)

def _load_module():
    spec = importlib.util.spec_from_file_location("learning_log_manifest", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

M = _load_module()


def _write(tmp_path, bot, lines):
    d = tmp_path / bot
    d.mkdir(parents=True, exist_ok=True)
    p = d / "learning_log.jsonl"
    p.write_bytes(("\n".join(lines) + "\n").encode())
    return str(p)


def _rec(**kw):
    base = {
        "symbol": "BTCUSDT",
        "side": "long",
        "entry_ts": 1700000000,
        "exit_ts": 1700003600,
        "net": 5.0,
        "gross": 5.5,
        "fees": 0.5,
    }
    base.update(kw)
    return json.dumps(base)


# ── file mancante ──────────────────────────────────────────────────────────

def test_missing_file(tmp_path):
    m = M.manifest_one(str(tmp_path / "hawk" / "learning_log.jsonl"), "hawk")
    assert m["exists"] is False
    assert m["sha256"] is None
    assert m["lines_valid"] == 0
    assert m["error"] is not None


# ── file vuoto ─────────────────────────────────────────────────────────────

def test_empty_file(tmp_path):
    p = tmp_path / "hawk" / "learning_log.jsonl"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"")
    m = M.manifest_one(str(p), "hawk")
    assert m["exists"] is True
    assert m["lines_valid"] == 0
    assert m["lines_total"] == 0
    assert m["sha256"] == hashlib.sha256(b"").hexdigest()


# ── JSON invalido contato ──────────────────────────────────────────────────

def test_invalid_json_counted(tmp_path):
    _write(tmp_path, "hawk", [
        _rec(),
        "non-json",
        "{broken",
        _rec(symbol="ETHUSDT"),
    ])
    p = str(tmp_path / "hawk" / "learning_log.jsonl")
    m = M.manifest_one(p, "hawk")
    assert m["lines_invalid_json"] == 2
    assert m["lines_valid"] == 2


# ── campi mancanti ─────────────────────────────────────────────────────────

def test_missing_fields_counted(tmp_path):
    bad = json.dumps({"symbol": "BTCUSDT"})  # manca side, entry_ts, etc.
    _write(tmp_path, "hawk", [_rec(), bad])
    p = str(tmp_path / "hawk" / "learning_log.jsonl")
    m = M.manifest_one(p, "hawk")
    assert m["lines_missing_fields"] == 1
    assert m["lines_valid"] == 1


# ── sha256 deterministico ──────────────────────────────────────────────────

def test_sha256_deterministic(tmp_path):
    content = (_rec() + "\n").encode()
    p = tmp_path / "hawk" / "learning_log.jsonl"
    p.parent.mkdir(parents=True)
    p.write_bytes(content)
    m = M.manifest_one(str(p), "hawk")
    assert m["sha256"] == hashlib.sha256(content).hexdigest()
    # Secondo passaggio: stesso risultato
    m2 = M.manifest_one(str(p), "hawk")
    assert m["sha256"] == m2["sha256"]


# ── output non contiene valori di trade grezzi ────────────────────────────

def test_no_raw_trade_values_in_output(tmp_path, capsys):
    """Il manifesto stampato non deve contenere net/gross/fees individuali."""
    _write(tmp_path, "hawk", [
        _rec(net=123.456, gross=200.0, fees=0.77, symbol="SOLUSDT"),
    ])
    p = str(tmp_path / "hawk" / "learning_log.jsonl")
    m = M.manifest_one(p, "hawk")
    # Stampa in human-readable
    M.print_human([m])
    captured = capsys.readouterr().out
    # I valori monetari individuali non devono apparire
    assert "123.456" not in captured
    assert "200.0" not in captured
    assert "0.77" not in captured
    # Il simbolo aggregato (conteggio) può apparire, ma non il valore
    # Verifica che il numero di simboli distinti sia presente (1)
    assert m["symbols_seen"] == 1


# ── lati e simboli aggregati ──────────────────────────────────────────────

def test_sides_and_symbols_aggregated(tmp_path):
    _write(tmp_path, "bull", [
        _rec(symbol="BTCUSDT", side="long"),
        _rec(symbol="ETHUSDT", side="short"),
        _rec(symbol="BTCUSDT", side="long"),
    ])
    p = str(tmp_path / "bull" / "learning_log.jsonl")
    m = M.manifest_one(p, "bull")
    assert m["symbols_seen"] == 2
    assert set(m["sides_seen"]) == {"long", "short"}
    assert m["sides_counts"]["long"] == 2
    assert m["sides_counts"]["short"] == 1


# ── ts_min / ts_max ────────────────────────────────────────────────────────

def test_ts_range(tmp_path):
    _write(tmp_path, "hawk", [
        _rec(entry_ts=1000, exit_ts=2000),
        _rec(entry_ts=500,  exit_ts=3000),
    ])
    p = str(tmp_path / "hawk" / "learning_log.jsonl")
    m = M.manifest_one(p, "hawk")
    assert m["ts_min"] == 500
    assert m["ts_max"] == 3000


# ── versione schema ignota ────────────────────────────────────────────────

def test_unknown_schema_version_counted(tmp_path):
    r = json.loads(_rec())
    r["schema_version"] = "99"
    _write(tmp_path, "hawk", [_rec(), json.dumps(r)])
    p = str(tmp_path / "hawk" / "learning_log.jsonl")
    m = M.manifest_one(p, "hawk")
    assert m["lines_unknown_version"] == 1
    assert m["lines_valid"] == 2  # entrambi validi, ma uno ha versione ignota


# ── righe vuote ignorate ───────────────────────────────────────────────────

def test_empty_lines_ignored(tmp_path):
    # splitlines() non genera riga vuota per il \n finale:
    # "\n".join(["", rec, "", rec2, ""]) → "\nrec\n\nrec2\n"
    # splitlines dà 4 elementi: "", rec, "", rec2 → 2 vuote, 2 valide
    lines = ["", _rec(), "", _rec(symbol="ETHUSDT"), ""]
    p = tmp_path / "hawk" / "learning_log.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("\n".join(lines))
    m = M.manifest_one(str(p), "hawk")
    assert m["lines_empty"] == 2
    assert m["lines_valid"] == 2


# ── due bot indipendenti ──────────────────────────────────────────────────

def test_two_bots_independent(tmp_path):
    _write(tmp_path, "hawk", [_rec(symbol="BTCUSDT")] * 5)
    _write(tmp_path, "bull", [_rec(symbol="ETHUSDT")] * 3 + ["bad-json"])
    mh = M.manifest_one(str(tmp_path / "hawk" / "learning_log.jsonl"), "hawk")
    mb = M.manifest_one(str(tmp_path / "bull" / "learning_log.jsonl"), "bull")
    assert mh["lines_valid"] == 5
    assert mb["lines_valid"] == 3
    assert mb["lines_invalid_json"] == 1
    assert mh["sha256"] != mb["sha256"]
