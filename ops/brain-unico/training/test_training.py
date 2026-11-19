"""Test SINTETICI del Training Dataset Builder (nessun dato reale, nessuna rete)."""
import hashlib
import contextlib
import io
import json
from collections import Counter
import os
import random
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import attestation as AT  # noqa: E402
import builder as B  # noqa: E402
import candles as C  # noqa: E402
import eligibility as EL  # noqa: E402
import features as F  # noqa: E402
import labels as L  # noqa: E402
import readers as R  # noqa: E402
import schema as S  # noqa: E402
import split as SP  # noqa: E402
import sufficiency as SU  # noqa: E402

IV = C.INTERVAL_MS
T0 = 1_795_000_000_000 // IV * IV
H = 3_600_000
DAY = 86_400_000


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rd(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def gen_candles(n, seed=1, start=T0, p0=100.0, drift=0.0):
    rng = random.Random(seed)
    out, prev = [], p0
    for i in range(n):
        c = prev * (1 + rng.gauss(drift, 0.002))
        o = prev
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.001)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.001)))
        out.append({"t": start + i * IV, "o": round(o, 6), "h": round(h, 6), "l": round(l, 6), "c": round(c, 6),
                    "v": round(100 + rng.random() * 50, 3)})
        prev = c
    return out


def write_store(root, symbol, cs):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, symbol + ".jsonl"), "w") as fh:
        for c in cs:
            fh.write(json.dumps(c) + "\n")
    return C.CandleStore(root)


def hand(t0, bars):
    """bars: [(o,h,l,c)] consecutive da t0."""
    return [{"t": t0 + i * IV, "o": o, "h": h, "l": l, "c": c, "v": 1} for i, (o, h, l, c) in enumerate(bars)]


META = {"exchange": "bitget", "market": "usdt_perp", "interval_ms": IV, "price_basis": "last", "source": "public_rest_v2"}


def write_meta(root, **over):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, C.META_FILE), "w") as fh:
        json.dump({**META, **over}, fh)


RUN_SEQ = [0]


def make_run(dirpath, files, verdict="PASS", complete=True, status="OK", mutate=None):
    """Directory di run sigillata SINTETICA, coerente come quella di `sealed_root.execute` (mode=full, SNAPSHOT_GO)."""
    RUN_SEQ[0] += 1
    run_dir = os.path.join(dirpath, "run-20261119T120000Z-r%06d" % RUN_SEQ[0])
    for sub in (("public",), ("private", "snapshot"), ("private", "reports")):
        os.makedirs(os.path.join(run_dir, *sub))
    items = [{"id": "src%d" % i, "status": status, "sha256": sha(f)} for i, f in enumerate(files)]
    entries = [{"path": "snapshot/src%d/%s" % (i, os.path.basename(f)), "bytes": os.path.getsize(f), "sha256": sha(f)}
               for i, f in enumerate(files)]
    chains = {"db0": {"ok": True, "count": 3, "head": "h" * 64, "max_seq": 3, "per_run": {}}}
    man = {"complete": True, "unstable_count": 0, "entries": entries, "manifest_digest": AT.manifest_digest(entries)}
    aud = {"verdict": verdict, "checks": {"v3_chains": chains}, "certifies_backup": False}
    summ = {"schema": 1, "run_id": os.path.basename(run_dir), "mode": "full", "verdict": "SNAPSHOT_GO", "code_sha256": "c" * 64,
            "certifies_backup": False,
            "snapshot": {"complete": complete, "items": len(items), "items_ok": sum(i["status"] == "OK" for i in items)},
            "manifest": {"complete": True, "unstable_count": 0, "files_hashed": len(entries), "manifest_digest": man["manifest_digest"]},
            "audit": {"verdict": verdict, "v3_chains_ok": 1, "v3_chains_total": 1, "anchors_digest": AT.anchors_digest(chains)}}
    docs = {"summary": summ, "snapshot_log": {"complete": complete, "items": items}, "manifest": man, "audit": aud}
    if mutate:
        mutate(docs)
    for k, d in docs.items():
        with open(os.path.join(run_dir, *AT.PATHS[k]), "w") as fh:
            json.dump(d, fh)
    return run_dir


def make_attestation(dirpath, files, verdict="PASS", complete=True, status="OK", name="att", anchors=None, mutate=None):
    """Attestazione sintetica nel modo reale: run sigillata -> build_attestation. Con `anchors` (dict) registra l'ancora
    esterna come farebbe l'operatore al momento della run."""
    run_dir = make_run(dirpath, files, verdict, complete, status, mutate)
    att = AT.build_attestation(run_dir)
    if anchors is not None:
        anchors[att["run_id"]] = att["summary_sha256"]
    path = os.path.join(dirpath, name + ".json")
    with open(path, "w") as fh:
        json.dump(att, fh)
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = os.path.realpath(self.tmp.name)

    def p(self, *a):
        return os.path.join(self.t, *a)


# ----------------------------------------------------------------------------------------------- schema

class SchemaTests(unittest.TestCase):
    def good(self):
        return {"schema_version": 2, "example_id": "x", "source_system": "falco", "source_run": "run1", "source_kind": "classic",
                "record_kind": "executed", "decision_ts_ms": T0, "decision_day": S.utc_day(T0), "symbol": "BTCUSDT",
                "action": "LONG", "side": 1, "executed": True, "features": {"a": 1}, "feature_source": "logged_at_decision",
                "proposal": {}, "outcome": {"status": "closed", "net_pnl": -5.0, "closed_ms": T0 + 1, "mfe_mae_source": "none"},
                "labels": {}, "label_complete": False, "horizons_complete": False, "label_origin": "realized_outcome",
                "quality_flags": [], "eligible_for_training": True, "ineligible_reasons": [], "is_synthetic": False,
                "provenance": {"input_id": "i"}}

    def test_valid_row_and_each_corruption_is_caught(self):
        self.assertEqual(S.validate_row(self.good()), [])
        cases = {"source_system": ("source_system", "nope"), "record_kind": ("record_kind", "x"), "action": ("action", "BUY"),
                 "decision_ts_ms": ("decision_ts_ms", -1), "decision_day": ("decision_day", "1999-01-01"),
                 "feature_source": ("feature_source", "magic"), "synthetic_example": ("is_synthetic", True),
                 "schema_version": ("schema_version", 1), "label_complete": ("label_complete", "yes"),
                 "label_origin": ("label_origin", "x"), "quality_flags": ("quality_flags", "s")}
        for code, (k, v) in cases.items():
            r = self.good()
            r[k] = v
            self.assertIn(code, " ".join(S.validate_row(r)), code)

    def test_logical_inconsistencies(self):
        r = self.good(); r["side"] = -1
        self.assertIn("side_action_mismatch", S.validate_row(r))
        r = self.good(); r["features"] = None
        self.assertIn("features_vs_source", S.validate_row(r))
        r = self.good(); r["executed"] = False
        self.assertIn("executed_vs_outcome", S.validate_row(r))
        r = self.good(); r["outcome"]["net_pnl"] = None
        self.assertIn("closed_without_result", S.validate_row(r))
        r = self.good(); r["outcome"] = {"status": "open_censored", "net_pnl": 3.0, "mfe_mae_source": "none"}
        self.assertIn("result_without_close", S.validate_row(r))
        r = self.good(); r["features"] = {"a": float("nan")}
        self.assertTrue(any(e.startswith("non_finite") for e in S.validate_row(r)))
        r = self.good(); del r["provenance"]
        self.assertIn("missing:provenance", S.validate_row(r))
        r = self.good(); r["eligible_for_training"] = True; r["ineligible_reasons"] = ["duplicate"]
        self.assertIn("eligibility_inconsistent", S.validate_row(r))
        r = self.good(); r["eligible_for_training"] = False
        self.assertIn("eligibility_inconsistent", S.validate_row(r))
        r = self.good(); r["outcome"] = {"status": "closed_unknown_pnl", "net_pnl": None, "closed_ms": T0 + 1, "mfe_mae_source": "none"}
        self.assertEqual(S.validate_row(r), [])

    def test_example_id_stable_and_short_code_strips_free_text(self):
        self.assertEqual(S.example_id("falco", "run1", "executed", "k"), S.example_id("falco", "run1", "executed", "k"))
        self.assertNotEqual(S.example_id("falco", "run1", "executed", "k"), S.example_id("toro", "run1", "executed", "k"))
        self.assertEqual(S.short_code("Rifiutata: margine insufficiente per XYZ"), "rifiutata")
        self.assertEqual(S.short_code("a b/c!d"), "a_b_c_d")
        self.assertEqual(S.short_code(None), "unknown")


# ----------------------------------------------------------------------------------------------- candele

class CandleTests(Tmp):
    def test_closed_before_never_returns_an_open_candle(self):
        st = write_store(self.p("c"), "X", gen_candles(10))
        ts = T0 + 5 * IV + 1                              # la candela 5 e' APERTA (t=5*IV, chiude a 6*IV)
        got = st.closed_before("X", ts, 100)
        self.assertEqual([c.t for c in got], [T0 + i * IV for i in range(5)])
        self.assertEqual([c.t for c in st.closed_before("X", T0 + 5 * IV, 100)], [T0 + i * IV for i in range(5)])
        self.assertEqual(st.closed_before("X", T0, 5), [])

    def test_bad_rows_duplicates_and_unsorted_are_counted_not_hidden(self):
        cs = gen_candles(5)
        os.makedirs(self.p("c"))
        with open(self.p("c", "X.jsonl"), "w") as fh:
            for c in [cs[0], cs[2], cs[1], cs[1]]:
                fh.write(json.dumps(c) + "\n")
            fh.write("not json\n")
            fh.write(json.dumps({**cs[3], "h": 1.0}) + "\n")                 # high < close: non valida
            fh.write(json.dumps({**cs[4], "t": cs[4]["t"] + 1}) + "\n")      # non allineata
        st = C.CandleStore(self.p("c"))
        self.assertEqual([c.t for c in st._load("X")], [cs[0]["t"], cs[1]["t"], cs[2]["t"]])
        self.assertEqual((st.stats["bad_rows"], st.stats["duplicates"], st.stats["unsorted_fixed"]), (3, 1, 2))

    def test_symlinked_candle_file_is_not_read(self):
        write_store(self.p("real"), "X", gen_candles(3))
        os.makedirs(self.p("c"))
        os.symlink(self.p("real", "X.jsonl"), self.p("c", "X.jsonl"))
        self.assertFalse(C.CandleStore(self.p("c")).has("X"))

    def test_window_contiguity_and_first_bar(self):
        st = write_store(self.p("c"), "X", gen_candles(6))
        self.assertTrue(st.contiguous(st.window("X", T0, T0 + 6 * IV)))
        self.assertEqual(C.first_bar_start(T0 + 1, IV), T0 + IV)
        self.assertEqual(C.first_bar_start(T0, IV), T0)


# ----------------------------------------------------------------------------------------------- feature

