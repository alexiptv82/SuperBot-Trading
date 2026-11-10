"""Prove del backup cifrato di Brain V3 (brain_v3_snapshot.py, external_backup_brain_v3.py, restore_brain_v3_backup.py).

Si lanciano con:  python3 -m unittest deploy/scripts/test_brain_v3_backup.py -v
Servono `age`, `age-keygen` e `git`; tutto il resto e' sintetico: nessun server, nessuna chiave vera, nessun dato vero,
repository "remoti" locali in cartelle temporanee. Quello che non si puo' eseguire si SALTA e lo dice (SKIP, mai PASS):
  - senza age/git le prove di cifratura e di invio;
  - senza SUPERBOT_RC84_SRC (checkout di RC84, es. SUPERBOT_RC84_SRC=/percorso/SuperBot-Trading) le prove di confronto con
    il codice VERO di RC84 (run preparata dal programma vero, catena e impronta dei limiti ufficiali).

I "vettori d'oro" (catena hash e impronte dei limiti) sono stati prodotti dal codice vero di RC84 (0e29a73) e incollati qui:
verificano le formule ricalcolate da brain_v3_snapshot.py anche dove RC84 non c'e'.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brain_v3_snapshot as S                                   # noqa: E402
import age_recipients as AR                                     # noqa: E402

PIPE = os.path.join(HERE, "external_backup_brain_v3.py")
RESTORE = os.path.join(HERE, "restore_brain_v3_backup.py")
HAVE_AGE = bool(shutil.which("age") and shutil.which("age-keygen") and shutil.which("git"))
RC84 = os.environ.get("SUPERBOT_RC84_SRC", "")
HAVE_RC84 = bool(RC84) and os.path.isfile(os.path.join(RC84, "backend", "v3", "events.py"))

# --- vettori d'oro dal codice vero di RC84 0e29a73 (EventJournal.append / _policy_hash) ---
GOLDEN_ROWS = [
    (1, "v3-prepared-abc", "brain", "run-g", "run_prepared", 1760000000000, "rc_setup",
     '{"config_sha256":"' + "a" * 64 + '","initial_equity":"1000","mandate_approved":false,"paper_only":true,'
     '"paused":true,"schema_version":1}', "0" * 64,
     "e18f4e2d596b387c8b46a61a4a868f720eacd7f42162a35f399c82af70efacc0"),
    (2, "brain-g-1", "brain", "run-g", "brain_decision", 1760000060000, "brain_f2_engine",
     '{"claim":"c1","kind":"no_trade","rationale":"sanitized","regime":"UNKNOWN","sources":[],"status":"rejected",'
     '"symbol":"BTCUSDT"}', "e18f4e2d596b387c8b46a61a4a868f720eacd7f42162a35f399c82af70efacc0",
     "39ccf82c016cb9028b5971d9136fe8bdefef6e8e87f5795bf6fe958bfb4d8eba"),
    (3, "paper_open.p1", "brain", "run-g", "paper_open", 1760000120000, "executor.paper",
     '{"fill_price":"100","leverage":10,"margin_used":"10","position_id":"p1","quantity":"1","side":1,'
     '"symbol":"BTCUSDT"}', "39ccf82c016cb9028b5971d9136fe8bdefef6e8e87f5795bf6fe958bfb4d8eba",
     "56efe51993efa2175d1d7637858e548c0940bf492087cddd55ab6ec4ea544953"),
    (4, "paper_close.p1", "brain", "run-g", "paper_close", 1760000180000, "executor.paper_close",
     '{"opened_at_ms":1760000120000,"position_id":"p1","realized_pnl":"1","side":1,"symbol":"BTCUSDT"}',
     "56efe51993efa2175d1d7637858e548c0940bf492087cddd55ab6ec4ea544953",
     "0da4802176e22a53402fa09d3142c81d4ed6317c829224d10dc36c04b5910630"),
    (5, "paper_open.p2", "brain", "run-g", "paper_open", 1760000240000, "executor.paper",
     '{"fill_price":"50","leverage":5,"margin_used":"5","position_id":"p2","quantity":"2","side":-1,'
     '"symbol":"ETHUSDT"}', "0da4802176e22a53402fa09d3142c81d4ed6317c829224d10dc36c04b5910630",
     "d4f84bace4232c3d50553db93e1301d90cabfd327456b5ceda9503c6a09c9aee"),
]
GOLDEN_HEAD = "d4f84bace4232c3d50553db93e1301d90cabfd327456b5ceda9503c6a09c9aee"
RISK_DEFAULT = {"estimated_roundtrip_cost_bp": "16", "liquidation_buffer_fraction": "0.5", "max_loss_fraction": "0.02",
                "max_open_risk_fraction": "0.05", "max_position_margin_fraction": "0.1",
                "max_total_margin_fraction": "0.3", "minimum_equity": "450"}
RISK_PROFILE = {"estimated_roundtrip_cost_bp": "16", "liquidation_buffer_fraction": "0.5", "max_leverage": 50,
                "max_loss_fraction": "0.042857142857142857", "max_loss_margin_fraction": "0.214285714285714285",
                "max_open_risk_fraction": "0.12", "max_position_margin_fraction": "0.20",
                "max_total_margin_fraction": "0.55", "min_leverage": 20, "minimum_equity": "450"}
POLICY_DEFAULT, POLICY_PROFILE = "c31ad48159749a03", "f1ddeb578537a50e"

# impronte dei file del backup di Falco/Toro al commit 521f7fd (gia' installato): l'estensione NON deve toccarli
CLASSIC_PINS = {
    "external_backup.py": "7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab",
    "restore_external_backup.py": "fa86e0cf41a380b21b467e6e51db1d7d523f144eab95726a04fd878c1a8c5532",
    "backup_brain.py": "4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c",
    "../extbackup/run.sh": "e6dc3efc37a2d151be470cfad73b31919b545334cbbe13e2dff18ecebc64e7c5",
    "../extbackup/install-wrapper.sh": "8d0ae1daf7bba8e861c7c33d348512aec05a9c08fcb58b3bc5df3a81ab113241",
}
SECRET = "SEGRETO-V3-7731"

JOURNAL_DDL = """
CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
  portfolio_id TEXT NOT NULL CHECK (portfolio_id IN ('hawk','bull','brain')), run_id TEXT NOT NULL, kind TEXT NOT NULL,
  occurred_at_ms INTEGER NOT NULL, source TEXT NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL);
CREATE INDEX ix_v3_portfolio_run ON v3_events(portfolio_id,run_id,seq);
CREATE TRIGGER v3_no_update BEFORE UPDATE ON v3_events BEGIN SELECT RAISE(ABORT,'v3_events_immutable'); END;
CREATE TRIGGER v3_no_delete BEFORE DELETE ON v3_events BEGIN SELECT RAISE(ABORT,'v3_events_immutable'); END;
"""


def digest(prev, eid, pf, rid, kind, at, src, pj):
    f = [prev, eid, pf, rid, kind, str(at), src, pj]
    return hashlib.sha256(json.dumps(f, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def jdump(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pin(recipient_file):
    """Impronta approvata dei destinatari di un file (cio' che i wrapper reali fissano)."""
    return AR.fingerprint(AR.read_recipients(recipient_file))


def sh(*cmd, cwd=None, check=True, env=None):
    p = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, timeout=300, env=env)
    if check and p.returncode != 0:
        raise AssertionError("%s -> %s" % (cmd, p.stdout + p.stderr))
    return p


def keygen(path):
    sh("age-keygen", "-o", path)
    os.chmod(path, 0o600)
    return sh("age-keygen", "-y", path).stdout.strip()


def append_event(db_path, run_id, kind, payload, event_id, at_ms, source="brain_f2_engine", portfolio="brain"):
    """Scrive come EventJournal.append (BEGIN IMMEDIATE, catena sull'ultimo evento di TUTTA la tabella)."""
    pj = jdump(payload)
    con = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT event_hash FROM v3_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row[0] if row else "0" * 64
        con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                    "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                    (event_id, portfolio, run_id, kind, at_ms, source, pj, prev,
                     digest(prev, event_id, portfolio, run_id, kind, at_ms, source, pj)))
        con.execute("COMMIT")
    finally:
        con.close()


def writer_loop(db_path, run_id, seconds):
    end = time.time() + seconds
    i = 0
    while time.time() < end:
        i += 1
        append_event(db_path, run_id, "brain_decision", {"n": i}, "w-%s-%d" % (os.getpid(), i),
                     int(time.time() * 1000))
        time.sleep(0.002)


