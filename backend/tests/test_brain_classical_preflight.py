import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[2]/'deploy/scripts/brain_classical_preflight.py'
spec=importlib.util.spec_from_file_location('preflight',PATH)
preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)


class ReadonlyBackupTests(unittest.TestCase):
    def test_actual_restore_preserves_source_db_and_append_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();dest=Path(tmp)/'backup'
            db=sqlite3.connect(source/'brain.sqlite3');db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
            db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,body TEXT)')
            state={'version':'brain-pilot-v1','account':{'name':'brain-paper','positions':{'ETH':{'id':1}}}}
            db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(state),))
            db.execute('INSERT INTO events VALUES(1,?,?)',('journal','{"kind":"cycle"}'));db.commit()
            (source/'spend.jsonl').write_text('{"day":"2026-10-27","cost":0.1}\n')
            files=[source/'brain.sqlite3',source/'brain.sqlite3-wal',source/'spend.jsonl']
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
            result=preflight.backup(source,dest)
            self.assertEqual(result['restore_comparison'],'pass')
            self.assertFalse(result['activation_spend_baseline_frozen'])
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
            self.assertEqual((dest/'verification.json').stat().st_mode & 0o077,0)
            db.close()
    def test_existing_destination_fails_without_source_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();dest=Path(tmp)/'backup';dest.mkdir()
            with self.assertRaises(ValueError):preflight.backup(source,dest)
            self.assertEqual(list(source.iterdir()),[])
    def test_inventory_requires_paper_and_never_returns_environment_secrets(self):
        item={'Config':{'Env':['DESK_MODE=paper','DEEPSEEK_API_KEY=PRIVATE_SENTINEL'],'Labels':{'superbot.sha':'a'*40}},
              'State':{'Running':True,'Health':{'Status':'healthy'}},'Mounts':[{'Source':str(preflight.SOURCE),'Destination':'/out'}]}
        with patch.object(preflight.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps([item]))):
            self.assertNotIn('PRIVATE_SENTINEL',json.dumps(preflight.inventory(preflight.LEGACY)))
        item['Config']['Env'][0]='DESK_MODE=live'
        with patch.object(preflight.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps([item]))):
            with self.assertRaises(ValueError):preflight.inventory(preflight.LEGACY)


if __name__=='__main__':unittest.main()
