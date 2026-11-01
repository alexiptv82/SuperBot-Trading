"""Docker Brain preflight: read-only, aggregate and NEVER confirms ownership."""
import json
import unittest
from long_shadow_brain_docker_metadata_preflight import (
    inspect_running_brain_writer_candidates as inspect,
    FREE_MOUNT, PILOT_MOUNT,
)


def reader(definitions):
    def simulate(args):
        if args==['ps','--format','{{.Names}}']:
            return '\n'.join(definitions)+'\n'
        if (len(args)==4 and args[:3]==['inspect','--format','{{json .Mounts}}']
                and args[3] in definitions):
            return json.dumps(definitions[args[3]])
        raise AssertionError('unapproved_docker_subcommand')
    return simulate


def mount(path, writable):
    return {'Destination':path, 'RW':writable,
            'Source':'/SECRET/USER/DATA/DO_NOT_PRINT'}


class WriterAttestationTests(unittest.TestCase):
    def test_app_with_two_readonly_mounts_is_not_writer(self):
        d={'superbot':[mount(FREE_MOUNT,False),mount(PILOT_MOUNT,False)]}
        result=inspect(reader(d))
        self.assertEqual(result['status'],'NO_WRITABLE_BRAIN_MOUNT_CANDIDATE')
        self.assertEqual(result['candidate_counts']['app_readonly'],1)
        self.assertFalse(result['active_owner_confirmed'])

    def test_one_free_candidate_not_process_confirmation(self):
        d={'superbot-brain-free':[mount(FREE_MOUNT,True)]}
        r=inspect(reader(d))
        self.assertEqual(r['status'],'ONE_WRITABLE_MOUNT_CANDIDATE_NOT_PROVEN_OWNER')
        self.assertEqual(r['candidate_counts']['free'],1)
        self.assertFalse(r['brain_source_autoselected'])

    def test_one_pilot_candidate_not_process_confirmation(self):
        d={'superbot-brain-pilot':[mount(PILOT_MOUNT,True)]}
        self.assertEqual(inspect(reader(d))['candidate_counts']['pilot'],1)

    def test_both_brain_writers_ambiguous(self):
        d={'superbot-brain-free':[mount(FREE_MOUNT,True)],
           'superbot-brain-pilot':[mount(PILOT_MOUNT,True)]}
        self.assertEqual(inspect(reader(d))['status'],
                         'MULTIPLE_OR_AMBIGUOUS_WRITERS')

    def test_one_writer_mounts_both_paths_ambiguous(self):
        d={'superbot-brain-free':[mount(FREE_MOUNT,True),mount(PILOT_MOUNT,True)]}
        result=inspect(reader(d))
        self.assertEqual(result['candidate_counts']['both'],1)
        self.assertEqual(result['status'],'MULTIPLE_OR_AMBIGUOUS_WRITERS')

    def test_no_sensitive_values_emitted(self):
        d={'superbot-brain-free':[mount(FREE_MOUNT,True)]}
        raw=json.dumps(inspect(reader(d)))
        for token in ('SECRET','USER','DO_NOT_PRINT','superbot-brain-free',
                      '/opt/','api_key','account_id'):
            self.assertNotIn(token,raw)

    def test_unrelated_docker_containers_ignored(self):
        d={'nginx':[mount(FREE_MOUNT,True)],'redis':[]}
        result=inspect(reader(d))
        self.assertEqual(result['running_writer_mount_candidate_count'],0)

    def test_invalid_metadata_fails_closed(self):
        def broken(args):
            return 'superbot-brain-free\n' if args[0]=='ps' else '{"secret":1}'
        with self.assertRaisesRegex(ValueError,'invalid_docker_mount_metadata'):
            inspect(broken)

    def test_rejects_unsafe_container_name(self):
        def malicious(args):
            return 'superbot; rm -rf /\n'
        with self.assertRaisesRegex(ValueError,'invalid_container_name'):
            inspect(malicious)

    def test_never_calls_docker_write_api(self):
        calls=[]
        def safe(args):
            calls.append(tuple(args))
            return 'superbot\n' if args[0]=='ps' else '[]'
        result=inspect(safe)
        self.assertFalse(result['deployment_approved'])
        self.assertTrue(all(x[0] in ('ps','inspect') for x in calls))

if __name__=='__main__':
    unittest.main()