class FeatureTests(Tmp):
    def setUp(self):
        super().setUp()
        self.cs = gen_candles(400, seed=7)
        self.ts = T0 + 200 * IV + 5 * 60_000
        self.st = write_store(self.p("c"), "ETHUSDT", self.cs)
        write_store(self.p("c"), "BTCUSDT", gen_candles(400, seed=3, p0=500.0))

    def test_features_do_not_change_when_the_future_changes(self):
        base = F.compute_features(C.CandleStore(self.p("c")), "ETHUSDT", self.ts)
        self.assertIsNotNone(base)
        mutated = [dict(c) for c in self.cs]
        for c in mutated:
            if c["t"] + IV > self.ts:                       # tutto cio' che NON e' chiuso alla decisione
                c.update(o=1.0, h=999.0, l=0.5, c=777.0, v=1e9)
        write_store(self.p("c2"), "ETHUSDT", mutated)
        write_store(self.p("c2"), "BTCUSDT", gen_candles(400, seed=3, p0=500.0))
        self.assertEqual(F.compute_features(C.CandleStore(self.p("c2")), "ETHUSDT", self.ts), base)

    def test_features_do_change_when_the_past_changes(self):
        base = F.compute_features(self.st, "ETHUSDT", self.ts)
        mutated = [dict(c) for c in self.cs]
        mutated[190].update(c=mutated[190]["c"] * 1.2, h=mutated[190]["h"] * 1.3)
        write_store(self.p("c3"), "ETHUSDT", mutated)
        self.assertNotEqual(F.compute_features(C.CandleStore(self.p("c3")), "ETHUSDT", self.ts), base)

    def test_asof_is_the_last_closed_candle_and_values_are_plausible(self):
        f = F.compute_features(self.st, "ETHUSDT", self.ts)
        self.assertEqual(f["asof_candle_open_ms"], T0 + 199 * IV)           # la 200 e' aperta alla decisione
        self.assertEqual(f["feature_set"], F.FEATURE_SET)
        self.assertTrue(0 <= f["rsi14"] <= 100)
        self.assertGreater(f["atr_pct14"], 0)
        self.assertIn(f["ema20_50"], (-1, 1))
        self.assertIsNotNone(f["btc_ret_24h"])
        self.assertEqual((f["hour_utc"], f["dow"]), (__import__("time").gmtime(self.ts / 1000).tm_hour,
                                                     __import__("time").gmtime(self.ts / 1000).tm_wday))

    def test_insufficient_history_or_gap_yields_none_not_invented_values(self):
        self.assertIsNone(F.compute_features(self.st, "ETHUSDT", T0 + 50 * IV))
        gappy = [c for i, c in enumerate(self.cs) if i != 150]
        write_store(self.p("g"), "ETHUSDT", gappy)
        self.assertIsNone(F.compute_features(C.CandleStore(self.p("g")), "ETHUSDT", self.ts))
        self.assertIsNone(F.compute_features(self.st, "NOPEUSDT", self.ts))

    def test_deterministic(self):
        a = json.dumps(F.compute_features(self.st, "ETHUSDT", self.ts), sort_keys=True)
        b = json.dumps(F.compute_features(C.CandleStore(self.p("c")), "ETHUSDT", self.ts), sort_keys=True)
        self.assertEqual(a, b)


# ----------------------------------------------------------------------------------------------- etichette

class LabelTests(Tmp):
    def store(self, bars, start=T0 + IV):
        return write_store(self.p("c" + str(random.random())), "X", hand(start, bars))

    def test_entry_is_next_bar_open_and_costs_are_subtracted(self):
        st = self.store([(100, 101, 99, 100)] * 4 + [(110, 111, 109, 110)] * 4)       # decisione a meta' della barra 0
        r = L.forward_returns(st, "X", T0 + 60_000, 1, 16, {"1h": H})
        self.assertTrue(r["1h"]["complete"])
        self.assertAlmostEqual(r["1h"]["gross_bp"], 0.0, places=4)                      # open 100 -> close ultima barra 100
        r2 = L.forward_returns(st, "X", T0 + 60_000, 1, 16, {"2h": 2 * H})
        self.assertAlmostEqual(r2["2h"]["gross_bp"], 1000.0, places=3)                  # 100 -> 110
        self.assertAlmostEqual(r2["2h"]["net_bp"], 984.0, places=3)
        r3 = L.forward_returns(st, "X", T0 + 60_000, -1, 16, {"2h": 2 * H})
        self.assertAlmostEqual(r3["2h"]["gross_bp"], -1000.0, places=3)

    def test_missing_candle_makes_the_label_incomplete_never_interpolated(self):
        bars = hand(T0 + IV, [(100, 101, 99, 100)] * 8)
        del bars[3]
        st = write_store(self.p("gap"), "X", bars)
        self.assertEqual(L.forward_returns(st, "X", T0 + 60_000, 1, 0, {"2h": 2 * H}), {"2h": {"complete": False}})
        self.assertEqual(L.forward_returns(st, "X", T0 + 60_000, 1, 0, {"10h": 10 * H}), {"10h": {"complete": False}})

    def test_barrier_stop_target_ambiguous_timeout_long_and_short(self):
        mk = lambda bars: self.store(bars)  # noqa: E731
        stop = L.barrier(mk([(100, 100.5, 98.9, 99.5)] + [(99.5, 100, 99, 99.8)] * 7), "X", T0 + 60_000, 1, 0.01, 0.02, 2 * H, 10)
        self.assertEqual((stop["first"], stop["bars"], stop["ambiguous"]), ("stop", 1, False))
        self.assertAlmostEqual(stop["net_bp"], -100 - 10, places=3)
        tgt = L.barrier(mk([(100, 100.4, 99.8, 100.2), (100.2, 102.5, 100, 102)] + [(102, 103, 101, 102)] * 6), "X", T0 + 60_000, 1, 0.01, 0.02, 2 * H, 10)
        self.assertEqual((tgt["first"], tgt["bars"]), ("target", 2))
        self.assertAlmostEqual(tgt["net_bp"], 200 - 10, places=3)
        amb = L.barrier(mk([(100, 103, 98, 100)] + [(100, 101, 99.5, 100)] * 7), "X", T0 + 60_000, 1, 0.01, 0.02, 2 * H, 0)
        self.assertEqual((amb["first"], amb["ambiguous"]), ("stop", True))              # stop e target nella stessa barra: vince lo stop
        to = L.barrier(mk([(100, 100.5, 99.6, 100.1)] * 8), "X", T0 + 60_000, 1, 0.01, 0.02, 2 * H, 0)
        self.assertEqual((to["first"], to["bars"], to["ambiguous"]), ("timeout", 8, False))
        sh = L.barrier(mk([(100, 100.3, 98.9, 99)] + [(99, 99.5, 98.5, 99)] * 7), "X", T0 + 60_000, -1, 0.01, 0.02, 2 * H, 0)
        self.assertEqual(sh["first"], "timeout")
        sh2 = L.barrier(mk([(100, 101.5, 99.9, 101)] + [(101, 101.5, 100.9, 101)] * 7), "X", T0 + 60_000, -1, 0.01, 0.02, 2 * H, 0)
        self.assertEqual(sh2["first"], "stop")

    def test_barrier_invalid_or_incomplete_inputs(self):
        st = self.store([(100, 101, 99, 100)] * 8)
        for kw in ({"side": 0}, {"stop_pct": 0}, {"target_pct": -1}):
            args = dict(side=1, stop_pct=0.01, target_pct=0.02)
            args.update(kw)
            self.assertFalse(L.barrier(st, "X", T0 + 60_000, args["side"], args["stop_pct"], args["target_pct"], 2 * H, 0)["complete"])
        quiet = self.store([(100, 100.5, 99.6, 100)] * 8)
        self.assertFalse(L.barrier(quiet, "X", T0 + 60_000, 1, 0.01, 0.02, 10 * H, 0)["complete"])  # nessun tocco, orizzonte non coperto

    def test_mfe_mae_in_r(self):
        st = self.store([(100, 103, 99.5, 102), (102, 104, 98, 99), (99, 100, 98.5, 99.5)], start=T0)
        m = L.mfe_mae_r(st, "X", 1, 100.0, 98.0, T0 - 1, T0 + 3 * IV)               # R = 2: MFE (104-100)/2, MAE (100-98)/2
        self.assertEqual(m, {"mfe_r": 2.0, "mae_r": 1.0, "resolution_ms": IV})
        self.assertIsNone(L.mfe_mae_r(st, "X", 1, 100.0, 100.0, T0, T0 + IV))            # R nullo
        self.assertIsNone(L.mfe_mae_r(st, "X", 1, 100.0, 98.0, T0, T0 + 10 * IV))        # mancano candele


# ----------------------------------------------------------------------------------------------- lettori

