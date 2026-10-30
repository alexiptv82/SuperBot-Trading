from unittest.mock import Mock
from director.brain_scalp.service import BrainService

def test_owner_consumes_confirmation_only_after_protective_tick():
    service=BrainService.__new__(BrainService)
    service.clock=lambda:1800000000000
    service.account=Mock()
    service.account.brain.store.load.return_value={'positions':{}}
    service.feed=Mock();service.feed.poll.return_value=({}, {})
    service.trend_v11=Mock();service.trend_v11.poll.return_value={}
    service.structure_enabled=False
    service.operator=Mock()
    service.supervisor=Mock()
    order=[]
    def step(*a,**k):
        order.append('protect');return {'tick':'ok'}
    service.supervisor.step.side_effect=step
    service.operator_inbox=Mock()
    def consume(operator,now):
        assert operator is service.operator
        order.append('confirmation')
        raise OSError('temporary inbox issue')
    service.operator_inbox.consume.side_effect=consume
    service.last_teaching_recovery=1800000000000
    service.teaching_status='recorded'
    result=service.tick()
    assert order==['protect','confirmation']
    assert result['tick']=='ok'
    assert result['operator_confirmations']==[{'status':'inbox_unavailable'}]
