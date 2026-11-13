"""Prove dell'analizzatore LONG/SHORT (deploy/scripts/audit_long_short.py). Tutto sintetico e locale.

I record di chiusura sono prodotti dal motore PAPER VERO (backend/desk/engine.py: PaperAccount.open/close/partial_close),
con lo stesso schema di trade_history.jsonl e degli eventi open/close di learning_log.jsonl scritti da cli.py e long_s25.py.
Per usare il motore di una versione precisa: SUPERBOT_DESK_SRC=/checkout/backend (predefinito: backend/ di questo repository).

    python3 -m unittest deploy/scripts/test_audit_long_short.py -v
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.environ.get("SUPERBOT_DESK_SRC") or os.path.join(ROOT, "backend"))
import audit_long_short as A                                   # noqa: E402
from desk.engine import Limits, PaperAccount                   # noqa: E402

H = 3_600_000
T0 = A.ts_ms("2026-11-11T06:00:00Z")
CUT = A.ts_ms(A.DEFAULT_CUTOFF)
SINCE = A.ts_ms(A.DEFAULT_SINCE)


def tree(root):
    """Contenuto e date di TUTTI i file: per provare che l'analisi non scrive nei dati."""
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in dn + fn:
            p = os.path.join(dp, n)
            st = os.lstat(p)
            h = None
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
            out[os.path.relpath(p, root)] = (st.st_mode, st.st_size, st.st_mtime_ns, h)
    return out


class Book:
    """Un portafoglio sintetico: conto PAPER vero + i registri come li scrive il bot."""

    def __init__(self, folder, name, run_no=1, limits=None):
        self.dir, self.name, self.run_no = folder, name, run_no
        os.makedirs(folder, exist_ok=True)
        self.acc = PaperAccount(limits or Limits(), "main")
        self.hist, self.learn = [], []

    def open(self, sym, side, ms, price, sl, tp, source, tt="scalp", lev=15, margin=100.0, features=None):
        pos, msg = self.acc.open(sym, side, margin, lev, price, sl, tp, ms, {sym: price}, confidence=70,
                                 reason="prova", source=source, trade_type=tt, features=features or {})
        assert pos, msg
        self.learn.append({"schema": 1, "ev": "open", "ts": ms, "id": pos.id, "portfolio": self.name,
                           "run_no": self.run_no, "symbol": sym, "side": side, "price": price, "entry": pos.entry,
                           "sl": pos.sl, "tp": pos.tp, "leverage": pos.leverage, "margin_first": pos.total_margin,
                           "risk_plan_usd": pos.risk_plan_usd, "r_dist": pos.r_dist, "trade_type": tt, "source": source,
                           "confidence": 0 if source == "rules_long_s25" else 70, "split_plan": None,
                           "features": features or {}})
        return pos

    def _record(self, rec):
        self.hist.append(rec)
        self.learn.append({"schema": 1, "ev": "close", "ts": rec["close_ms"], "portfolio": self.name,
                           "run_no": self.run_no, **rec})

    def close(self, sym, price, ms, why):
        rec = self.acc.close(sym, price, ms, why)
        self._record(rec)
        return rec

    def partial(self, sym, price, ms, frac):
        rec = self.acc.partial_close(sym, price, ms, frac)
        self._record(rec)
        return rec

    def candidate(self, sym, ms, feats):
        self.learn.append({"schema": 1, "ev": "candidate", "ts": ms, "portfolio": self.name, "run_no": self.run_no,
                           "symbol": sym, "status": "cooldown", "features": feats})

    def write(self, sub_hist=None, state_extra=None):
        hist_path = os.path.join(self.dir, sub_hist or "trade_history.jsonl")
        os.makedirs(os.path.dirname(hist_path), exist_ok=True)
        with open(hist_path, "a") as f:
            for r in self.hist:
                f.write(json.dumps(r) + "\n")
        with open(os.path.join(self.dir, "learning_log.jsonl"), "a") as f:
            for r in self.learn:
                f.write(json.dumps(r) + "\n")
        st = {"run_no": self.run_no, "main": self.acc.to_dict()}
        st.update(state_extra or {})
        with open(os.path.join(self.dir, "state_v2.json"), "w") as f:
            json.dump(st, f, default=str)
        self.hist, self.learn = [], []


def s25_feats(price, atr, ms):
    return {"strategy": "S25", "ema9": price * 0.998, "vwap": price * 0.996, "atr1h": atr,
            "trigger": price - 0.2 * atr, "signal_open_ms": ms - H - 600_000}


