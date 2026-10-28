from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest

from desk.engine import PaperAccount, Limits
from desk.salvadanaio import activate, rollover_today, settle_after_close, POLICY
from desk.vault_manager import VaultState


def ms(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)


def state(cash=1000):
    a=PaperAccount(Limits(daily_stop=.12))
    a.cash=cash;a.day='2026-10-27';a.day_start_equity=1000
    return {'main':a.to_dict(),'run_no':7,'budget':{'spent':.21},'last_call_ms':123,'memo':'keep'}


@pytest.mark.parametrize('cash,expected_cash,expected_vault',[(1100,1000,100),(950,950,0),(900,900,0),(1000,1000,0),(1100.123456789,1000.003456789,100.12)])
def test_rollover_profit_and_loss_without_refill(cash,expected_cash,expected_vault):
    st=state(cash);before=deepcopy(st);activate(st,ms('2026-10-27T12:00'))
    assert st['main']==before['main'] and st['budget']==before['budget']
    assert rollover_today(st,ms('2026-10-28T00:00'),{})
    assert st['main']['cash']==pytest.approx(expected_cash)
    assert Decimal(st['capital']['vault']['balance'])==Decimal(str(expected_vault))
    assert st['main']['day_start_equity']==pytest.approx(expected_cash)
    assert st['run_no']==7 and st['budget']==before['budget']
    copy=deepcopy(st);assert not rollover_today(st,ms('2026-10-28T00:01'),{});assert st==copy


def test_existing_vault_and_all_trade_state_survive_activation():
    st=state(900);st['capital']={'schema_version':1,'status':'ROLLOVER_PENDING','revision':8,
                                'vault':{'balance':'73.25','pending':[]},'old_key':'preserve'}
    before=deepcopy(st);assert activate(st,ms('2026-10-27T12:00'))
    assert st['main']==before['main'] and st['budget']==before['budget']
    assert st['capital']['vault']['balance']=='73.25' and st['capital']['old_key']=='preserve'
    assert not activate(st,ms('2026-10-27T13:00'))


def test_fees_already_reduce_distributable_profit():
    st=state(1009);st['main']['closed']=[{'close_ms':ms('2026-10-27T23:59'),'gross':12,'fees':3,'funding':0,'net':9}]
    activate(st,ms('2026-10-27T12:00'));rollover_today(st,ms('2026-10-28T00:00'),{})
    assert st['capital']['vault']['balance']=='9.00'
    assert st['capital']['deposits'][0]['net_realized']=='9.00'


def test_unrealized_profit_is_pending_not_protected_cash_and_settles_once():
    st=state(900);a=PaperAccount.from_dict(st['main']);a.cash=1000
    p,_=a.open('BTC',1,100,10,100,98,120,ms('2026-10-27T22:00'),{})
    st['main']=a.to_dict();activate(st,ms('2026-10-27T23:00'))
    original=deepcopy(st['main']['positions'])
    bar=[ms('2026-10-27T23:45'),100,111,99,110,5]
    rollover_today(st,ms('2026-10-28T00:00'),{'BTC':[bar]})
    assert st['capital']['vault']['balance']=='0'
    assert st['main']['positions']==original
    assert VaultState.from_dict(st['capital']['vault']).pending_total>0
    # Close the position as a separate account transaction before settling.
    a=PaperAccount.from_dict(st['main']);rec=a.close('BTC',110,ms('2026-10-28T00:03'),'test')
    st['main']=a.to_dict();reference=st['main']['day_start_equity']
    stamp=ms('2026-10-28T00:04')
    assert settle_after_close(st,{},event_id=f'settle:cycle:{stamp}')
    assert st['main']['cash']==pytest.approx(1000,abs=.011)
    assert st['main']['day_start_equity']<reference
    old=deepcopy(st);assert not settle_after_close(st,{},event_id=f'settle:cycle:{stamp}');assert st==old


def test_missing_boundary_retries_across_restart_without_changing_positions():
    st=state();a=PaperAccount.from_dict(st['main'])
    p,_=a.open('BTC',-1,100,10,100,102,95,ms('2026-10-27T22:00'),{})
    st['main']=a.to_dict();activate(st,ms('2026-10-27T23:00'))
    rollover_today(st,ms('2026-10-28T00:00'),{})
    assert st['capital']['status']=='ROLLOVER_PENDING'
    st=json.loads(json.dumps(st))
    bar=[ms('2026-10-27T23:45'),100,101,99,100,5]
    rollover_today(st,ms('2026-10-28T00:01'),{'BTC':[bar]})
    assert st['capital']['status']=='READY'