class Run:
    """Cartella di una run Brain V3 sintetica, costruita come prepare_new_paper_run (ma senza il codice di RC84)."""

    def __init__(self, parent, name="brain-v3-run1", run_id=None, equity="1000", profile=False):
        self.dir = os.path.join(parent, name)
        self.name, self.run_id = name, run_id or name
        self.equity, self.profile = equity, profile
        self.t0 = int(time.time() * 1000)
        self.build()

    @property
    def journal(self):
        return os.path.join(self.dir, "journal.db")

    @property
    def budget(self):
        return os.path.join(self.dir, "budget.db")

    def cfg_bytes(self):
        cfg = {"schema_version": 1, "symbols": ["BTCUSDT", "ETHUSDT"], "initial_equity": self.equity,
               "slippage_bps": 2, "fee_bps": "6", "maintenance_fraction": "0.004",
               "risk_policy": RISK_PROFILE if self.profile else RISK_DEFAULT, "model": "m-1", "thinking": "omit",
               "reasoning_effort": "omit", "max_tokens": 2048, "cycle_minutes": 60,
               "input_usd_per_million_tokens": "0.28", "output_usd_per_million_tokens": "0.42", "daily_cap_usd": "1",
               "daily_loss_warn_fraction": "0.35", "daily_loss_halt_fraction": "0.5"}
        return (jdump(cfg) + "\n").encode()

    def build(self):
        os.makedirs(self.dir, mode=0o700)
        cfg = self.cfg_bytes()
        with open(os.path.join(self.dir, "runner_config.json"), "wb") as f:
            f.write(cfg)
        with open(os.path.join(self.dir, "PREPARED_PAUSED_ONLY.json"), "w") as f:
            f.write(jdump({"run_id": self.run_id, "portfolio_id": "brain", "paper_only": True, "paused": True,
                           "mandate_approved": False, "config_sha256": sha(cfg), "initial_equity": self.equity}))
        with open(os.path.join(self.dir, "mandate.json"), "w") as f:
            f.write(jdump({"version": "v1", "approved": False, "approved_by": "", "portfolio_id": "brain",
                           "run_id": self.run_id, "policy_hash": POLICY_PROFILE if self.profile else POLICY_DEFAULT}))
        with open(os.path.join(self.dir, "pause.flag"), "w") as f:
            f.write("prepared_and_paused\n")
        con = sqlite3.connect(self.journal)
        con.executescript(JOURNAL_DDL)
        con.close()
        con = sqlite3.connect(self.budget)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE spend_events (id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, "
                    "provider TEXT NOT NULL, units INTEGER NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
        con.commit()
        con.close()
        append_event(self.journal, self.run_id, "run_prepared",
                     {"paper_only": True, "paused": True, "mandate_approved": False, "initial_equity": self.equity,
                      "config_sha256": sha(cfg), "schema_version": 1},
                     "v3-prepared-" + sha(self.run_id.encode())[:20], self.t0, source="rc_setup")

    def decision(self, n, rationale="sanitized"):
        append_event(self.journal, self.run_id, "brain_decision",
                     {"kind": "no_trade", "status": "rejected", "rationale": rationale, "sources": [],
                      "claim": "c%d" % n, "symbol": "BTCUSDT", "regime": "UNKNOWN"},
                     "%s-d%d" % (self.name, n), self.t0 + 1000 * n)

    def open(self, pid, symbol="BTCUSDT", side=1, at=None):
        append_event(self.journal, self.run_id, "paper_open",
                     {"position_id": pid, "symbol": symbol, "side": side, "fill_price": "100", "quantity": "1",
                      "margin_used": "10", "leverage": 10}, "paper_open." + pid, at or self.t0 + 5000,
                     source="executor.paper")

    def close(self, pid, symbol="BTCUSDT", side=1, opened=None, at=None):
        append_event(self.journal, self.run_id, "paper_close",
                     {"position_id": pid, "symbol": symbol, "side": side, "opened_at_ms": opened or self.t0 + 5000,
                      "realized_pnl": "1"}, "paper_close." + pid, at or self.t0 + 9000, source="executor.paper_close")

    def spend(self, units=100, at=None):
        con = sqlite3.connect(self.budget)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("INSERT INTO spend_events(occurred_at,provider,units,metadata) VALUES(?,?,?,?)",
                    ((at or datetime.now(timezone.utc)).isoformat(), "deepseek", units, '{"basis":"usage"}'))
        con.commit()
        con.close()

    def write(self, name, data):
        with open(os.path.join(self.dir, name), "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)


def slurp(path):
    with open(path, "rb") as f:
        return f.read()


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def spit(path, text):
    with open(path, "wb" if isinstance(text, bytes) else "w") as f:
        f.write(text)


def lines_of(path):
    with open(path) as f:
        return f.read().splitlines()


def tree_state(root):
    """(percorso -> (tipo, dimensione, mtime_ns, sha256)) di TUTTO l'albero: per provare che la sorgente non cambia."""
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in dn + fn:
            full = os.path.join(dp, n)
            st = os.lstat(full)
            h = sha(slurp(full)) if os.path.isfile(full) and not os.path.islink(full) else None
            out[os.path.relpath(full, root)] = (st.st_mode, st.st_size, st.st_mtime_ns, h)
    return out


def rows_of(db, sql):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def capture(run, now_ms=None, **kw):
    stage = tempfile.mkdtemp(prefix="stage-")
    try:
        return S.capture_run(run.dir, os.path.join(stage, run.name), now_ms or int(time.time() * 1000) + 1000, **kw)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


class SnapshotCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.td.name, "runs")
        os.makedirs(self.root)

    def tearDown(self):
        self.td.cleanup()

    def refused(self, code, fn, *a, **k):
        with self.assertRaises(S.Refused) as cm:
            fn(*a, **k)
        self.assertEqual(cm.exception.code, code, str(cm.exception))
        return cm.exception


class GoldenAndJournalTests(SnapshotCase):
    def test_golden_chain_from_real_rc84_is_reproduced_event_by_event(self):
        for i, r in enumerate(GOLDEN_ROWS):
            prev = "0" * 64 if i == 0 else GOLDEN_ROWS[i - 1][9]
            self.assertEqual(S._journal_digest(prev, r[1], r[2], r[3], r[4], r[5], r[6], r[7]), r[9])
        self.assertEqual(GOLDEN_ROWS[-1][9], GOLDEN_HEAD)

    def test_golden_policy_hash_matches_real_rc84_for_both_config_shapes(self):
        self.assertEqual(S.policy_hash_from_config({"risk_policy": RISK_DEFAULT}), POLICY_DEFAULT)
        self.assertEqual(S.policy_hash_from_config({"risk_policy": RISK_PROFILE}), POLICY_PROFILE)

    def test_valid_run_is_certified_with_expected_facts(self):
        r = Run(self.root)
        r.decision(1)
        r.open("p1")
        r.open("p2", "ETHUSDT", -1)
        r.close("p1")
        r.spend(250)
        f = capture(r)
        j = f["journal"]
        self.assertEqual((j["eventi"], j["seq_max"]), (5, 5))
        self.assertEqual(j["paper"]["aperte_totali"], 2)
        self.assertEqual(j["paper"]["chiuse"], 1)
        self.assertEqual(j["paper"]["ids_aperte"], ["p2"])
        self.assertEqual(f["budget"]["righe"], 1)
        self.assertEqual(f["budget"]["unita"], 250)
        self.assertEqual(f["config"]["policy_hash"], POLICY_DEFAULT)
        self.assertTrue(f["controllo"]["in_pausa"])

    def test_altered_event_payload_breaks_the_chain(self):
        r = Run(self.root)
        r.decision(1)
        r.decision(2)
        con = sqlite3.connect(r.journal)
        con.execute("DROP TRIGGER v3_no_update")                      # chi altera davvero toglie i trigger
        con.execute("UPDATE v3_events SET payload_json=replace(payload_json,'sanitized','ALTERATO') WHERE seq=2")
        con.execute("CREATE TRIGGER v3_no_update BEFORE UPDATE ON v3_events BEGIN SELECT RAISE(ABORT,'x'); END")
        con.commit()
        con.close()
        self.refused("journal_chain_invalid", capture, r)

    def test_deleted_middle_event_breaks_the_chain(self):
        r = Run(self.root)
        for n in (1, 2, 3):
            r.decision(n)
        con = sqlite3.connect(r.journal)
        con.execute("DROP TRIGGER v3_no_delete")
        con.execute("DELETE FROM v3_events WHERE seq=3")
        con.execute("CREATE TRIGGER v3_no_delete BEFORE DELETE ON v3_events BEGIN SELECT RAISE(ABORT,'x'); END")
        con.commit()
        con.close()
        self.refused("journal_chain_invalid", capture, r)

    def test_missing_immutability_triggers_refused(self):
        r = Run(self.root)
        con = sqlite3.connect(r.journal)
        con.execute("DROP TRIGGER v3_no_delete")
        con.commit()
        con.close()
        self.refused("journal_schema_unexpected", capture, r)

    def test_event_of_another_run_inside_the_journal_is_refused(self):
        r = Run(self.root)
        append_event(r.journal, "altra-run", "brain_decision", {"x": 1}, "foreign-1", r.t0 + 10)
        self.refused("journal_identity_mixed", capture, r)

    def test_close_without_open_and_wrong_open_time_are_refused(self):
        r = Run(self.root)
        r.close("ghost")
        self.refused("paper_incoherent", capture, r)
        r2 = Run(self.root, "brain-v3-test2")
        r2.open("p1")
        r2.close("p1", opened=r2.t0 + 1)                              # opened_at_ms non coincide con l'apertura
        self.refused("paper_incoherent", capture, r2)

    def test_journal_without_prepared_event_is_refused(self):
        r = Run(self.root)
        con = sqlite3.connect(r.journal)
        con.executescript("DROP TRIGGER v3_no_delete; DELETE FROM v3_events; "
                          "CREATE TRIGGER v3_no_delete BEFORE DELETE ON v3_events BEGIN SELECT RAISE(ABORT,'x'); END;")
        con.close()
        self.refused("journal_empty", capture, r)


class CoherenceAndIdentityTests(SnapshotCase):
    def test_two_runs_with_different_identities_keep_separate_facts(self):
        a = Run(self.root, "brain-v3-alfa1", equity="1000")
        b = Run(self.root, "brain-v3-beta1", equity="2000", profile=True)
        b.decision(1)
        fa, fb = capture(a), capture(b)
        self.assertNotEqual(fa["identita_sha256"], fb["identita_sha256"])
        self.assertEqual((fa["config"]["capitale_iniziale"], fb["config"]["capitale_iniziale"]), ("1000", "2000"))
        self.assertEqual((fa["config"]["policy_hash"], fb["config"]["policy_hash"]), (POLICY_DEFAULT, POLICY_PROFILE))
        self.assertNotEqual(fa["journal"]["testa"], fb["journal"]["testa"])

    def test_mandate_of_another_run_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1")
        b = Run(self.root, "brain-v3-beta1")
        shutil.copyfile(os.path.join(b.dir, "mandate.json"), os.path.join(a.dir, "mandate.json"))
        self.refused("mandate_run_mismatch", capture, a)

    def test_config_of_another_run_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1", equity="1000")
        b = Run(self.root, "brain-v3-beta1", equity="2000")
        shutil.copyfile(os.path.join(b.dir, "runner_config.json"), os.path.join(a.dir, "runner_config.json"))
        self.refused("config_hash_mismatch", capture, a)

    def test_marker_of_another_run_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1")
        b = Run(self.root, "brain-v3-beta1")
        shutil.copyfile(os.path.join(b.dir, "PREPARED_PAUSED_ONLY.json"), os.path.join(a.dir, "PREPARED_PAUSED_ONLY.json"))
        with self.assertRaises(S.Refused) as cm:                      # qualunque incoerenza di identita' blocca la copia
            capture(a)
        self.assertIn(cm.exception.code, ("mandate_run_mismatch", "config_hash_mismatch", "marker_mismatch",
                                          "journal_identity_mixed"))

    def test_mandate_with_other_limits_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1")
        m = jload(os.path.join(a.dir, "mandate.json"))
        m["policy_hash"] = "0" * 16
        a.write("mandate.json", jdump(m))
        self.refused("mandate_policy_mismatch", capture, a)

    def test_budget_of_an_older_run_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1")
        a.spend(10, at=datetime.fromtimestamp(a.t0 / 1000 - 86400 * 3, timezone.utc))
        self.refused("budget_run_mismatch", capture, a)

    def test_budget_in_the_future_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1")
        a.spend(10, at=datetime.fromtimestamp(time.time() + 86400, timezone.utc))
        self.refused("budget_run_mismatch", capture, a)

    def test_heartbeat_of_another_run_is_refused(self):
        a = Run(self.root, "brain-v3-alfa1")
        a.write("heartbeat.json", jdump({"ts_ms": int(time.time() * 1000), "run_id": "altra", "state": "paused"}))
        self.refused("heartbeat_run_mismatch", capture, a)

    def test_runs_in_different_directories_never_mix_in_one_snapshot(self):
        Run(self.root, "brain-v3-alfa1")
        Run(self.root, "brain-v3-beta1", equity="2000")
        stage = os.path.join(self.td.name, "stage")
        facts, ignored = S.build_runs_snapshot(self.root, stage, int(time.time() * 1000) + 1000, attempts=1)
        self.assertEqual(sorted(f["run_name"] for f in facts), ["brain-v3-alfa1", "brain-v3-beta1"])
        self.assertTrue(os.path.isfile(os.path.join(stage, "runs", "brain-v3-alfa1", "journal.db")))
        self.assertTrue(os.path.isfile(os.path.join(stage, "runs", "brain-v3-beta1", "journal.db")))
        self.assertNotEqual(facts[0]["journal"]["testa"], facts[1]["journal"]["testa"])

    def test_a_copy_of_a_run_under_another_name_is_refused_as_duplicated_identity(self):
        a = Run(self.root, "brain-v3-alfa1")
        a.decision(1)
        shutil.copytree(a.dir, os.path.join(self.root, "brain-v3-copia1"))
        e = self.refused("runs_not_certifiable", S.build_runs_snapshot, self.root, os.path.join(self.td.name, "stage"),
                         int(time.time() * 1000) + 1000, attempts=1)
        self.assertEqual(sorted((n, c) for n, c, _ in e.failures),
                         [("brain-v3-alfa1", "identity_duplicated"), ("brain-v3-copia1", "identity_duplicated")])

    def test_directory_name_different_from_run_id_is_reported_not_refused(self):
        a = Run(self.root, "brain-v3-alfa1", run_id="altro-id-run")
        self.assertFalse(capture(a)["nome_cartella_uguale_a_run_id"])

    def test_one_broken_run_blocks_the_whole_snapshot_and_names_it(self):
        Run(self.root, "brain-v3-alfa1")
        b = Run(self.root, "brain-v3-beta1")
        os.unlink(b.budget)
        e = self.refused("runs_not_certifiable", S.build_runs_snapshot, self.root,
                         os.path.join(self.td.name, "stage"), int(time.time() * 1000) + 1000, attempts=1)
        self.assertEqual([(n, c) for n, c, _ in e.failures], [("brain-v3-beta1", "file_missing")])


class MissingTruncatedAndSourceTests(SnapshotCase):
    def test_missing_files_are_refused_and_never_recreated_in_the_source(self):
        for victim in ("journal.db", "budget.db", "runner_config.json", "PREPARED_PAUSED_ONLY.json", "mandate.json"):
            with self.subTest(victim=victim):
                r = Run(self.root, "brain-v3-m-%s" % victim.split(".")[0].lower().replace("_", "")[:10])
                os.unlink(os.path.join(r.dir, victim))
                before = tree_state(r.dir)
                self.refused("file_missing", capture, r)
                self.assertEqual(tree_state(r.dir), before)         # nessun database vuoto al posto del file assente
                self.assertFalse(os.path.exists(os.path.join(r.dir, victim)))

    def test_truncated_databases_are_refused(self):
        for victim in ("journal.db", "budget.db"):
            with self.subTest(victim=victim):
                r = Run(self.root, "brain-v3-t-" + victim[:3])
                r.decision(1)
                data = slurp(os.path.join(r.dir, victim))
                with open(os.path.join(r.dir, victim), "wb") as f:
                    f.write(data[: len(data) // 2])
                with self.assertRaises(S.Refused):
                    capture(r)

    def test_truncated_config_and_garbage_database_are_refused(self):
        r = Run(self.root, "brain-v3-cfg")
        raw = slurp(os.path.join(r.dir, "runner_config.json"))
        r.write("runner_config.json", raw[:40])
        self.refused("config_invalid", capture, r)
        r2 = Run(self.root, "brain-v3-gar")
        r2.write("budget.db", b"questo non e' sqlite" * 20)
        self.refused("sqlite_not_a_database", capture, r2)

    def test_unexpected_directory_or_symlink_in_the_run_is_refused(self):
        r = Run(self.root, "brain-v3-dir")
        os.mkdir(os.path.join(r.dir, "sconosciuta"))
        self.refused("unexpected_entry", capture, r)
        os.rmdir(os.path.join(r.dir, "sconosciuta"))
        os.symlink("/etc/hostname", os.path.join(r.dir, "collegamento"))
        self.refused("unexpected_entry", capture, r)

    def test_symlinked_database_is_refused(self):
        r = Run(self.root, "brain-v3-lnk")
        shutil.move(r.journal, os.path.join(self.td.name, "altrove.db"))
        os.symlink(os.path.join(self.td.name, "altrove.db"), r.journal)
        self.refused("file_unsafe", capture, r)

    def test_real_hot_rollback_journal_is_refused_and_left_alone(self):
        r = Run(self.root, "brain-v3-hot")
        for n in range(1, 40):
            r.decision(n)
        crash = ("import sqlite3, os, sys\n"
                 "con = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
                 "con.execute('PRAGMA cache_size=2')\ncon.execute('BEGIN EXCLUSIVE')\n"
                 "con.execute('CREATE TABLE junk(x)')\n"
                 "for i in range(3000): con.execute('INSERT INTO junk VALUES(?)', ('z' * 300,))\nos._exit(0)\n")
        subprocess.run([sys.executable, "-c", crash, r.journal], check=True)       # arresto brusco a meta' transazione
        self.assertGreater(os.path.getsize(r.journal + "-journal"), 0)
        before = tree_state(r.dir)
        self.refused("hot_journal", capture, r)
        self.assertEqual(tree_state(r.dir), before)                  # nessun recupero, nessuna modifica

    def test_wal_sidecar_alone_is_unexpected(self):
        r = Run(self.root, "brain-v3-wal")
        r.write("budget.db-wal", b"")
        self.refused("wal_sidecar_state_unexpected", capture, r)

    def test_unknown_small_file_is_copied_as_extra_with_original_path(self):
        r = Run(self.root, "brain-v3-xtr")
        r.write("nota.txt", "appunti dell'operatore\n")
        f = capture(r)
        (e,) = f["extra"]
        self.assertEqual((e["nome"], e["archiviato_in"], e["size"]), ("nota.txt", "extra/nota.txt", 23))
        self.assertEqual(e["percorso_originale"], os.path.join(r.dir, "nota.txt"))
        self.assertEqual(e["sha256"], sha(b"appunti dell'operatore\n"))

    def test_empty_runs_root_means_nothing_to_protect(self):
        facts, ignored = S.build_runs_snapshot(os.path.join(self.td.name, "non-esiste"), os.path.join(self.td.name, "s"),
                                               int(time.time() * 1000), attempts=1)
        self.assertEqual(facts, [])

    def test_quiescent_wal_budget_creates_no_files_in_the_source(self):
        r = Run(self.root, "brain-v3-quiet1")
        r.spend(5)
        before_list, before = sorted(os.listdir(r.dir)), tree_state(r.dir)
        capture(r)
        self.assertEqual(sorted(os.listdir(r.dir)), before_list)
        self.assertEqual(tree_state(r.dir), before)
        self.assertFalse([n for n in os.listdir(r.dir) if n.endswith(("-wal", "-shm"))])

    def test_live_wal_writer_rows_are_in_the_copy_and_source_is_untouched(self):
        r = Run(self.root, "brain-v3-live")
        r.spend(1)
        w = sqlite3.connect(r.budget)                                 # processo "vivo": WAL con righe non ancora nel file
        w.execute("PRAGMA journal_mode=WAL")
        w.execute("PRAGMA wal_autocheckpoint=0")
        w.executemany("INSERT INTO spend_events(occurred_at,provider,units,metadata) VALUES(?,?,?,?)",
                      [(datetime.now(timezone.utc).isoformat(), "deepseek", 7, "{}")] * 30)
        w.commit()
        try:
            self.assertTrue(os.path.exists(r.budget + "-wal") and os.path.exists(r.budget + "-shm"))
            main_hash = sha(slurp(r.budget))
            listing = sorted(os.listdir(r.dir))
            f = capture(r)
            self.assertEqual(f["budget"]["righe"], 31)
            self.assertEqual(f["budget"]["unita"], 1 + 30 * 7)
            self.assertEqual(sha(slurp(r.budget)), main_hash)
            self.assertEqual(sorted(os.listdir(r.dir)), listing)
        finally:
            w.close()

    def test_copy_is_a_single_file_without_sidecars(self):
        r = Run(self.root, "brain-v3-sng")
        r.spend(3)
        stage = tempfile.mkdtemp(prefix="stage-")
        try:
            S.capture_run(r.dir, os.path.join(stage, r.name), int(time.time() * 1000) + 1000, attempts=1)
            self.assertEqual(sorted(os.listdir(os.path.join(stage, r.name))),
                             ["PREPARED_PAUSED_ONLY.json", "budget.db", "journal.db", "mandate.json", "pause.flag",
                              "runner_config.json"])
        finally:
            shutil.rmtree(stage, ignore_errors=True)


class ConcurrentWriteTests(SnapshotCase):
    def test_write_during_copy_is_refused_when_it_never_settles(self):
        r = Run(self.root)
        n = [0]

        def hook(attempt):
            n[0] += 1
            r.decision(100 + n[0])
        self.refused("source_changed_during_capture", capture, r, attempts=3, wait=0, hooks={"after_copy": hook})
        self.assertEqual(n[0], 3)

    def test_write_only_on_first_attempt_gives_a_consistent_second_snapshot(self):
        r = Run(self.root)

        def hook(attempt):
            if attempt == 1:
                r.decision(100)
        f = capture(r, attempts=3, wait=0, hooks={"after_copy": hook})
        self.assertEqual(f["journal"]["eventi"], 2)                  # la copia buona include l'evento arrivato in mezzo
        self.assertEqual(f["journal"]["testa"], rows_of(r.journal, "SELECT event_hash FROM v3_events ORDER BY seq DESC LIMIT 1")[0][0])

    def test_budget_change_during_copy_is_detected(self):
        r = Run(self.root)

        def hook(attempt):
            r.spend(5)
        self.refused("source_changed_during_capture", capture, r, attempts=2, wait=0, hooks={"after_copy": hook})

    def test_small_file_change_during_copy_is_detected(self):
        r = Run(self.root)

        def hook(attempt):
            r.write("pause.flag", "cambiato %d\n" % attempt)
        self.refused("source_changed_during_capture", capture, r, attempts=2, wait=0, hooks={"after_copy": hook})

    def test_real_concurrent_writer_process_never_yields_a_corrupt_snapshot(self):
        r = Run(self.root)
        code = "import sys; sys.path.insert(0, %r); import test_brain_v3_backup as t; t.writer_loop(%r, %r, 2.5)" % (
            HERE, r.journal, r.run_id)
        p = subprocess.Popen([sys.executable, "-c", code])
        ok = refused = 0
        try:
            end = time.time() + 2.0
            while time.time() < end:
                try:
                    f = capture(r, attempts=2, wait=0.01)
                    ok += 1
                    self.assertGreaterEqual(f["journal"]["eventi"], 1)
                except S.Refused as e:
                    self.assertEqual(e.code, "source_changed_during_capture")
                    refused += 1
        finally:
            p.wait(timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertGreater(ok + refused, 0)
        self.assertEqual(S.read_journal(r.journal, r.run_id)["eventi"], rows_of(r.journal, "SELECT COUNT(*) FROM v3_events")[0][0])


# ======================================================================================================
# Giro completo: pipeline di backup (age + repository git locale finto) e ripristino isolato
# ======================================================================================================

def plaintext_hits(gitdir, markers):
    hits = []
    objs = sh("git", "-C", gitdir, "cat-file", "--batch-all-objects", "--batch-check").stdout.split("\n")
    for line in objs:
        if not line.strip():
            continue
        oid, typ = line.split()[:2]
        if typ != "blob":
            continue
        data = subprocess.run(["git", "-C", gitdir, "cat-file", "blob", oid], capture_output=True, timeout=60).stdout
        hits += [m for m in markers if m in data]
    return hits


@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git: installare age per eseguire queste prove")
class PipelineCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = self.td.name
        self.runs = os.path.join(t, "runs")
        self.work = os.path.join(t, "work")
        self.remote = os.path.join(t, "remote.git")
        self.ident = os.path.join(t, "id.txt")
        self.recfile = os.path.join(t, "recipient.txt")
        os.makedirs(self.runs)
        self.pub = keygen(self.ident)
        with open(self.recfile, "w") as f:
            f.write("# prova\n%s\n" % self.pub)
        self.recpin = pin(self.recfile)
        sh("git", "init", "-q", "--bare", "-b", "main", self.remote)

    def tearDown(self):
        self.td.cleanup()

    def args(self, *extra, mode="v3", remote=None):
        return [sys.executable, "-I", PIPE, "--mode", mode, "--runs-root", self.runs, "--work", self.work,
                "--remote", remote or self.remote, "--recipient-file", self.recfile, "--tools", HERE,
                "--expect-recipients-sha256", self.recpin, "--push-wait", "0", "--attempt-wait", "0", *extra]

    def backup(self, *extra, mode="v3", env=None, remote=None):
        p = subprocess.run(self.args(*extra, mode=mode, remote=remote), capture_output=True, text=True, timeout=600,
                           env=env)
        return p.returncode, p.stdout + p.stderr

    def clone(self, branch="brain-v3"):
        dst = os.path.join(self.td.name, "clone-%d" % (time.time_ns()))
        sh("git", "clone", "-q", "--branch", branch, self.remote, dst)
        return dst

    def archives(self, clone, sub="brain-v3"):
        out = []
        for dp, _dn, fn in os.walk(os.path.join(clone, sub)):
            out += [os.path.join(dp, f) for f in fn if f.endswith(".tar.gz.age")]
        return sorted(out)

    def restore(self, archive, out=None, ident=None, *extra):
        out = out or os.path.join(self.td.name, "ripristino-%d" % time.time_ns())
        p = subprocess.run([sys.executable, "-I", RESTORE, "--archive", archive, "--identity", ident or self.ident,
                            "--out", out, *extra], capture_output=True, text=True, timeout=300)
        return p.returncode, p.stdout + p.stderr, out

    def status(self, mode="v3"):
        with open(os.path.join(self.work, mode, "status.json")) as f:
            return json.load(f)

    def populated_runs(self):
        a = Run(self.runs, "brain-v3-alfa1", equity="1000")
        for n in range(1, 4):
            a.decision(n, SECRET)
        a.open("p1")
        a.open("p2", "ETHUSDT", -1)
        a.close("p1")
        a.spend(120)
        a.spend(30)
        a.write("daily_loss.json", jdump({"day_start_ms": 1, "warn_sent": False, "halt_sent": False, "halt_latched": False}))
        a.write("heartbeat.json", jdump({"ts_ms": int(time.time() * 1000), "cycle": 3, "state": "paused",
                                         "run_id": a.run_id, "last_error": None, "exit_mode": "sidecar"}))
        a.write("close_request.json", jdump({"ts_ms": int(time.time() * 1000), "all": True}))
        a.write(".exit_service.lock", "0" * 32)
        b = Run(self.runs, "brain-v3-beta1", equity="2000", profile=True)
        b.decision(1)
        os.unlink(os.path.join(b.dir, "pause.flag"))                 # una run senza pausa: il ripristino la mettera' in pausa
        return a, b


class RoundTripTests(PipelineCase):
    def test_full_round_trip_two_runs_and_isolated_restore(self):
        a, b = self.populated_runs()
        before = tree_state(self.runs)
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertEqual(tree_state(self.runs), before, "la sorgente e' cambiata")
        clone = self.clone()
        (arc,) = self.archives(clone)
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        self.assertIn("RISULTATO: OK", rout)
        self.assertEqual(tree_state(self.runs), before, "la sorgente e' cambiata dopo il ripristino")
        base = os.path.join(dest, "dati", "runs")
        self.assertEqual(sorted(os.listdir(base)), ["brain-v3-alfa1", "brain-v3-beta1"])
        for r in (a, b):
            d = os.path.join(base, r.name)
            self.assertEqual(rows_of(os.path.join(d, "journal.db"), "SELECT * FROM v3_events ORDER BY seq"),
                             rows_of(r.journal, "SELECT * FROM v3_events ORDER BY seq"))
            self.assertEqual(rows_of(os.path.join(d, "budget.db"), "SELECT * FROM spend_events ORDER BY id"),
                             rows_of(r.budget, "SELECT * FROM spend_events ORDER BY id"))
            for n in ("runner_config.json", "PREPARED_PAUSED_ONLY.json", "mandate.json"):
                self.assertEqual(slurp(os.path.join(d, n)), slurp(os.path.join(r.dir, n)))
            trig = rows_of(os.path.join(d, "journal.db"), "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")
            self.assertEqual(trig, [("v3_no_delete",), ("v3_no_update",)])
        da = os.path.join(base, "brain-v3-alfa1")
        self.assertTrue(os.path.isfile(os.path.join(da, "daily_loss.json")))
        self.assertTrue(os.path.isfile(os.path.join(da, "transient", "heartbeat.json")))
        self.assertTrue(os.path.isfile(os.path.join(da, "transient", "close_request.json")))
        self.assertFalse(os.path.exists(os.path.join(da, ".exit_service.lock")), "il lease dell'exit-worker non si copia")
        self.assertFalse(os.path.exists(os.path.join(da, "close_request.json")), "una richiesta di chiusura non torna attiva")
        self.assertEqual(slurp(os.path.join(base, "brain-v3-beta1", "pause.flag")), b"restored_and_paused\n")
        self.assertIn("pausa FORZATA", rout)
        rep = jload(os.path.join(dest, "RESTORE-REPORT.json"))
        self.assertEqual(rep["esito"], "OK")
        self.assertIn("NON ESEGUITO", rout)                          # senza --v3-src il confronto con RC84 non e' un PASS
        with open(os.path.join(dest, "INTERNAL-MANIFEST.json")) as f:
            man = json.load(f)
        ra = [r for r in man["runs"] if r["run_name"] == "brain-v3-alfa1"][0]
        self.assertEqual(ra["journal"]["paper"]["ids_aperte"], ["p2"])
        self.assertTrue(ra["richiesta_chiusura_in_sospeso"])

    def test_no_duplicate_or_missing_events_across_two_archives(self):
        a, _b = self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        a.decision(10)
        a.decision(11)
        self.assertEqual(self.backup()[0], 0)
        clone = self.clone()
        first, second = self.archives(clone)
        _, _, d1 = self.restore(first)
        _, _, d2 = self.restore(second)
        e1 = [r[1] for r in rows_of(os.path.join(d1, "dati", "runs", "brain-v3-alfa1", "journal.db"), "SELECT seq,event_id FROM v3_events ORDER BY seq")]
        e2 = [r[1] for r in rows_of(os.path.join(d2, "dati", "runs", "brain-v3-alfa1", "journal.db"), "SELECT seq,event_id FROM v3_events ORDER BY seq")]
        self.assertEqual(e2[: len(e1)], e1)                          # il secondo estende il primo, nulla di rielaborato
        self.assertEqual(len(e2), len(e1) + 2)
        self.assertEqual(len(set(e2)), len(e2))
        seqs = [r[0] for r in rows_of(os.path.join(d2, "dati", "runs", "brain-v3-alfa1", "journal.db"), "SELECT seq FROM v3_events ORDER BY seq")]
        self.assertEqual(seqs, list(range(1, len(e2) + 1)))
        # ripristinare lo stesso archivio due volte da' lo stesso risultato logico
        _, _, d3 = self.restore(second)
        self.assertEqual(rows_of(os.path.join(d3, "dati", "runs", "brain-v3-alfa1", "journal.db"), "SELECT * FROM v3_events ORDER BY seq"),
                         rows_of(os.path.join(d2, "dati", "runs", "brain-v3-alfa1", "journal.db"), "SELECT * FROM v3_events ORDER BY seq"))

    def test_remote_holds_only_ciphertext_and_a_minimal_manifest(self):
        self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        clone = self.clone()
        names = []
        for dp, dn, fn in os.walk(clone):
            dn[:] = [d for d in dn if d != ".git"]
            names += [os.path.relpath(os.path.join(dp, f), clone) for f in fn]
        for n in names:
            self.assertTrue(n in ("LEGGIMI.md", "recipient.txt") or n.endswith(".tar.gz.age") or n.endswith(".manifest.json"),
                            "file inatteso nel repository: " + n)
        markers = [SECRET.encode(), b"SQLite format 3", b"BTCUSDT", b"initial_equity", b"AGE-SECRET-KEY"]
        self.assertEqual(plaintext_hits(self.remote, markers), [])
        (arc,) = self.archives(clone)
        man = jload(arc[: -len(".tar.gz.age")] + ".manifest.json")
        self.assertEqual(man["sha256"], sha(slurp(arc)))
        self.assertEqual(man["cifratura"]["destinatario"], self.pub)
        self.assertEqual(sorted(man["ancore"]), ["brain-v3-alfa1", "brain-v3-beta1"])
        self.assertNotIn(SECRET, json.dumps(man))
        secret_key = [l.strip() for l in lines_of(self.ident) if l.startswith("AGE-SECRET-KEY")][0]
        for n in names:
            self.assertNotIn(secret_key.encode(), slurp(os.path.join(clone, n)))

    def test_unchanged_state_publishes_nothing_new_changed_state_publishes(self):
        a, _b = self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertIn("INVARIATO", out)
        self.assertEqual(len(self.archives(self.clone())), 1)
        a.decision(20)
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.archives(self.clone())), 2)
        rc, out = self.backup("--force")
        self.assertEqual(len(self.archives(self.clone())), 3)

    def test_heartbeat_only_changes_do_not_force_new_archives(self):
        a, _b = self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        a.write("heartbeat.json", jdump({"ts_ms": int(time.time() * 1000), "cycle": 9, "state": "paused", "run_id": a.run_id}))
        rc, out = self.backup()
        self.assertIn("INVARIATO", out)

    def test_restore_rejects_wrong_key_tampered_archive_and_forbidden_destination(self):
        self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone())
        other = os.path.join(self.td.name, "altra-chiave.txt")
        keygen(other)
        rc, rout, _ = self.restore(arc, ident=other)
        self.assertEqual(rc, 1)
        self.assertIn("decifratura non riuscita", rout)
        bad = os.path.join(self.td.name, "alterato.tar.gz.age")
        data = bytearray(slurp(arc))
        data[len(data) // 2] ^= 0x01
        spit(bad, bytes(data))
        shutil.copyfile(arc[: -len(".tar.gz.age")] + ".manifest.json", bad[: -len(".tar.gz.age")] + ".manifest.json")
        rc, rout, _ = self.restore(bad)
        self.assertEqual(rc, 1)
        self.assertIn("NON coincide col manifesto", rout)
        os.unlink(bad[: -len(".tar.gz.age")] + ".manifest.json")      # senza manifesto lo ferma age (cifratura autenticata)
        rc, rout, _ = self.restore(bad)
        self.assertEqual(rc, 1)
        self.assertIn("decifratura non riuscita", rout)
        rc, rout, _ = self.restore(arc, out="/opt/superbot-v3-paper-runs/ripristino-prova")
        self.assertEqual(rc, 1)
        self.assertIn("cartella di produzione", rout)
        self.assertFalse(os.path.exists("/opt/superbot-v3-paper-runs"))
        full = os.path.join(self.td.name, "non-vuota")
        os.makedirs(full)
        spit(os.path.join(full, "x"), "x")
        rc, rout, _ = self.restore(arc, out=full)
        self.assertEqual(rc, 1)
        self.assertIn("non e' vuota", rout)

    def test_restore_detects_content_swapped_inside_a_valid_archive(self):
        """Un archivio ricifrato con un file diverso (manifest interno coerente ma journal alterato) non passa."""
        a, _b = self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone())
        _, _, ok_dir = self.restore(arc)
        # dal ripristino buono costruisco un archivio con un budget.db della run beta messo nella run alfa
        import tarfile
        import gzip
        shutil.copyfile(os.path.join(ok_dir, "dati", "runs", "brain-v3-beta1", "budget.db"),
                        os.path.join(ok_dir, "dati", "runs", "brain-v3-alfa1", "budget.db"))
        inner = jload(os.path.join(ok_dir, "INTERNAL-MANIFEST.json"))
        for x in inner["file"]:
            x["sha256"] = sha(slurp(os.path.join(ok_dir, *x["file"].split("/"))))
            x["size"] = os.path.getsize(os.path.join(ok_dir, *x["file"].split("/")))
        plain = os.path.join(self.td.name, "falso.tar.gz")
        with tarfile.open(plain, "w:gz") as tar:
            for x in inner["file"]:
                tar.add(os.path.join(ok_dir, *x["file"].split("/")), arcname=x["file"])
            blob = os.path.join(self.td.name, "INTERNAL-MANIFEST.json")
            spit(blob, json.dumps(inner))
            tar.add(blob, arcname="INTERNAL-MANIFEST.json")
        fake = os.path.join(self.td.name, "falso.tar.gz.age")
        sh("age", "-r", self.pub, "-o", fake, plain)
        rc, rout, _ = self.restore(fake)
        self.assertEqual(rc, 1, rout)
        self.assertIn("diverso dal manifesto del backup", rout)       # budget e identita' non coincidono con quanto registrato


class FailureModeTests(PipelineCase):
    def test_subset_backup_keeps_the_anchors_of_the_other_runs(self):
        a, b = self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        a.decision(40)
        rc, out = self.backup("--run", "brain-v3-alfa1")
        self.assertEqual(rc, 0, out)
        (first, second) = self.archives(self.clone())
        man = jload(second[: -len(".tar.gz.age")] + ".manifest.json")
        self.assertEqual(sorted(man["ancore"]), ["brain-v3-alfa1", "brain-v3-beta1"])
        self.assertEqual(man["ancore"]["brain-v3-beta1"], jload(first[: -len(".tar.gz.age")] + ".manifest.json")["ancore"]["brain-v3-beta1"])
        shutil.rmtree(b.dir)                                          # una run sparita non passa piu' inosservata
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("run_missing_since_last_backup", out)

    def test_runs_root_replaced_by_a_symlink_or_file_is_refused_not_ignored(self):
        self.populated_runs()
        real = os.path.join(self.td.name, "runs-vere")
        os.rename(self.runs, real)
        os.symlink(real, self.runs)
        rc, out = self.backup("--plan")
        self.assertEqual(rc, 1, out)
        self.assertIn("run_dir_unsafe", out)
        os.unlink(self.runs)
        spit(self.runs, "non sono una cartella")
        rc, out = self.backup("--plan")
        self.assertEqual(rc, 1, out)
        self.assertIn("run_dir_unsafe", out)

    def fake_age_path(self):
        d = os.path.join(self.td.name, "fakebin")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "age"), "w") as f:
            f.write("#!/bin/sh\necho 'age: errore simulato' >&2\nexit 1\n")
        os.chmod(os.path.join(d, "age"), 0o755)
        return dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"])

    def test_encryption_failure_sends_nothing_and_leaves_no_plaintext(self):
        self.populated_runs()
        before = tree_state(self.runs)
        rc, out = self.backup(env=self.fake_age_path())
        self.assertEqual(rc, 1, out)
        self.assertIn("RISULTATO: FALLITO", out)
        ls = subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout
        self.assertEqual(ls.strip(), "", "qualcosa e' arrivato sul remoto")
        leftovers = [n for n in os.listdir(os.path.join(self.work, "v3")) if n.startswith("staging") or n.endswith(".age")]
        self.assertEqual(leftovers, [], "restano testo in chiaro o archivi nel lavoro: %s" % leftovers)
        st = self.status()
        self.assertIn("ultimo_errore", st)
        self.assertNotIn("ultimo_successo", st)
        self.assertEqual(tree_state(self.runs), before)

    def test_remote_push_failure_is_reported_and_no_success_is_recorded(self):
        self.populated_runs()
        hook = os.path.join(self.remote, "hooks", "pre-receive")
        with open(hook, "w") as f:
            f.write("#!/bin/sh\necho 'rifiutato dal test' >&2\nexit 1\n")
        os.chmod(hook, 0o755)
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("push rifiutato", out)
        st = self.status()
        self.assertNotIn("ultimo_successo", st)
        self.assertIn("ultimo_errore", st)
        self.assertEqual([n for n in os.listdir(os.path.join(self.work, "v3")) if n.endswith(".age")], [])
        # tolto l'ostacolo, il tentativo successivo riesce e pubblica
        os.unlink(hook)
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertIn("ultimo_successo", self.status())

    def test_unreachable_remote_fails_cleanly(self):
        self.populated_runs()
        rc, out = self.backup(remote=os.path.join(self.td.name, "non-esiste.git"))
        self.assertEqual(rc, 1, out)
        self.assertIn("non raggiungibile", out)

    def test_regressed_or_rewritten_history_is_refused_and_nothing_is_published(self):
        a, _b = self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        ok_status = self.status()["ultimo_successo"]
        # 1) stessa run, stessa lunghezza ma storia diversa (rigenerata)
        shutil.rmtree(a.dir)
        a2 = Run(self.runs, "brain-v3-alfa1", equity="1000")
        for n in range(1, 4):
            a2.decision(n, "altra-storia")
        a2.open("q1")
        a2.open("q2", "ETHUSDT", -1)
        a2.close("q1")
        a2.spend(1)
        a2.spend(1)
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("anchor_regressed", out)
        # 2) run scomparsa
        shutil.rmtree(a2.dir)
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("run_missing_since_last_backup", out)
        self.assertEqual(len(self.archives(self.clone())), 1)
        self.assertEqual(self.status()["ultimo_successo"], ok_status)
        self.assertIn("run_missing_since_last_backup", self.status()["ultimo_errore"])

    def test_broken_run_blocks_everything_and_names_the_run(self):
        a, b = self.populated_runs()
        os.unlink(os.path.join(b.dir, "mandate.json"))
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("runs_not_certifiable", out)
        self.assertIn("brain-v3-beta1=file_missing", out)
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")

    def test_nothing_to_protect_exits_3_without_error_state(self):
        rc, out = self.backup()
        self.assertEqual(rc, 3, out)
        self.assertIn("NIENTE DA PROTEGGERE", out)
        self.assertNotIn("ultimo_errore", self.status())

    def test_plan_is_local_only_and_sends_nothing(self):
        self.populated_runs()
        rc, out = self.backup("--plan", remote=os.path.join(self.td.name, "irraggiungibile.git"))
        self.assertEqual(rc, 0, out)
        self.assertIn("PIANO (nessun invio, nessuna rete)", out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "v3", "repo")))
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")

    def test_workdir_of_the_classic_backup_is_refused(self):
        self.populated_runs()
        classic_like = os.path.join(self.td.name, "superbot-extbackup")
        p = subprocess.run([sys.executable, "-I", PIPE, "--mode", "v3", "--runs-root", self.runs, "--work", classic_like,
                            "--plan", "--recipient-file", self.recfile, "--expect-recipients-sha256", pin(self.recfile), "--tools", HERE],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("Falco/Toro", p.stdout)
        self.assertFalse(os.path.exists(classic_like))

    def test_prune_needs_explicit_confirmation_and_never_runs_by_default(self):
        a, _b = self.populated_runs()
        for n in range(3):
            a.decision(30 + n)
            self.assertEqual(self.backup()[0], 0)
        rc, out = self.backup("--prune")
        self.assertEqual(rc, 1)
        self.assertIn("--confirm-prune", out)
        self.assertEqual(len(self.archives(self.clone())), 3)         # nessuna rimozione senza conferma
        rc, out = self.backup("--prune", "--confirm-prune", "--keep-recent", "1", "--keep-weeks", "0", "--keep-months", "0",
                              "--force")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.archives(self.clone())), 1)          # restano solo i recenti richiesti
        # la storia git conserva comunque gli archivi tolti dalla punta
        n_blobs = sh("git", "-C", self.remote, "rev-list", "--count", "brain-v3").stdout.strip()
        self.assertGreaterEqual(int(n_blobs), 4)


