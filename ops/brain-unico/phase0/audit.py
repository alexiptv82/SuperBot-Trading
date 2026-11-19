#!/usr/bin/env python3
"""Fase 0 — ripristino su directory VUOTA e audit di quadratura, SOLO su copie di laboratorio.

Non legge mai le sorgenti: parte da snapshot_log.json e dai file copiati da snapshot.py.

Controlli (ogni esito e' PASS / WARN / FAIL):
- file attesi vs presenti (mancanti / extra), SHA256 dei file ripristinati contro il log;
- SQLite: integrity_check, conteggi righe per tabella uguali a quelli registrati alla copia;
- journal V3 (tabella v3_events): catena SHA-256 ricalcolata con la STESSA formula del codice di produzione
  (verificatore indipendente, nessun import da backend/), collegamento previous_hash, buchi di seq,
  event_id duplicati, payload non canonico, conteggio per (portfolio_id, run_id), testa della catena;
- JSONL: righe e righe non valide uguali a quelle registrate alla copia;
- avvertenze: tentativi ripetuti, riga parziale in coda, finestra di cattura lunga, DB con -wal residuo.

La catena puo' rilevare manomissioni o troncamenti interni, NON un troncamento di coda senza un'ancora
esterna (conteggio/testa attesi): per questo l'audit riporta count e head da confrontare con un riscontro
indipendente (--expect-v3 FILE.json: {"<db_id>": {"count": N, "head": "<sha256>"}}).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
from typing import Any, Optional
from urllib.parse import quote

if not getattr(sys, "_phase0_sealed", False):          # bundle sigillato: nessuna modifica di sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inventory as inv  # noqa: E402
from snapshot import inside_git, mkdirs_private, safe_new_dir  # noqa: E402

GENESIS = "0" * 64
MAX_WINDOW_WARN_S = 900


def _digest(prev: str, event_id: str, portfolio: str, run: str, kind: str, ts: int, source: str, payload: str) -> str:
    # Stessa formula di backend/v3/events.py::_digest (ricopiata, non importata).
    fields = [prev, event_id, portfolio, run, kind, str(ts), source, payload]
    return hashlib.sha256(json.dumps(fields, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def ro_connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect("file:" + quote(path, safe="/") + "?mode=ro", uri=True, timeout=2)
    con.execute("PRAGMA query_only=1")
    return con


def verify_v3_chain(path: str) -> dict:
    """Ricalcola la catena di v3_events. Ritorna {present, ok, count, head, max_seq, per_run, errors, warnings}."""
    con = ro_connect(path)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v3_events'").fetchone():
            return {"present": False}
        errors: list[str] = []
        warns: list[str] = []
        prev, count, last_seq, ids = GENESIS, 0, None, set()
        per_run: dict[str, int] = {}
        for (seq, eid, pf, run, kind, ts, src, payload, ph, eh) in con.execute(
                "SELECT seq,event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                "previous_hash,event_hash FROM v3_events ORDER BY seq"):
            if last_seq is not None and seq != last_seq + 1:
                warns.append("seq_gap")
            if eid in ids:
                errors.append("duplicate_event_id")
            ids.add(eid)
            if ph != prev:
                errors.append("previous_hash_mismatch")
            elif eh != _digest(prev, eid, pf, run, kind, ts, src, payload):
                errors.append("event_hash_mismatch")
            try:
                if json.dumps(json.loads(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                              allow_nan=False) != payload:
                    warns.append("payload_not_canonical")
            except ValueError:
                errors.append("payload_not_json")
            if errors:
                break                                       # catena rotta: il resto non e' attendibile
            prev, last_seq, count = eh, seq, count + 1
            per_run[f"{pf}/{run}"] = per_run.get(f"{pf}/{run}", 0) + 1
        return {"present": True, "ok": not errors, "count": count, "head": prev, "max_seq": last_seq,
                "per_run": per_run, "errors": sorted(set(errors)), "warnings": sorted(set(warns))}
    finally:
        con.close()


def restore(snapshot_dir: str, restore_dir: str) -> dict:
    log_path = os.path.join(snapshot_dir, "snapshot_log.json")
    with open(log_path, encoding="utf-8") as fh:
        log = json.load(fh)
    rd = os.path.abspath(restore_dir)
    sd = os.path.realpath(snapshot_dir)
    rreal = os.path.join(os.path.realpath(os.path.dirname(rd)), os.path.basename(rd))
    if rreal == sd or rreal.startswith(sd + os.sep) or sd.startswith(rreal + os.sep):
        raise ValueError("restore_dir_overlaps_snapshot")
    rd = safe_new_dir(rd)                           # deve essere NUOVA: mai riusare o toccare directory esistenti
    restored, bad = [], []
    for it in log["items"]:
        if it["status"] != "OK":
            continue
        src = os.path.join(snapshot_dir, it["dst_rel"])
        dst = os.path.join(rd, it["dst_rel"])
        mkdirs_private(rd, os.path.dirname(it["dst_rel"]))
        try:
            with open(src, "rb") as fi, open(dst, "xb") as fo:
                while True:
                    b = fi.read(inv.CHUNK)
                    if not b:
                        break
                    fo.write(b)
        except OSError as exc:
            bad.append({"id": it["id"], "error": type(exc).__name__})
            continue
        restored.append(it["dst_rel"])
    return {"restored": restored, "restore_errors": bad, "log": log}


def audit(restore_dir: str, log: dict, expect_v3: Optional[dict] = None) -> dict:
    fails: list[dict] = []
    warns: list[dict] = []
    checks: dict[str, Any] = {}

    def fail(code: str, **kw):
        fails.append({"code": code, **kw})

    def warn(code: str, **kw):
        warns.append({"code": code, **kw})

    expected = {it["dst_rel"]: it for it in log["items"] if it["status"] == "OK"}
    for it in log["items"]:
        if it["status"] != "OK":
            fail("snapshot_item_not_ok", id=it["id"], reason=it.get("reason"))
    present = set()
    for d, _, fs in os.walk(restore_dir, followlinks=False):
        for n in fs:
            present.add(os.path.relpath(os.path.join(d, n), restore_dir))
    for rel in sorted(set(expected) - present):
        fail("missing_file", id=expected[rel]["id"])
    for rel in sorted(present - set(expected)):
        fail("extra_file", path=rel)

    chains = {}
    for rel, it in sorted(expected.items()):
        p = os.path.join(restore_dir, rel)
        if rel not in present:
            continue
        r = inv.read_regular(p, parse_jsonl=(it["kind"] == "jsonl"))
        if r.get("special"):
            fail("not_regular_after_restore", id=it["id"])
            continue
        if r["sha256"] != it["sha256"]:
            fail("sha256_mismatch", id=it["id"])
        if it.get("attempts", 1) > 1:
            warn("copy_needed_retries", id=it["id"], attempts=it["attempts"])
        if it.get("partial_tail_bytes"):
            warn("partial_tail_excluded", id=it["id"], bytes=it["partial_tail_bytes"])
        if it["kind"] == "jsonl":
            res = r["_js"].result(False)
            for k in ("lines", "invalid_lines"):
                if res[k] != it.get(k):
                    fail("jsonl_count_mismatch", id=it["id"], field=k)
        if it["kind"] == "sqlite":
            for suffix in inv.DB_SIDE:
                if os.path.lexists(p + suffix):
                    warn("wal_or_journal_residue", id=it["id"])
            try:
                con = ro_connect(p)
                try:
                    ic = [x[0] for x in con.execute("PRAGMA integrity_check").fetchall()]
                    if ic != ["ok"]:
                        fail("integrity_check_failed", id=it["id"])
                    for t, n in (it.get("tables") or {}).items():
                        got = con.execute('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
                        if got != n:
                            fail("row_count_mismatch", id=it["id"], table=t)
                finally:
                    con.close()
                ch = verify_v3_chain(p)
                if ch["present"]:
                    chains[it["id"]] = ch
                    for e in ch["errors"]:
                        fail("v3_chain_" + e, id=it["id"])
                    for w in ch["warnings"]:
                        warn("v3_chain_" + w, id=it["id"])
                    ex = (expect_v3 or {}).get(it["id"])
                    if ex is not None and (ex.get("count") != ch["count"] or ex.get("head") != ch["head"]):
                        fail("v3_chain_external_anchor_mismatch", id=it["id"])
                    if ex is None:
                        warn("v3_chain_no_external_anchor", id=it["id"])
            except sqlite3.Error as exc:
                fail("sqlite_open_or_query_failed", id=it["id"], error=type(exc).__name__)
    if log.get("window_seconds", 0) > MAX_WINDOW_WARN_S:
        warn("capture_window_long", seconds=log["window_seconds"])
    checks["v3_chains"] = {k: {kk: v[kk] for kk in ("ok", "count", "head", "max_seq", "per_run")}
                           for k, v in chains.items()}
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")
    blockers = ["same_host_copy", "capture_not_atomic_across_sources"]
    if any(w["code"] == "v3_chain_no_external_anchor" for w in warns):
        blockers.append("no_external_anchor")
    return {"schema": 1, "certifies_backup": False, "certification_blockers": blockers, "classification": "PRIVATE_DO_NOT_COMMIT", "verdict": verdict, "fails": fails,
            "warnings": warns, "notes": ["capture_not_atomic_across_sources"], "checks": checks, "items_expected": len(expected), "files_present": len(present)}


def summary_of(rep: dict) -> dict:
    return {"schema": 1, "classification": "PUBLIC_SUMMARY_NUMBERS_ONLY", "verdict": rep["verdict"],
            "certifies_backup": False, "certification_blockers": rep["certification_blockers"],
            "fail_codes": sorted({f["code"] for f in rep["fails"]}),
            "warning_codes": sorted({w["code"] for w in rep["warnings"]}),
            "items_expected": rep["items_expected"], "files_present": rep["files_present"],
            "v3_chains_ok": sum(1 for c in rep["checks"]["v3_chains"].values() if c["ok"]),
            "v3_chains_total": len(rep["checks"]["v3_chains"])}


def _write_new(path: str, data: dict, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True, help="directory prodotta da snapshot.py")
    ap.add_argument("--restore-dir", required=True, help="directory VUOTA di ripristino")
    ap.add_argument("--report", required=True, help="report PRIVATO (nuovo file, 0600, fuori da repo git)")
    ap.add_argument("--summary", help="riepilogo con soli codici e numeri")
    ap.add_argument("--expect-v3", help="JSON con ancore esterne {db_id: {count, head}}")
    a = ap.parse_args(argv)
    for p in (a.report, a.summary):
        if p and (os.path.lexists(p) or inv.inside_git_worktree(p)):
            print("NO-GO: output esistente o dentro un working tree git")
            return 1
    if inside_git(a.restore_dir):
        print("NO-GO: la directory di ripristino non puo' stare in un working tree git")
        return 1
    try:
        res = restore(a.snapshot, a.restore_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"NO-GO: ripristino non eseguibile ({type(exc).__name__}: {str(exc)[:80]})")
        return 1
    expect = None
    if a.expect_v3:
        with open(a.expect_v3, encoding="utf-8") as fh:
            expect = json.load(fh)
    rep = audit(a.restore_dir, res["log"], expect)
    for e in res["restore_errors"]:
        rep["fails"].append({"code": "restore_copy_failed", **e})
    if res["restore_errors"]:
        rep["verdict"] = "FAIL"
    _write_new(a.report, rep, 0o600)
    if a.summary:
        _write_new(a.summary, summary_of(rep), 0o644)
    print(f"{'GO' if rep['verdict'] != 'FAIL' else 'NO-GO'}: audit={rep['verdict']} "
          f"fails={len(rep['fails'])} warnings={len(rep['warnings'])} certifies_backup=False "
          f"blockers={','.join(rep['certification_blockers'])}")
    return 0 if rep["verdict"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
