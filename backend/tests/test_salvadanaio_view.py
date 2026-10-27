from copy import deepcopy
import json
from pathlib import Path
import pytest
from salvadanaio_view import build_view
from desk_view import build_status


def sample():
    return {'capital':{'policy':'salvadanaio-only-v1','status':'READY',
                       'vault':{'balance':'100','pending':[{'remaining':'20'}]},
                       'deposits':[{'utc_day':'2026-10-27','amount':'70','kind':'rollover'},
                                   {'utc_day':'2026-10-27','amount':'30','kind':'pending_settled'}]}}


def test_readonly_balance_pending_and_daily_deposits():
    st=sample();old=deepcopy(st)
    v=build_view(st,{'exec_mode':'paper','age_s':2},1793100000)
    assert v['balance']=='100' and v['pending']=='20'
    assert v['deposited_today']=='100' and v['days']==[{'utc_day':'2026-10-27','amount':'100'}]
    assert st==old


@pytest.mark.parametrize('mode',['live',None])
def test_no_balance_in_live_or_unknown_mode(mode):
    v=build_view(sample(),{'exec_mode':mode},1793100000)
    assert not v['available'] and 'balance' not in v


@pytest.mark.parametrize('bad',['NaN','Infinity',True,'-10'])
def test_invalid_money_never_becomes_fake_zero(bad):
    st=sample();st['capital']['vault']['balance']=bad
    v=build_view(st,{'exec_mode':'paper'},1793100000)
    assert not v['available'] and 'balance' not in v


def test_offline_vault_remains_visible_as_last_saved_balance():
    v=build_view(sample(),{'exec_mode':'paper','age_s':999},1793100000)
    assert v['available'] and not v['bot_online'] and v['balance']=='100'


def test_status_counts_vault_in_total_pnl_not_operating_cash(tmp_path):
    st=sample();st['main']={'cash':900,'positions':{},'closed':[],
                           'limits':{'start_equity':1000,'daily_stop':.12},'day_start_equity':900}
    (tmp_path/'state_v2.json').write_text(json.dumps(st))
    (tmp_path/'heartbeat.json').write_text(json.dumps({'ts':1793100000,'exec_mode':'paper','reset_keeps_brain':True}))
    v=build_status(str(tmp_path),'hawk',now=1793100000)
    assert v['cash']==900 and v['equity']==900 and v['total_equity']==1000
    assert v['pnl_total']==0 and not v['can_reset'] and v['salvadanaio']['balance']=='100'
