from unittest.mock import Mock
from director.brain_scalp.service import BrainService


def test_teaching_retries_after_protection_without_failing_tick():
    now=[1800000000000]
    order=[]
    s=BrainService.__new__(BrainService)
    s.clock=lambda:now[0]
    s.account=Mock()
    s.account.brain.store.load.return_value={'positions':{}}
    s.feed=Mock();s.feed.poll.return_value=({}, {})
    s.trend_v11=Mock();s.trend_v11.poll.return_value={}
    s.structure_enabled=False
    s.last_teaching_recovery=None;s.teaching_status='pending_recovery'
    s.supervisor=Mock()
    def protect(*args,**kwargs):
        order.append('protect');return {'tick':'ok'}
    s.supervisor.step.side_effect=protect
    s.operator=Mock()
    def fail():
        order.append('recover');raise OSError('temporary')
    s.operator.sync.side_effect=fail
    assert s.tick()=={'tick':'ok','teaching_status':'pending_recovery'}
    assert order==['protect','recover']
    now[0]+=5000
    assert s.tick()['teaching_status']=='pending_recovery'
    assert s.operator.sync.call_count==1
    now[0]+=60000;s.operator.sync.side_effect=None
    assert s.tick()['teaching_status']=='recorded'
    assert s.operator.sync.call_count==2
