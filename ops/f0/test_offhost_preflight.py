"""Offline fixtures; never touch the VPS or actual historical databases."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ops.f0.offhost_preflight import inspect


class F0ExternalBackupPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.status = self.root / 'status.json'
        self.manifest = self.root / 'manifest.json'
        self.status.write_text(json.dumps({
            'ultimo_successo': '2026-11-02T03:28:45Z',
            'archivio': 'superbot-backup-20261102T032845Z.tar.gz.age',
            'ultimo_errore': None,
            'secret_that_must_never_print': 'VERY_SECRET',
        }))
        obs = {'event_count': 8447, 'max_event_seq': 8447,
               'events_sha256': 'a' * 64}
        self.manifest.write_text(json.dumps({
            'schema': 'superbot-v3-f0-brain-snapshot-v1',
            'created_utc': '2026-11-03T03:55:00+00:00',
            'snapshot_db_sha256': 'b' * 64,
            'source_observation': obs,
            'snapshot_observation': obs,
            'secret_that_must_never_print': 'VERY_SECRET',
        }))

    def test_backup_predating_snapshot_not_sufficient(self):
        value = inspect(self.status, self.manifest)
        self.assertFalse(value['archive_newer_than_brain_snapshot'])
        self.assertEqual(value['brain_events_reported'], 8447)
        self.assertFalse(value['externally_certified'])
        self.assertNotIn('VERY_SECRET', json.dumps(value))

    def test_newer_archive_still_not_a_restore_certificate(self):
        status = json.loads(self.status.read_text())
        status['ultimo_successo'] = '2026-11-03T10:00:00Z'
        self.status.write_text(json.dumps(status))
        value = inspect(self.status, self.manifest)
        self.assertTrue(value['archive_newer_than_brain_snapshot'])
        self.assertFalse(value['archive_coverage_verified'])
        self.assertFalse(value['external_storage_verified'])
        self.assertFalse(value['restore_verified'])

    def test_invalid_and_malicious_status_never_leak(self):
        self.status.write_text('NOT JSON SUPERSECRET')
        value = inspect(self.status, self.manifest)
        self.assertEqual(value['legacy_status'], 'UNAVAILABLE')
        self.assertNotIn('SUPERSECRET', json.dumps(value))

    def test_status_symlink_refused(self):
        other = self.root / 'private.json'
        other.write_text('SECRET')
        self.status.unlink()
        self.status.symlink_to(other)
        self.assertEqual(inspect(self.status, self.manifest)['legacy_status'], 'UNAVAILABLE')

    def test_manifest_snapshot_observation_mismatch_fails_closed(self):
        manifest = json.loads(self.manifest.read_text())
        manifest['snapshot_observation'] = {'event_count': 1}
        self.manifest.write_text(json.dumps(manifest))
        self.assertEqual(inspect(self.status, self.manifest)['brain_manifest'], 'UNAVAILABLE')

    def test_oversized_status_rejected(self):
        self.status.write_text('A' * 65537)
        self.assertEqual(inspect(self.status, self.manifest)['legacy_status'], 'UNAVAILABLE')

    def test_malformed_timestamps_do_not_infer_freshness(self):
        value = json.loads(self.status.read_text())
        value['ultimo_successo'] = 'yesterday'
        self.status.write_text(json.dumps(value))
        result = inspect(self.status, self.manifest)
        self.assertEqual(result['archive_newer_than_brain_snapshot'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
