import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import contextlib
import io
import sys
from types import SimpleNamespace
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[2]/'deploy/scripts/brain_classical_activate.py'
spec=importlib.util.spec_from_file_location('activate',PATH)
activate=importlib.util.module_from_spec(spec);spec.loader.exec_module(activate)


class ActivationGates(unittest.TestCase):
    def test_quiescence_requires_a_completed_non_calling_paper_cycle_after_pause(self):
        s={'mode':'paper','applied':False,'ts_ms':2000,'last_cycle':{'called':False}}
        self.assertTrue(activate.quiescent(s,1000,3000))
        for field,value in (('mode','live'),('applied',True),('ts_ms',500)):
            bad=dict(s,**{field:value});self.assertFalse(activate.quiescent(bad,1000,3000))
        bad=dict(s,last_cycle={'called':True});self.assertFalse(activate.quiescent(bad,1000,3000))
    def test_initial_account_gate_is_readonly_and_rejects_unexpected_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'brain-hawk';folder.mkdir();db=sqlite3.connect(folder/'brain.sqlite3')
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
            s={'version':'classical-adaptive-v1','profile':'hawk','method':'a'*64,'operator_paused':True,'desk':{'main':{'name':'brain-hawk','positions':{},'closed':[],'cash':1000,'limits':{'start_equity':1000}}}}
            db.execute('INSERT INTO state VALUES (1,?)',(json.dumps(s),));db.commit()
            (folder/'status.json').write_text(json.dumps({'mode':'paper','profile':'hawk','version':s['version'],'method_version':'a'*64,'ts_ms':3000,'fresh_fast_data':True}))
            self.assertTrue(activate.initial_account(root,'hawk',4000))
            s['desk']['main']['positions']['ETH']={'id':1}
            db.execute('UPDATE state SET body=?',(json.dumps(s),));db.commit()
            with self.assertRaises(ValueError):activate.initial_account(root,'hawk',4000)
            db.close()
    def test_private_exclusive_control_files_never_overwrite_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'flag';activate.create_private(path,'token')
            self.assertEqual(path.stat().st_mode & 0o077,0)
            with self.assertRaises(FileExistsError):activate.create_private(path,'overwrite')
            self.assertEqual(path.read_text(),'token')

    def simulate(self,failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'target';root.mkdir();old=base/'old';old.mkdir();repo=base/'repo';repo.mkdir()
            (old/'spend.jsonl').write_text('{"day":"2026-10-27","cost":0.1}\n')
            (old/'status.json').write_text('{}')
            sha='a'*40;classic='b'*40;legacy='c'*40;app='d'*40
            stopped=[];calls=[]
            def inventory(name):
                return {'name':name,'mode':'paper','running':True,'health':'healthy',
                        'sha':legacy if name=='superbot-brain-pilot' else classic if name.startswith('superbot-desk-') else sha,
                        'policy_environment':{'DESK_CAPITAL_V1':'off'} if name.startswith('superbot-desk-') else {}}
            def backup(*_):self.assertFalse((old/'pause.flag').exists())
            h=SimpleNamespace(inventory=inventory,backup=backup)
            def command(args,timeout=60):
                calls.append(args)
                if args[0]=='git':return sha if 'rev-parse' in args else ''
                if args[1]=='inspect':return json.dumps([{'Config':{'Labels':{'superbot.sha':app}},'Mounts':[{'Source':str(root),'Destination':str(root),'RW':False}]}])
                if args[1]=='build' and failure=='build':raise ValueError('CONTROL_COMMAND_FAILED')
                if args[1]=='stop':stopped.append(args[-1]);return ''
                if args[1]=='run' and '--name' in args:
                    profile=args[args.index('--profile')+1];folder=root/('brain-'+profile)
                    self.assertTrue((old/'pause.flag').exists())
                    self.assertTrue((folder/'pause.flag').exists())
                    from director.classical_adaptive.budget import SharedBudget
                    from director.ai_shadow.config import Config
                    SharedBudget(root/'brain-api-budget.sqlite3',Config(),json.loads((root/'api_budget_baseline.json').read_text()))
                    s={'version':'classical-adaptive-v1','profile':profile,'method':'e'*64,'operator_paused':True,
                       'desk':{'main':{'name':'brain-'+profile,'cash':1000,'positions':{'ETH':{'id':1}} if failure=='exposure' else {},'closed':[],'limits':{'start_equity':1000}}}}
                    with sqlite3.connect(folder/'brain.sqlite3') as db:
                        db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)');db.execute('INSERT INTO state VALUES (1,?)',(json.dumps(s),))
                    (folder/'status.json').write_text(json.dumps({'mode':'paper','profile':profile,'version':s['version'],'method_version':s['method'],'ts_ms':1793102400000,'fresh_fast_data':True}))
                return ''
            argv=['activate','--sha',sha,'--classic-sha',classic,'--legacy-sha',legacy,'--app-sha',app,'--repo',str(repo)]
            tick=[0]
            def monotonic():tick[0]+=1000;return tick[0]
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(activate,'ROOT',root));stack.enter_context(patch.object(activate,'OLD',old))
                stack.enter_context(patch.object(activate,'load_preflight',return_value=h));stack.enter_context(patch.object(activate,'run',side_effect=command))
                stack.enter_context(patch.object(activate.subprocess,'run',return_value=SimpleNamespace(returncode=1)))
                stack.enter_context(patch.object(activate,'quiescent',return_value=True))
                stack.enter_context(patch.object(activate.time,'time',return_value=1793102400))
                stack.enter_context(patch.object(activate.time,'monotonic',side_effect=monotonic))
                stack.enter_context(patch.object(sys,'argv',argv));stack.enter_context(patch.object(sys,'path',list(sys.path)))
                stack.enter_context(patch.dict('os.environ',{'BRAIN_CLASSICAL_ACTIVATE_APPROVED':'paper:'+sha,'DEEPSEEK_API_KEY':'test-only'}))
                output=io.StringIO()
                with contextlib.redirect_stdout(output):
                    if failure:
                        with self.assertRaises(ValueError):activate.main()
                    else:activate.main()
            if failure=='build':
                self.assertFalse((old/'pause.flag').exists());self.assertEqual(list(root.iterdir()),[])
            elif failure=='exposure':
                self.assertTrue((old/'pause.flag').exists());self.assertFalse(stopped)
                self.assertTrue(all((root/('brain-'+p)/'pause.flag').exists() for p in ('hawk','bull')))
            else:
                self.assertTrue(json.loads(output.getvalue())['ok'])
                self.assertTrue((old/'pause.flag').exists());self.assertFalse(stopped)
                self.assertTrue(all(not (root/('brain-'+p)/'pause.flag').exists() for p in ('hawk','bull')))
                with sqlite3.connect(root/'brain-api-budget.sqlite3') as db:self.assertAlmostEqual(db.execute('SELECT SUM(cost) FROM reservations').fetchone()[0],.1)
    def test_simulated_rollout_warms_paused_carries_spend_then_releases_only_new_profiles(self):self.simulate()
    def test_build_failure_cannot_pause_old_runtime_or_initialize_accounts(self):self.simulate('build')
    def test_uncertain_exposure_keeps_management_running_and_never_resets_budget(self):self.simulate('exposure')


if __name__=='__main__':unittest.main()