class SizeAndChunkingTests(PipelineCase):
    def big_run(self):
        a = Run(self.runs, "brain-v3-grande")
        for n in range(1, 700):
            a.decision(n, os.urandom(2048).hex())                     # payload incomprimibile: archivio di alcuni MB
        return a

    def test_large_archive_is_split_into_parts_and_restores_from_them(self):
        self.big_run()
        rc, out = self.backup("--max-file-mib", "1")
        self.assertEqual(rc, 0, out)
        clone = self.clone()
        parts = sorted(f for f in os.listdir(os.path.join(clone, "brain-v3", time.strftime("%Y"), time.strftime("%m")))
                       if ".part" in f)
        self.assertGreaterEqual(len(parts), 2)
        base = os.path.join(clone, "brain-v3", time.strftime("%Y"), time.strftime("%m"))
        arc = os.path.join(base, [f for f in os.listdir(base) if f.endswith(".manifest.json")][0][: -len(".manifest.json")] + ".tar.gz.age")
        self.assertFalse(os.path.exists(arc), "l'archivio intero non deve esserci quando e' spezzato")
        for p in parts:
            self.assertLessEqual(os.path.getsize(os.path.join(base, p)), 1 << 20)
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        self.assertIn("ricomposto da %d parti" % len(parts), rout)
        # una parte alterata o mancante ferma il ripristino
        victim = os.path.join(base, parts[1])
        good = slurp(victim)
        spit(victim, good[:-1] + bytes([good[-1] ^ 1]))
        rc, rout, _ = self.restore(arc)
        self.assertEqual(rc, 1)
        self.assertIn("non coincide col manifesto", rout)
        os.unlink(victim)
        rc, rout, _ = self.restore(arc)
        self.assertEqual(rc, 1)
        self.assertIn("parte mancante", rout)

    def test_size_guards_refuse_before_sending(self):
        self.big_run()
        rc, out = self.backup("--max-archive-mib", "1")
        self.assertEqual(rc, 1, out)
        self.assertIn("oltre il limite", out)
        rc, out = self.backup("--max-repo-mib", "1")
        self.assertEqual(rc, 1, out)
        self.assertIn("rotazione", out)
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")


