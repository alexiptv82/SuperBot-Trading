"""Synthetic audit evidence; never accesses VPS or network."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('audit',ROOT/'deploy/scripts/profit_review_audit.py')
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)
NOW=a.START+20*3600000


def fixture():
    o=dict(schema=1,ev='open',portfolio='hawk',run_no=1,id=1,symbol='PRIVATE_ASSET',
           ts=a.START-3600000,side=-1,source='rules',code_version='4aabeb8',features={'sig_long':10,'sig_short':75})
    p=dict(id=1,symbol='PRIVATE_ASSET',open_ms=o['ts'],side=-1,entry=100,qty=1,fee_open=.06,
           margin=10,total_margin=10,dca_levels=[],last_review_ms=o['ts'])
    limits=dict(fee_bp_side=6,slip_bp_side=2,funding_bp_8h_long=1)
    st=dict(run_no=1,budget={'day':'2026-10-22','spent':.68},last_prices={'PRIVATE_ASSET':94},last_prices_ms=NOW,
            main={'positions':{'PRIVATE_ASSET':p},'closed':[],'limits':limits})
    hb=dict(exec_mode='paper',portfolio='hawk',cycle_running=False,last_ok=True,ts=NOW/1000,
            mode='running',daily_cap_usd=.7,claude_schedule={'allowed':True})
    return [o],st,hb


def envelope(body):
    return {'sequence':1,'previous':'0'*64,'hash':a.sha(a.canonical(['0'*64,1,body])),'body':body}


class AuditTests(unittest.TestCase):
    def test_window_rome_midnight(self):
        self.assertEqual(a.START,1792620000000)
        self.assertEqual(a.END-a.START,86400000)

    def test_missing_decision_log_is_unknown_not_zero(self):
        ev,st,hb=fixture();r=a.audit_bot(ev,st,hb,[],NOW)
        self.assertEqual(r['positions_active_during_window'],1)
        self.assertIsNone(r['exact_historical_management_actions'])
        self.assertIsNone(r['no_review_caused_by_budget'])
        self.assertEqual(r['runtime_budget_band'],'95_to_100pct')

    def test_call_opportunity_not_counted_as_review(self):
        ev,st,hb=fixture();ev.append(dict(ev[0],ev='claude_call',ts=a.START+1,ok=True))
        r=a.audit_bot(ev,st,hb,[],NOW)
        self.assertEqual(r['call_opportunities_per_position_bands'],{'1':1})
        self.assertEqual(r['current_positions_with_timestamp_matched_hold_lower_bound'],0)
        st['main']['positions']['PRIVATE_ASSET']['last_review_ms']=a.START+1
        r=a.audit_bot(ev,st,hb,[],NOW)
        self.assertEqual(r['current_positions_with_timestamp_matched_hold_lower_bound'],1)
        self.assertIsNone(r['exact_historical_management_actions'])

    def test_sidecar_checkpoint_correlated_but_never_applied(self):
        ev,st,hb=fixture();p=st['main']['positions']['PRIVATE_ASSET']
        b=dict(ev='cycle',asof_ms=NOW,run_no=1,mode='ombra',applied=False,
               positions=[{'snapshot':p,'roi':{'roi':70,'checkpoint':'LASCIA_CORRERE'}}])
        r=a.audit_bot(ev,st,hb,[b],NOW)
        self.assertEqual(r['positions_observed_at_or_above_50pct'],1)
        self.assertEqual(r['sidecar_checkpoint_bands'][0]['roi_band'],'50_to_100')
        b['applied']=True
        with self.assertRaises(a.Blocked): a.audit_bot(ev,st,hb,[b],NOW)

    def test_hash_chain_and_duplicate_json(self):
        body={'ev':'freeze','reason':'anything'};e=envelope(body)
        raw=a.canonical(e)+b'\n'
        self.assertEqual(a.sidecar_bodies([raw]),[body])
        with self.assertRaises(a.Blocked):a.sidecar_bodies([raw,raw])
        with self.assertRaises(a.Blocked):a.jsonl(b'{"x":1,"x":2}\n')
        for raw in (b'',b'\n',b'{}',b'{"x":NaN}\n',b'{"x":1e999}\n'):
            with self.assertRaises(a.Blocked):a.jsonl(raw)

    def test_no_symbols_prices_free_text_or_amounts_in_output(self):
        ev,st,hb=fixture();hb['claude_schedule']['allowed']='PRIVATE_SECRET'
        ev.append(dict(ev[0],ts=a.START+2,id=2,source='PRIVATE_SECRET',code_version='PRIVATE_SECRET'))
        result=json.dumps(a.audit_bot(ev,st,hb,[],NOW),allow_nan=False)
        for text in ('PRIVATE_SECRET','PRIVATE_ASSET','"entry"','"spent"','"cash"','"margin"'):
            self.assertNotIn(text,result)

    def test_current_roi_and_stale_mark(self):
        _,st,_=fixture();p=st['main']['positions']['PRIVATE_ASSET']
        self.assertGreater(a.current_roi(st,p,NOW),50)
        st['last_prices_ms']=NOW-3000000
        self.assertIsNone(a.current_roi(st,p,NOW))

    def test_ai_previous_utc_day_tail_and_isolation(self):
        cycles=[dict(ts_ms=a.START-1,decision={'called':True},events=[{'ev':'fill','side':1}]),
                dict(ts_ms=a.START+1,decision={'called':True},events=[{'ev':'fill','side':-1}])]
        r=a.audit_ai(cycles,[],NOW)
        self.assertEqual(r['called'],1);self.assertEqual(r['virtual_fills_by_side'],{'short':1})
        self.assertFalse(r['applied_to_bots'])

    def test_new_opens_grouping_and_reviewed_bonus(self):
        ev,st,hb=fixture();ev[0]['ts']=a.START+1
        r=a.audit_bot(ev,st,hb,[],NOW)
        self.assertEqual(r['opens'][0]['source'],'rules')
        self.assertEqual(r['opens'][0]['nominal_bonus_reconstruction'],{'1_to_4':1})
        self.assertEqual(r['opens'][0]['bonus_evidence'],{'reconstructed_not_directly_logged':1})

    def test_paper_and_stale_gates(self):
        ev,st,hb=fixture()
        for field,value in (('exec_mode','live'),('cycle_running',True),('ts',0)):
            changed=dict(hb,**{field:value})
            with self.assertRaises(a.Blocked):a.audit_bot(ev,st,changed,[],NOW)

    def test_read_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_bytes(b'x');l=Path(d)/'link';l.symlink_to(p)
            with self.assertRaises(OSError):a.read(l)

    def test_full_snapshot_and_concurrent_append_block(self):
        ev,st,hb=fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for bot in ("hawk","bull"):
                folder=root/"data"/bot;folder.mkdir(parents=True)
                (folder/"learning_log.jsonl").write_bytes(b"".join(a.canonical(dict(r,portfolio=bot))+b"\n" for r in ev))
                (folder/"state_v2.json").write_bytes(a.canonical(st))
                (folder/"heartbeat.json").write_bytes(a.canonical(dict(hb,portfolio=bot)))
                (root/"sidecar"/bot).mkdir(parents=True)
            (root/"ai"/"ai").mkdir(parents=True)
            r=a.run(root/"data",root/"sidecar",root/"ai",NOW)
            self.assertEqual(r["scope"],a.SCOPE)
            self.assertIn("ai_cycles_2026-10-21",r["missing_sources"])
            original=a.read;calls={}
            def mutate(p):
                key=str(p);calls[key]=calls.get(key,0)+1
                return original(p)+(b" " if calls[key]>1 else b"")
            with patch.object(a,"read",side_effect=mutate),self.assertRaises(a.Blocked):
                a.run(root/"data",root/"sidecar",root/"ai",NOW)

    def test_workflow_isolated_no_activation(self):
        s=(ROOT/'.github/workflows/desk-profit-review-audit.yml').read_text()
        for x in ('--network none','--read-only',':/data:ro',':/sidecar:ro',':/ai:ro','LOADED_WORKFLOW_SHA','trap finish EXIT'):
            self.assertIn(x,s)
        for x in ('docker stop','docker restart','docker exec','workflow_dispatch'):
            self.assertNotIn(x,s)
        self.assertFalse((ROOT/'deploy/desk-profit-review-audit.trigger').exists())

if __name__=='__main__':unittest.main()
