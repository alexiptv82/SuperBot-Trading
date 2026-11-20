"""Test SINTETICI di integrita' e provenienza degli archivi di candele (nessuna rete).

Un falsario puo' modificare i dati E ricalcolare gli hash del manifest: l'integrita' torna "intact", ma la provenienza
deve fallire (file non derivato dalle risposte grezze, oppure manifest non ancorato / ancora diversa).
"""
import hashlib
import json
import os
import shutil
import tempfile
import unittest

import candle_provenance as CP

IV = 900_000
T0 = 1_780_000_000_000 // IV * IV
META = {"exchange": "bitget", "market": "usdt_perp", "price_basis": "last", "source": "public_rest_v2"}


def body(rows):
    return {"code": "00000", "data": [[str(t), o, h, l, c, v, "0"] for t, o, h, l, c, v in rows]}


def url(sym, gran, lo, hi):
    return (f"https://api.bitget.com/api/v2/mix/market/history-candles?symbol={sym}&productType=USDT-FUTURES"
            f"&granularity={gran}&startTime={lo}&endTime={hi}&limit=200")


def rows(n, start=T0, step=IV):
    return [(start + i * step, "100", "101.5", "99.5", f"{100 + i % 3}.25", "12.5") for i in range(n)]


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.anchors = {}

    def make(self, layout="tf", mid="candles-20261120T080000Z-a1", n=20, extra=None, acquired=None):
        fetched = {}
        specs = [("15m", IV, "15m"), ("1h", 3_600_000, "1H")] if layout == "tf" else [("", IV, "15m")]
        for d, step, gran in specs:
            for sym in ("BTCUSDT", "ETHUSDT"):
                rs = rows(n, step=step)
                resp = [(url(sym, gran, rs[0][0], rs[-1][0]), body(rs + (extra or [])))]
                fetched[(d + "/" if d else "") + sym + ".jsonl"] = {"symbol": sym, "interval_ms": step,
                                                                     "responses": resp}
        sha = CP.write_archive(self.root, manifest_id=mid, acquired_at_ms=acquired or T0 + 400 * IV * 4,
                               tool={"name": "test"}, fetched=fetched, meta=META)
        self.anchors[mid] = sha
        return sha

    def check(self):
        return CP.check(self.root, self.anchors)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def reforge_manifest(self):
        """Il falsario ricalcola TUTTI gli hash del manifest dopo aver cambiato i file."""
        with open(self.path(CP.MANIFEST)) as fh:
            m = json.load(fh)
        m["sha256"] = {rel: CP._sha(self.path(rel)) for rel in CP._files(self.root)}
        raw = json.dumps(m, sort_keys=True, indent=1).encode()
        with open(self.path(CP.MANIFEST), "wb") as fh:
            fh.write(raw)
        return hashlib.sha256(raw).hexdigest()

    def edit_jsonl(self, rel, fn):
        with open(self.path(rel)) as fh:
            lines = [json.loads(x) for x in fh]
        lines = fn(lines)
        with open(self.path(rel), "w") as fh:
            for d in lines:
                fh.write(json.dumps(d) + "\n")


class AttestedTests(Base):
    def test_tf_layout_is_intact_and_attested(self):
        self.make()
        r = self.check()
        self.assertEqual((r["integrity"], r["provenance"]), ("intact", "attested"))

    def test_flat_layout_is_attested(self):
        self.make(layout="flat")
        self.assertEqual(self.check()["provenance"], "attested")

    def test_without_manifest_it_is_only_declared(self):
        os.makedirs(self.path("15m"))
        with open(self.path("15m/" + CP.META), "w") as fh:
            json.dump({**META, "interval_ms": IV}, fh)
        r = self.check()
        self.assertEqual((r["integrity"], r["provenance"]), ("manifest_missing", "declared_only"))

    def test_missing_directory(self):
        self.assertEqual(CP.check(os.path.join(self.root, "nope"))["provenance"], "archive_missing")

    def test_an_archive_cannot_be_written_twice(self):
        self.make()
        with self.assertRaises(ValueError):
            self.make()


class IntegrityTests(Base):
    def test_an_edited_file_breaks_integrity(self):
        self.make()
        self.edit_jsonl("15m/BTCUSDT.jsonl", lambda ls: ls[:-1])
        r = self.check()
        self.assertEqual((r["integrity"], r["provenance"]), ("file_hash_mismatch", "integrity_file_hash_mismatch"))

    def test_an_added_or_removed_file_breaks_integrity(self):
        self.make()
        with open(self.path("15m/SOLUSDT.jsonl"), "w") as fh:
            fh.write("")
        self.assertEqual(self.check()["integrity"], "file_unlisted")
        os.remove(self.path("15m/SOLUSDT.jsonl"))
        os.remove(self.path("1h/ETHUSDT.jsonl"))
        self.assertEqual(self.check()["integrity"], "file_missing")

    def test_a_raw_response_is_covered_too(self):
        self.make()
        raw = self.path("raw/15m/BTCUSDT/00000.json")
        with open(raw, "a") as fh:
            fh.write(" ")
        self.assertEqual(self.check()["integrity"], "file_hash_mismatch")