class PreflightTests(PipelineCase):
    def test_preflight_is_read_only_and_reports_blockers(self):
        self.populated_runs()
        before = tree_state(self.td.name)
        p = subprocess.run(self.args("--preflight", "--no-network"), capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PREFLIGHT: OK (solo metadati", p.stdout)
        self.assertEqual(tree_state(self.td.name), before)
        self.assertFalse(os.path.exists(self.work))
        os.unlink(os.path.join(self.runs, "brain-v3-alfa1", "mandate.json"))
        p = subprocess.run(self.args("--preflight", "--no-network"), capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 1)
        self.assertIn("MANCANTI mandate.json", p.stdout)
        os.unlink(self.recfile)
        p = subprocess.run(self.args("--preflight", "--no-network"), capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 1)
        self.assertIn("recipient_file_unreadable", p.stdout)


# ======================================================================================================
# Database storico Brain Free (famiglia separata)
# ======================================================================================================

def legacy_measure(path):
    """Misura indipendente (copiata dalla formula di backend/v3/backup_certification.py::_inspect)."""
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        body = con.execute("SELECT body FROM state WHERE id=1").fetchone()[0]
        stream, n, last = hashlib.sha256(), 0, 0
        for row in con.execute("SELECT seq,id,kind,ts,body FROM events ORDER BY seq"):
            enc = json.dumps(row, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
            stream.update(len(enc).to_bytes(8, "big"))
            stream.update(enc)
            n, last = n + 1, row[0]
        return {"eventi": n, "seq_max": last, "events_sha256": stream.hexdigest(),
                "state_sha256": sha(body.encode())}
    finally:
        con.close()


def make_legacy(path, n_events=40, mode="paper", dead_process_wal=False):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
    con.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, kind TEXT NOT NULL, "
                "ts INTEGER NOT NULL, body TEXT NOT NULL)")
    con.execute("INSERT INTO state VALUES(1, ?)", (json.dumps({"mode": mode, "account_id": "brain-free-paper", "positions": {}}),))
    con.commit()
    if not dead_process_wal:
        con.executemany("INSERT INTO events(id,kind,ts,body) VALUES(?,?,?,?)",
                        [("e%d" % i, "decision", 1760000000000 + i, json.dumps({"nota": SECRET, "i": i})) for i in range(n_events)])
        con.commit()
    con.close()
    if dead_process_wal:                       # eventi SOLO nel -wal di un processo morto (residuo tipico di un container fermo)
        code = ("import sqlite3, os, sys, json\\n"
                "c = sqlite3.connect(sys.argv[1], isolation_level=None)\\n"
                "c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0')\\n"
                "for i in range(%d): c.execute('INSERT INTO events(id,kind,ts,body) VALUES(?,?,?,?)', "
                "('e%%d' %% i, 'decision', 1760000000000 + i, json.dumps({'nota': %r, 'i': i})))\\n"
                "os._exit(0)\\n") % (n_events, SECRET)
        subprocess.run([sys.executable, "-c", code.replace("\\n", "\n"), path], check=True)


class LegacyBrainFreeTests(PipelineCase):
    def setUp(self):
        super().setUp()
        self.legacy_dir = os.path.join(self.td.name, "brain-free")
        os.makedirs(self.legacy_dir)
        self.legacy = os.path.join(self.legacy_dir, "brain.sqlite3")

    def free(self, *extra, **kw):
        return self.backup("--legacy-db", self.legacy, *extra, mode="brain-free", **kw)

    def test_dead_process_wal_residue_is_backed_up_in_its_own_family_and_restored(self):
        make_legacy(self.legacy, 60, dead_process_wal=True)
        self.assertTrue(os.path.exists(self.legacy + "-wal") and os.path.exists(self.legacy + "-shm"))
        before = tree_state(self.legacy_dir)
        rc, out = self.free()
        self.assertEqual(rc, 0, out)
        self.assertEqual(tree_state(self.legacy_dir), before)                       # database, -wal e -shm: byte, data e elenco identici
        heads = subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout
        self.assertIn("refs/heads/brain-free", heads)
        self.assertNotIn("refs/heads/brain-v3", heads)
        clone = self.clone("brain-free")
        (arc,) = self.archives(clone, "brain-free")
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        restored = os.path.join(dest, "dati", "legacy", "brain.sqlite3")
        self.assertEqual(rows_of(restored, "PRAGMA integrity_check"), [("ok",)])
        m = legacy_measure(restored)
        self.assertEqual(m["eventi"], 60)
        man = jload(arc[: -len(".tar.gz.age")] + ".manifest.json")
        self.assertEqual({k: man["ancora_legacy"][k] for k in m}, m)                # misura indipendente = manifesto
        self.assertEqual(plaintext_hits(self.remote, [SECRET.encode(), b"SQLite format 3"]), [])

    def test_unchanged_legacy_database_is_not_uploaded_again(self):
        make_legacy(self.legacy, 30)
        self.assertEqual(self.free()[0], 0)
        rc, out = self.free()
        self.assertEqual(rc, 0, out)
        self.assertIn("INVARIATO", out)
        self.assertEqual(len(self.archives(self.clone("brain-free"), "brain-free")), 1)

    def test_regressed_or_non_paper_legacy_database_is_refused(self):
        make_legacy(self.legacy, 30)
        self.assertEqual(self.free()[0], 0)
        os.unlink(self.legacy)
        for ext in ("-wal", "-shm"):
            if os.path.exists(self.legacy + ext):
                os.unlink(self.legacy + ext)
        make_legacy(self.legacy, 10)
        rc, out = self.free()
        self.assertEqual(rc, 1, out)
        self.assertIn("legacy_regressed", out)
        os.unlink(self.legacy)
        make_legacy(self.legacy, 50, mode="live")
        rc, out = self.free()
        self.assertEqual(rc, 1, out)
        self.assertIn("legacy_not_paper", out)
        self.assertEqual(len(self.archives(self.clone("brain-free"), "brain-free")), 1)

    def test_missing_legacy_database_is_refused_not_recreated(self):
        rc, out = self.free()
        self.assertEqual(rc, 1, out)
        self.assertIn("file_missing", out)
        self.assertFalse(os.path.exists(self.legacy))

    def test_v3_and_legacy_families_never_touch_each_other(self):
        self.populated_runs()
        make_legacy(self.legacy, 20)
        self.assertEqual(self.backup()[0], 0)
        tip_v3 = sh("git", "-C", self.remote, "rev-parse", "brain-v3").stdout.strip()
        self.assertEqual(self.free()[0], 0)
        self.assertEqual(sh("git", "-C", self.remote, "rev-parse", "brain-v3").stdout.strip(), tip_v3)
        tip_free = sh("git", "-C", self.remote, "rev-parse", "brain-free").stdout.strip()
        self.assertEqual(self.backup("--force")[0], 0)
        self.assertEqual(sh("git", "-C", self.remote, "rev-parse", "brain-free").stdout.strip(), tip_free)


# ======================================================================================================
# Compatibilita' con il backup di Falco e Toro gia' funzionante
# ======================================================================================================

class ClassicCompatibilityTests(unittest.TestCase):
    def test_classic_files_are_byte_identical_to_the_installed_commit(self):
        """Se una di queste impronte cambia, l'estensione ha toccato il backup che gia' funziona: serve revisione."""
        for rel, expected in CLASSIC_PINS.items():
            with self.subTest(file=rel):
                path = os.path.normpath(os.path.join(HERE, rel))
                self.assertTrue(os.path.isfile(path), path)
                self.assertEqual(sha(slurp(path)), expected)

    @unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
    def test_classic_and_v3_backups_coexist_on_the_same_private_repository(self):
        import test_external_backup as classic_tests
        case = classic_tests.ExternalBackupTests("test_full_round_trip_backup_then_restore")
        case.setUp()
        try:
            rc, out = case.backup()
            self.assertEqual(rc, 0, out)
            main_tip = sh("git", "-C", case.remote, "rev-parse", "main").stdout.strip()
            runs = os.path.join(case.td.name, "v3runs")
            os.makedirs(runs)
            r = Run(runs, "brain-v3-alfa1")
            r.decision(1)
            v3 = [sys.executable, "-I", PIPE, "--mode", "v3", "--runs-root", runs, "--work", os.path.join(case.td.name, "w3"),
                  "--remote", case.remote, "--recipient-file", case.recfile, "--tools", HERE, "--push-wait", "0",
                  "--attempt-wait", "0", "--expect-recipients-sha256", pin(case.recfile)]
            p = subprocess.run(v3, capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(sh("git", "-C", case.remote, "rev-parse", "main").stdout.strip(), main_tip,
                             "l'estensione ha mosso il ramo del backup di Falco/Toro")
            tree_v3 = sh("git", "-C", case.remote, "ls-tree", "-r", "brain-v3").stdout
            time.sleep(1.1)
            rc, out = case.backup("--keep-recent", "1", "--keep-weeks", "0", "--keep-months", "0")
            self.assertEqual(rc, 0, out)                              # il backup classico (anche con la sua retention) va avanti
            self.assertEqual(sh("git", "-C", case.remote, "ls-tree", "-r", "brain-v3").stdout, tree_v3,
                             "il backup classico ha toccato i file di Brain V3")
            clone = case.clone_remote()
            archives = case.archives(clone)
            self.assertEqual(len(archives), 1)                        # la retention classica ha fatto il suo lavoro sul suo ramo
            rc, rout, _ = case.restore(archives[-1])
            self.assertEqual(rc, 0, rout)
            self.assertIn("RISULTATO: OK", rout)
            v3clone = os.path.join(case.td.name, "v3clone")
            sh("git", "clone", "-q", "--branch", "brain-v3", case.remote, v3clone)
            (arc,) = [os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(v3clone, "brain-v3")) for f in fn if f.endswith(".tar.gz.age")]
            out_dir = os.path.join(case.td.name, "ripr-v3")
            p = subprocess.run([sys.executable, "-I", RESTORE, "--archive", arc, "--identity", case.ident, "--out", out_dir],
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(p.stdout.count("RISULTATO: OK"), 1)
        finally:
            case.tearDown()


# ======================================================================================================
# Confronto con il codice VERO di RC84 (si salta se SUPERBOT_RC84_SRC non e' indicato)
# ======================================================================================================

RC84_PREPARE = r"""
import json, os, sys, time
from pathlib import Path
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
from backend.v3.runner.config import load_runner_config
from backend.v3.events import Event, EventJournal
from backend.v3.budget import BudgetLedger
from backend.v3.brain_f2.engine import _policy_hash
parent, cfgname = Path(sys.argv[1]), sys.argv[2]
raw = Path(sys.argv[3], "backend/v3/runner", cfgname).read_bytes()
cfg = load_runner_config(raw)
now = int(time.time() * 1000)
root = prepare_new_paper_run(parent=parent, run_name="brain-v3-rc84real", run_id="brain-v3-rc84real", config_bytes=raw,
                             desk_mode="paper", now_ms=now - 60000, expected_initial_equity=str(cfg.initial_equity))
j = EventJournal(root / "journal.db")
for n in range(1, 6):
    j.append(Event("brain-d-%d" % n, "brain", "brain-v3-rc84real", "brain_decision", now - 50000 + n, "brain_f2_engine",
                   {"kind": "no_trade", "status": "rejected", "rationale": "sanitized", "sources": [], "claim": "c%d" % n,
                    "symbol": "BTCUSDT", "regime": "UNKNOWN"}))
j.append(Event("paper_open.p1", "brain", "brain-v3-rc84real", "paper_open", now - 40000, "executor.paper",
               {"position_id": "p1", "symbol": "BTCUSDT", "side": 1, "fill_price": "100", "quantity": "1",
                "margin_used": "10", "leverage": 10}))
led = BudgetLedger(str(root / "budget.db"))
led.record_spend("deepseek", 1234, {"basis": "usage"})
led.close()
n, head = j.verify_chain()
print(json.dumps({"count": n, "head": head, "policy": _policy_hash(cfg.risk_policy), "equity": str(cfg.initial_equity)}))
"""


@unittest.skipUnless(HAVE_AGE and HAVE_RC84, "SKIP: servono age/git e SUPERBOT_RC84_SRC (checkout di RC84)")
class Rc84CrossCheckTests(PipelineCase):
    def prepare(self, cfgname):
        env = dict(os.environ, PYTHONPATH=RC84)
        p = subprocess.run([sys.executable, "-c", RC84_PREPARE, self.runs, cfgname, RC84], capture_output=True, text=True,
                           env=env, cwd=RC84, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_run_prepared_and_written_by_real_rc84_is_certified_and_restored(self):
        for cfgname, policy_equity in (("runner_config_brain2000_paper.json", "2000"),):
            official = self.prepare(cfgname)
            before = tree_state(self.runs)
            rc, out = self.backup()
            self.assertEqual(rc, 0, out)
            self.assertEqual(tree_state(self.runs), before)
            (arc,) = self.archives(self.clone())
            man = jload(arc[: -len(".tar.gz.age")] + ".manifest.json")
            anc = man["ancore"]["brain-v3-rc84real"]
            self.assertEqual((anc["eventi"], anc["testa"]), (official["count"], official["head"]))
            rc, rout, dest = self.restore(arc, None, None, "--v3-src", RC84)
            self.assertEqual(rc, 0, rout)
            self.assertIn("RC84 (codice vero) accetta la run brain-v3-rc84real", rout)
            self.assertIn("1 posizioni aperte coincidono", rout)
            inner = jload(os.path.join(dest, "INTERNAL-MANIFEST.json"))
            self.assertEqual(inner["runs"][0]["config"]["policy_hash"], official["policy"])
            self.assertEqual(inner["runs"][0]["config"]["capitale_iniziale"], policy_equity)

    def test_default_config_policy_hash_matches_real_rc84(self):
        official = self.prepare("runner_config.json")
        rc, out = self.backup("--plan")
        self.assertEqual(rc, 0, out)
        stage = os.path.join(self.td.name, "stage")
        facts, _ = S.build_runs_snapshot(self.runs, stage, int(time.time() * 1000) + 1000, attempts=1)
        self.assertEqual(facts[0]["config"]["policy_hash"], official["policy"])
        self.assertEqual(facts[0]["journal"]["testa"], official["head"])

    def test_real_and_replicated_schema_agree(self):
        self.prepare("runner_config.json")
        con = sqlite3.connect(os.path.join(self.runs, "brain-v3-rc84real", "journal.db"))
        cols = [r[1] for r in con.execute("PRAGMA table_info(v3_events)")]
        trig = sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
        con.close()
        self.assertEqual(cols, S.JOURNAL_COLS)
        self.assertEqual(trig, ["v3_no_delete", "v3_no_update"])
        con = sqlite3.connect(os.path.join(self.runs, "brain-v3-rc84real", "budget.db"))
        self.assertEqual([r[1] for r in con.execute("PRAGMA table_info(spend_events)")], S.BUDGET_COLS)
        con.close()

    def test_a_chain_broken_for_rc84_is_also_refused_here(self):
        self.prepare("runner_config.json")
        d = os.path.join(self.runs, "brain-v3-rc84real")
        con = sqlite3.connect(os.path.join(d, "journal.db"))
        con.execute("DROP TRIGGER v3_no_update")
        con.execute("UPDATE v3_events SET payload_json=replace(payload_json,'sanitized','x') WHERE seq=3")
        con.execute("CREATE TRIGGER v3_no_update BEFORE UPDATE ON v3_events BEGIN SELECT RAISE(ABORT,'x'); END")
        con.commit()
        con.close()
        code = ("import sys; from pathlib import Path; from backend.v3.events import EventJournal\n"
                "try:\n    EventJournal(Path(sys.argv[1])).verify_chain(); print('OK')\n"
                "except ValueError as e:\n    print('RIFIUTA', e)\n")
        p = subprocess.run([sys.executable, "-c", code, os.path.join(d, "journal.db")], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=RC84), cwd=RC84)
        self.assertIn("RIFIUTA journal_hash_chain_invalid", p.stdout)
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("journal_chain_invalid", out)


# ======================================================================================================
# Revisione di sicurezza: WAL senza toccare i file collaterali, preflight non invasivo
# ======================================================================================================

HOLDER = r"""
import sqlite3, sys, time
from datetime import datetime, timezone
c = sqlite3.connect(sys.argv[1], isolation_level=None)
c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0')
for i in range(40):
    c.execute("INSERT INTO spend_events(occurred_at,provider,units,metadata) VALUES(?,?,?,?)",
              (datetime.now(timezone.utc).isoformat(), 'deepseek', 3, '{}'))
print('ready', flush=True)
if sys.argv[2] == 'idle':
    time.sleep(120)
else:
    end = time.time() + 120
    while time.time() < end:
        c.execute("INSERT INTO spend_events(occurred_at,provider,units,metadata) VALUES(?,?,?,?)",
                  (datetime.now(timezone.utc).isoformat(), 'deepseek', 1, '{}'))
        time.sleep(0.003)
"""


@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
class WalCaptureTests(PipelineCase):
    """WAL pulito, residuo dopo un arresto brusco, scrittore attivo: sorgente intatta e dati completi."""

    def live_holder(self, db, mode):
        p = subprocess.Popen([sys.executable, "-c", HOLDER, db, mode], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (p.kill(), p.wait(timeout=30), p.stdout.close()))
        self.assertEqual(p.stdout.readline().strip(), "ready")
        return p

    def crash_residue(self, db):
        code = HOLDER.replace("print('ready', flush=True)", "import os; os._exit(0)")
        subprocess.run([sys.executable, "-c", code, db, "idle"], check=True)

    def preflight(self, *extra):
        return subprocess.run(self.args("--preflight", "--no-network", *extra), capture_output=True, text=True, timeout=120)

    def test_clean_wal_is_described_and_captured_without_any_change(self):
        r = Run(self.runs, "brain-v3-pulito")
        r.spend(5)
        d = S.describe_source(r.budget)
        self.assertEqual(d["stato"], "wal_pulito")
        self.assertEqual(d["collaterali"], {})
        before = tree_state(self.td.name)
        p = self.preflight()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("wal_pulito", p.stdout)
        self.assertEqual(tree_state(self.td.name), before)
        f = capture(r)
        self.assertEqual(f["budget"]["righe"], 1)
        self.assertEqual(tree_state(self.td.name), before)

    def test_crash_residue_is_described_without_opening_sqlite_and_captured_with_originals_intact(self):
        r = Run(self.runs, "brain-v3-residuo")
        self.crash_residue(r.budget)
        self.assertTrue(os.path.exists(r.budget + "-wal") and os.path.exists(r.budget + "-shm"))
        d = S.describe_source(r.budget)
        self.assertEqual(d["stato"], "wal_con_file_collaterali")
        self.assertEqual(d["processi"], [])
        before = tree_state(self.runs)
        p = self.preflight()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("wal_con_file_collaterali", p.stdout)
        self.assertIn("originali (-shm compreso) intatti", p.stdout)
        self.assertEqual(tree_state(self.runs), before, "il preflight ha toccato la sorgente (anche solo il -shm)")
        f = capture(r)
        self.assertEqual(f["budget"]["righe"], 40)                     # righe presenti SOLO nel -wal del processo morto
        self.assertEqual(tree_state(self.runs), before, "la cattura ha toccato database, -wal o -shm")

    def test_idle_live_writer_is_detected_and_captured_with_originals_intact(self):
        r = Run(self.runs, "brain-v3-vivo")
        holder = self.live_holder(r.budget, "idle")
        d = S.describe_source(r.budget)
        self.assertEqual(d["stato"], "wal_con_file_collaterali")
        self.assertIn(holder.pid, d["processi"])
        before = tree_state(self.runs)
        p = self.preflight()
        self.assertIn("aperto da processi", p.stdout)
        self.assertEqual(tree_state(self.runs), before)
        f = capture(r)
        self.assertEqual(f["budget"]["righe"], 40)
        self.assertEqual(tree_state(self.runs), before)

    def test_busy_live_writer_yields_a_consistent_snapshot_or_an_explicit_refusal(self):
        r = Run(self.runs, "brain-v3-attivo")
        self.live_holder(r.budget, "busy")
        ok = refused = 0
        for _ in range(6):
            try:
                f = capture(r, attempts=2, wait=0.01)
                ok += 1
                self.assertGreaterEqual(f["budget"]["righe"], 40)
            except S.Refused as e:
                self.assertIn(e.code, ("source_changed_during_capture", "sqlite_busy"))
                refused += 1
        self.assertEqual(ok + refused, 6)
        # nessun file creato da noi nella cartella vera
        self.assertEqual(sorted(n for n in os.listdir(r.dir) if n.startswith(".scratch")), [])

    def test_scratch_copy_is_private_and_removed(self):
        r = Run(self.runs, "brain-v3-privato")
        self.crash_residue(r.budget)
        root = os.path.join(self.td.name, "scratch-root")
        S.SCRATCH_ROOT = root
        self.addCleanup(setattr, S, "SCRATCH_ROOT", None)
        conn = S.open_source_db(r.budget)
        (sub,) = os.listdir(root)
        self.assertEqual(oct(os.stat(os.path.join(root, sub)).st_mode & 0o777), "0o700")
        conn.close()
        self.assertEqual(os.listdir(root), [])

    def test_changing_wal_during_the_copy_is_refused(self):
        r = Run(self.runs, "brain-v3-cambia")
        self.crash_residue(r.budget)
        real = S.sha256_file
        done = []

        def flaky(path):
            if path.endswith("-wal") and not done:
                done.append(1)
                with open(path, "ab") as f:                          # qualcuno scrive nel -wal tra copia e riverifica
                    f.write(b"\0")
            return real(path)
        S.sha256_file = flaky
        self.addCleanup(setattr, S, "sha256_file", real)
        with self.assertRaises(S.Refused) as cm:
            S.open_source_db(r.budget)
        self.assertEqual(cm.exception.code, "source_changed_during_capture")

    def test_describe_source_never_opens_sqlite_or_writes(self):
        r = Run(self.runs, "brain-v3-meta")
        self.crash_residue(r.budget)
        before = tree_state(r.dir)
        for path in (r.budget, r.journal):
            S.describe_source(path)
        self.assertEqual(tree_state(r.dir), before)
        self.assertEqual(S.describe_source(r.journal)["stato"], "rollback_pulito")
        self.assertEqual(S.describe_source(os.path.join(r.dir, "non-esiste.db"))["stato"], "assente")


# ======================================================================================================
# Falsi positivi: nessuna run / uscita 3 non certificano nulla; esecuzione pianificata senza prova
# ======================================================================================================

class FalsePositiveTests(PipelineCase):
    def test_exit_3_records_no_success_and_no_verification(self):
        rc, out = self.backup()
        self.assertEqual(rc, 3, out)
        self.assertIn("NESSUN BACKUP E' STATO ESEGUITO", out)
        st = self.status()
        for k in ("ultimo_successo", "ultima_verifica_ok", "archivio", "sha256", "verifica"):
            self.assertNotIn(k, st)
        self.assertEqual(st["stato"], "nessuna_run")
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")

    def test_scheduled_run_without_timer_gate_is_refused_and_does_nothing(self):
        self.populated_runs()
        rc, out = self.backup(env=dict(os.environ, SUPERBOT_V3_SCHEDULED="1"))
        self.assertEqual(rc, 1, out)
        self.assertIn("timer_gate_missing", out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "v3")))
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")
        os.makedirs(self.work)
        spit(os.path.join(self.work, "timer-gate.json"), "{}")
        rc, out = self.backup(env=dict(os.environ, SUPERBOT_V3_SCHEDULED="1"))
        self.assertEqual(rc, 0, out)

    def test_unit_files_have_no_persistent_and_no_success_exit_3(self):
        base = os.path.join(HERE, "..", "extbackup", "brain-v3")
        timer, service = slurp(os.path.join(base, "superbot-extbackup-v3.timer")).decode(), slurp(os.path.join(base, "superbot-extbackup-v3.service")).decode()
        self.assertFalse([l for l in timer.splitlines() if l.strip().startswith("Persistent")])
        self.assertNotIn("SuccessExitStatus", service)
        self.assertIn("SUPERBOT_V3_SCHEDULED=1", service)
        self.assertIn("ExecStopPost", service)


# ======================================================================================================
# Interruzioni anomale della pipeline: staging, cifratura
# ======================================================================================================

@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
class InterruptionTests(PipelineCase):
    def slow_age(self):
        d = os.path.join(self.td.name, "slowbin")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "age"), "w") as f:
            f.write('#!/bin/sh\n# scrive un cifrato parziale e poi resta in attesa\nwhile [ "$1" != "-o" ]; do shift; done\n'
                    'echo parziale > "$2"\nsleep 60\n')
        os.chmod(os.path.join(d, "age"), 0o755)
        return dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"])

    def start_until_encrypting(self):
        proc = subprocess.Popen(self.args(), env=self.slow_age(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: (proc.kill(), proc.wait(timeout=30), proc.stdout.close()))
        wd = os.path.join(self.work, "v3")
        end = time.time() + 60
        while time.time() < end:
            names = os.listdir(wd) if os.path.isdir(wd) else []
            if os.path.isfile(os.path.join(wd, "staging.tar.gz")) and any(n.endswith(".tar.gz.age") for n in names):
                return proc, wd
            time.sleep(0.05)
        self.fail("la cifratura non e' partita")

    def test_sigterm_during_encryption_removes_every_plaintext_and_partial_file(self):
        self.populated_runs()
        before = tree_state(self.runs)
        proc, wd = self.start_until_encrypting()
        self.assertTrue(os.path.isdir(os.path.join(wd, "staging")))
        proc.terminate()
        out, _ = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 143, out)
        self.assertIn("INTERROTTO", out)
        self.assertEqual(sorted(n for n in os.listdir(wd) if n != "repo" and n != "status.json" and n != ".lock"), [])
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")
        self.assertIn("interrotto da un segnale", self.status()["ultimo_errore"])
        self.assertEqual(tree_state(self.runs), before)

    def test_sigkill_leaves_only_private_temp_files_and_the_next_run_sweeps_them(self):
        self.populated_runs()
        before = tree_state(self.runs)
        proc, wd = self.start_until_encrypting()
        proc.kill()
        proc.communicate(timeout=60)
        subprocess.run(["pkill", "-f", "slowbin"], check=False)
        self.assertTrue(os.path.isfile(os.path.join(wd, "staging.tar.gz")))
        for n in ("staging", "staging.tar.gz"):
            mode = os.stat(os.path.join(wd, n)).st_mode & 0o777
            self.assertEqual(mode & 0o077, 0, "%s leggibile da altri (%o)" % (n, mode))
        self.assertEqual(os.stat(self.work).st_mode & 0o077, 0)
        self.assertEqual(os.stat(wd).st_mode & 0o077, 0)
        # il testo in chiaro non e' nel clone che si pubblica, ne' sul remoto
        self.assertFalse(os.path.exists(os.path.join(wd, "repo", "staging.tar.gz")))
        self.assertEqual(subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout.strip(), "")
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertIn("ripulito il residuo temporaneo", out)
        self.assertEqual(sorted(n for n in os.listdir(wd) if n not in ("repo", "status.json", ".lock")), [])
        self.assertEqual(plaintext_hits(self.remote, [SECRET.encode(), b"SQLite format 3"]), [])
        self.assertEqual(tree_state(self.runs), before)


