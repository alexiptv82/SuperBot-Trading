import copy
import json
import tempfile
from pathlib import Path
import unittest
from desk.profit_sidecar.reader import read_consistent, read_bytes
from desk.profit_sidecar.accounting import snapshot, closed_records
from desk.profit_sidecar.journal import Journal
from desk.profit_sidecar.common import Freeze


def fixture():
    pos = dict(id=1,symbol="BTC",side=1,margin=100,leverage=10,entry=100,qty=10,
               fee_open=.6,total_margin=100,open_ms=1000,sl=95,tp=120,liq=90,
               dca_levels=[],dca_count=0,legs=1,entry0=100,px_hi=115,px_lo=99,
               pending_split=None,trade_type="medio",source="rules")
    state = dict(run_no=3,run_started_ms=500,last_prices={"BTC":110},last_prices_ms=3600000,
                 main=dict(positions={"BTC":pos},closed=[],limits=dict(fee_bp_side=6,slip_bp_side=2,funding_bp_8h_long=1)))
    hb = dict(started_ms=100,cycles=2,last_start_ms=3600000,last_end_ms=3601000,
              cycle_running=False,exec_mode="paper",portfolio="hawk",last_ok=True,open_positions=1,ts=3601)
    return state,hb


class SidecarIOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.state,self.hb = fixture()
        self.write()

    def write(self):
        (self.source/"state_v2.json").write_text(json.dumps(self.state))
        (self.source/"heartbeat.json").write_text(json.dumps(self.hb))

    def obs(self, **kw):
        return read_consistent(self.source,"hawk",3602000,**kw)

    def test_reader_does_not_write(self):
        before = {p.name:p.read_bytes() for p in self.source.iterdir()}
        self.obs()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.source.iterdir()})

    def test_cycle_running_rejected(self):
        self.hb["cycle_running"]=True
        self.write()
        with self.assertRaises(Freeze): self.obs()

    def test_heartbeat_change_rejected(self):
        calls=0
        def race(path):
            nonlocal calls
            calls+=1
            if calls==4:
                return json.dumps(dict(self.hb,cycles=3)).encode()
            return read_bytes(path)
        with self.assertRaisesRegex(Freeze,"source_changed"): self.obs(read=race)

    def test_atomic_state_replace_rejected(self):
        calls=0
        def race(path):
            nonlocal calls
            calls+=1
            if calls==3:
                changed=copy.deepcopy(self.state)
                changed["main"]["positions"]["BTC"]["qty"]=9
                return json.dumps(changed).encode()
            return read_bytes(path)
        with self.assertRaisesRegex(Freeze,"source_changed"): self.obs(read=race)

    def test_missing_corrupt_stale_and_live(self):
        p=self.source/"state_v2.json"
        p.unlink()
        with self.assertRaises(Freeze): self.obs()
        p.write_text("{")
        with self.assertRaises(Freeze): self.obs()
        self.write()
        with self.assertRaises(Freeze): read_consistent(self.source,"hawk",9999999)
        self.hb["exec_mode"]="live"
        self.write()
        with self.assertRaises(Freeze): self.obs()

    def test_partial_occurrences_and_reconciliation(self):
        p=self.state["main"]["positions"]["BTC"]
        self.state["main"]["closed"]=[dict(id=1,symbol="BTC",open_ms=1000,close_ms=3600000,net=24.63,partial=True),
                                      dict(id=1,symbol="BTC",open_ms=1000,close_ms=3600000,net=18.47,partial=True)]
        p.update(qty=5.625,total_margin=56.25,fee_open=.3375)
        self.write()
        snap,view,_,_=snapshot(self.obs(),p)
        self.assertAlmostEqual(view.realized_net,43.10)
        self.assertEqual(snap["reference_margin"],100)
        hashes,outcomes=closed_records(self.obs(),[])
        self.assertEqual(len(outcomes),2)
        self.assertNotEqual(outcomes[0]["event_id"],outcomes[1]["event_id"])
        self.state["main"]["closed"].append(dict(id=1,symbol="BTC",open_ms=1000,close_ms=3601000,net=10))
        self.write()
        _,final=closed_records(self.obs(),hashes)
        self.assertAlmostEqual(final[0]["lifecycle_net_usd"],53.10)
        self.state["main"]["closed"].pop(0)
        self.write()
        with self.assertRaisesRegex(Freeze,"prefix"): closed_records(self.obs(),hashes)

    def test_dca_and_split_margin_funding(self):
        p=self.state["main"]["positions"]["BTC"]
        p.update(margin=200,legs=2,dca_levels=[dict(margin=80,added_ms=3600000)],total_margin=280)
        self.write()
        snap,view,costs,_=snapshot(self.obs(),p)
        self.assertEqual(view.reference_margin,280)
        self.assertAlmostEqual(view.funding_paid,10*100*.0001*3599000/28800000)  # clock = engine cycle start (price_ms), not cycle end
        self.assertEqual(costs.slippage_fraction,.0002)
        self.assertEqual(snap["legs"],2)

    def test_dca_and_partial_same_cycle_ambiguous(self):
        p=self.state["main"]["positions"]["BTC"]
        p["dca_levels"]=[dict(margin=40,added_ms=3600000)]
        self.state["main"]["closed"]=[dict(id=1,symbol="BTC",open_ms=1000,close_ms=3600000,net=1,partial=True)]
        self.write()
        self.assertTrue(snapshot(self.obs(),p,previous_cycle_end=3500000)[0]["ambiguous_order"])

    def test_journal_restart_dedup_rotation_and_lock(self):
        root=self.root/"output"
        a=dict(event_id="a",portfolio="hawk",cache={"value":1})
        with Journal(root,max_segment_bytes=1) as j:
            self.assertTrue(j.append(a))
            self.assertFalse(j.append(a))
            with self.assertRaises(Freeze): Journal(root)
            with self.assertRaises(Freeze): j.append(dict(a,cache={"value":2}))
            j.append(dict(event_id="b",portfolio="bull",cache={"value":3}))
        self.assertEqual(len(list(root.glob("events-*.jsonl"))),2)
        with Journal(root) as j:
            self.assertFalse(j.append(a))
            self.assertEqual(j.cache["hawk"],{"value":1})

    def test_corrupted_journal_stops_without_erasing(self):
        root=self.root/"output"
        with Journal(root) as j: j.append(dict(event_id="a"))
        path=next(root.glob("events-*.jsonl"))
        with path.open("ab") as stream: stream.write(b'{"torn":')
        before=path.read_bytes()
        with self.assertRaises(Freeze): Journal(root)
        self.assertEqual(path.read_bytes(),before)


if __name__=="__main__": unittest.main()