def desk_feats(trend4h, trend1h, rsi, side):
    return {"sig_side": side, "sig_long": 64 if side == 1 else 20, "sig_short": 20 if side == 1 else 64,
            "ema50_200_4h": trend4h, "ema20_50_1h": trend1h, "daily_trend": 0, "rsi1h": rsi, "roc24h": -0.02,
            "funding_rate": 0.0001}


def build_fixture(base):
    """Falco (hawk) e Toro (bull) con: S25 LONG perdenti (duplicate tra portafogli), SHORT rules scalp vincenti,
    un LONG Claude con chiusura parziale + finale, un trade aperto, un reset con id riusato, righe rotte/duplicate."""
    hawk, bull = os.path.join(base, "hawk"), os.path.join(base, "bull")
    # ---- Falco, run 1 archiviata dal reset (prima del periodo): id 1 che verra' riusato
    old = Book(hawk, "hawk", run_no=1)
    old.open("ETH", -1, T0 - 30 * H, 3000.0, 3030.0, 2940.0, "rules")
    old.close("ETH", 2950.0, T0 - 28 * H, "take profit")
    old.write(sub_hist=os.path.join("archive", "20261110-120000", "trade_history.jsonl"))
    # ---- Falco, run 2 corrente
    fa = Book(hawk, "hawk", run_no=2)
    for k, (sym, px, atr) in enumerate((("BCH", 500.0, 4.0), ("BNB", 600.0, 5.0), ("SOL", 150.0, 1.5))):
        ms = T0 + k * H
        fa.candidate(sym, ms - 20 * 60_000, desk_feats(-1, 1, 62, 1))      # contesto desk vicino: trend 4h contro
        fa.open(sym, 1, ms, px, px - 1.5 * atr, px + 1.5 * atr, "rules_long_s25", "medio", 15, 100.0, s25_feats(px, atr, ms))
        fa.close(sym, px - 1.5 * atr, ms + 3 * H, "stop loss")
    for k in range(4):                                                    # SHORT rules scalp, 3 vinti e 1 perso
        ms = T0 + (6 + k) * H
        fa.open("BTC", -1, ms, 90000.0, 90900.0, 88380.0, "rules", "scalp", 25, 150.0, desk_feats(-1, -1, 41, -1))
        fa.close("BTC", 88380.0 if k < 3 else 90900.0, ms + H, "take profit" if k < 3 else "stop loss")
    ms = CUT + 2 * H                                                       # dopo RC84: LONG Claude con parziale + finale
    fa.open("ETH", 1, ms, 3000.0, 2970.0, 3060.0, "claude", "scalp", 20, 120.0, desk_feats(1, 1, 58, 1))
    fa.partial("ETH", 3030.0, ms + H, 0.35)
    fa.close("ETH", 3060.0, ms + 2 * H, "take profit")
    fa.open("XRP", -1, CUT + 5 * H, 2.0, 2.02, 1.96, "rules", "scalp", 20, 100.0, desk_feats(-1, -1, 40, -1))   # resta aperto
    fa.write(state_extra={"last_prices": {"XRP": 1.99}})
    # riga rotta (scrittura a meta') e una riga duplicata nello storico corrente
    with open(os.path.join(hawk, "trade_history.jsonl"), "rb") as f:
        first = f.readline()
    with open(os.path.join(hawk, "trade_history.jsonl"), "ab") as f:
        f.write(first)
        f.write(b'{"symbol": "TRONCATA", "side": 1, "clo')
    # ---- Toro: S25 duplicate delle stesse aperture di Falco + SHORT rules
    to = Book(bull, "bull", run_no=1, limits=Limits(max_margin_trade=350.0, daily_stop=0.5))   # stop giornaliero largo: e' un fixture
    for k, (sym, px, atr) in enumerate((("BCH", 500.0, 4.0), ("BNB", 600.0, 5.0), ("SOL", 150.0, 1.5))):
        ms = T0 + k * H + 60_000
        to.open(sym, 1, ms, px, px - 1.5 * atr, px + 1.5 * atr, "rules_long_s25", "medio", 15, 350.0, s25_feats(px, atr, ms))
        to.close(sym, px - 1.5 * atr, ms + 4 * H, "stop loss")
    for k in range(2):
        ms = T0 + (8 + k) * H
        to.open("ETH", -1, ms, 3000.0, 3030.0, 2946.0, "rules", "scalp", 20, 200.0)
        to.close("ETH", 2946.0, ms + H, "take profit")
    to.write()
    return hawk, bull


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = os.path.join(self.td.name, "superbot-desk-data")
        self.hawk, self.bull = build_fixture(self.root)

    def run_main(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = A.main(list(args))
        return rc, buf.getvalue()

    def trades(self, folder, label):
        p = A.load_portfolio(label, folder)
        return p, A.build_trades(p)


class ReconstructionTests(FixtureCase):
    def test_trades_are_keyed_by_symbol_id_and_open_time_across_a_reset(self):
        p, tr = self.trades(self.hawk, "Falco")
        ids = [t["id"] for t in tr]
        self.assertGreater(len(ids), len(set(ids)), "il fixture deve riusare un id dopo il reset")
        self.assertEqual(len({(t["symbol"], t["id"], t["open_ms"]) for t in tr}), len(tr))
        self.assertGreaterEqual(p["integrity"]["id riusati dopo un reset (distinti da open_ms)"], 1)
        old = [t for t in tr if t["open_ms"] < A.ts_ms(A.DEFAULT_SINCE)]
        self.assertEqual(len(old), 1)
        self.assertEqual(old[0]["origins"], ["archivio 20261110-120000"])

    def test_partials_are_summed_into_one_trade_with_additive_r(self):
        _p, tr = self.trades(self.hawk, "Falco")
        (eth,) = [t for t in tr if t["symbol"] == "ETH" and t["source"] == "claude"]
        self.assertEqual(eth["status"], "chiuso")
        self.assertEqual(eth["n_partial"], 1)
        with open(os.path.join(self.hawk, "trade_history.jsonl")) as f:
            rows = [json.loads(l) for l in f if '"claude"' in l]
        self.assertAlmostEqual(eth["net"], sum(r["net"] for r in rows), places=6)
        self.assertAlmostEqual(eth["net_r"], sum(r["net_r"] for r in rows), places=6)
        self.assertGreater(eth["net"], 0)

    def test_open_positions_come_from_the_state_and_broken_or_duplicate_rows_are_counted(self):
        p, tr = self.trades(self.hawk, "Falco")
        (xrp,) = [t for t in tr if t["symbol"] == "XRP"]
        self.assertEqual(xrp["status"], "aperto")
        self.assertAlmostEqual(xrp["unrealized_est"], -1 * (1.99 - xrp["entry"]) * self.qty(xrp), places=6)
        self.assertEqual(p["integrity"]["righe storico illeggibili"], 1)
        self.assertEqual(p["integrity"]["righe storico duplicate (ignorate)"], 1)
        self.assertEqual(p["integrity"]["trade senza evento open nel learning"], 0)

    def qty(self, t):
        with open(os.path.join(self.hawk, "state_v2.json")) as f:
            st = json.load(f)
        return st["main"]["positions"]["XRP"]["qty"]

    def test_learning_join_brings_entry_plan_and_features(self):
        _p, tr = self.trades(self.hawk, "Falco")
        s25 = [t for t in tr if t["strategy"] == "S25"]
        self.assertEqual(len(s25), 3)
        for t in s25:
            self.assertEqual(t["run_no"], 2)
            # R:R pianificato 1:1 sul prezzo, ma rispetto al prezzo eseguito (slippage) e' gia' sotto 1
            self.assertLess(t["rr"], 1.0)
            self.assertGreater(t["rr"], 0.9)
            self.assertIn("atr1h", t["features"])
            self.assertEqual(t["why"], "stop loss")
            self.assertGreater(t["funding"], 0)                         # nel PAPER il funding lo pagano solo i LONG
        shorts = [t for t in tr if t["side"] == -1 and t["strategy"] == "Rules" and t["open_ms"] >= SINCE and t["status"] == "chiuso"]
        self.assertTrue(all(t["funding"] == 0 for t in shorts))
        self.assertTrue(all(t["features"].get("ema50_200_4h") == -1 for t in shorts))

    def test_metrics_match_a_hand_computation(self):
        _p, tr = self.trades(self.bull, "Toro")
        s25 = [t for t in tr if t["strategy"] == "S25"]
        m = A.metrics(s25)
        self.assertEqual((m["n"], m["win"]), (3, 0))
        self.assertEqual(m["pf"], 0.0)
        self.assertAlmostEqual(m["net"], sum(t["net"] for t in s25), places=6)
        self.assertAlmostEqual(m["net_ex_funding"] - m["net"], m["funding"], places=6)
        sh = A.metrics([t for t in tr if t["side"] == -1])
        self.assertEqual((sh["n"], sh["win"], sh["pf"]), (2, 2, float("inf")))


class ReportTests(FixtureCase):
    def test_full_report_separates_open_and_close_time_and_diagnoses_s25(self):
        before = tree(self.root)
        rc, out = self.run_main("--portfolio", "Falco=" + self.hawk, "--portfolio", "Toro=" + self.bull)
        self.assertEqual(rc, 0)
        self.assertEqual(tree(self.root), before, "l'analisi ha scritto nei dati")
        for frag in ("REPORT PRINCIPALE - per ORA DI APERTURA", "REPORT SECONDARIO - per ORA DI CHIUSURA",
                     "--- prima di RC84", "--- dopo RC84", "DIAGNOSTICA S25 (6 trade nel periodo)",
                     "DUPLICATO: stessa apertura S25 anche su Toro", "DUPLICATO: stessa apertura S25 anche su Falco",
                     "contesto desk piu' vicino (Falco, candidate, -20 min): trend4h(cod.) giu",
                     "POSIZIONI ANCORA APERTE (1)", "INTEGRITA' DEI REGISTRI", "Falco LONG S25", "Toro SHORT Rules",
                     "TOTALE LONG", "TOTALE SHORT", "pareggio con win rate", "12:37 Europe/Rome"):
            self.assertIn(frag, out, frag)
        self.assertEqual(out.count("esito='stop loss'"), 6)
        # il LONG Claude e' aperto e chiuso dopo il rilascio; gli S25 prima
        principal = out.split("REPORT PRINCIPALE")[1].split("REPORT SECONDARIO")[0]
        before_rc84, after_rc84 = principal.split("--- dopo RC84")
        self.assertIn("Falco LONG S25 medio", before_rc84)
        self.assertNotIn("S25", after_rc84)
        self.assertIn("Falco LONG Claude scalp", after_rc84)

    def test_a_trade_opened_before_and_closed_after_the_cutoff_changes_era_between_reports(self):
        b = Book(os.path.join(self.td.name, "x"), "hawk")
        b.open("ADA", -1, CUT - H, 1.0, 1.01, 0.98, "rules", "scalp")
        b.close("ADA", 0.98, CUT + H, "take profit")
        b.write()
        rc, out = self.run_main("--portfolio", "X=" + os.path.join(self.td.name, "x"))
        principal = out.split("REPORT PRINCIPALE")[1].split("REPORT SECONDARIO")[0]
        secondary = out.split("REPORT SECONDARIO")[1].split("CONTESTO")[0]
        self.assertIn("X SHORT Rules scalp", principal.split("--- prima di RC84")[1])
        self.assertIn("X SHORT Rules scalp", secondary.split("--- dopo RC84")[1])

    def test_cutoff_is_12_37_rome_on_12_november(self):
        self.assertEqual(A.DEFAULT_CUTOFF, "2026-11-12T11:37:00Z")
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            rome = datetime(2026, 11, 12, 12, 37, tzinfo=ZoneInfo("Europe/Rome"))
        except Exception:                                              # tzdata assente: si verifica l'offset noto
            self.assertEqual(A.ts_ms("2026-11-12T11:37:00Z") + H, A.ts_ms("2026-11-12T12:37:00Z"))
            return
        self.assertEqual(int(rome.timestamp() * 1000), A.ts_ms(A.DEFAULT_CUTOFF))


class SnapshotTests(FixtureCase):
    def test_vps_mode_copies_coherently_analyzes_and_removes_the_copies_without_touching_the_data(self):
        before = tree(self.root)
        tmp_before = set(os.listdir(tempfile.gettempdir()))
        rc, out = self.run_main("--vps", self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(tree(self.root), before)
        self.assertIn("Falco: copia COERENTE di 4 file in 1 tentativo", out)       # 3 file + 1 storico archiviato
        self.assertIn("Toro: copia COERENTE di 3 file in 1 tentativo", out)
        self.assertIn("cancellate alla fine", out)
        self.assertEqual({n for n in set(os.listdir(tempfile.gettempdir())) - tmp_before if n.startswith("audit-long-short-")}, set())

    def test_a_file_that_changes_during_the_copy_is_retried_and_then_declared_not_coherent(self):
        real = A.shutil.copyfileobj
        calls = {"n": 0}

        def writer(fi, fo, *a, **k):                                   # un bot che aggiunge una riga mentre si copia
            real(fi, fo, *a, **k)
            calls["n"] += 1
            if calls["n"] <= limit["n"]:
                with open(os.path.join(self.hawk, "trade_history.jsonl"), "a") as f:
                    f.write("\n")
        limit = {"n": 2}
        sleep = A.time.sleep
        A.time.sleep = lambda s: None
        A.shutil.copyfileobj = writer
        try:
            ok, att, _ = A.snapshot(self.hawk, os.path.join(self.td.name, "c1"))
            self.assertEqual((ok, att), (True, 2))       # il primo giro vede la scrittura, il secondo e' pulito
            limit["n"] = 10 ** 6
            ok, att, _ = A.snapshot(self.hawk, os.path.join(self.td.name, "c2"))
            self.assertEqual((ok, att), (False, 6))
        finally:
            A.shutil.copyfileobj, A.time.sleep = real, sleep

    def test_copies_can_never_be_written_inside_the_data(self):
        with self.assertRaises(SystemExit):
            A.snapshot(self.hawk, os.path.join(self.hawk, "copie"))
        self.assertFalse(os.path.exists(os.path.join(self.hawk, "copie")))

    def test_keep_copies_needs_a_new_folder(self):
        os.makedirs(os.path.join(self.td.name, "esiste"))
        with self.assertRaises(SystemExit):
            self.run_main("--vps", self.root, "--keep-copies", os.path.join(self.td.name, "esiste"))
        rc, out = self.run_main("--vps", self.root, "--keep-copies", os.path.join(self.td.name, "nuova"))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.td.name, "nuova", "hawk", "trade_history.jsonl")))


    def test_rc84_layout_explicit_mapping_preserves_realistic_wallets(self):
        v3 = os.path.join(self.td.name, "superbot-v3-paper-runs")
        os.makedirs(v3)
        shutil.copytree(self.hawk, os.path.join(v3, "classic-hawk-paper20261111"))
        shutil.copytree(self.bull, os.path.join(v3, "classic-bull-paper20261111"))
        before = tree(v3)
        rc, out = self.run_main("--vps", v3, "--layout", "rc84",
                                "--since", "2026-11-10T23:00:00Z")
        self.assertEqual(rc, 0)
        self.assertIn("LAYOUT=rc84", out)
        self.assertIn("Falco", out)
        self.assertIn("Toro", out)
        self.assertEqual(before, tree(v3), "audit must not mutate actual wallet files")

    def test_rc84_layout_fails_closed_on_missing_wallet_or_required_file(self):
        v3 = os.path.join(self.td.name, "superbot-v3-paper-runs")
        os.makedirs(v3)
        with self.assertRaises(SystemExit):
            self.run_main("--vps", v3, "--layout", "rc84")
        shutil.copytree(self.hawk, os.path.join(v3, "classic-hawk-paper20261111"))
        shutil.copytree(self.bull, os.path.join(v3, "classic-bull-paper20261111"))
        os.remove(os.path.join(v3, "classic-bull-paper20261111", "learning_log.jsonl"))
        with self.assertRaises(SystemExit):
            self.run_main("--vps", v3, "--layout", "rc84")

    def test_no_report_if_snapshot_remains_inconsistent(self):
        original = A.snapshot
        A.snapshot = lambda *_args, **_kwargs: (False, 6, [])
        try:
            with self.assertRaises(SystemExit):
                self.run_main("--vps", self.root, "--layout", "legacy")
        finally:
            A.snapshot = original


class SafetyTests(unittest.TestCase):
    def test_the_analyzer_opens_data_files_only_for_reading_and_uses_no_network(self):
        with open(A.__file__, encoding="utf-8") as f:
            src = f.read()
        import ast
        mods = {n.names[0].name.split(".")[0] for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import)}
        mods |= {n.module.split(".")[0] for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(mods - {"argparse", "hashlib", "json", "math", "os", "shutil", "sys", "tempfile", "time",
                                 "collections", "datetime"}, set())
        for bad in ("urllib", "socket", "subprocess", "requests", "os.remove(", "os.unlink(", "os.replace(", "os.rename("):
            self.assertNotIn(bad, src, bad)
        # le sole aperture in scrittura sono quelle delle copie (dentro snapshot, verso la cartella temporanea)
        writes = [l.strip() for l in src.splitlines() if 'open(' in l and ('"wb"' in l or '"w"' in l or '"a"' in l)]
        self.assertEqual(len(writes), 1, writes)
        self.assertIn("open(dst, \"wb\")", writes[0])


if __name__ == "__main__":
    unittest.main()