# ======================================================================================================
# File sconosciuti in extra/: manifesto, recupero senza perdite, nessuna attivazione
# ======================================================================================================

@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
class ExtraFilesTests(PipelineCase):
    PAYLOADS = {"appunti.txt": b"riga senza a capo e senza UTF-8: \\xff\\xfe\\x00 fine",
                ".memoria.jsonl": b'{"i":1}\\n{"i":2}\\n', "vuoto.bin": b"", "dati.bin": os.urandom(5000)}

    def run_with_extras(self):
        r = Run(self.runs, "brain-v3-memo")
        r.decision(1)
        for n, data in self.PAYLOADS.items():
            r.write(n, data)
            os.utime(os.path.join(r.dir, n), (1700000000 + len(n), 1700000000 + len(n)))
        os.chmod(os.path.join(r.dir, "appunti.txt"), 0o640)
        return r

    def test_extra_files_are_listed_with_original_path_and_restored_byte_for_byte(self):
        r = self.run_with_extras()
        before = tree_state(self.runs)
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertEqual(tree_state(self.runs), before)
        (arc,) = self.archives(self.clone())
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        inner = jload(os.path.join(dest, "INTERNAL-MANIFEST.json"))
        listed = {e["nome"]: e for e in inner["runs"][0]["extra"]}
        self.assertEqual(sorted(listed), sorted(self.PAYLOADS))
        base = os.path.join(dest, "dati", "runs", "brain-v3-memo")
        for n, data in self.PAYLOADS.items():
            e = listed[n]
            self.assertEqual(e["percorso_originale"], os.path.join(r.dir, n))
            self.assertEqual((e["size"], e["sha256"], e["archiviato_in"]), (len(data), sha(data), "extra/" + n))
            self.assertEqual(slurp(os.path.join(base, "extra", n)), data)                  # nessuna perdita
            self.assertEqual(int(os.stat(os.path.join(base, "extra", n)).st_mtime), 1700000000 + len(n))
            self.assertIn("originale %s" % os.path.join(r.dir, n), rout)
        self.assertEqual(listed["appunti.txt"]["modo"], "0o640")
        # nessuna attivazione: niente di tutto questo e' nella cartella della run
        self.assertEqual(sorted(set(self.PAYLOADS) & set(os.listdir(base))), [])
        self.assertIn("nessuna attivazione automatica", rout)
        rep = jload(os.path.join(dest, "RESTORE-REPORT.json"))
        self.assertEqual(sorted(e["nome"] for e in rep["extra"]), sorted(self.PAYLOADS))
        self.assertEqual(rep["extra"][0]["modo_originale"] in ("0o600", "0o640", "0o644"), True)

    def test_changing_an_extra_file_makes_a_new_archive(self):
        r = self.run_with_extras()
        self.assertEqual(self.backup()[0], 0)
        rc, out = self.backup()
        self.assertIn("INVARIATO", out)
        r.write("appunti.txt", b"contenuto cambiato")
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("INVARIATO", out)
        self.assertEqual(len(self.archives(self.clone())), 2)

    def test_extra_file_changing_during_the_copy_is_detected(self):
        r = self.run_with_extras()

        def hook(attempt):
            r.write("appunti.txt", b"modificato durante la copia %d" % attempt)
        with self.assertRaises(S.Refused) as cm:
            capture(r, attempts=2, wait=0, hooks={"after_copy": hook})
        self.assertEqual(cm.exception.code, "source_changed_during_capture")

    def test_oversize_or_nested_unknown_entries_are_refused_not_dropped(self):
        r = Run(self.runs, "brain-v3-grosso")
        with open(os.path.join(r.dir, "enorme.jsonl"), "wb") as f:
            f.truncate(S.EXTRA_MAX_EACH + 1)
        with self.assertRaises(S.Refused) as cm:
            capture(r)
        self.assertEqual(cm.exception.code, "unexpected_entry")

    def test_restore_rejects_extra_files_that_differ_from_the_manifest(self):
        r = self.run_with_extras()
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone())
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        import restore_brain_v3_backup as R
        problems = []

        class P(list):
            def add(self, m):
                self.append(m)
        rec = jload(os.path.join(dest, "INTERNAL-MANIFEST.json"))["runs"][0]
        spit(os.path.join(dest, "dati", "runs", "brain-v3-memo", "extra", "appunti.txt"), b"alterato")
        spit(os.path.join(dest, "dati", "runs", "brain-v3-memo", "intruso.txt"), b"x")
        problems = P()
        R.check_extras(dest, rec, problems)
        self.assertTrue(any("extra/appunti.txt diverso" in m for m in problems), problems)
        self.assertTrue(any("file non previsti" in m and "intruso.txt" in m for m in problems), problems)


