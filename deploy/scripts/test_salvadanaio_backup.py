"""Verify vault-only backup journal selection without server or account data."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

class VaultBackupTests(unittest.TestCase):
    def test_required_journal_tracks_active_policy_and_rejects_damage(self):
        spec=importlib.util.spec_from_file_location('vault_backup',Path(__file__).with_name('backup_brain.py'))
        backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
        self.assertIn('salvadanaio-journal.jsonl',backup.CRITICAL)
        self.assertIn('salvadanaio-journal.jsonl',backup.CORE)
        for policy,journal in [('salvadanaio-only-v1','salvadanaio-journal.jsonl'),('capital-v1','capital-v1-journal.jsonl')]:
            with self.subTest(policy=policy),tempfile.TemporaryDirectory() as folder:
                d=Path(folder)/'hawk';d.mkdir()
                for name in backup.REQUIRED:(d/name).write_text('')
                (d/'state_v2.json').write_text(json.dumps({'capital':{'schema_version':1,'policy':policy}}))
                self.assertEqual(backup.required_missing(folder,['hawk']),['hawk/'+journal])
                (d/journal).write_text('{}\n')
                self.assertEqual(backup.required_missing(folder,['hawk']),[])
                (d/journal).write_text('{broken\n')
                self.assertTrue(backup.required_missing(folder,['hawk']))

if __name__=='__main__':unittest.main()
