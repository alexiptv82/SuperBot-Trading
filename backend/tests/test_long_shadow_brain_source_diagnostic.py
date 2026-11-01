"""Brain source audit fails closed and does not expose wallet secrets."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from long_shadow_brain_source_diagnostic import inspect_brain_sources

NOW=1800000000000


def create_free(path, timestamp=NOW):
    path.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path/'brain.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps({
            'mode':'paper','account_id':'brain-free-paper',
            'heartbeat_ms':timestamp,
            'positions':{'BTC':{'side':-1}}}),))


def create_pilot(path, timestamp=NOW):
    path.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path/'brain.sqlite3') as db:
        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
        db.execute('INSERT INTO state VALUES(1,?)',(json.dumps({
            'version':'brain-pilot-v1',
            'account':{'name':'brain-paper','positions':{'ETH':{'side':1}}}}),))
    (path/'status.json').write_text(json.dumps({
        'mode':'paper','applied':False,'ts_ms':timestamp}))


class BrainSourceDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.free=self.root/'free'
        self.pilot=self.root/'pilot'

    def diagnose(self,**overrides):
        params={'brain_free_dir':str(self.free),
                'brain_pilot_dir':str(self.pilot),'now_ms':NOW}
        params.update(overrides)
        return inspect_brain_sources(**params)

    def test_neither_source_is_not_verified(self):
        r=self.diagnose()
        self.assertEqual(r['status'],'NO_VALID_SOURCE')
        self.assertFalse(r['active_process_owner_confirmed'])
        self.assertFalse(r['may_autoselect_brain_source'])

    def test_free_source_only_is_not_runtime_certification(self):
        create_free(self.free)
        r=self.diagnose()
        self.assertEqual(r['status'],'SINGLE_VALID_SOURCE_NOT_RUNTIME_CONFIRMED')
        self.assertEqual(r['sources']['free']['status'],'FORMAT_AND_HEARTBEAT_OK')
        self.assertFalse(r['active_process_owner_confirmed'])
        self.assertFalse(r['can_execute_orders'])

    def test_pilot_source_only_is_not_runtime_certification(self):
        create_pilot(self.pilot)
        r=self.diagnose()
        self.assertEqual(r['sources']['pilot']['status'],'FORMAT_AND_HEARTBEAT_OK')
        self.assertEqual(r['valid_source_count'],1)

    def test_two_sources_ambiguity_rejected(self):
        create_free(self.free)
        create_pilot(self.pilot)
        r=self.diagnose()
        self.assertEqual(r['status'],'MULTIPLE_VALID_SOURCES_AMBIGUOUS')
        self.assertEqual(r['valid_source_count'],2)
        self.assertFalse(r['may_autoselect_brain_source'])

    def test_stale_free_not_reported_valid(self):
        create_free(self.free,timestamp=NOW-900000)
        r=self.diagnose()
        self.assertEqual(r['sources']['free']['status'],'NOT_VERIFIED')

    def test_stale_pilot_not_reported_valid(self):
        create_pilot(self.pilot,timestamp=NOW-900000)
        r=self.diagnose()
        self.assertEqual(r['sources']['pilot']['status'],'NOT_VERIFIED')

    def test_invalid_source_identity_not_verified(self):
        create_free(self.free)
        with sqlite3.connect(self.free/'brain.sqlite3') as db:
            db.execute('UPDATE state SET body=? WHERE id=1',
                       (json.dumps({'account_id':'wrong','mode':'paper',
                                    'heartbeat_ms':NOW,'positions':{}}),))
        r=self.diagnose()
        self.assertEqual(r['sources']['free']['status'],'NOT_VERIFIED')

    def test_no_sensitive_values_leak(self):
        create_free(self.free)
        r=self.diagnose()
        raw=json.dumps(r)
        for token in ('BTC','ETH','positions',str(self.root),'balances','USDT'):
            if token in ('positions','balances'):
                # Explicit privacy flags do not leak actual data.
                self.assertIn(token+'_exposed',raw)
            else:
                self.assertNotIn(token,raw)

    def test_diagnostic_reads_never_edit_files(self):
        create_free(self.free)
        create_pilot(self.pilot)
        paths=[self.free/'brain.sqlite3',self.pilot/'brain.sqlite3',
               self.pilot/'status.json']
        before=[(p.read_bytes(),p.stat().st_mtime_ns) for p in paths]
        self.diagnose()
        after=[(p.read_bytes(),p.stat().st_mtime_ns) for p in paths]
        self.assertEqual(before,after)

    def test_invalid_clock_rejected(self):
        with self.assertRaisesRegex(ValueError,'clock'):
            self.diagnose(now_ms=True)

if __name__=='__main__':
    unittest.main()