# ======================================================================================================
# Installazione / rollback della sola estensione e cancello del timer
# ======================================================================================================

INSTALLER = os.path.join(HERE, "..", "extbackup", "brain-v3", "install_brain_v3_extension.py")
FAKE_SYSTEMCTL = r'''#!%(py)s
import json, os, signal, sys, time
state_p, log_p, unitdir = os.environ["FAKE_SC_STATE"], os.environ["FAKE_SC_LOG"], os.environ["FAKE_SC_UNITDIR"]
st = {"enabled": [], "active": []}
if os.path.exists(state_p):
    with open(state_p) as f:
        st = json.load(f)
verb, args = sys.argv[1], sys.argv[2:]
with open(log_p, "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
if verb in os.environ.get("FAKE_SC_SLEEP", "-").split(","):
    time.sleep(30)
if verb == os.environ.get("FAKE_SC_KILL", "-"):
    os.kill(os.getppid(), signal.SIGKILL)
    sys.exit(0)
if verb in os.environ.get("FAKE_SC_FAIL", "-").split(","):
    print("errore simulato di systemd", file=sys.stderr)
    sys.exit(1)
units = [x for x in args if not x.startswith("-")]
unit = units[-1] if units else ""
def save():
    with open(state_p, "w") as f:
        json.dump(st, f)
def exists():
    return os.path.isfile(os.path.join(unitdir, unit))
if verb == "is-active":
    if unit == "superbot-extbackup.service":
        s = os.environ.get("FAKE_SC_CLASSIC", "inactive")
    elif unit == "superbot-extbackup-v3.service":
        s = os.environ.get("FAKE_SC_V3_SERVICE", "inactive")
    else:
        s = "active" if unit in st["active"] else "inactive"
    print(s)
    sys.exit(0 if s == "active" else 3)
if verb == "is-enabled":
    s = "enabled" if unit in st["enabled"] else "disabled"
    print(s)
    sys.exit(0 if s == "enabled" else 1)
if verb == "enable":
    if not exists():
        print("Failed to enable unit: Unit file %%s does not exist." %% unit, file=sys.stderr)
        sys.exit(1)
    if unit not in st["enabled"]:
        st["enabled"].append(unit)
    if "--now" in args and unit not in st["active"]:
        st["active"].append(unit)
    save()
elif verb == "start":
    if not exists():
        print("Unit not found", file=sys.stderr)
        sys.exit(5)
    if unit not in st["active"]:
        st["active"].append(unit)
    save()
elif verb == "stop":
    if unit in st["active"]:
        st["active"].remove(unit)
    save()
elif verb == "disable":
    if unit in st["enabled"]:
        st["enabled"].remove(unit)
    if "--now" in args and unit in st["active"]:
        st["active"].remove(unit)
    save()
sys.exit(0)
'''