def test_gap_fails_closed_and_preserves_cash_vault():
    st=state(1100);activate(st,ms('2026-10-27T12:00'))
    rollover_today(st,ms('2026-10-29T00:01'),{})
    assert st['capital']['status']=='RECONCILIATION_REQUIRED'
    assert st['main']['cash']==1100 and st['capital']['vault']['balance']=='0'


def test_fixed_baseline_config_not_v1_percentages_or_regime(monkeypatch):
    from desk import cli
    monkeypatch.setenv('DESK_CAPITAL_V1','paper')
    h,b=cli._make_hawk_config(),cli._make_bull_config()
    assert h.limits.max_open==10 and b.limits.max_open==3
    assert h.limits.daily_stop==b.limits.daily_stop==.12
    assert cli.tier_entry_score('ADA')==70 and cli.tier_entry_score('BTC')==60
    assert not b.refuse_below_min_margin and b.max_leverage is None
    st=state(1000);activate(st,ms('2026-10-27T12:00'))
    a=cli.make_account(st)
    assert a._capital_reference is None and a._capital_day_budget is None
    assert a.limits.max_margin_trade==250
    assert a.limits.min_initial_margin==100 and a.limits.min_initial_leverage==10


def test_journal_recovery_and_fractional_cash_conservation(tmp_path,monkeypatch):
    from desk import cli
    monkeypatch.setattr(cli,'DATA_DIR',str(tmp_path));monkeypatch.setattr(cli,'STATE_FILE',str(tmp_path/'state_v2.json'))
    monkeypatch.setattr(cli,'_CAPITAL_JOURNAL_INSTANCE',None)
    st=state(1100.123456789);Path(cli.STATE_FILE).write_text(json.dumps(st))
    activate(st,ms('2026-10-27T12:00'));cli.save_state(st,cli.STATE_FILE)
    rollover_today(st,ms('2026-10-28T00:00'),{});cli.save_state(st,cli.STATE_FILE)
    recovered=cli.load_state(cli.STATE_FILE)
    assert recovered==st and recovered['capital']['vault']['balance']=='100.12'
    assert (tmp_path/'salvadanaio-journal.jsonl').exists()
    assert not (tmp_path/'capital-v1-journal.jsonl').exists()
    # Simulate a crash after intent fsync but before replace(state).
    import desk.capital_journal as journal
    original=journal._replace_json
    monkeypatch.setattr(journal,'_replace_json',lambda *args: (_ for _ in ()).throw(OSError('crash')))
    future=deepcopy(st);future['last_call_ms']=456
    with pytest.raises(OSError):cli.save_state(future,cli.STATE_FILE)
    monkeypatch.setattr(journal,'_replace_json',original)
    monkeypatch.setattr(cli,'_CAPITAL_JOURNAL_INSTANCE',None)
    assert cli.load_state(cli.STATE_FILE)['last_call_ms']==456


def test_same_day_loss_never_uses_existing_vault():
    st=state(900);activate(st,ms('2026-10-27T12:00'))
    st['capital']['vault']['balance']='100'
    rollover_today(st,ms('2026-10-28T00:00'),{})
    assert st['main']['cash']==900 and st['capital']['vault']['balance']=='100'


