"""Offline SQLite migration checks; never operate on production data."""
import copy
import fcntl
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('seed_migration',ROOT/'migrate_method_digest.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OLD='a'*64;NEW='b'*64;SHA='c'*40

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.folder=self.root/'brain-hawk';self.folder.mkdir()
        (self.folder/'writer.lock').touch();(self.folder/'pause.flag').write_text('test')
        self.path=self.folder/'brain.sqlite3'
        self.state={'version':'classical-adaptive-v1','profile':'hawk','method':OLD,
                    'desk':{'main':{'name':'brain-hawk','cash':731.4,'positions':{'BTC':{'id':9,'margin':100}}}},
                    'contexts':{'9:123':{'strategy_version':'old-cohort'}},'learning':{'cursor':1},
                    'api_budget_checkpoint':{'monthly_reserved':.35}}
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)')
            db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,body TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(self.state),))
            db.execute("INSERT INTO events VALUES(1,'trade',?)",(json.dumps({'net':-2}),))
        self.original=self.read()
        self.compute=patch.object(m,'compute_method_digest_subprocess',return_value=NEW);self.compute.start();self.addCleanup(self.compute.stop)
    def read(self):
        with sqlite3.connect(self.path) as db:
            return (db.execute('SELECT body FROM state').fetchone()[0],db.execute('SELECT * FROM events').fetchall())
    def run_migration(self,**kwargs):
        return m.migrate('hawk',OLD,data_root=self.root,source_sha=SHA,**kwargs)
    def test_dry_run_does_not_modify_state_events_or_create_backup(self):
        r=self.run_migration(dry_run=True)
        self.assertEqual(r['to_method'],NEW);self.assertEqual(self.read(),self.original)
        self.assertFalse(list(self.folder.glob('*.before-method-*')))
    def test_atomic_migration_preserves_all_other_state_and_prior_events(self):
        r=self.run_migration();raw,events=self.read();state=json.loads(raw)
        self.assertEqual(state['method'],NEW);state['method']=OLD
        self.assertEqual(state,self.state);self.assertEqual(events[:1],self.original[1])
        self.assertEqual(len(events),2);self.assertEqual(events[-1][1],'journal')
        with sqlite3.connect(r['backup']) as db:
            self.assertEqual(db.execute('SELECT body FROM state').fetchone()[0],self.original[0])
        before=self.read()
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_OLD_METHOD'):self.run_migration()
        self.assertEqual(self.read(),before)
    def test_refuses_active_writer(self):
        with (self.folder/'writer.lock').open('rb') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'WRITER_STILL_ACTIVE'):self.run_migration()
        self.assertEqual(self.read(),self.original)
    def test_requires_pause_and_correct_profile(self):
        (self.folder/'pause.flag').unlink()
        with self.assertRaisesRegex(ValueError,'PAUSE_REQUIRED'):self.run_migration()
        (self.folder/'pause.flag').touch()
        with sqlite3.connect(self.path) as db:
            s=copy.deepcopy(self.state);s['profile']='bull';db.execute('UPDATE state SET body=?',(json.dumps(s),))
        with self.assertRaisesRegex(ValueError,'PROFILE_STATE_MISMATCH'):self.run_migration()
    def test_event_insert_failure_rolls_back_method_change(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER reject_new BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.run_migration()
        self.assertEqual(self.read(),self.original)

if __name__=='__main__':unittest.main()