@unittest.skipUnless(HAVE_AGE, "mancano age/git")
class InstallerBase(PipelineCase):
    profile_args = ()

    def setUp(self):
        super().setUp()
        t = self.td.name
        self.tools = os.path.join(t, "tools")
        self.classic = os.path.join(t, "extbackup")
        self.systemd = os.path.join(t, "systemd")
        self.state = os.path.join(t, "state")
        self.v2 = os.path.join(t, "v2")
        self.key = os.path.join(t, "key")
        self.fakebin = os.path.join(t, "fakebin")
        self.sc_state = os.path.join(t, "sc-state.json")
        self.sc_log = os.path.join(t, "systemctl.log")
        for d in (self.tools, self.classic, self.systemd, self.fakebin):
            os.makedirs(d)
        for n in ("external_backup.py", "backup_brain.py", "backup_app_db.py"):
            shutil.copyfile(os.path.join(HERE, n), os.path.join(self.tools, n))
        for n in ("recipient.txt", "known_hosts", "run.sh", "status.json"):
            spit(os.path.join(self.classic, n), n + "\n")                 # il V1: l'installatore usa SOLO known_hosts
        spit(self.key, "chiave finta\n")
        with open(os.path.join(self.fakebin, "systemctl"), "w") as f:
            f.write(FAKE_SYSTEMCTL % {"py": sys.executable})
        os.chmod(os.path.join(self.fakebin, "systemctl"), 0o755)

    def env(self, **extra):
        return dict(os.environ, PATH=self.fakebin + os.pathsep + os.environ["PATH"], FAKE_SC_STATE=self.sc_state,
                    FAKE_SC_LOG=self.sc_log, FAKE_SC_UNITDIR=self.systemd, **extra)

    def inst_args(self, *args, host="vps-singapore"):
        return [sys.executable, INSTALLER, *args, "--tools-dir", self.tools, "--work-dir", self.work,
                "--classic-dir", self.classic, "--systemd-dir", self.systemd, "--state-dir", self.state,
                "--v2-dir", self.v2, "--ssh-key", self.key, "--allow-nonroot", "--host-name", host, *self.profile_args]

    def run_inst(self, *args, host="vps-singapore", **env):
        p = subprocess.run(self.inst_args(*args, host=host), capture_output=True, text=True, timeout=120, env=self.env(**env))
        return p.returncode, p.stdout + p.stderr

    def log(self):
        return slurp(self.sc_log).decode().splitlines() if os.path.exists(self.sc_log) else []

    def mutating_calls(self):
        return [l for l in self.log() if l.split()[0] in ("daemon-reload", "enable", "start", "stop", "disable")]

    def sc(self):
        return jload(self.sc_state) if os.path.exists(self.sc_state) else {"enabled": [], "active": []}

    def approval(self, *extra):
        rc, out = self.run_inst("status")
        return [l.split()[-1] for l in out.splitlines() if "impronta di approvazione" in l][0]

    def snap(self):
        out = {}
        for d in (self.tools, self.classic, self.systemd, self.state, self.work, self.v2):
            if os.path.isdir(d):
                for k, v in tree_state(d).items():
                    out[os.path.join(d, k)] = v
        out["radice"] = sorted(n for n in os.listdir(self.td.name) if n in ("extbackup-v3", "work") or ".removed-" in n)
        return out

    def classic_state(self):
        st = {n: sha(slurp(os.path.join(self.tools, n))) for n in ("external_backup.py", "backup_brain.py", "backup_app_db.py")}
        st.update({"classic/" + n: sha(slurp(os.path.join(self.classic, n))) for n in os.listdir(self.classic)})
        return st

    def make_proof(self):
        """Un backup VERO (pubblicato e verificato) e il certificato di un ripristino indipendente."""
        self.populated_runs()
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        (arc,) = self.archives(self.clone())
        cert = os.path.join(self.td.name, "cert.json")
        rc, rout, _ = self.restore(arc, None, None, "--certificate", cert)
        self.assertEqual(rc, 0, rout)
        return cert, arc

    def assert_timer_invariant(self):
        """Mai un timer attivo o abilitato senza un'unita' valida (identica al file rivisto)."""
        st = self.sc()
        for unit in set(st["enabled"]) | set(st["active"]):
            path = os.path.join(self.systemd, unit)
            self.assertTrue(os.path.isfile(path), "%s attivo/abilitato ma senza unita'" % unit)
            self.assertEqual(sha(slurp(path)), sha(slurp(os.path.join(HERE, "..", "extbackup", "brain-v3", unit))))