def test_cycle_protective_close_before_midnight_sweeps_net_once_and_preserves_memory(tmp_path,monkeypatch):
    from desk import cli
    import numpy as np
    now=ms('2026-10-28T00:01')
    monkeypatch.setattr(cli,'DATA_DIR',str(tmp_path));monkeypatch.setattr(cli,'STATE_FILE',str(tmp_path/'state_v2.json'))
    monkeypatch.setattr(cli,'_CAPITAL_JOURNAL_INSTANCE',None)
    monkeypatch.setattr(cli,'SYMBOLS',['BTC'])
    monkeypatch.setattr(cli.time,'sleep',lambda _:None)
    monkeypatch.setattr(cli,'read_symbol',lambda *a,**k:None)
    monkeypatch.setattr(cli,'four_hour_bars',lambda *a:None)
    monkeypatch.setattr(cli,'apply_claude_schedule',lambda *a:False)
    monkeypatch.setattr(cli,'call_claude',lambda *a,**k:pytest.fail('no model call expected'))
    for name in ['notify_close','notify_daily_report','notify_halt','notify_split']:
        monkeypatch.setattr(cli,name,lambda *a,**k:None)
    # A short closes at TP on the bar ending at UTC midnight.
    # Seed a historical 10x position before applying current limits.
    a=PaperAccount();a.day='2026-10-27';a.day_start_equity=1000
    p,_=a.open('BTC',-1,100,10,100,102,98,ms('2026-10-27T23:00'),{},source='rules')
    st={'main':a.to_dict(),'run_no':7,'last_ctx_ts':now,'budget':{'spent':.21},'memo':'keep'}
    Path(cli.STATE_FILE).write_text(json.dumps(st))
    (tmp_path/'lessons.md').write_bytes(b'keep lessons\n');(tmp_path/'errors.md').write_bytes(b'keep errors\n')
    (tmp_path/'trade_history.jsonl').write_text('{"symbol":"OLD","net":1}\n')
    activate(st,ms('2026-10-27T23:01'));cli.save_state(st,cli.STATE_FILE)
    bars=[[now//900000*900000-900000,100,100.1,97.5,98,5],
          [now//900000*900000,98,98.1,97.9,98,1]]
    monkeypatch.setattr(cli,'fetch_candles',lambda *a,**k:bars)
    cli.run_cycle(st,now)
    balance=Decimal(st['capital']['vault']['balance'])
    assert balance>0 and st['main']['cash']==pytest.approx(1000,abs=.011)
    assert len(st['main']['closed'])==1 and not st['main']['positions']
    assert balance==Decimal(str(st['main']['closed'][0]['net'])).quantize(Decimal('.01'),rounding='ROUND_DOWN')
    assert (tmp_path/'lessons.md').read_bytes()==b'keep lessons\n'
    assert (tmp_path/'errors.md').read_bytes()==b'keep errors\n'
    before=(tmp_path/'trade_history.jsonl').read_text();assert before.startswith('{"symbol":"OLD","net":1}\n')
    cli.run_cycle(st,now+1000)
    assert Decimal(st['capital']['vault']['balance'])==balance
    assert (tmp_path/'trade_history.jsonl').read_text()==before
    assert st['memo']=='keep' and st['run_no']==7


def test_long_short_management_uses_own_side_score():
    from types import SimpleNamespace
    from desk import brain
    r=SimpleNamespace(symbol='BTC',long_score=75,short_score=20,score=75,side=1,trade_type='scalp',sl_pct=.01,tp_pct=.018,why=[])
    pos={'symbol':'BTC','side':1}
    decisions=brain.rules_decisions([r],[pos],{'BTC'},60)
    assert decisions==[]
    pos['side']=-1
    assert decisions!=brain.rules_decisions([r],[pos],{'BTC'},60)
    assert brain.rules_decisions([r],[],set(),60)[0]['action']=='open_long'
    r.long_score=20;r.short_score=75;r.side=-1
    assert brain.rules_decisions([r],[],set(),60)[0]['action']=='open_short'


def test_flat_indicators_do_not_create_a_short_or_long_bias(monkeypatch):
    from types import SimpleNamespace
    from desk import signals
    import numpy as np
    monkeypatch.setattr(signals,'get_seasonal',lambda *a:SimpleNamespace(long_bonus=0,short_bonus=0,note='neutral'))
    arr=np.array([[i*900000,100,100,100,100,1] for i in range(1000)])
    four=np.array([[i*14400000,100,100,100,100,1] for i in range(250)])
    r=signals.read_symbol('BTC',arr,four_hour=four)
    assert r.side==0 and r.long_score==r.short_score==0
    assert signals.rsi(np.ones(100))==50


def test_first_install_activates_vault_but_existing_empty_state_is_rejected(tmp_path, monkeypatch):
    from desk import cli
    monkeypatch.setattr(cli, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(cli, 'STATE_FILE', str(tmp_path / 'state_v2.json'))
    monkeypatch.setattr(cli, '_CAPITAL_JOURNAL_INSTANCE', None)
    monkeypatch.setattr(cli, '_acquire_capital_writer_lock', lambda: None)
    monkeypatch.setattr(cli, 'ensure_live_since', lambda: None)
    monkeypatch.setattr(cli, 'process_flags', lambda state: None)
    monkeypatch.setattr(cli, 'drain_reason', lambda now: None)
    monkeypatch.setattr(cli.sys, 'argv', ['desk', '--once'])
    seen = []
    monkeypatch.setattr(cli, 'iteration', lambda state, **kw: seen.append(deepcopy(state)))
    cli.main()
    assert seen[0]['capital']['policy'] == 'salvadanaio-only-v1'
    assert seen[0]['main']['cash'] == 1000
    assert float(cli.load_state(cli.STATE_FILE)['capital']['vault']['balance']) == 0
    # An existing empty file is not a new installation, even if valid JSON.
    monkeypatch.setattr(cli, 'load_state', lambda path: {})
    with pytest.raises(ValueError, match='Empty existing account'):
        cli.main()
