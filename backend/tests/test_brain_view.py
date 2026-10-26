"""Offline native-schema fixtures: no bot runtime, Docker, exchange or network."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from desk import brain_view as view

NOW = 1793016000000  # 2026-10-26 UTC, synthetic PAPER fixture only


def native_state():
    return {'version': 'brain-pilot-v1', 'account': {
        'name': 'brain-paper', 'cash': 800, 'positions': {
            'BTC': {'id': 1, 'symbol': 'BTC', 'side': 1, 'entry': 100, 'qty': 2,
                    'total_margin': 100, 'open_ms': NOW - 900000,
                    'features': {'bull_scenario': 'Support holds', 'bear_scenario': 'Support breaks', 'verdict': 'Long at support'}},
            'ETH': {'id': 2, 'symbol': 'ETH', 'side': -1, 'entry': 50, 'qty': 3,
                    'total_margin': 100, 'open_ms': NOW - 1800000, 'features': {}}},
        'brain_daily': {'day': '2026-10-26', 'start_equity': 1100, 'stopped': False}},
        'last_prices': {'BTC': 110, 'ETH': 45}, 'last_bar': NOW - 900000, 'pending': []}


def trade(ident=1, net=10, partial=False, why='take profit'):
    return {'id': ident, 'symbol': 'BTC', 'side': 1, 'entry': 100, 'exit': 110,
            'open_ms': NOW - 3600000, 'close_ms': NOW, 'net': net, 'why': why,
            'partial': partial, 'account': 'brain-paper'}


class BrainViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'brain'
        self.root.mkdir()
        self.state = native_state()
        self.writer = sqlite3.connect(self.root / 'brain.sqlite3')
        self.addCleanup(self.writer.close)
        self.writer.executescript('CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT NOT NULL);'
                                  'CREATE TABLE events(seq INTEGER PRIMARY KEY, kind TEXT, body TEXT);')
        self.save()

    def save(self):
        self.writer.execute('INSERT OR REPLACE INTO state VALUES(1,?)', (json.dumps(self.state),))
        self.writer.commit()

    def event(self, kind, row):
        self.writer.execute('INSERT INTO events(kind,body) VALUES(?,?)', (kind, json.dumps(row)))
        self.writer.commit()

    def read(self):
        return view.read_status(self.root, now_ms=NOW)

    def test_equity_native_long_and_short(self):
        value = self.read()
        self.assertEqual(value['status'], 'ok')
        self.assertEqual(value['portfolio']['equity'], 1035)
        self.assertEqual(value['portfolio']['cash'], 800)
        self.assertEqual(value['portfolio']['pnl'], 35)
        self.assertAlmostEqual(value['portfolio']['pnl_pct'], 3.5)
        self.assertEqual([p['floating_pnl'] for p in value['positions']], [20, 15])
        self.assertEqual([p['side'] for p in value['positions']], ['LONG', 'SHORT'])

    def test_missing_database_no_creation(self):
        root = self.root / 'does-not-exist'
        self.assertEqual(view.read_status(root)['reason'], 'missing_database')
        self.assertFalse(root.exists())

    def test_empty_state_unavailable(self):
        self.writer.execute('DELETE FROM state'); self.writer.commit()
        self.assertEqual(self.read()['reason'], 'missing_state')

    def test_rejects_foreign_and_old_guessed_schema(self):
        self.state['account']['name'] = 'hawk'; self.save()
        self.assertEqual(self.read()['reason'], 'unsupported_state')
        self.writer.execute('DROP TABLE state'); self.writer.commit()
        self.writer.execute('CREATE TABLE state_json(value TEXT)'); self.writer.commit()
        self.assertEqual(self.read()['status'], 'unavailable')

    def test_corrupt_database_no_internal_path(self):
        self.writer.close()
        (self.root / 'brain.sqlite3').write_bytes(b'not sqlite')
        value = self.read()
        self.assertEqual(value['status'], 'unavailable')
        self.assertNotIn(str(self.root), json.dumps(value))

    def test_invalid_state_and_nonfinite_never_serialized(self):
        for value in (float('nan'), float('inf'), True):
            self.state['account']['cash'] = value; self.save()
            self.assertEqual(self.read()['status'], 'unavailable')

    def test_missing_mark_is_unknown_not_entry_fallback(self):
        del self.state['last_prices']['ETH']; self.save()
        value = self.read()
        self.assertIsNone(value['portfolio']['equity'])
        self.assertIsNone(value['portfolio']['pnl'])
        self.assertIsNone(value['positions'][1]['floating_pnl'])

    def test_no_positions_zero_trades(self):
        self.state['account']['positions'] = {}; self.save()
        value = self.read()
        self.assertEqual(value['positions'], [])
        self.assertEqual(value['stats']['closed_trades'], 0)
        self.assertIsNone(value['stats']['win_rate_pct'])

    def test_statistics_full_history_partials_aggregated(self):
        for i in range(25):
            self.event('trade', trade(i, net=1))
        self.event('trade', trade(50, net=20, partial=True))
        self.event('trade', trade(50, net=-25))
        self.event('trade', trade(51, net=-3, partial=True))  # still open, not a completed trade
        value = self.read()['stats']
        self.assertEqual(value['closed_trades'], 26)
        self.assertAlmostEqual(value['win_rate_pct'], 25 / 26 * 100)
        self.assertAlmostEqual(value['average_pnl'], 20 / 26)
        self.assertEqual(value['realized_pnl'], 17)

    def test_tail_last_twenty_skips_torn_and_malformed_lines(self):
        rows = [trade(i, net=i) for i in range(35)]
        path = self.root / 'trade_history.jsonl'
        path.write_text('\n'.join(json.dumps(t) for t in rows) + '\nbroken\n{"net":', encoding='utf8')
        value = self.read()['trades']
        self.assertEqual(len(value), 20)
        self.assertEqual([t['pnl'] for t in value], list(range(34, 14, -1)))

    def test_tail_bounded_with_large_prefix_and_utf8_boundary(self):
        path = self.root / 'trade_history.jsonl'
        path.write_text('è' * (view.TAIL_BYTES + 1) + '\n' + json.dumps(trade()) + '\n', encoding='utf8')
        self.assertEqual(len(self.read()['trades']), 1)

    def test_reason_mapping_protective_ai_and_partial(self):
        for why, expected in [('stop loss', 'stop_loss'), ('take profit', 'take_profit'),
                              ('brain: close', 'ai_close'), ('brain: save_profit', 'ai_close'),
                              ('brain: early_close', 'ai_close'), ('liquidazione', 'liquidazione')]:
            self.assertEqual(view._trade(trade(why=why))['reason'], expected)
        self.assertTrue(view._trade(trade(partial=True))['partial'])

    def test_daily_stop_equity_includes_floating_and_latch(self):
        self.state['account']['brain_daily']['stopped'] = True; self.save()
        daily = self.read()['daily_stop']
        self.assertAlmostEqual(daily['drawdown_pct'], (1 - 1035 / 1100) * 100)
        self.assertAlmostEqual(daily['used_limit_pct'], (1 - 1035 / 1100) * 500)
        self.assertTrue(daily['stopped'])  # no reader reset, even after equity recovery

    def test_new_utc_day_no_reader_rollover(self):
        before = copy.deepcopy(self.state)
        value = view.read_status(self.root, now_ms=NOW + 86400000)
        self.assertEqual(value['daily_stop']['state'], 'awaiting_utc_rollover')
        self.assertIsNone(value['daily_stop']['stopped'])
        self.assertEqual(json.loads(self.writer.execute('SELECT body FROM state').fetchone()[0]), before)

    def test_reasoning_source_and_attempt_distinct(self):
        self.event('journal', {'kind': 'model_attempt', 'ts_ms': NOW})
        self.event('journal', {'kind': 'cycle', 'ts_ms': NOW, 'market_view': 'Balanced', 'called': True})
        self.state['pending'] = [{'symbol': 'SOL', 'execute_t': NOW, 'bull_scenario': '<script>x</script>',
                                  'bear_scenario': 'Breakdown', 'verdict': 'Wait for confirmation'}]; self.save()
        value = self.read()
        self.assertEqual(value['portfolio']['cycles'], 1)
        self.assertEqual(value['reasoning']['symbol'], 'SOL')
        self.assertEqual(value['reasoning']['source'], 'pending_decision')
        self.assertEqual(value['reasoning']['last_call_ms'], NOW)

    def test_no_fabricated_reasoning_or_docker_health_sha_uptime(self):
        self.state['account']['positions'] = {}; self.save()
        value = self.read()
        self.assertIsNone(value['reasoning']['bull_scenario'])
        self.assertEqual(value['system']['health'], 'unknown')
        self.assertIsNone(value['system']['sha'])
        self.assertIsNone(value['system']['uptime_seconds'])

    def test_fresh_stale_future_heartbeat(self):
        for stamp, expected in [(NOW, 'fresh'), (NOW - view.FRESH_MS - 1, 'stale'), (NOW + 60000, 'stale')]:
            (self.root / 'status.json').write_text(json.dumps({'mode': 'paper', 'applied': False, 'ts_ms': stamp}))
            self.assertEqual(self.read()['system']['heartbeat'], expected)
            self.assertEqual(self.read()['system']['health'], 'unknown')

    def test_stale_price_timestamp_explicit(self):
        self.state['last_bar'] -= view.FRESH_MS + 1; self.save()
        self.assertTrue(self.read()['portfolio']['stale'])

    def test_exclusive_lock_bounded_no_reset(self):
        self.writer.execute('BEGIN EXCLUSIVE')
        started = time.monotonic()
        with patch.object(view, 'QUERY_SECONDS', .08):
            self.assertEqual(self.read()['reason'], 'locked')
        self.assertLess(time.monotonic() - started, .5)
        self.writer.rollback()
        self.assertEqual(self.read()['status'], 'ok')

    def test_deadline_interrupts_scan(self):
        for i in range(10): self.event('journal', {'kind': 'cycle', 'ts_ms': NOW})
        with patch.object(view, 'QUERY_SECONDS', 0):
            self.assertEqual(self.read()['reason'], 'query_timeout')

    def test_wal_committed_data_visible_and_authoritative_bytes_unchanged(self):
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.execute('PRAGMA wal_autocheckpoint=0')
        self.state['account']['cash'] = 810; self.save()
        self.event('trade', trade())
        for name in ('trade_history.jsonl', 'journal.jsonl', 'learning_log.jsonl', 'lessons.md', 'errors.md'):
            (self.root / name).write_text('preserve\n')
        def hashes():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if not p.name.endswith('-shm')}
        before = hashes()
        self.assertEqual(self.read()['portfolio']['cash'], 810)
        self.assertEqual(hashes(), before)

    def test_readonly_connect_flags_and_no_checkpoint_sql(self):
        connect = sqlite3.connect
        calls, statements = [], []
        def traced(*args, **kwargs):
            calls.append((args, kwargs))
            db = connect(*args, **kwargs); db.set_trace_callback(statements.append); return db
        with patch.object(view.sqlite3, 'connect', traced): self.read()
        self.assertTrue(calls[0][0][0].endswith('?mode=ro'))
        self.assertEqual(calls[0][1]['uri'], True)
        self.assertEqual(calls[0][1]['check_same_thread'], False)
        self.assertLessEqual(calls[0][1]['timeout'], 2)
        self.assertFalse(any('checkpoint' in s.lower() or 'insert' in s.lower() or 'update' in s.lower() for s in statements))

    def test_parallel_readers_while_writer_has_wal_transaction(self):
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.save()
        self.writer.execute('BEGIN IMMEDIATE')
        self.writer.execute('UPDATE state SET body=? WHERE id=1', ('{}',))  # uncommitted, readers must not see
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: self.read(), range(8)))
        self.writer.rollback()
        self.assertTrue(all(v['status'] == 'ok' for v in values))

    def test_allowlist_does_not_return_arbitrary_fields(self):
        self.state['unrelated_secret'] = 'DO_NOT_EXPORT'
        self.state['account']['unused'] = 'DO_NOT_EXPORT'; self.save()
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(self.read()))

    def test_fastapi_auth_get_only_and_no_cache(self):
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient
        def denied(): raise HTTPException(401)
        app = FastAPI(); view.register_fastapi(app, denied)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/brain/status').status_code, 401)
        app = FastAPI(); view.register_fastapi(app, lambda: 'authenticated')
        with patch.dict(os.environ, {'BRAIN_DATA_DIR': str(self.root)}), TestClient(app) as client:
            response = client.get('/api/brain/status')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.json()['mode'], 'paper')
            self.assertEqual(client.post('/api/brain/status').status_code, 405)
        self.assertEqual([r.path for r in app.routes if r.path.startswith('/api/')], ['/api/brain/status'])


if __name__ == '__main__':
    unittest.main()