class InstallerTests(InstallerBase):
    # ---- senza timer ----
    def test_simulation_changes_nothing(self):
        before = self.snap()
        rc, out = self.run_inst("install")
        self.assertEqual(rc, 0, out)
        self.assertIn("SIMULAZIONE RIUSCITA", out)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.mutating_calls(), [])

    def test_apply_needs_the_exact_approval_fingerprint(self):
        self.assertEqual(self.run_inst("install", "--apply")[0], 1)
        rc, out = self.run_inst("install", "--apply", "--approve", "0" * 64)
        self.assertEqual(rc, 1)
        self.assertIn("--approve", out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "run-v3.sh")))

    def test_install_without_timer_creates_only_new_files_and_leaves_the_classic_backup_alone(self):
        classic_before = self.classic_state()
        ap = self.approval()
        rc, out = self.run_inst("install", "--apply", "--approve", ap)
        self.assertEqual(rc, 0, out)
        for p in (os.path.join(self.tools, "brain_v3_snapshot.py"), os.path.join(self.tools, "external_backup_brain_v3.py"),
                  os.path.join(self.work, "run-v3.sh")):
            self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o700")
        self.assertEqual(self.classic_state(), classic_before)
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertEqual(self.mutating_calls(), [])
        self.assertEqual(jload(os.path.join(self.state, "INSTALL-MANIFEST.json"))["stato"], "completo")
        rc, out = self.run_inst("install", "--apply", "--approve", ap)
        self.assertIn("GIA' INSTALLATO", out)
        p = subprocess.run([sys.executable, "-I", os.path.join(self.tools, "external_backup_brain_v3.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(subprocess.run(["sh", os.path.join(self.work, "run-v3.sh"), "--mode", "boh"], capture_output=True).returncode, 2)

    def test_rollback_removes_only_the_extension_and_moves_the_work_dir_aside(self):
        classic_before = self.classic_state()
        self.assertEqual(self.run_inst("install", "--apply", "--approve", self.approval())[0], 0)
        os.makedirs(os.path.join(self.work, "v3"))
        spit(os.path.join(self.work, "v3", "status.json"), "{}")
        rc, out = self.run_inst("rollback")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.exists(os.path.join(self.tools, "brain_v3_snapshot.py")))
        rc, out = self.run_inst("rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(self.tools, "brain_v3_snapshot.py")))
        self.assertFalse(os.path.exists(self.work))
        moved = [d for d in os.listdir(self.td.name) if d.startswith("work.removed-")]
        self.assertEqual(len(moved), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.td.name, moved[0], "v3", "status.json")))
        self.assertEqual(self.classic_state(), classic_before)
        self.assertEqual(self.run_inst("rollback", "--apply")[0], 1)

    def test_blocks_when_classic_backup_is_running_or_tools_differ_or_file_exists(self):
        rc, out = self.run_inst("install", FAKE_SC_CLASSIC="active")
        self.assertEqual(rc, 1)
        self.assertIn("e' in corso", out)
        with open(os.path.join(self.tools, "external_backup.py"), "a") as f:
            f.write("# modificato\n")
        rc, out = self.run_inst("install")
        self.assertIn("versione rivista", out)
        shutil.copyfile(os.path.join(HERE, "external_backup.py"), os.path.join(self.tools, "external_backup.py"))
        os.makedirs(self.work)
        spit(os.path.join(self.work, "run-v3.sh"), "#!/bin/sh\necho mio\n")
        rc, out = self.run_inst("install")
        self.assertEqual(rc, 1)
        self.assertIn("non lo sovrascrivo", out)

    def test_modified_installed_file_is_left_in_place_by_rollback(self):
        self.assertEqual(self.run_inst("install", "--apply", "--approve", self.approval())[0], 0)
        with open(os.path.join(self.tools, "brain_v3_snapshot.py"), "a") as f:
            f.write("# modifica dell'operatore\n")
        rc, out = self.run_inst("rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("MODIFICATO dopo l'installazione", out)
        self.assertTrue(os.path.exists(os.path.join(self.tools, "brain_v3_snapshot.py")))

    def test_status_is_read_only_and_says_that_no_real_backup_is_certified(self):
        before = self.snap()
        rc, out = self.run_inst("status")
        self.assertEqual(rc, 0, out)
        self.assertIn("cancello del timer: NON soddisfatto", out)
        self.assertIn("nessun backup reale", out)
        self.assertEqual(self.snap(), before)
        self.assertEqual(self.mutating_calls(), [])

    # ---- il cancello del timer ----
    def test_first_install_with_timer_is_blocked_without_any_real_backup(self):
        ap = self.approval("--with-timer")
        before = self.snap()
        for args in (("install", "--with-timer"), ("install", "--with-timer", "--apply", "--approve", ap)):
            rc, out = self.run_inst(*args)
            self.assertEqual(rc, 1, out)
            self.assertIn("CANCELLO DEL TIMER", out)
            self.assertIn("nessun backup reale", out)
        self.assertEqual(self.snap(), before)
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertEqual(self.mutating_calls(), [])

    def test_a_plan_or_exit_3_or_failed_run_do_not_satisfy_the_gate(self):
        ap = self.approval("--with-timer")
        self.assertEqual(self.backup()[0], 3)                                 # niente da proteggere
        self.assertIn("CANCELLO", self.run_inst("install", "--with-timer", "--apply", "--approve", ap)[1])
        self.populated_runs()
        self.assertEqual(self.backup("--plan")[0], 0)
        rc, out = self.run_inst("install", "--with-timer", "--apply", "--approve", ap)
        self.assertEqual(rc, 1, out)
        self.assertIn("CANCELLO", out)
        os.unlink(os.path.join(self.runs, "brain-v3-alfa1", "mandate.json"))
        self.assertEqual(self.backup()[0], 1)                                 # tentativo fallito
        self.assertIn("CANCELLO", self.run_inst("install", "--with-timer", "--restore-certificate", "/non/esiste")[1])
        self.assertEqual(os.listdir(self.systemd), [])

    def test_gate_rejects_missing_forged_same_host_or_mismatching_certificates(self):
        cert, _arc = self.make_proof()
        base = jload(cert)
        self.assertIn("manca --restore-certificate", self.run_inst("install", "--with-timer")[1])
        rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", cert, host=base["eseguito_su"])
        self.assertEqual(rc, 1)
        self.assertIn("QUESTA macchina", out)
        cases = {"altro_archivio": lambda c: c.update(archivio_sha256="0" * 64),
                 "altra_testa": lambda c: c["run"][0].update(testa="f" * 64),
                 "meno_eventi": lambda c: c["run"][0].update(eventi=1),
                 "run_mancante": lambda c: c.update(run=c["run"][:1]),
                 "strumenti": lambda c: c["strumenti"].update({"brain_v3_snapshot.py": "1" * 64}),
                 "esito": lambda c: c.update(esito="FALLITO"),
                 "famiglia": lambda c: c.update(famiglia="brain-free")}
        for name, mutate in cases.items():
            with self.subTest(caso=name):
                c = json.loads(json.dumps(base))
                mutate(c)
                path = os.path.join(self.td.name, "cert-%s.json" % name)
                spit(path, json.dumps(c))
                rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", path)
                self.assertEqual(rc, 1, out)
                self.assertIn("CANCELLO DEL TIMER", out)
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertEqual(self.mutating_calls(), [])

    def test_restore_writes_no_certificate_when_anything_fails(self):
        self.populated_runs()
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone())
        cert = os.path.join(self.td.name, "cert-no.json")
        other = os.path.join(self.td.name, "altra.txt")
        keygen(other)
        rc, _out, _ = self.restore(arc, None, other, "--certificate", cert)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(cert))

    def test_gate_satisfied_activates_the_timer_without_a_backlog_run(self):
        cert, _arc = self.make_proof()
        ap = self.approval("--with-timer")
        rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", cert)
        self.assertEqual(rc, 0, out)
        self.assertIn("cancello del timer soddisfatto", out)
        self.assertEqual(self.mutating_calls(), [])                          # la simulazione non attiva niente
        rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap)
        self.assertEqual(rc, 0, out)
        unit_timer = slurp(os.path.join(self.systemd, "superbot-extbackup-v3.timer")).decode()
        self.assertFalse([l for l in unit_timer.splitlines() if l.strip().startswith("Persistent")])
        calls = self.mutating_calls()
        self.assertEqual(calls, ["daemon-reload", "enable superbot-extbackup-v3.timer", "start superbot-extbackup-v3.timer"])
        self.assertFalse([l for l in self.log() if "--now" in l or l.endswith("superbot-extbackup-v3.service") and l.startswith(("start", "restart"))])
        self.assertEqual(self.sc(), {"enabled": ["superbot-extbackup-v3.timer"], "active": ["superbot-extbackup-v3.timer"]})
        self.assertTrue(os.path.isfile(os.path.join(self.work, "timer-gate.json")))
        self.assertEqual(jload(os.path.join(self.state, "INSTALL-MANIFEST.json"))["stato"], "completo")
        self.assert_timer_invariant()
        n = len(self.log())
        rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap)
        self.assertIn("GIA' INSTALLATO", out)
        self.assertEqual(self.mutating_calls(), calls)                       # nessuna nuova azione di systemd

    def test_reactivation_after_rollback_starts_no_backup_either(self):
        cert, _arc = self.make_proof()
        ap = self.approval("--with-timer")
        args = ("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap)
        self.assertEqual(self.run_inst(*args)[0], 0)
        rc, out = self.run_inst("rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.sc(), {"enabled": [], "active": []})
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertFalse(os.path.exists(os.path.join(self.work, "timer-gate.json")))
        open(self.sc_log, "w").close()
        # il lavoro (stato, clone con le prove) e' stato spostato, non cancellato: lo rimetto dov'era per riattivare
        (moved,) = [d for d in os.listdir(self.td.name) if d.startswith("work.removed-")]
        shutil.move(os.path.join(self.td.name, moved), self.work)
        for f in ("run-v3.sh",):
            if os.path.exists(os.path.join(self.work, f)):
                os.unlink(os.path.join(self.work, f))
        rc, out = self.run_inst(*args)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.mutating_calls(), ["daemon-reload", "enable superbot-extbackup-v3.timer", "start superbot-extbackup-v3.timer"])
        self.assertNotIn("start superbot-extbackup-v3.service", self.log())
        self.assertFalse([l for l in self.log() if "--now" in l])
        self.assert_timer_invariant()

    def test_partial_systemd_failures_leave_nothing_active_and_nothing_installed(self):
        cert, _arc = self.make_proof()
        ap = self.approval("--with-timer")
        args = ("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap)
        classic_before = self.classic_state()
        for verb in ("daemon-reload", "enable", "start"):
            with self.subTest(fallisce=verb):
                for f in (self.sc_state, self.sc_log):
                    if os.path.exists(f):
                        os.unlink(f)
                rc, out = self.run_inst(*args, FAKE_SC_FAIL=verb)
                self.assertEqual(rc, 1, out)
                self.assertIn("installazione interrotta", out)
                self.assertEqual(self.sc(), {"enabled": [], "active": []})
                self.assertEqual(os.listdir(self.systemd), [])
                self.assertFalse(os.path.exists(os.path.join(self.work, "timer-gate.json")))
                self.assertFalse(os.path.exists(os.path.join(self.state, "INSTALL-MANIFEST.json")))
                self.assertFalse(os.path.exists(os.path.join(self.tools, "brain_v3_snapshot.py")))
                self.assertIn("disable superbot-extbackup-v3.timer", self.log())   # compensazione eseguita
                self.assertEqual(self.classic_state(), classic_before)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "v3", "status.json")), "lo stato del backup non si tocca")

    def test_unexpected_service_start_triggers_compensation(self):
        cert, _arc = self.make_proof()
        ap = self.approval("--with-timer")
        rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap,
                                FAKE_SC_V3_SERVICE="active")
        self.assertEqual(rc, 1, out)
        self.assertIn("il servizio di backup e' partito", out)
        self.assertEqual(self.sc(), {"enabled": [], "active": []})
        self.assertEqual(os.listdir(self.systemd), [])

    def test_sigkill_during_install_never_leaves_a_timer_without_a_valid_unit_and_rollback_recovers(self):
        cert, _arc = self.make_proof()
        ap = self.approval("--with-timer")
        args = ("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap)
        for verb in ("daemon-reload", "enable", "start"):
            with self.subTest(ucciso_a=verb):
                for f in (self.sc_state, self.sc_log):
                    if os.path.exists(f):
                        os.unlink(f)
                p = subprocess.run(self.inst_args(*args), capture_output=True, text=True, timeout=120, env=self.env(FAKE_SC_KILL=verb))
                self.assertEqual(p.returncode, -9)
                self.assert_timer_invariant()                                  # unita' valide finche' qualcosa e' attivo
                self.assertEqual(jload(os.path.join(self.state, "INSTALL-MANIFEST.json"))["stato"], "in_corso")
                rc, out = self.run_inst("install", "--with-timer", "--restore-certificate", cert)
                self.assertEqual(rc, 1)
                self.assertIn("interrotta", out)
                rc, out = self.run_inst("status")
                self.assertIn("installazione interrotta", out)
                rc, out = self.run_inst("rollback", "--apply")
                self.assertEqual(rc, 0, out)
                self.assertEqual(self.sc(), {"enabled": [], "active": []})
                self.assertEqual(os.listdir(self.systemd), [])
                self.assertFalse(os.path.exists(os.path.join(self.work, "timer-gate.json")))
                self.assertFalse(os.path.exists(os.path.join(self.tools, "brain_v3_snapshot.py")))
                (moved,) = [d for d in os.listdir(self.td.name) if d.startswith("work.removed-")]
                shutil.move(os.path.join(self.td.name, moved), self.work)       # rimetto il lavoro per il giro dopo

    def test_sigterm_during_install_compensates(self):
        cert, _arc = self.make_proof()
        ap = self.approval("--with-timer")
        args = ("install", "--with-timer", "--restore-certificate", cert, "--apply", "--approve", ap)
        proc = subprocess.Popen(self.inst_args(*args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                env=self.env(FAKE_SC_SLEEP="daemon-reload"))
        self.addCleanup(lambda: (proc.kill(), proc.wait(timeout=30), proc.stdout.close()))
        end = time.time() + 60
        while time.time() < end and not any(l.startswith("daemon-reload") for l in self.log()):
            time.sleep(0.05)
        proc.terminate()
        out, _ = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 143, out)
        self.assertIn("ESITO: FALLITO", out)
        self.assertEqual(self.sc(), {"enabled": [], "active": []})
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertFalse(os.path.exists(os.path.join(self.state, "INSTALL-MANIFEST.json")))

    def test_rollback_removes_temp_files_left_by_an_interrupted_write(self):
        self.assertEqual(self.run_inst("install", "--apply", "--approve", self.approval())[0], 0)
        stray = os.path.join(self.work, ".run-v3.sh.new.4242")
        spit(stray, "residuo")
        rc, out = self.run_inst("rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("temporaneo di un'installazione interrotta", out)
        (moved,) = [d for d in os.listdir(self.td.name) if d.startswith("work.removed-")]
        self.assertFalse(os.path.exists(os.path.join(self.td.name, moved, ".run-v3.sh.new.4242")))


if __name__ == "__main__":
    unittest.main()
