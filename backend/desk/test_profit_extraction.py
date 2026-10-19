import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from desk.extract_replay_input import extract, REQUIRED, strict_json


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "backup"
        self.source.mkdir()
        (self.source / "state_v2.json").write_text(json.dumps({"run_no":3,"main":{}}))
        (self.source / "heartbeat.json").write_text(json.dumps({"portfolio":"hawk","exec_mode":"paper","version":"declared"}))
        (self.source / "trade_history.jsonl").write_text('{"run_no":3,"portfolio":"hawk","net":-1}\n')
        (self.source / "learning_log.jsonl").write_text('{"run_no":3,"portfolio":"hawk","ev":"open"}\n')
        self.manifest = self.root / "hashes.json"
        self.output = self.root / "private"
        self.hashes()

    def hashes(self):
        self.manifest.write_text(json.dumps({n:hashlib.sha256((self.source/n).read_bytes()).hexdigest() for n in REQUIRED}))

    def run_extract(self):
        return extract(self.source,self.output,self.manifest,"hawk",3)

    def test_verified_private_evidence_only(self):
        before = {n:(self.source/n).read_bytes() for n in REQUIRED}
        report = self.run_extract()
        self.assertFalse(report["replay_ready"])
        self.assertFalse((self.output/"input.json").exists())
        for n,raw in before.items():
            self.assertEqual((self.output/n).read_bytes(),raw)
            self.assertEqual((self.source/n).read_bytes(),raw)
            self.assertEqual((self.output/n).stat().st_mode & 0o777,0o600)

    def test_existing_output_untouched(self):
        self.output.mkdir()
        marker = self.output/"keep"
        marker.write_text("preserve")
        with self.assertRaises(ValueError): self.run_extract()
        self.assertEqual(marker.read_text(),"preserve")

    def test_modified_source_rejected(self):
        (self.source/"state_v2.json").write_text('{}')
        with self.assertRaises(ValueError): self.run_extract()
        self.assertFalse(self.output.exists())

    def test_truncated_log_rejected_even_with_matching_hash(self):
        (self.source/"learning_log.jsonl").write_text('{"ev":"open"}')
        self.hashes()
        with self.assertRaises(ValueError): self.run_extract()

    def test_live_rejected(self):
        (self.source/"heartbeat.json").write_text('{"portfolio":"hawk","exec_mode":"live"}')
        self.hashes()
        with self.assertRaises(ValueError): self.run_extract()

    def test_missing_run_rejected(self):
        (self.source/"trade_history.jsonl").write_text('{"run_no":2}\n')
        self.hashes()
        with self.assertRaises(ValueError): self.run_extract()

    def test_output_in_checkout_rejected(self):
        repo = self.root/"repo"
        repo.mkdir()
        (repo/".git").write_text("gitdir: elsewhere")
        self.output = repo/"private"
        with self.assertRaises(ValueError): self.run_extract()

    def test_source_symlink_rejected(self):
        p = self.source/"state_v2.json"
        p.rename(self.root/"state")
        p.symlink_to(self.root/"state")
        with self.assertRaises(ValueError): self.run_extract()

    def test_invalid_json_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): strict_json(raw)


if __name__ == "__main__":
    unittest.main()
