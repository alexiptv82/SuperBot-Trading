"""Offline regression tests for golden/crisis provenance. No VPS, exchange or AI."""
import subprocess
import unittest
from pathlib import Path
from rollback_lab.tape_audit import analyze,load_tape,SOURCE

REPO=Path(__file__).resolve().parents[2]


def original_bytes():
    return subprocess.check_output(
        ["git","show","origin/diario:"+SOURCE],cwd=REPO,timeout=15)


class TapeAudit(unittest.TestCase):
    def test_immutable_export_reconciles_position_level(self):
        result=analyze(original_bytes())
        gold=result["groups"]["golden"]["all"]
        crisis=result["groups"]["first_crisis"]["all"]
        self.assertEqual(gold["positions"],93)
        self.assertAlmostEqual(gold["net_usd"],1861.3621,places=3)
        self.assertEqual(gold["exits"]["TP"]["n"],54)
        self.assertEqual(gold["exits"]["SL"]["n"],34)
        self.assertEqual(gold["exits"]["model_or_rule_close_labeled_claude"]["n"],4)
        self.assertEqual(crisis["positions"],53)
        self.assertAlmostEqual(crisis["net_usd"],-429.549,places=3)
        self.assertEqual(crisis["exits"]["model_or_rule_close_labeled_claude"]["n"],16)
        self.assertAlmostEqual(crisis["exits"]["model_or_rule_close_labeled_claude"]["net_usd"],-225.492,places=3)
        self.assertEqual(gold["missing_fields"]["exit_code"],93)
        self.assertEqual(gold["missing_fields"]["entry_log"],4)
        self.assertEqual(gold["opening_sources"],{"rules":93})
        self.assertEqual(crisis["opening_sources"],{"rules":53})
        self.assertTrue(all(x["attribution"]=="UNKNOWN_NOT_PROVEN_CLAUDE"
                            for x in result["ambiguous_exits"]))

    def test_bad_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"missing_export_columns"):
            load_tape(b"symbol,net\nBTC,1.0\n")

    def test_deterministic_output(self):
        raw=original_bytes()
        one=analyze(raw)
        two=analyze(raw)
        self.assertEqual(one,two)
        self.assertEqual(len(one["export_sha256"]),64)


if __name__=="__main__":
    unittest.main()