class ProvenanceTests(Base):
    def test_data_changed_with_recomputed_hashes_is_not_derived_from_the_source(self):
        self.make()
        self.edit_jsonl("15m/BTCUSDT.jsonl", lambda ls: [dict(d, c="100.5") if i == 3 else d for i, d in enumerate(ls)])
        self.anchors["candles-20261120T080000Z-a1"] = self.reforge_manifest()    # anche l'ancora "aggiornata"
        r = self.check()
        self.assertEqual((r["integrity"], r["provenance"]), ("intact", "file_not_derived_from_source"))

    def test_data_and_raw_changed_consistently_still_fail_on_the_external_anchor(self):
        self.make()
        self.edit_jsonl("15m/BTCUSDT.jsonl", lambda ls: [dict(d, c="100.5") if i == 3 else d for i, d in enumerate(ls)])
        raw = self.path("raw/15m/BTCUSDT/00000.json")
        with open(raw) as fh:
            b = json.load(fh)
        with open(self.path("15m/BTCUSDT.jsonl")) as fh:
            t3 = [json.loads(x) for x in fh][3]["t"]
        for row in b["data"]:
            if int(row[0]) == t3:
                row[4] = "100.5"
        with open(raw, "w") as fh:
            json.dump(b, fh, sort_keys=True, separators=(",", ":"))
        self.reforge_manifest()                                                  # l'ancora esterna NON cambia
        self.assertEqual(self.check()["provenance"], "anchor_mismatch")

    def test_unanchored_manifest_is_not_attested(self):
        self.make()
        self.anchors.clear()
        r = self.check()
        self.assertEqual((r["integrity"], r["provenance"]), ("intact", "manifest_unanchored"))

    def _edit_manifest(self, fn):
        with open(self.path(CP.MANIFEST)) as fh:
            m = json.load(fh)
        fn(m)
        raw = json.dumps(m, sort_keys=True, indent=1).encode()
        with open(self.path(CP.MANIFEST), "wb") as fh:
            fh.write(raw)
        self.anchors["candles-20261120T080000Z-a1"] = hashlib.sha256(raw).hexdigest()

    def test_an_unexpected_source_is_refused(self):
        self.make()
        self._edit_manifest(lambda m: m["source"].update(path="/api/v2/mix/market/candles"))
        self.assertEqual(self.check()["provenance"], "source_unexpected")

    def test_a_request_for_another_symbol_or_granularity_is_refused(self):
        self.make()
        self._edit_manifest(lambda m: m["files"][0]["requests"][0].update(
            url=m["files"][0]["requests"][0]["url"].replace("symbol=BTCUSDT", "symbol=XRPUSDT")))
        self.assertEqual(self.check()["provenance"], "request_not_matching_file")
        shutil.rmtree(self.root)
        os.makedirs(self.root)
        self.make()
        self._edit_manifest(lambda m: m["files"][0]["requests"][0].update(
            url=m["files"][0]["requests"][0]["url"].replace("granularity=15m", "granularity=4H")))
        self.assertEqual(self.check()["provenance"], "request_not_matching_file")

    def test_a_file_without_requests_is_refused(self):
        self.make()
        self._edit_manifest(lambda m: m["files"][0].update(requests=[]))
        self.assertEqual(self.check()["provenance"], "requests_missing")

    def test_candles_not_closed_at_acquisition_are_never_part_of_the_archive(self):
        acquired = T0 + 10 * IV                                  # solo 10 candele da 15m chiuse
        self.make(layout="flat", acquired=acquired)
        with open(self.path("BTCUSDT.jsonl")) as fh:
            ts = [json.loads(x)["t"] for x in fh]
        self.assertTrue(ts and max(ts) + IV <= acquired)
        self.assertEqual(self.check()["provenance"], "attested")

    def test_rows_outside_the_request_window_are_ignored(self):
        self.make(layout="flat", extra=[(T0 - 5 * IV, "1", "1", "1", "1", "1")])
        with open(self.path("BTCUSDT.jsonl")) as fh:
            self.assertNotIn(T0 - 5 * IV, [json.loads(x)["t"] for x in fh])
        self.assertEqual(self.check()["provenance"], "attested")

    def test_meta_interval_must_match_the_file(self):
        self.make()
        with open(self.path("1h/" + CP.META), "w") as fh:
            json.dump({**META, "interval_ms": IV}, fh)
        self.anchors["candles-20261120T080000Z-a1"] = self.reforge_manifest()
        self.assertEqual(self.check()["provenance"], "meta_interval_mismatch")


class AnchorFileTests(Base):
    def test_anchor_file_format(self):
        p = os.path.join(self.root, "a.json")
        with open(p, "w") as fh:
            json.dump({"candles-20261120T080000Z-a1": "a" * 64}, fh)
        self.assertEqual(CP.load_anchors(p), {"candles-20261120T080000Z-a1": "a" * 64})
        with open(p, "w") as fh:
            json.dump({"run-1": "a" * 64}, fh)
        with self.assertRaises(ValueError):
            CP.load_anchors(p)
        self.assertEqual(CP.load_anchors(None), {})


if __name__ == "__main__":
    unittest.main()
