"""Synthetic causality/isolation contracts; NOT a predictive backtest."""
from copy import deepcopy
import hashlib
from pathlib import Path
from threading import Event
import unittest

from director.structural_advisory import observe_structure, project_advisory, BAR_MS
from director.structural_shadow import StructuralShadow

NOW = 1793318400000 // BAR_MS * BAR_MS


def history(n=1000, turn=True):
    rows = []
    for i in range(n):
        close = 120-i*0.02
        rows.append([NOW-(n-i)*BAR_MS, close+0.01, close+0.04, close-0.04, close, 80.])
    if turn:
        for row in rows[-2:]:
            row[1:5] = [102., 102.1, 101.9, 102.]
    return rows


class Structure(unittest.TestCase):
    def test_reassessment_can_precede_slow_context_confirmation(self):
        item = observe_structure('BTC', history(), NOW)
        self.assertEqual(item['phase'], 'UP_REASSESSMENT')
        self.assertEqual(item['context_1h'], 'DOWN')
        self.assertEqual(item['context_4h'], 'DOWN')
        self.assertFalse(item['may_block_entry'])
        self.assertFalse(item['may_modify_scores'])

    def test_price_reflection_swaps_fast_direction(self):
        rows = history()
        reflected = [[b[0], 250-b[1], 250-b[3], 250-b[2], 250-b[4], b[5]] for b in rows]
        item = observe_structure('BTC', reflected, NOW)
        self.assertEqual(item['phase'], 'DOWN_REASSESSMENT')
        self.assertEqual(item['context_1h'], 'UP')

    def test_future_values_and_incomplete_candle_do_not_change_reading(self):
        rows = history()
        original = observe_structure('BTC', rows, NOW)
        rows += [[NOW, 'unknown', None, -1000, float('nan'), -1]]
        self.assertEqual(observe_structure('BTC', rows, NOW), original)

    def test_gap_conflict_stale_and_malformed_are_no_opinion(self):
        rows = history()
        for bad in (rows[:-1], rows[:90]+rows[91:], rows+[rows[-1][:4]+[999, 80]]):
            # A bar only 15m old is still permitted, so test stale separately.
            if bad == rows[:-1]:
                continue
            self.assertIsNone(observe_structure('BTC', bad, NOW))
        self.assertIsNone(observe_structure('BTC', rows, NOW+3*BAR_MS))
        self.assertIsNone(observe_structure('BTC', [[1]], NOW))

    def test_duplicate_identical_and_order_normalization(self):
        rows = history()
        self.assertEqual(observe_structure('BTC', rows, NOW),
                         observe_structure('BTC', list(reversed(rows))+[rows[-1]], NOW))

    def test_unknown_slow_context_does_not_suppress_fast_advice(self):
        item = observe_structure('BTC', history()[-32:], NOW)
        self.assertEqual(item['phase'], 'UP_REASSESSMENT')
        self.assertEqual(item['context_1h'], 'UNKNOWN')

    def test_whitelist_rejects_authority_and_removes_extra_text(self):
        item = observe_structure('BTC', history(), NOW)
        item['instruction'] = 'SECRET_OVERRIDE'
        self.assertNotIn('SECRET_OVERRIDE', str(project_advisory(item, 'BTC', NOW)))
        item['may_block_entry'] = True
        self.assertEqual(project_advisory(item, 'BTC', NOW), {'status': 'unavailable'})

    def test_worker_slow_loader_does_not_wait_or_duplicate_jobs(self):
        worker = StructuralShadow();entered=Event();release=Event();calls=[]
        def loader(symbol):
            calls.append(symbol);entered.set();release.wait(2)
            return history()
        try:
            self.assertEqual(worker.poll(NOW, ['BTC'], loader), {})
            self.assertTrue(entered.wait(1))
            future = worker.future
            self.assertEqual(worker.poll(NOW+60000, ['BTC'], loader), {})
            self.assertIs(worker.future, future)
            self.assertEqual(calls, ['BTC'])
            release.set();future.result(timeout=2)
            out=worker.poll(NOW+60000, [], loader)
            self.assertIn('BTC', out)
            out['BTC']['phase']='CORRUPTED'
            self.assertNotEqual(worker.cache['BTC']['phase'], 'CORRUPTED')
        finally:
            release.set();worker.close()

    def test_failed_refresh_removes_previous_opinion(self):
        worker=StructuralShadow()
        try:
            worker.poll(NOW,['BTC'],lambda s:history());worker.future.result(timeout=2)
            self.assertIn('BTC',worker.poll(NOW,[],lambda s:[]))
            worker.poll(NOW+60000,['BTC'],lambda s:[]);worker.future.result(timeout=2)
            self.assertEqual(worker.poll(NOW+60000,[],lambda s:[]),{})
        finally:worker.close()


if __name__ == '__main__':
    unittest.main()