class ReaderTests(Tmp):
    def classic_dir(self, name="hawk"):
        d = self.p(name)
        os.makedirs(d)
        return d

    def test_sanitize_features_drops_free_text_and_non_finite(self):
        out = R.sanitize_features({"rsi": 55.5, "ok": True, "pattern": "bull flag", "reason": "testo libero",
                                   "why": ["a", "b"], "sig_type": "scalp", "long text": "x" * 40, "nan": float("nan"),
                                   "seasonal": "bla", "k" * 50: 1, "tier": "A", "none": None})
        self.assertEqual(out, {"rsi": 55.5, "ok": True, "sig_type": "scalp", "tier": "A", "none": None})
        self.assertEqual(R.sanitize_features("x"), {})

    def test_exit_reason_mapping(self):
        for raw, exp in (("SL colpito", "stop"), ("stop loss", "stop"), ("TP2", "take_profit"), ("take profit", "take_profit"),
                         ("chiusura manuale", "manual"), ("manual", "manual"), ("liquidazione", "liquidation"),
                         ("timeout 24h", "timeout"), ("Claude close", "brain_close"), ("boh", "unknown"), (None, "unknown")):
            self.assertEqual(R.map_exit_reason(raw), exp, raw)

    def test_classic_partials_history_duplicates_and_history_only(self):
        d = self.classic_dir()
        ll = [{"ev": "open", "id": "p1", "run_no": 2, "ts": T0, "symbol": "A", "side": 1, "entry": 10, "features": {"rsi1h": 50}},
              {"ev": "close", "id": "p1", "run_no": 2, "close_ms": T0 + H, "net": -3.0, "net_r": -0.5, "why": "SL"},
              {"ev": "close", "id": "p1", "run_no": 2, "close_ms": T0 + 2 * H, "net": 1.0, "net_r": 0.2, "why": "TP"},
              {"ev": "candidate", "ts": T0, "symbol": "B", "side": -1, "status": "rifiutata:margine", "features": {}},
              {"ev": "split_fill", "id": "p1"}, {"ev": "claude_call", "ts": 1}]
        th = [{"id": "p1", "close_ms": T0 + H, "net": -3.0},                       # duplicato del learning_log
              {"id": "p9", "close_ms": T0 + 5, "net": 4.0, "symbol": "C", "side": 1, "open_ms": T0 - H},   # solo storico
              ["vecchia", "riga"]]
        with open(os.path.join(d, "learning_log.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(x) for x in ll) + "\nBROKEN\n")
        with open(os.path.join(d, "trade_history.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(x) for x in th) + "\n")
        r = R.read_classic(d)
        self.assertEqual(len(r["closes"][(2, "p1")]), 2)
        self.assertIn((None, "p9"), r["closes"])
        self.assertEqual((r["stats"]["history_duplicates_skipped"], r["stats"]["history_only_closes"]), (1, 1))
        self.assertEqual((r["stats"]["bad_rows"], r["stats"]["non_dict_rows"]), (1, 1))
        self.assertEqual(len(r["candidates"]), 1)
        self.assertEqual(r["other_events"], {"split_fill": 1, "claude_call": 1})

    def test_classic_missing_files_are_reported(self):
        d = self.classic_dir()
        r = R.read_classic(d)
        self.assertEqual(r["stats"]["file_missing"], 2)
        self.assertEqual((r["opens"], r["closes"], r["candidates"]), ({}, {}, []))

    def test_open_frozen_refuses_sidecars_and_symlinks(self):
        db = self.p("a.db")
        sqlite3.connect(db).execute("CREATE TABLE t(a)").connection.close()
        open(db + "-wal", "w").close()
        with self.assertRaises(ValueError):
            R.open_frozen(db)
        os.remove(db + "-wal")
        os.symlink(db, self.p("ln.db"))
        with self.assertRaises(ValueError):
            R.open_frozen(self.p("ln.db"))
        R.open_frozen(db).close()


# ----------------------------------------------------------------------------------------------- sorgenti sintetiche per il builder

def make_v3(path, events):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, portfolio_id TEXT, run_id TEXT,"
                " kind TEXT, occurred_at_ms INTEGER, source TEXT, payload_json TEXT, previous_hash TEXT, event_hash TEXT)")
    for i, (eid, kind, ts, payload) in enumerate(events):
        con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,previous_hash,"
                    "event_hash) VALUES(?,?,?,?,?,?,?,?,?)", (eid, "brain", "runA", kind, ts, "s", json.dumps(payload), "0" * 64, "0" * 64))
    con.commit()
    con.close()


def v3_events(base):
    """Un NO_TRADE, un OPEN eseguito+chiuso a stop, uno manuale, un rifiuto, un'apertura non collegata, una ancora aperta."""
    ev = [("d1", "brain_decision", base, {"kind": "NO_TRADE", "status": "REJECTED", "symbol": "ETHUSDT", "regime": "RANGING",
                                          "rationale": "TESTO-RISERVATO"}),
          ("d2", "brain_decision", base + 2 * H, {"kind": "OPEN", "status": "APPROVED", "symbol": "ETHUSDT", "regime": "TRENDING",
                                                  "strategy_id": "S07", "strategy_origin": "library"}),
          ("o2", "paper_open", base + 2 * H + 1000, {"position_id": "pos2", "symbol": "ETHUSDT", "side": 1, "fill_price": "100",
                                                     "quantity": "10", "stop_price": "99", "leverage": 30, "originating_ai": "deepseek",
                                                     "decision_event_id": "d2", "rationale": "TESTO-RISERVATO"}),
          ("c2", "paper_close", base + 4 * H, {"position_id": "pos2", "realized_pnl": "-12.5", "fees": "1.2", "reason": "stop",
                                               "held_ms": 2 * H, "loss_exceeds_margin": False}),
          ("d3", "brain_decision", base + 5 * H, {"kind": "OPEN", "status": "APPROVED", "symbol": "BTCUSDT"}),
          ("o3", "paper_open", base + 5 * H + 1000, {"position_id": "pos3", "symbol": "BTCUSDT", "side": -1, "fill_price": "200",
                                                     "quantity": "1", "stop_price": "202", "leverage": 20, "decision_event_id": "d3"}),
          ("c3", "paper_close", base + 6 * H, {"position_id": "pos3", "realized_pnl": "3.0", "fees": "0.5", "reason": "manual",
                                               "held_ms": H}),
          ("d4", "brain_decision", base + 7 * H, {"kind": "OPEN", "status": "RISK_REJECTED", "symbol": "SOLUSDT"}),
          ("o5", "paper_open", base + 8 * H, {"position_id": "pos5", "symbol": "ETHUSDT", "side": 1, "fill_price": "100",
                                              "quantity": "1", "stop_price": "99", "leverage": 25}),
          ("d6", "brain_decision", base + 9 * H, {"kind": "OPEN", "status": "APPROVED", "symbol": "ETHUSDT"}),
          ("o6", "paper_open", base + 9 * H + 1000, {"position_id": "pos6", "symbol": "ETHUSDT", "side": 1, "fill_price": "101",
                                                     "quantity": "1", "stop_price": "100", "leverage": 25, "decision_event_id": "d6"}),
          ("d7", "brain_decision", base + 10 * H, {"kind": "HOLD", "status": "REJECTED", "symbol": "ETHUSDT"})]
    return ev


class BuilderBase(Tmp):
    def setUp(self):
        super().setUp()
        self.base = T0 + 120 * IV + 5 * 60_000                          # 120 barre di storia prima delle decisioni
        n = 120 + 4 * 24 * 4 + 10
        write_store(self.p("candles"), "ETHUSDT", gen_candles(n, seed=11, p0=100.0))
        write_store(self.p("candles"), "BTCUSDT", gen_candles(n, seed=12, p0=200.0))
        write_store(self.p("candles"), "SOLUSDT", gen_candles(n, seed=13, p0=50.0))
        write_meta(self.p("candles"))
        self.v3 = self.p("arena_minimax.db")
        make_v3(self.v3, v3_events(self.base))
        d = self.p("hawk")
        os.makedirs(d)
        ll = [{"ev": "open", "id": "p1", "run_no": 3, "ts": self.base + 12 * H, "symbol": "ETHUSDT", "side": 1, "price": 100, "entry": 100,
               "sl": 99, "tp": 102, "leverage": 10, "confidence": 70, "source": "claude", "trade_type": "scalp",
               "features": {"rsi1h": 55.5, "reason": "TESTO-RISERVATO", "tier": "B"}},
              {"ev": "close", "id": "p1", "run_no": 3, "open_ms": self.base + 12 * H, "close_ms": self.base + 13 * H, "net": -7.5,
               "gross": -6, "fees": 1.0, "funding": 0.5, "net_r": -0.9, "mfe_r": 0.3, "mae_r": 1.1, "why": "SL", "symbol": "ETHUSDT",
               "side": 1},
              {"ev": "open", "id": "p2", "run_no": 3, "ts": self.base + 14 * H, "symbol": "BTCUSDT", "side": -1, "entry": 200, "sl": 202,
               "tp": 196, "leverage": 10, "features": {"rsi1h": 40.0}},
              {"ev": "close", "id": "p2", "run_no": 3, "open_ms": self.base + 14 * H, "close_ms": self.base + 15 * H, "net": 4.0,
               "why": "manuale", "symbol": "BTCUSDT", "side": -1, "net_r": 0.5},
              {"ev": "open", "id": "p3", "run_no": 3, "ts": self.base + 16 * H, "symbol": "SOLUSDT", "side": 1, "entry": 50, "sl": 49,
               "features": {}},
              {"ev": "candidate", "ts": self.base + 17 * H, "symbol": "ETHUSDT", "side": -1, "price": 100,
               "status": "rifiutata:margine insufficiente", "features": {"rsi1h": 61.0}}]
        with open(os.path.join(d, "learning_log.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(x) for x in ll) + "\n")
        with open(os.path.join(d, "trade_history.jsonl"), "w") as fh:
            fh.write(json.dumps({"id": "p1", "close_ms": self.base + 13 * H, "net": -7.5}) + "\n")
        os.makedirs(self.p("att"))
        self.anchors = {}
        self.spec = {"inputs": [
            {"id": "falco_hawk", "source_system": "falco", "kind": "classic", "path": d,
             "attestation": make_attestation(self.p("att"), [self.p("hawk", "learning_log.jsonl"), self.p("hawk", "trade_history.jsonl")],
                                             name="a1", anchors=self.anchors)},
            {"id": "arena_minimax", "source_system": "arena_minimax", "kind": "v3", "path": self.v3,
             "attestation": make_attestation(self.p("att"), [self.v3], name="a2", anchors=self.anchors)}]}

    def build(self, **kw):
        kw.setdefault("anchors", self.anchors)
        return B.build(self.spec, self.p("candles"), **kw)

    def by(self, res, **kv):
        return [r for r in res["rows"] if all(r.get(k) == v or r["outcome"].get(k) == v or r["provenance"].get(k) == v for k, v in kv.items())]


class BuilderRows(BuilderBase):
    def test_every_decision_type_becomes_a_row(self):
        res = self.build()
        kinds = {}
        for r in res["rows"]:
            kinds[(r["source_system"], r["record_kind"])] = kinds.get((r["source_system"], r["record_kind"]), 0) + 1
        self.assertEqual(kinds, {("arena_minimax", "no_trade"): 1, ("arena_minimax", "executed"): 4,
                                 ("arena_minimax", "candidate_rejected"): 1, ("falco", "executed"): 3,
                                 ("falco", "candidate_rejected"): 1})
        self.assertTrue(all(S.validate_row(r) == [] for r in res["rows"]))
        self.assertEqual(sum(1 for r in res["rows"] if r["is_synthetic"]), 0)

    def test_losses_manual_closes_and_open_positions_are_kept(self):
        res = self.build()
        loss = next(r for r in res["rows"] if r["source_system"] == "arena_minimax" and r["outcome"].get("net_pnl") == -12.5)
        self.assertEqual((loss["outcome"]["exit_reason"], loss["action"], loss["outcome"]["status"]), ("stop", "LONG", "closed"))
        self.assertAlmostEqual(loss["outcome"]["net_r"], -12.5 / 10.0, places=3)             # rischio = |100-99| x 10
        man = [r for r in res["rows"] if r["outcome"].get("is_manual")]
        self.assertEqual(sorted(r["source_system"] for r in man), ["arena_minimax", "falco"])
        cens = [r for r in res["rows"] if r["outcome"]["status"] == "open_censored"]
        self.assertEqual(len(cens), 3)                                                       # pos5, pos6 (V3) e p3 (classico)
        self.assertTrue(all(r["outcome"]["net_pnl"] is None and r["labels"]["status"] == "ok" for r in cens))

    def test_no_trade_and_rejections_carry_counterfactual_labels_for_both_sides(self):
        res = self.build()
        nt = self.by(res, record_kind="no_trade")[0]
        self.assertEqual((nt["action"], nt["side"], nt["executed"], nt["outcome"]["status"]), ("NO_TRADE", 0, False, "not_executed"))
        self.assertEqual(sorted(nt["labels"]["sides"]), ["long", "short"])
        self.assertEqual(nt["feature_source"], "reconstructed_from_candles")
        self.assertTrue(nt["label_complete"], nt["labels"])
        self.assertEqual(nt["labels"]["sides"]["long"]["barrier"]["barrier_source"], "atr_default")
        rej = [r for r in res["rows"] if r["action"] == "OPEN_REJECTED"][0]
        self.assertEqual((rej["side"], rej["proposal"]["reject_code"]), (0, "risk_rejected"))
        self.assertEqual(sorted(rej["labels"]["sides"]), ["long", "short"])

    def test_classic_rows_use_logged_features_and_logged_mfe_mae_and_funding(self):
        res = self.build()
        p1 = next(r for r in res["rows"] if r["source_system"] == "falco" and r["outcome"].get("net_pnl") == -7.5)
        self.assertEqual(p1["feature_source"], "logged_at_decision")
        self.assertEqual(p1["features"], {"rsi1h": 55.5, "tier": "B"})                      # niente testo libero
        o = p1["outcome"]
        self.assertEqual((o["mfe_mae_source"], o["mfe_r"], o["mae_r"], o["funding_known"], o["funding"], o["exit_reason"]),
                         ("logged", 0.3, 1.1, True, 0.5, "stop"))
        self.assertEqual(p1["labels"]["sides"]["long"]["barrier"]["barrier_source"], "proposal")
        self.assertEqual(p1["source_run"], "run3")
        rej = next(r for r in res["rows"] if r["source_system"] == "falco" and r["record_kind"] == "candidate_rejected")
        self.assertEqual((rej["action"], rej["proposal"]["reject_code"]), ("SHORT", "margine_insufficiente"))
        self.assertEqual(sum(1 for r in res["rows"] if r["source_system"] == "falco" and r["record_kind"] == "executed"), 3)
        self.assertEqual(res["per_input"]["falco_hawk"]["stats"]["reader:history_duplicates_skipped"], 1)

    def test_v3_executed_rows_have_reconstructed_features_and_mfe_mae(self):
        res = self.build()
        r = next(r for r in res["rows"] if r["source_system"] == "arena_minimax" and r["outcome"].get("net_pnl") == -12.5)
        self.assertEqual(r["feature_source"], "reconstructed_from_candles")
        self.assertEqual(r["outcome"]["mfe_mae_source"], "approximate_candles")
        self.assertIn("mfe_mae_approximate", r["quality_flags"])
        self.assertEqual(r["outcome"]["mfe_mae_resolution_ms"], IV)
        self.assertIsNotNone(r["outcome"]["mfe_r"])
        self.assertFalse(r["outcome"]["funding_known"])
        self.assertEqual((r["proposal"]["strategy_id"], r["proposal"]["regime"]), ("s07", "trending"))
        self.assertEqual(r["provenance"]["link_status"], "linked")

    def test_unlinked_and_dangling_opens_are_flagged(self):
        res = self.build()
        un = next(r for r in res["rows"] if r["source_system"] == "arena_minimax" and r["outcome"].get("opened_ms") == self.base + 8 * H)
        self.assertEqual(un["provenance"]["link_status"], "unlinked")

    def test_non_entry_decisions_are_counted_not_turned_into_rows(self):
        res = self.build()
        self.assertEqual(res["per_input"]["arena_minimax"]["stats"]["non_entry_decisions"], 1)

    def test_without_candles_rows_survive_with_missing_features_and_incomplete_labels(self):
        res = B.build(self.spec, None)
        v3 = [r for r in res["rows"] if r["source_system"] == "arena_minimax"]
        self.assertTrue(all(r["feature_source"] == "none" and r["features"] is None for r in v3))
        self.assertTrue(all(r["label_complete"] is False and r["labels"]["status"] == "no_candles" for r in res["rows"]))
        self.assertTrue(any(r["outcome"].get("net_pnl") == -12.5 for r in v3))                  # l'esito reale resta

    def test_cross_input_duplicate_trade_is_flagged_not_deleted(self):
        d2 = self.p("hawk_copy")
        os.makedirs(d2)
        for n in ("learning_log.jsonl", "trade_history.jsonl"):
            with open(self.p("hawk", n)) as src, open(os.path.join(d2, n), "w") as dst:
                dst.write(src.read())
        self.spec["inputs"].append({"id": "falco_copy", "source_system": "toro", "kind": "classic", "path": d2})
        res = self.build()
        dups = [r for r in res["rows"] if r["provenance"].get("duplicate_of")]
        self.assertEqual(len(dups), 3)                                                       # i 3 trade eseguiti, non i candidati
        self.assertEqual(res["duplicate_trades_flagged"], 3)
        self.assertEqual(len([r for r in res["rows"] if r["source_system"] == "toro"]), 4)    # tutto resta nel dataset

    def test_same_input_twice_is_deduplicated_by_example_id(self):
        self.spec["inputs"].append(dict(self.spec["inputs"][0], id="again"))
        res = self.build()
        self.assertGreater(res["duplicate_example_ids"], 0)
        self.assertEqual(len({r["example_id"] for r in res["rows"]}), len(res["rows"]))

    def test_bad_input_spec_is_rejected(self):
        for bad in ({"id": "x", "source_system": "nope", "kind": "classic", "path": "/x"},
                    {"id": "x", "source_system": "falco", "kind": "magic", "path": "/x"}):
            with self.assertRaises(ValueError):
                B.build({"inputs": [bad]}, None)


class BuilderBrainFree(Tmp):
    def test_tolerant_reader_and_rows(self):
        db = self.p("brain.sqlite3")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY, kind TEXT, ts INTEGER, body TEXT)")
        evs = [("experiment_started", T0, {}),
               ("ai_input", T0 + 10, {"symbol": "ETHUSDT", "btc_ret": 0.01, "rsi": 55, "note": "testo"}),
               ("open", T0 + 20, {"position_id": 1, "symbol": "ETHUSDT", "side": "long", "entry": 100, "sl": 99, "tp": 102, "leverage": 10}),
               ("partial_trade", T0 + H, {"position_id": 1, "symbol": "ETHUSDT", "net": 2.0}),
               ("trade_closed", T0 + 2 * H, {"position_id": 1, "symbol": "ETHUSDT", "net": -1.0, "reason": "SL", "fees": 0.5}),
               ("ai_decision", T0 + 3 * H, {"symbol": "BTCUSDT", "action": "hold"}),
               ("ai_decision", T0 + 100, {"symbol": "ETHUSDT", "action": "hold"}),           # a 80 ms dall'apertura: coperta
               ("execution_rejected", T0 + 4 * H, {"symbol": "SOLUSDT", "side": "short", "reason": "Margine: insufficiente"}),
               ("experiment_reframed", T0 + 5 * H, {"old_cash": 1}),
               ("open", T0 + 6 * H, {"position_id": 1, "symbol": "ETHUSDT", "side": "short", "entry": 100, "sl": 101})]
        for k, ts, b in evs:
            con.execute("INSERT INTO events(kind,ts,body) VALUES(?,?,?)", (k, ts, json.dumps(b)))
        con.commit()
        con.close()
        res = B.build({"inputs": [{"id": "bf", "source_system": "brain_storico", "kind": "brain_free", "path": db}]}, None)
        rows = res["rows"]
        kinds = sorted((r["record_kind"], r["action"]) for r in rows)
        self.assertEqual(kinds, [("candidate_rejected", "SHORT"), ("executed", "LONG"), ("executed", "SHORT"), ("no_trade", "NO_TRADE")])
        ex1 = next(r for r in rows if r["action"] == "LONG")
        self.assertEqual((ex1["outcome"]["net_pnl"], ex1["outcome"]["exit_reason"], ex1["outcome"]["partials"], ex1["source_run"]),
                         (-1.0, "stop", 2, "epoch0"))
        self.assertEqual(ex1["features"], {"btc_ret": 0.01, "rsi": 55})
        self.assertEqual(next(r for r in rows if r["action"] == "SHORT" and r["executed"])["source_run"], "epoch1")  # ID riusato: epoca diversa
        self.assertTrue(all(r["provenance"]["schema_unverified"] for r in rows))
        self.assertIn("open", res["keys_seen"]["bf"])
        self.assertEqual(next(r for r in rows if r["record_kind"] == "no_trade")["symbol"], "BTCUSDT")  # ETH e' coperto dalla riga eseguita

    def test_empty_or_wrong_sqlite_does_not_crash_the_builder(self):
        db = self.p("empty.sqlite3")
        sqlite3.connect(db).execute("CREATE TABLE events(seq INTEGER PRIMARY KEY, kind TEXT, ts INTEGER, body TEXT)").connection.close()
        res = B.build({"inputs": [{"id": "bf", "source_system": "brain_storico", "kind": "brain_free", "path": db}]}, None)
        self.assertEqual(res["rows"], [])


class BuilderOutputs(BuilderBase):
    def test_outputs_private_numbers_only_summary_and_no_free_text(self):
        res = self.build()
        info = B.write_outputs(res, self.p("out"))
        self.assertEqual(oct(os.stat(self.p("out")).st_mode & 0o777), "0o700")
        for n, m in (("examples.jsonl", 0o600), ("manifest.json", 0o600), ("public_summary.json", 0o644)):
            self.assertEqual(os.stat(self.p("out", n)).st_mode & 0o777, m, n)
        self.assertEqual(sha(self.p("out", "examples.jsonl")), info["examples_sha256"])
        for n in ("examples.jsonl", "manifest.json", "public_summary.json"):
            self.assertNotIn("TESTO-RISERVATO", rd(self.p("out", n)))
        pub = json.loads(rd(self.p("out", "public_summary.json")))
        self.assertEqual(pub["classification"], "NUMBERS_ONLY")
        for leak in (self.t, "ETHUSDT", "BTCUSDT", "pos2"):
            self.assertNotIn(leak, json.dumps(pub))
        self.assertEqual((pub["rows"], pub["executed"], pub["losses"], pub["manual_closes"]), (len(res["rows"]), 7, 2, 2))
        self.assertEqual(pub["sufficiency"]["status"], "insufficient")

    def test_deterministic_digest_and_inputs_untouched(self):
        before = {p: sha(p) for p in (self.v3, self.p("hawk", "learning_log.jsonl"), self.p("hawk", "trade_history.jsonl"))}
        a = B.write_outputs(self.build(), self.p("o1"))
        b = B.write_outputs(self.build(), self.p("o2"))
        self.assertEqual(a["examples_sha256"], b["examples_sha256"])
        self.assertEqual(before, {p: sha(p) for p in before})
        self.assertEqual(sorted(os.listdir(self.p("hawk"))), ["learning_log.jsonl", "trade_history.jsonl"])

    def test_rows_are_sorted_chronologically(self):
        ts = [r["decision_ts_ms"] for r in self.build()["rows"]]
        self.assertEqual(ts, sorted(ts))

    def test_output_guards(self):
        res = self.build()
        os.makedirs(self.p("exists"))
        with self.assertRaises(FileExistsError):
            B.write_outputs(res, self.p("exists"))
        repo = self.p("repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        with self.assertRaises(ValueError):
            B.write_outputs(res, os.path.join(repo, "out"))
        os.symlink(self.t, self.p("lnk"))
        with self.assertRaises(ValueError):
            B.write_outputs(res, os.path.join(self.p("lnk"), "out"))
        with self.assertRaises(ValueError):
            B.write_outputs(res, self.p("nope", "out"))
        self.assertFalse(os.path.exists(self.p("nope")))

    def test_no_network_is_ever_used(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("rete vietata")), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("rete vietata")):
            B.write_outputs(self.build(), self.p("o"))

    def test_cli_end_to_end(self):
        sp = self.p("spec.json")
        with open(sp, "w") as fh:
            json.dump(self.spec, fh)
        self.assertEqual(B.main(["--spec", sp, "--out", self.p("cli_out"), "--candles", self.p("candles")]), 0)
        self.assertEqual(B.main(["--spec", sp, "--out", self.p("cli_out"), "--candles", self.p("candles")]), 1)   # esiste gia'

    def test_manifest_records_input_hashes_but_not_paths(self):
        B.write_outputs(self.build(), self.p("out"))
        m = json.loads(rd(self.p("out", "manifest.json")))
        self.assertEqual(m["per_input"]["arena_minimax"]["files"], {"arena_minimax.db": sha(self.v3)})
        self.assertEqual(sorted(m["per_input"]["falco_hawk"]["files"]), ["learning_log.jsonl", "trade_history.jsonl"])
        self.assertNotIn(self.t, json.dumps(m))
        self.assertEqual(m["classification"], "PRIVATE_DO_NOT_COMMIT")


# ----------------------------------------------------------------------------------------------- split e sufficienza

def synth_rows(n, days=None, span_ms=H, verified="i", executed=True, manual=False, feats=True, complete=True, start=T0,
               distinct_days=None):
    rows = []
    for i in range(n):
        if distinct_days:
            ts = start // DAY * DAY + (i % distinct_days) * DAY + (i // distinct_days) * 60_000     # esattamente N giorni UTC distinti
        else:
            ts = start + (i * (days * DAY // n if days else 600_000))
        rows.append({"example_id": f"e{i:05d}", "decision_ts_ms": ts, "decision_day": S.utc_day(ts), "source_system": "falco",
                     "executed": executed, "is_synthetic": False, "features": {"a": 1} if feats else None,
                     "eligible_for_training": True, "ineligible_reasons": [], "quality_flags": [],
                     "label_complete": complete, "outcome": {"status": "closed" if executed else "not_executed",
                                                           "net_pnl": 1.0 if executed else None, "closed_ms": ts + span_ms if executed else None,
                                                           "is_manual": manual},
                     "provenance": {"input_id": verified}})
    return rows


class SplitTests(unittest.TestCase):
    def test_chronological_split_has_no_leakage_over_many_random_datasets(self):
        for seed in range(25):
            rng = random.Random(seed)
            rows = []
            for i in range(rng.randint(30, 120)):
                ts = T0 + rng.randint(0, 20 * DAY)
                rows.append({"example_id": f"s{seed}-{i}", "decision_ts_ms": ts, "is_synthetic": False, "provenance": {},
                             "eligible_for_training": True, "ineligible_reasons": [],
                             "outcome": {"closed_ms": ts + rng.randint(0, 3 * DAY) if rng.random() < 0.7 else None}})
            emb = rng.choice([0, H, DAY])
            sp = SP.chronological_split(rows, embargo_ms=emb)
            SP.assert_no_leakage(sp["train"], sp["valid"] + sp["test"], emb)
            SP.assert_no_leakage(sp["train"] + sp["valid"], sp["test"], emb)
            ids = [r["example_id"] for k in ("train", "valid", "test", "purged") for r in sp[k]]
            self.assertEqual(len(ids), len(set(ids)))                                         # nessun esempio in due insiemi
            self.assertEqual(set(ids), {r["example_id"] for r in rows})                      # niente perso: i purgati restano elencati

    def test_purging_removes_labels_that_straddle_the_boundary(self):
        rows = synth_rows(30, days=30)
        straddler = rows[17]
        straddler["outcome"]["closed_ms"] = rows[25]["decision_ts_ms"] + DAY                  # chiude dentro il test
        sp = SP.chronological_split(rows, embargo_ms=0, span_ms=H)
        self.assertIn(straddler["example_id"], {r["example_id"] for r in sp["purged"]} | {r["example_id"] for r in sp["test"]})
        self.assertNotIn(straddler["example_id"], {r["example_id"] for r in sp["train"]})

    def test_embargo_widens_the_purge(self):
        rows = synth_rows(60, days=60)
        a = SP.chronological_split(rows, embargo_ms=0, span_ms=H)
        b = SP.chronological_split(rows, embargo_ms=5 * DAY, span_ms=H)
        self.assertGreater(len(b["purged"]), len(a["purged"]))
        SP.assert_no_leakage(b["train"], b["test"], 5 * DAY, H)

    def test_duplicates_and_synthetic_rows_are_excluded_from_splits(self):
        rows = synth_rows(30, days=30)
        for i, why in ((3, "duplicate"), (4, "synthetic")):
            rows[i]["eligible_for_training"], rows[i]["ineligible_reasons"] = False, [why]
        used = {r["example_id"] for k in ("train", "valid", "test", "purged") for r in SP.chronological_split(rows)[k]}
        self.assertEqual((rows[3]["example_id"] in used, rows[4]["example_id"] in used), (False, False))

    def test_walk_forward_folds_are_leak_free_and_ordered(self):
        rows = synth_rows(120, days=60)
        folds = SP.walk_forward(rows, 20 * DAY, 5 * DAY, 5 * DAY, embargo_ms=DAY, span_ms=H)
        self.assertGreaterEqual(len(folds), 5)
        for f in folds:
            SP.assert_no_leakage(f["train"], f["test"], DAY, H)
            self.assertTrue(all(r["decision_ts_ms"] >= f["test_start_ms"] for r in f["test"]))
        self.assertEqual([f["test_start_ms"] for f in folds], sorted(f["test_start_ms"] for f in folds))

    def test_assert_no_leakage_detects_real_leaks(self):
        rows = synth_rows(10, days=10)
        with self.assertRaises(AssertionError):
            SP.assert_no_leakage(rows[5:], rows[:5])                                          # train dopo il test
        with self.assertRaises(AssertionError):
            SP.assert_no_leakage(rows[:5], rows[3:])                                          # sovrapposizione
        late = synth_rows(10, days=10)
        late[2]["outcome"]["closed_ms"] = late[8]["decision_ts_ms"] + 1
        with self.assertRaises(AssertionError):
            SP.assert_no_leakage(late[:5], late[5:], 0, H)

    def test_invalid_fractions(self):
        for fr in ((0.5, 0.5), (0.5, 0.3, 0.3), (0.0, 0.5, 0.5)):
            with self.assertRaises(ValueError):
                SP.chronological_split(synth_rows(10), fr)


class SufficiencyTests(unittest.TestCase):
    def rep(self, rows, verified=None):
        return SU.report(rows)

    def test_thresholds_exactly(self):
        rr = lambda n, d: self.rep(synth_rows(n, distinct_days=d))  # noqa: E731
        self.assertEqual(rr(299, 20)["status"], "insufficient")
        self.assertEqual(rr(300, 19)["status"], "insufficient")
        self.assertEqual(rr(300, 20)["status"], "shadow_offline_ok")
        self.assertEqual(rr(999, 60)["status"], "shadow_offline_ok")
        self.assertEqual(rr(1000, 44)["status"], "shadow_offline_ok")
        self.assertEqual(rr(1000, 20)["distinct_days"], 20)
        r = rr(1000, 45)
        self.assertEqual(r["status"], "promotion_considerable")
        self.assertIn("explicit_user_approval", r["promotion_also_requires"])
        self.assertIn("non garanzie", r["note"])

    def test_only_eligible_rows_count_and_reasons_are_reported(self):
        rows = synth_rows(300, distinct_days=25)
        self.assertEqual(self.rep(rows)["status"], "shadow_offline_ok")
        for i in range(20):
            rows[i]["eligible_for_training"], rows[i]["ineligible_reasons"] = False, ["label_incomplete"]
        r = self.rep(rows)
        self.assertEqual((r["eligible_examples"], r["status"], r["excluded_by_reason"]), (280, "insufficient", {"label_incomplete": 20}))

    def test_sufficiency_ignores_a_verified_argument(self):
        rows = synth_rows(300, distinct_days=25)
        for x in rows:
            x["eligible_for_training"], x["ineligible_reasons"] = False, ["input_not_attested"]
        self.assertEqual(SU.report(rows, {"i"})["status"], "insufficient")                     # un set "verified" non conta piu'

    def test_duplicates_excluded_and_reported(self):
        rows = synth_rows(300, distinct_days=25)
        rows[0]["eligible_for_training"], rows[0]["ineligible_reasons"] = False, ["duplicate"]
        r = self.rep(rows)
        self.assertEqual((r["eligible_examples"], r["status"], r["excluded_by_reason"]), (299, "insufficient", {"duplicate": 1}))

    def test_non_executed_counterfactual_rows_count_when_labeled(self):
        r = self.rep(synth_rows(300, days=25, executed=False))
        self.assertEqual((r["status"], r["counterfactual_simulations"], r["realized_outcomes"]), ("shadow_offline_ok", 300, 0))

    def test_losses_and_wins_are_reported(self):
        rows = synth_rows(10, days=2)
        for r in rows[:4]:
            r["outcome"]["net_pnl"] = -2.0
        r = self.rep(rows)
        self.assertEqual((r["losses"], r["wins"], r["realized_outcomes"]), (4, 6, 10))


# ----------------------------------------------------------------------------------------------- fix della revisione PR #118

class BarrierPrefixTests(Tmp):
    def store(self, bars, start=T0 + IV):
        return write_store(self.p("c" + str(random.random())), "X", hand(start, bars))

    def test_early_hit_is_complete_even_if_archive_ends_before_the_horizon(self):
        st = self.store([(100, 100.4, 99.8, 100.2), (100.2, 102.5, 100, 102)])              # target alla 2a barra; l'archivio finisce li'
        b = L.barrier(st, "X", T0 + 60_000, 1, 0.01, 0.02, 24 * H, 0)
        self.assertEqual((b["first"], b["bars"], b["complete"]), ("target", 2, True))
        self.assertEqual(L.forward_returns(st, "X", T0 + 60_000, 1, 0, {"24h": 24 * H}), {"24h": {"complete": False}})   # il forward NO

    def test_no_hit_with_short_archive_is_incomplete_timeout_requires_full_horizon(self):
        st = self.store([(100, 100.5, 99.6, 100.1)] * 10)
        b = L.barrier(st, "X", T0 + 60_000, 1, 0.01, 0.02, 24 * H, 0)
        self.assertEqual((b["first"], b["complete"], b["bars_available"]), ("incomplete", False, 10))
        full = self.store([(100, 100.5, 99.6, 100.1)] * 96)
        self.assertEqual(L.barrier(full, "X", T0 + 60_000, 1, 0.01, 0.02, 24 * H, 0)["first"], "timeout")

    def test_gap_before_the_hit_blocks_the_label_gap_after_it_does_not(self):
        before = hand(T0 + IV, [(100, 100.4, 99.8, 100.2)] * 3 + [(100, 100.4, 99.8, 100.2)] * 3)
        del before[2]                                                                       # buco prima di qualunque tocco
        before[-1] = dict(before[-1], h=103)                                               # il target e' DOPO il buco: non dimostrabile
        st = write_store(self.p("gap1"), "X", before)
        self.assertFalse(L.barrier(st, "X", T0 + 60_000, 1, 0.01, 0.02, 3 * H, 0)["complete"])
        after = hand(T0 + IV, [(100, 100.4, 99.8, 100.2), (100.2, 102.6, 100, 102)] + [(102, 103, 101, 102)] * 4)
        del after[4]                                                                        # buco DOPO il tocco
        st2 = write_store(self.p("gap2"), "X", after)
        b = L.barrier(st2, "X", T0 + 60_000, 1, 0.01, 0.02, 3 * H, 0)
        self.assertEqual((b["first"], b["complete"]), ("target", True))

    def test_label_complete_is_the_barrier_while_horizons_complete_is_separate(self):
        rows = {}
        base = T0 + 150 * IV + 60_000
        cs = gen_candles(150 + 6, seed=5)                                                   # solo 6 candele dopo la decisione
        cs[150] = dict(cs[150], l=cs[150]["o"] * 0.90)                                      # crollo nella prima candela futura
        write_store(self.p("cd"), "ETHUSDT", cs)
        write_meta(self.p("cd"))
        make_v3(self.p("j.db"), [("d1", "brain_decision", base, {"kind": "NO_TRADE", "status": "REJECTED", "symbol": "ETHUSDT"})])
        res = B.build({"inputs": [{"id": "x", "source_system": "arena_minimax", "kind": "v3", "path": self.p("j.db")}]}, self.p("cd"))
        r = res["rows"][0]
        self.assertTrue(r["label_complete"], r["labels"])                                   # il lato long ha toccato lo stop subito
        self.assertFalse(r["horizons_complete"])                                            # ma gli orizzonti 4h/24h non sono coperti


class MfeMaeApproximationTests(Tmp):
    def test_partial_bars_are_excluded_so_spikes_outside_the_position_do_not_count(self):
        bars = [(100, 101, 99.5, 100.5), (100.5, 102, 100, 101), (101, 130, 100.8, 101)]    # la 3a barra ha un picco enorme
        st = write_store(self.p("c"), "X", hand(T0, bars))
        m = L.mfe_mae_r(st, "X", 1, 100.0, 98.0, T0 - 1, T0 + 2 * IV + IV // 2)           # chiusura A META' della 3a barra
        self.assertEqual(m["mfe_r"], 1.0)                                                   # (102-100)/2: il picco a 130 NON conta
        self.assertEqual(m["resolution_ms"], IV)
        self.assertIsNone(L.mfe_mae_r(st, "X", 1, 100.0, 98.0, T0 + 10, T0 + IV // 2))     # nessuna barra intera

    def test_builder_marks_reconstructed_mfe_mae_as_approximate_not_certified(self):
        b = BuilderBase()
        b.setUp()
        try:
            res = b.build()
            r = next(r for r in res["rows"] if r["source_system"] == "arena_minimax" and r["outcome"].get("net_pnl") == -12.5)
            self.assertEqual(r["outcome"]["mfe_mae_source"], "approximate_candles")
            self.assertIn("mfe_mae_approximate", r["quality_flags"])
            p1 = next(r for r in res["rows"] if r["source_system"] == "falco" and r["outcome"].get("net_pnl") == -7.5)
            self.assertEqual(p1["outcome"]["mfe_mae_source"], "logged")
            self.assertNotIn("mfe_mae_approximate", p1["quality_flags"])
        finally:
            b.tmp.cleanup()


class AttestationTests(BuilderBase):
    def rows_of(self, res, inp):
        return [r for r in res["rows"] if r["provenance"]["input_id"] == inp]

    def test_valid_attestation_makes_inputs_attested_and_rows_eligible_where_sound(self):
        res = self.build()
        self.assertEqual(sorted(res["attested"]), ["arena_minimax", "falco_hawk"])
        self.assertEqual(res["per_input"]["falco_hawk"]["verification"]["state"], "attested")
        elig = [r for r in res["rows"] if r["eligible_for_training"]]
        self.assertGreater(len(elig), 0)
        self.assertTrue(all(S.validate_row(r) == [] for r in res["rows"]))

    def test_verified_flag_alone_is_ignored_fail_closed(self):
        for inp in self.spec["inputs"]:
            inp.pop("attestation")
            inp["verified"] = True
        res = self.build()
        self.assertEqual(res["attested"], set())
        v = res["per_input"]["falco_hawk"]["verification"]
        self.assertEqual((v["state"], v["reason"], v["verified_flag_in_spec_ignored"]), ("not_certified", "no_attestation", True))
        self.assertTrue(all("input_not_attested" in r["ineligible_reasons"] and not r["eligible_for_training"] for r in res["rows"]))
        self.assertGreater(len(res["rows"]), 0)                                              # le righe restano tutte nel dataset
        self.assertEqual(SU.report(res["rows"])["status"], "insufficient")

    def test_attestation_does_not_cover_a_modified_input(self):
        con = sqlite3.connect(self.v3)                                                       # un evento in piu' DOPO l'attestazione
        con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,previous_hash,"
                    "event_hash) VALUES('late','brain','runA','brain_decision',?, 's', ?, '0','0')",
                    (self.base + 99 * H, json.dumps({"kind": "NO_TRADE", "status": "REJECTED", "symbol": "ETHUSDT"})))
        con.commit()
        con.close()
        res = self.build()
        self.assertNotIn("arena_minimax", res["attested"])
        self.assertEqual(res["per_input"]["arena_minimax"]["verification"]["reason"], "file_hash_not_attested")
        mm = [r for r in res["rows"] if r["provenance"]["input_id"] == "arena_minimax"]
        self.assertTrue(mm and all("input_not_attested" in r["ineligible_reasons"] for r in mm))      # lette, ma non ammesse

    def test_tampered_jsonl_input_loses_attestation(self):
        with open(self.p("hawk", "trade_history.jsonl"), "a") as fh:
            fh.write(json.dumps({"id": "zz", "close_ms": 1, "net": 1}) + "\n")
        res = self.build()
        self.assertNotIn("falco_hawk", res["attested"])
        self.assertEqual(res["per_input"]["falco_hawk"]["verification"]["reason"], "file_hash_not_attested")
        self.assertIn("arena_minimax", res["attested"])

    def test_failed_audit_incomplete_snapshot_and_bad_files_are_refused(self):
        for kw, why in ((dict(verdict="FAIL"), "audit_not_passed_or_mismatch"), (dict(complete=False), "snapshot_not_complete"),
                        (dict(status="FAILED"), "snapshot_item_not_ok")):
            with self.assertRaises(ValueError) as cm:
                make_attestation(self.p("att"), [self.v3], name="x", **kw)
            self.assertEqual(str(cm.exception), why)
        self.spec["inputs"][1]["attestation"] = self.p("att", "does_not_exist.json")
        self.assertEqual(self.build()["per_input"]["arena_minimax"]["verification"]["reason"], "attestation_unreadable")
        with open(self.p("att", "junk.json"), "w") as fh:
            fh.write("[1,2]")
        self.spec["inputs"][1]["attestation"] = self.p("att", "junk.json")
        self.assertEqual(self.build()["per_input"]["arena_minimax"]["verification"]["reason"], "attestation_invalid")

    def test_attestation_for_another_file_does_not_transfer(self):
        self.spec["inputs"][1]["attestation"] = self.spec["inputs"][0]["attestation"]
        self.assertEqual(self.build()["per_input"]["arena_minimax"]["verification"]["reason"], "file_hash_not_attested")

    # ---- PR #118, 2a revisione: provenienza legata alla run reale e ad un'ancora esterna -------------------------------

    def verif(self, res, inp="arena_minimax"):
        v = res["per_input"][inp]["verification"]
        return v["state"], v["reason"]

    def test_without_external_anchor_hashes_match_but_rows_are_not_eligible(self):
        res = self.build(anchors={})
        self.assertEqual(self.verif(res), ("hash_matched_untrusted", "no_external_anchor"))
        self.assertEqual(res["attested"], set())
        rows = self.rows_of(res, "arena_minimax")
        self.assertTrue(rows and all("provenance_not_anchored" in r["ineligible_reasons"] and not r["eligible_for_training"]
                                     for r in rows))
        self.assertTrue(all("input_not_attested" not in r["ineligible_reasons"] for r in rows))   # motivo distinto e preciso
        self.assertEqual(B.summarize(res)["inputs_hash_matched_untrusted"], ["arena_minimax", "falco_hawk"])
        self.assertEqual(SU.report(res["rows"])["status"], "insufficient")

    def test_wrong_anchor_is_refused(self):
        bad = {k: "0" * 64 for k in self.anchors}
        self.assertEqual(self.verif(self.build(anchors=bad)), ("hash_matched_untrusted", "external_anchor_mismatch"))

    def test_anchors_in_the_spec_are_ignored(self):
        self.spec["anchors"] = dict(self.anchors)
        for inp in self.spec["inputs"]:
            inp["anchors"] = dict(self.anchors)
        self.assertEqual(self.verif(self.build(anchors=None)), ("hash_matched_untrusted", "no_external_anchor"))

    def test_self_made_consistent_run_is_never_attested_without_anchor(self):
        """Il controesempio della revisione: un JSON/run costruito ad arte, coerente in ogni campo, NON basta."""
        self.spec["inputs"][1]["attestation"] = make_attestation(self.p("att"), [self.v3], name="forged")
        self.assertEqual(self.verif(self.build())[0], "hash_matched_untrusted")

    def test_edited_attestation_json_is_recomputed_and_refused(self):
        path = self.spec["inputs"][1]["attestation"]
        with open(path) as fh:
            att = json.load(fh)
        att["files"]["f" * 64] = {"status": "OK"}                                           # aggiunta di un file non copiato
        with open(path, "w") as fh:
            json.dump(att, fh)
        self.assertEqual(self.verif(self.build()), ("not_certified", "attestation_stale_or_tampered"))

    def test_run_files_edited_after_attestation_are_refused(self):
        with open(self.spec["inputs"][1]["attestation"]) as fh:
            run_dir = json.load(fh)["run_dir"]
        sp = os.path.join(run_dir, *AT.PATHS["summary"])
        with open(sp) as fh:
            summ = json.load(fh)
        summ["note"] = "edited"
        with open(sp, "w") as fh:
            json.dump(summ, fh)
        self.assertEqual(self.verif(self.build()), ("not_certified", "attestation_stale_or_tampered"))
        os.remove(os.path.join(run_dir, *AT.PATHS["audit"]))
        self.assertEqual(self.verif(self.build()), ("not_certified", "run_audit_missing"))

    def test_legacy_v1_attestation_is_not_accepted(self):
        path = self.p("att", "v1.json")
        with open(path, "w") as fh:
            json.dump({"kind": "phase0_attestation_v1", "files": {sha(self.v3): {"status": "OK"}}, "audit_verdict": "PASS"}, fh)
        self.spec["inputs"][1]["attestation"] = path
        self.assertEqual(self.verif(self.build()), ("not_certified", "attestation_legacy_unbound"))

    def test_incoherent_runs_are_refused_by_build_attestation(self):
        def m(*kv):
            def f(d):
                for (doc, key), val in kv:
                    if key is None:
                        d[doc] = val
                    elif isinstance(key, tuple):
                        d[doc][key[0]][key[1]] = val
                    else:
                        d[doc][key] = val
            return f
        cases = {
            "summary_run_id_mismatch": m((("summary", "run_id"), "run-20200101T000000Z-zz")),
            "run_not_a_successful_full": m((("summary", "mode"), "preflight")),
            "snapshot_counts_mismatch": m((("summary", ("snapshot", "items")), 7)),
            "manifest_not_complete": m((("manifest", "unstable_count"), 1)),
            "snapshot_not_complete": m((("snapshot_log", "complete"), False)),        # solo il log, summary dice completo
            "manifest_digest_mismatch": m((("summary", ("manifest", "manifest_digest")), "0" * 64)),
            "audit_not_passed_or_mismatch": m((("summary", ("audit", "verdict")), "WARN")),
            "audit_chain_mismatch": m((("summary", ("audit", "anchors_digest")), "0" * 64)),
            "audit_invalid": m((("audit", "checks"), {})),
        }
        for why, mut in cases.items():
            with self.assertRaises(ValueError, msg=why) as cm:
                make_attestation(self.p("att"), [self.v3], name="bad", mutate=mut)
            self.assertEqual(str(cm.exception), why)

        def drop_from_manifest(d):
            d["manifest"]["entries"] = []
            d["manifest"]["manifest_digest"] = d["summary"]["manifest"]["manifest_digest"] = AT.manifest_digest([])
        with self.assertRaises(ValueError) as cm:
            make_attestation(self.p("att"), [self.v3], name="bad", mutate=drop_from_manifest)
        self.assertEqual(str(cm.exception), "snapshot_items_not_in_manifest")

        def forged_digest(d):                                    # digest coerenti fra loro ma NON calcolati dalle entry
            d["manifest"]["manifest_digest"] = d["summary"]["manifest"]["manifest_digest"] = "0" * 64
        with self.assertRaises(ValueError) as cm:
            make_attestation(self.p("att"), [self.v3], name="bad", mutate=forged_digest)
        self.assertEqual(str(cm.exception), "manifest_digest_mismatch")

        def broken_chain(d):
            d["audit"]["checks"]["v3_chains"]["db0"]["ok"] = False
        with self.assertRaises(ValueError) as cm:
            make_attestation(self.p("att"), [self.v3], name="bad", mutate=broken_chain)
        self.assertEqual(str(cm.exception), "audit_chain_mismatch")

    def test_run_dir_name_and_symlinked_files_are_checked(self):
        run = make_run(self.p("att"), [self.v3])
        other = self.p("att", "not-a-run")
        os.rename(run, other)
        with self.assertRaises(ValueError) as cm:
            AT.build_attestation(other)
        self.assertEqual(str(cm.exception), "run_id_invalid")
        run = make_run(self.p("att"), [self.v3])
        ap = os.path.join(run, *AT.PATHS["audit"])
        os.rename(ap, ap + ".real")
        os.symlink(ap + ".real", ap)
        with self.assertRaises(ValueError) as cm:
            AT.build_attestation(run)
        self.assertEqual(str(cm.exception), "audit_missing")

    def test_anchor_file_format_and_cli(self):
        good = self.p("att", "anchors.json")
        with open(good, "w") as fh:
            json.dump(self.anchors, fh)
        self.assertEqual(AT.load_anchors(good), self.anchors)
        bad = self.p("att", "anchors_bad.json")
        for content in ({"not-a-run": "0" * 64}, {next(iter(self.anchors)): "xyz"}, [1]):
            with open(bad, "w") as fh:
                json.dump(content, fh)
            with self.assertRaises(ValueError):
                AT.load_anchors(bad)
        spec = self.p("spec.json")
        with open(spec, "w") as fh:
            json.dump(self.spec, fh)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(B.main(["--spec", spec, "--out", self.p("o1"), "--candles", self.p("candles"), "--anchors", good]), 0)
            self.assertEqual(B.main(["--spec", spec, "--out", self.p("o2"), "--candles", self.p("candles")]), 0)
            self.assertEqual(B.main(["--spec", spec, "--out", self.p("o3"), "--candles", self.p("candles"), "--anchors", bad]), 1)
        with open(self.p("o1", "public_summary.json")) as fh:
            self.assertEqual(json.load(fh)["inputs_attested"], ["arena_minimax", "falco_hawk"])
        with open(self.p("o2", "public_summary.json")) as fh:
            o2 = json.load(fh)
        self.assertEqual((o2["inputs_attested"], o2["eligible_for_training"]), ([], 0))
        run = make_run(self.p("att"), [self.v3])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(AT.main([run, "--out", self.p("att", "cli.json")]), 0)
            self.assertEqual(AT.main([run, "--out", self.p("att", "cli.json")]), 1)        # mai sovrascrivere
            self.assertEqual(AT.main([self.p("att"), "--out", self.p("att", "cli2.json")]), 1)
        self.assertEqual(oct(os.stat(self.p("att", "cli.json")).st_mode & 0o777), "0o600")
        self.assertIn("summary_sha256=", buf.getvalue())


class EligibilityAndSplitTests(BuilderBase):
    def test_every_reason_is_reachable_and_the_full_dataset_is_preserved(self):
        res = self.build()
        total = len(res["rows"])
        reasons = {x for r in res["rows"] for x in r["ineligible_reasons"]}
        self.assertTrue({"open_censored", "manual_close_not_imitable", "decision_link_untrusted"} <= reasons, reasons)
        self.assertEqual(sum(1 for r in res["rows"] if r["eligible_for_training"]) + sum(1 for r in res["rows"] if not r["eligible_for_training"]), total)
        self.assertTrue(all(r["eligible_for_training"] == (r["ineligible_reasons"] == []) for r in res["rows"]))

    def test_unit_reasons(self):
        base = self.build()["rows"]
        ok = next(r for r in base if r["eligible_for_training"])
        att = {ok["provenance"]["input_id"]}
        self.assertEqual(EL.reasons(ok, att), [])

        def mod(**kv):
            import copy
            r = copy.deepcopy(ok)
            for k, v in kv.items():
                if k == "prov":
                    r["provenance"].update(v)
                elif k == "out":
                    r["outcome"].update(v)
                else:
                    r[k] = v
            return r
        cases = {"duplicate": mod(prov={"duplicate_of": "x"}), "synthetic": mod(is_synthetic=True),
                 "schema_unverified": mod(prov={"schema_unverified": True}), "no_features": mod(features=None),
                 "label_incomplete": mod(label_complete=False), "open_censored": mod(out={"status": "open_censored"}),
                 "unknown_pnl": mod(out={"status": "closed_unknown_pnl"}), "manual_close_not_imitable": mod(out={"is_manual": True}),
                 "decision_link_untrusted": mod(prov={"link_status": "unlinked"}),
                 "ambiguous_feature_link": mod(quality_flags=["ambiguous_feature_link"]),
                 "market_data_unattested": mod(quality_flags=["market_data_unattested"])}
        for reason, row in cases.items():
            self.assertIn(reason, EL.reasons(row, att), reason)
        self.assertIn("input_not_attested", EL.reasons(ok, set()))

    def test_splits_only_ever_contain_eligible_rows(self):
        res = self.build()
        rows = res["rows"]
        for r in rows:                                                    # rendiamo il campione abbastanza grande per dividerlo
            pass
        big = []
        for k in range(30):
            for r in rows:
                if r["eligible_for_training"]:
                    big.append(dict(r, example_id=f"{r['example_id']}-{k}", decision_ts_ms=r["decision_ts_ms"] + k * DAY))
        mixed = big + [r for r in rows if not r["eligible_for_training"]]
        sp = SP.chronological_split(mixed, embargo_ms=0)
        for part in ("train", "valid", "test"):
            self.assertTrue(all(r["eligible_for_training"] for r in sp[part]), part)
        ids = {r["example_id"] for r in sp["train"] + sp["valid"] + sp["test"]}
        self.assertFalse(ids & {r["example_id"] for r in rows if not r["eligible_for_training"]})
        self.assertTrue(all(r["eligible_for_training"] for r in SP.usable(mixed)))
        for f in SP.walk_forward(mixed, 5 * DAY, 2 * DAY, 2 * DAY, 0, H):
            self.assertTrue(all(r["eligible_for_training"] for r in f["train"] + f["test"]))

    def test_split_rejects_rows_without_the_eligibility_field(self):
        r = {"example_id": "x", "decision_ts_ms": T0}
        with self.assertRaises(KeyError):
            SP.usable([r])

    def test_summary_separates_realized_from_counterfactual_and_lists_reasons(self):
        s = B.summarize(self.build())
        self.assertGreater(s["by_label_origin"].get("counterfactual_simulation", 0), 0)
        self.assertGreater(s["by_label_origin"].get("realized_outcome", 0), 0)
        self.assertIn("counterfactual_simulation", s["quality_flags"])
        self.assertIn("atr_default_barrier", s["quality_flags"])
        self.assertEqual(s["eligible_for_training"], sum(1 for r in self.build()["rows"] if r["eligible_for_training"]))


class MarketDataAttestationTests(BuilderBase):
    def test_without_candles_meta_every_market_derived_row_is_ineligible(self):
        os.remove(self.p("candles", C.META_FILE))
        res = self.build()
        self.assertIsNotNone(res["candles"]["meta_problem"])
        self.assertIsNone(res["candles"]["meta_id"])
        mk = [r for r in res["rows"] if r["labels"]["status"] == "ok"]
        self.assertTrue(mk and all("market_data_unattested" in r["quality_flags"] and not r["eligible_for_training"] for r in mk))

    def test_meta_with_wrong_interval_or_missing_keys_is_not_accepted(self):
        write_meta(self.p("candles"), interval_ms=60_000)
        self.assertEqual(self.build()["candles"]["meta_problem"], "meta_incomplete_or_interval_mismatch")
        os.remove(self.p("candles", C.META_FILE))
        with open(self.p("candles", C.META_FILE), "w") as fh:
            json.dump({"exchange": "x"}, fh)
        self.assertEqual(self.build()["candles"]["meta_problem"], "meta_incomplete_or_interval_mismatch")

    def test_valid_meta_is_bound_into_rows_and_manifest_with_file_hashes(self):
        res = self.build()
        c = res["candles"]
        self.assertEqual((c["meta"]["exchange"], c["meta_problem"]), ("bitget", None))
        self.assertTrue(all(r["provenance"]["market_dataset_id"] == c["meta_id"] for r in res["rows"]))
        self.assertEqual(c["files_sha256"]["ETHUSDT"], sha(self.p("candles", "ETHUSDT.jsonl")))
        self.assertTrue(set(c["files_sha256"]) <= {"ETHUSDT", "BTCUSDT", "SOLUSDT"})
        B.write_outputs(res, self.p("o"))
        m = json.loads(rd(self.p("o", "manifest.json")))
        self.assertEqual(m["candles"]["meta_id"], c["meta_id"])


class BrainFreeLinkTests(Tmp):
    def build(self, evs):
        db = self.p("bf%s.sqlite3" % random.random())
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY, kind TEXT, ts INTEGER, body TEXT)")
        for k, ts, b in evs:
            con.execute("INSERT INTO events(kind,ts,body) VALUES(?,?,?)", (k, ts, json.dumps(b)))
        con.commit()
        con.close()
        return B.build({"inputs": [{"id": "bf", "source_system": "brain_storico", "kind": "brain_free", "path": db}]}, None)

    def op(self, ts, sym, pid=1):
        return ("open", ts, {"position_id": pid, "symbol": sym, "side": "long", "entry": 10, "sl": 9})

    def test_two_symbols_in_the_same_window_get_their_own_features(self):
        res = self.build([("ai_input", T0, {"symbol": "BTCUSDT", "rsi": 11}), ("ai_input", T0 + 5, {"symbol": "ETHUSDT", "rsi": 77}),
                          self.op(T0 + 100, "ETHUSDT"), self.op(T0 + 110, "BTCUSDT", 2)])
        got = {r["symbol"]: r["features"] for r in res["rows"]}
        self.assertEqual(got, {"ETHUSDT": {"rsi": 77}, "BTCUSDT": {"rsi": 11}})                # mai l'input dell'altro simbolo
        self.assertTrue(all(r["feature_source"] == "logged_at_decision" for r in res["rows"]))

    def test_input_of_another_symbol_only_is_not_used(self):
        res = self.build([("ai_input", T0, {"symbol": "BTCUSDT", "rsi": 11}), self.op(T0 + 100, "ETHUSDT")])
        r = res["rows"][0]
        self.assertEqual((r["features"], r["feature_source"]), (None, "none"))
        self.assertIn("no_features", r["ineligible_reasons"])
        self.assertEqual(res["per_input"]["bf"]["stats"]["feature_link_missing"], 1)

    def test_input_without_symbol_or_cycle_is_ambiguous_and_never_attached(self):
        res = self.build([("ai_input", T0, {"rsi": 50}), self.op(T0 + 100, "ETHUSDT")])
        r = res["rows"][0]
        self.assertEqual((r["features"], r["feature_source"]), (None, "none"))
        self.assertIn("ambiguous_feature_link", r["quality_flags"])
        self.assertIn("ambiguous_feature_link", r["ineligible_reasons"])
        self.assertEqual(res["per_input"]["bf"]["stats"]["ambiguous_feature_link"], 1)

    def test_inputs_never_cross_epochs(self):
        res = self.build([("ai_input", T0, {"symbol": "ETHUSDT", "rsi": 30}), ("experiment_reframed", T0 + 10, {}),
                          self.op(T0 + 100, "ETHUSDT")])                                       # stessa finestra, epoca diversa
        self.assertEqual((res["rows"][0]["features"], res["rows"][0]["source_run"]), (None, "epoch1"))

    def opc(self, ts, sym, cycle, pid=1):
        return ("open", ts, {"position_id": pid, "symbol": sym, "side": "long", "entry": 10, "cycle_id": cycle})

    def test_same_cycle_but_different_symbol_never_links(self):
        """Controesempio della 2a revisione: input BTC del ciclo c1, trade ETH del ciclo c1 -> nessuna feature."""
        res = self.build([("ai_input", T0, {"cycle_id": "c1", "symbol": "BTCUSDT", "rsi": 11}), self.opc(T0 + 100, "ETHUSDT", "c1")])
        r = res["rows"][0]
        self.assertEqual((r["features"], r["feature_source"]), (None, "none"))
        self.assertEqual(res["per_input"]["bf"]["stats"]["symbol_conflict"], 1)
        self.assertIn("no_features", r["ineligible_reasons"])

    def test_same_cycle_same_symbol_beats_proximity(self):
        res = self.build([("ai_input", T0, {"cycle_id": "c1", "symbol": "ETHUSDT", "rsi": 41}),
                          ("ai_input", T0 + 5, {"cycle_id": "c2", "symbol": "ETHUSDT", "rsi": 99}),
                          ("ai_input", T0 + 6, {"cycle_id": "c1", "symbol": "BTCUSDT", "rsi": 7}),
                          self.opc(T0 + 100, "ETHUSDT", "c1")])
        self.assertEqual(res["rows"][0]["features"], {"rsi": 41})

    def test_same_symbol_from_another_known_cycle_is_not_used(self):
        res = self.build([("ai_input", T0, {"cycle_id": "c2", "symbol": "ETHUSDT", "rsi": 99}), self.opc(T0 + 100, "ETHUSDT", "c1")])
        self.assertIsNone(res["rows"][0]["features"])
        self.assertEqual(res["per_input"]["bf"]["stats"]["cycle_conflict"], 1)

    def test_same_symbol_input_without_cycle_links_to_a_cycled_decision(self):
        res = self.build([("ai_input", T0, {"symbol": "ETHUSDT", "rsi": 33}), self.opc(T0 + 100, "ETHUSDT", "c1")])
        self.assertEqual(res["rows"][0]["features"], {"rsi": 33})

    def test_symbolless_input_never_links_even_with_the_same_cycle(self):
        """Politica conservativa documentata: un ciclo puo' valutare piu' simboli, le sue feature non sono attribuibili."""
        res = self.build([("ai_input", T0, {"cycle_id": "c1", "rsi": 41}), self.opc(T0 + 100, "ETHUSDT", "c1")])
        r = res["rows"][0]
        self.assertIsNone(r["features"])
        self.assertIn("ambiguous_feature_link", r["quality_flags"])
        self.assertIn("ambiguous_feature_link", r["ineligible_reasons"])

    def test_link_unit_decision_without_symbol_never_links(self):
        inputs = [{"epoch": 1, "ts": T0, "symbol": None, "cycle": "c1", "features": {"rsi": 1}},
                  {"epoch": 1, "ts": T0 + 1, "symbol": "ETHUSDT", "cycle": "c1", "features": {"rsi": 2}}]
        st = Counter()
        self.assertEqual(B.link_input(inputs, T0 + 100, 1, None, "c1", st), (None, True))
        self.assertEqual(B.link_input(inputs, T0 + 100, 1, "", "c1", st), (None, True))
        self.assertEqual(st["ambiguous_feature_link"], 2)
        self.assertEqual(B.link_input(inputs, T0 + 100, 1, "ETHUSDT", "c1", st), ({"rsi": 2}, False))

    def test_no_trade_decisions_follow_the_same_symbol_rule(self):
        res = self.build([("ai_input", T0, {"cycle_id": "c1", "symbol": "BTCUSDT", "rsi": 11}),
                          ("ai_decision", T0 + 50, {"action": "hold", "symbol": "ETHUSDT", "cycle_id": "c1"})])
        nt = [r for r in res["rows"] if r["action"] == "NO_TRADE"]
        self.assertEqual(len(nt), 1)
        self.assertIsNone(nt[0]["features"])
        self.assertEqual(res["per_input"]["bf"]["stats"]["symbol_conflict"], 1)

    def test_missing_input_leaves_row_without_features_and_ineligible(self):
        res = self.build([self.op(T0 + 100, "ETHUSDT")])
        r = res["rows"][0]
        self.assertEqual((r["features"], r["eligible_for_training"]), (None, False))
        self.assertTrue({"no_features", "schema_unverified", "input_not_attested"} <= set(r["ineligible_reasons"]))

    def test_old_or_future_inputs_are_not_used(self):
        res = self.build([("ai_input", T0, {"symbol": "ETHUSDT", "rsi": 1}), ("ai_input", T0 + 900_000, {"symbol": "ETHUSDT", "rsi": 2}),
                          self.op(T0 + 700_000, "ETHUSDT")])                                   # il 1o e' > 10 min prima, il 2o e' DOPO
        self.assertIsNone(res["rows"][0]["features"])


class OutcomeAndAnnotationTests(BuilderBase):
    def test_classic_partial_without_net_is_unknown_pnl_not_a_partial_sum(self):
        with open(self.p("hawk", "learning_log.jsonl"), "a") as fh:
            fh.write(json.dumps({"ev": "open", "id": "q1", "run_no": 3, "ts": self.base + 20 * H, "symbol": "ETHUSDT", "side": 1,
                                 "entry": 100, "sl": 99, "features": {"rsi1h": 50}}) + "\n")
            fh.write(json.dumps({"ev": "close", "id": "q1", "run_no": 3, "open_ms": self.base + 20 * H, "close_ms": self.base + 21 * H,
                                 "net": 5.0, "why": "TP", "symbol": "ETHUSDT", "side": 1}) + "\n")
            fh.write(json.dumps({"ev": "close", "id": "q1", "run_no": 3, "open_ms": self.base + 20 * H, "close_ms": self.base + 22 * H,
                                 "why": "SL", "symbol": "ETHUSDT", "side": 1}) + "\n")      # parziale SENZA net
        res = self.build()
        r = next(r for r in res["rows"] if r["source_system"] == "falco" and r["source_run"] == "run3" and r["outcome"]["status"] == "closed_unknown_pnl")
        self.assertIsNone(r["outcome"]["net_pnl"])
        self.assertEqual((r["label_origin"], r["outcome"]["partials"]), ("unknown_pnl", 2))
        self.assertIn("unknown_pnl", r["ineligible_reasons"])

    def test_arena_annotations_are_linked_by_code_and_free_text_is_not_read(self):
        ann = self.p("human_close_annotations.jsonl")
        with open(ann, "w") as fh:
            fh.write(json.dumps({"position_id": "pos3", "reason": "profit_protection", "note": "TESTO-RISERVATO"}) + "\n")
            fh.write(json.dumps({"position_id": "pos2", "reason": "trend_change"}) + "\n")      # su una chiusura NON manuale
            fh.write(json.dumps({"position_id": "pos9", "reason": "boh"}) + "\n")
        self.spec["inputs"][1]["annotations"] = ann
        res = self.build()
        man = next(r for r in res["rows"] if r["outcome"].get("is_manual") and r["source_system"] == "arena_minimax")
        self.assertEqual(man["outcome"]["manual_reason_code"], "profit_protection")
        self.assertNotIn("manual_reason_not_available", man["quality_flags"])
        stop = next(r for r in res["rows"] if r["source_system"] == "arena_minimax" and r["outcome"].get("net_pnl") == -12.5)
        self.assertIn("manual_annotation_conflict", stop["quality_flags"])                        # annotazione su una chiusura non manuale
        self.assertNotIn("TESTO-RISERVATO", json.dumps(res["rows"]))
        self.assertEqual(R.read_annotations(ann)["by_position"]["pos9"], "invalid")

    def test_manual_close_without_annotation_is_still_manual_and_flagged(self):
        ann = self.p("empty_annotations.jsonl")
        open(ann, "w").close()
        self.spec["inputs"][1]["annotations"] = ann
        man = next(r for r in self.build()["rows"] if r["outcome"].get("is_manual") and r["source_system"] == "arena_minimax")
        self.assertEqual(man["outcome"]["manual_reason_code"], "unannotated")
        self.assertIn("manual_unannotated", man["quality_flags"])

    def test_without_annotation_file_manual_rows_say_so(self):
        for r in self.build()["rows"]:
            if r["outcome"].get("is_manual"):
                self.assertIn("manual_reason_not_available", r["quality_flags"])
                self.assertIn("manual_close_not_imitable", r["ineligible_reasons"])

    def test_counterfactual_rows_are_marked_as_simulation_with_assumptions(self):
        nt = next(r for r in self.build()["rows"] if r["record_kind"] == "no_trade")
        self.assertEqual(nt["label_origin"], "counterfactual_simulation")
        self.assertTrue({"counterfactual_simulation", "atr_default_barrier"} <= set(nt["quality_flags"]))
        self.assertEqual((nt["labels"]["cost_bp"], nt["labels"]["resolution_ms"]), (16.0, IV))


if __name__ == "__main__":
    unittest.main()
