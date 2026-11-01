"""Brain metadata diagnostic: fail closed, all running containers, no secrets."""
import json
import unittest
from long_shadow_brain_docker_metadata_preflight import (
    inspect_running_brain_writer_candidates as inspect,
    FREE_MOUNT, PILOT_MOUNT,
)


def reader(definitions):
    def simulate(args):
        if args == ['ps', '--format', '{{.Names}}']:
            return '\n'.join(definitions) + ('\n' if definitions else '')
        if (len(args) == 4 and
                args[:3] == ['inspect', '--format', '{{json .Mounts}}'] and
                args[3] in definitions):
            return json.dumps(definitions[args[3]])
        raise AssertionError('unapproved_docker_subcommand')
    return simulate


def mount(path, writable, source=None):
    return {'Destination': path, 'RW': writable,
            'Source': source or '/SECRET/USER/DATA/DO_NOT_PRINT'}


class WriterAttestationTests(unittest.TestCase):
    def test_readonly_app_has_no_writer(self):
        d = {'superbot': [mount(FREE_MOUNT, False), mount(PILOT_MOUNT, False)]}
        result = inspect(reader(d))
        self.assertEqual(result['status'], 'NO_KNOWN_WRITABLE_MOUNT_CANDIDATE')
        self.assertEqual(result['candidate_counts']['app_readonly'], 1)
        self.assertFalse(result['active_owner_confirmed'])

    def test_one_free_candidate_not_process_confirmation(self):
        d = {'superbot-brain-free': [mount(FREE_MOUNT, True)]}
        result = inspect(reader(d))
        self.assertEqual(result['status'],
                         'ONE_EXACT_WRITABLE_MOUNT_CANDIDATE_NOT_PROVEN_OWNER')
        self.assertEqual(result['candidate_counts']['free'], 1)
        self.assertFalse(result['brain_source_autoselected'])

    def test_one_pilot_candidate_not_process_confirmation(self):
        d = {'superbot-brain-pilot': [mount(PILOT_MOUNT, True)]}
        self.assertEqual(inspect(reader(d))['candidate_counts']['pilot'], 1)

    def test_both_brain_writers_ambiguous(self):
        d = {'superbot-brain-free': [mount(FREE_MOUNT, True)],
             'superbot-brain-pilot': [mount(PILOT_MOUNT, True)]}
        self.assertEqual(inspect(reader(d))['status'],
                         'AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT')

    def test_one_writer_mounts_both_paths_ambiguous(self):
        d = {'superbot-brain-free':
             [mount(FREE_MOUNT, True), mount(PILOT_MOUNT, True)]}
        result = inspect(reader(d))
        self.assertEqual(result['candidate_counts']['both'], 1)
        self.assertEqual(result['status'],
                         'AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT')

    def test_unknown_named_container_with_writer_is_NOT_ignored(self):
        d = {'nginx': [mount(FREE_MOUNT, True)], 'redis': []}
        result = inspect(reader(d))
        self.assertEqual(result['running_writer_mount_candidate_count'], 1)
        self.assertEqual(result['candidate_counts']['unexpected_writer'], 1)
        self.assertEqual(result['status'],
                         'AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT')
        self.assertEqual(result['running_containers_examined'], 2)

    def test_source_bind_at_real_wallet_path_detected_even_if_dest_different(self):
        d = {'random-worker': [mount('/data/anything', True, source=FREE_MOUNT)]}
        result = inspect(reader(d))
        self.assertEqual(result['candidate_counts']['free'], 1)
        self.assertEqual(result['candidate_counts']['unexpected_writer'], 1)

    def test_parent_writable_mount_treated_ambiguous(self):
        d = {'superbot-brain': [mount('/opt/superbot-desk-data', True)]}
        result = inspect(reader(d))
        self.assertEqual(result['candidate_counts']['pilot'], 1)
        self.assertEqual(result['candidate_counts']['broad_rw'], 1)
        self.assertEqual(result['status'],
                         'AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT')

    def test_web_app_writable_mount_is_not_considered_certified_brain(self):
        d = {'superbot': [mount(FREE_MOUNT, True)]}
        result = inspect(reader(d))
        self.assertEqual(result['candidate_counts']['web_app_writer'], 1)
        self.assertEqual(result['status'],
                         'AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT')

    def test_no_sensitive_values_emitted(self):
        d = {'superbot-brain-free': [mount(FREE_MOUNT, True)]}
        raw = json.dumps(inspect(reader(d)))
        for token in ('SECRET', 'USER', 'DO_NOT_PRINT', 'superbot-brain-free',
                      '/opt/', 'api_key', 'account_id'):
            self.assertNotIn(token, raw)

    def test_invalid_metadata_fails_closed(self):
        def broken(args):
            return 'superbot-brain-free\n' if args[0] == 'ps' else '{"secret":1}'
        with self.assertRaisesRegex(ValueError, 'invalid_docker_mount_metadata'):
            inspect(broken)

    def test_rejects_unsafe_container_name(self):
        def malicious(args):
            return 'superbot; rm -rf /\n'
        with self.assertRaisesRegex(ValueError, 'invalid_container_name'):
            inspect(malicious)

    def test_never_calls_docker_write_api(self):
        calls = []
        def safe(args):
            calls.append(tuple(args))
            return 'superbot\n' if args[0] == 'ps' else '[]'
        result = inspect(safe)
        self.assertFalse(result['deployment_approved'])
        self.assertTrue(all(x[0] in ('ps', 'inspect') for x in calls))

    def test_nonmatching_paths_are_not_falsely_classified(self):
        d = {'other': [mount('/other/app', True, source='/var/cache')]}
        r = inspect(reader(d))
        self.assertEqual(r['running_writer_mount_candidate_count'], 0)

    def test_duplicate_container_name_fails_closed(self):
        def dup(args):
            return 'superbot\nsuperbot\n'
        with self.assertRaisesRegex(ValueError, 'duplicate_container_metadata'):
            inspect(dup)

    def test_excess_containers_fail_closed(self):
        d = {'c'+str(i): [] for i in range(101)}
        with self.assertRaisesRegex(ValueError, 'too_many_running_containers'):
            inspect(reader(d))


if __name__ == '__main__':
    unittest.main()
