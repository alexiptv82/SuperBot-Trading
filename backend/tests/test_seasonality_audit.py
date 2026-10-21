import hashlib
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2] / 'deploy/scripts/seasonality_audit.py'
spec = importlib.util.spec_from_file_location('audit', PATH)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def row(**updates):
    r = dict(ev='candidate', portfolio='hawk', run_no=4, ts=1792540800000,
             symbol='BTC', code_version='reviewed', features=dict(sig_long=40, sig_short=62))
    r.update(updates)
    return r


class AuditTests(unittest.TestCase):
    def test_bonus_changes_eligibility_not_actual_trade(self):
        result = a.analyze([row()], 60, {'reviewed'})
        self.assertEqual(result['counts']['eligible_A'], 1)
        self.assertEqual(result['counts']['eligible_B'], 0)
        self.assertNotIn('pnl', result)

    def test_threshold_is_explicit(self):
        self.assertEqual(a.analyze([row()], 55, {'reviewed'})['counts']['eligible_B'], 1)

    def test_saturation_is_not_inverted(self):
        self.assertEqual(a.analyze([row(features=dict(sig_long=40, sig_short=100))], 60, {'reviewed'})['excluded'], {'saturated_score': 1})

    def test_unknown_version_excluded(self):
        self.assertEqual(a.analyze([row()], 60, {'other'})['excluded'], {'unreviewed_code_version': 1})

    def test_duplicates_and_run_identity(self):
        r = a.analyze([row(), row(ev='open'), row(run_no=5)], 60, {'reviewed'})
        self.assertEqual(r['counts']['unique_readings'], 2)
        self.assertEqual(r['counts']['duplicate_readings'], 1)

    def test_conflicts_fail(self):
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            a.analyze([row(), row(features=dict(sig_long=41, sig_short=62))], 60, {'reviewed'})

    def test_nan_and_missing_are_not_zero(self):
        for f in [{}, dict(sig_long=float('nan'), sig_short=62), dict(sig_long=True, sig_short=62)]:
            r = a.analyze([row(features=f)], 60, {'reviewed'})
            self.assertEqual(sum(r['excluded'].values()), 1)

    def test_strict_snapshot(self):
        for raw in [b'', b'{}', b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'[]\n', b'\n']:
            with self.assertRaises((ValueError, UnicodeError)):
                a.decode(raw, hashlib.sha256(raw).hexdigest())

    def test_hash(self):
        with self.assertRaisesRegex(ValueError, 'hash'):
            a.decode(b'{}\n', 'wrong')
        self.assertEqual(a.decode(b'{}\n', hashlib.sha256(b'{}\n').hexdigest()), [{}])

    def test_tie_means_no_direction(self):
        self.assertEqual(a.selection(60, 60, 60), (0, False))

    def test_input_unchanged_and_deterministic(self):
        import copy
        rows = [row()]
        original = copy.deepcopy(rows)
        self.assertEqual(a.analyze(rows, 60, {'reviewed'}), a.analyze(rows, 60, {'reviewed'}))
        self.assertEqual(rows, original)

    def test_november_first(self):
        from datetime import datetime, timezone
        ts = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(a.get_seasonal('BTC', ts).short_bonus, 9)
        self.assertEqual(a.get_seasonal('ETH', ts).short_bonus, 10)

if __name__ == '__main__':
    unittest.main()
