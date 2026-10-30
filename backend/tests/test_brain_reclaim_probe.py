import unittest
from copy import deepcopy
from research.long_reclaim.probe import observe

D=300000;NOW=22*D

def bars():
    rows=[[i*D,100,101,99,100,100] for i in range(22)]
    rows[-2]=[20*D,100,101,98,100,200]
    rows[-1]=[21*D,100,103,100,102,100]
    return rows

class Probe(unittest.TestCase):
    def test_confirmation_only_and_no_permission(self):
        r=observe('BTC',bars(),NOW)
        self.assertEqual(r['events'][0]['side'],'LONG')
        self.assertFalse(r['execution_permission'])
        self.assertEqual(observe('BTC',bars(),NOW-1)['events'],[])

    def test_exact_mirror(self):
        a=bars();b=[[t,200-o,200-l,200-h,200-c,v] for t,o,h,l,c,v in a]
        self.assertEqual(observe('BTC',b,NOW)['events'][0]['side'],'SHORT')

    def test_future_does_not_change_signal(self):
        a=bars();b=a+[[NOW,102,1000,1,999,100000]]
        self.assertEqual(observe('BTC',a,NOW),observe('BTC',b,NOW))

    def test_gap_and_stale(self):
        self.assertEqual(observe('BTC',bars()[1:],NOW)['status'],'data_unavailable')
        self.assertEqual(observe('BTC',bars(),NOW+2*D)['status'],'data_unavailable')

    def test_failed_confirmation_or_volume(self):
        for column,value in [(4,100),(5,20)]:
            rows=bars()
            rows[-1 if column==4 else -2][column]=value
            self.assertEqual(observe('BTC',rows,NOW)['events'],[])

    def test_stable_event_id_for_same_closed_event(self):
        self.assertEqual(observe('BTC',bars(),NOW)['events'],observe('BTC',bars(),NOW+1)['events'])

    def test_no_input_mutation_or_fabricated_flow(self):
        rows=bars();before=deepcopy(rows);r=observe('BTC',rows,NOW)
        self.assertEqual(rows,before)
        self.assertNotIn('cvd',str(r).lower())
