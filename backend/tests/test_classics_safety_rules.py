"""Safety invariants against the original frozen classics baseline, offline only."""
import os
import math
from unittest.mock import patch
from desk.engine import Limits, PaperAccount
from desk import cli


def test_dca_long_stop_never_moves_further_away():
    p=PaperAccount(Limits())
    pos,_=p.open('BTC',1,100,5,100.,95.,None,0,{})
    assert pos is not None
    old_stop=pos.sl
    out,msg=p.add_dca('BTC',94.,None,900000,{'BTC':97.})
    assert out is not None,msg
    assert out.sl==old_stop
    assert out.dca_count==1


def test_dca_short_stop_never_moves_further_away():
    p=PaperAccount(Limits())
    pos,msg=p.open('BTC',-1,100,5,100.,105.,None,0,{})
    assert pos is not None,msg
    old_stop=pos.sl
    out,msg=p.add_dca('BTC',106.,None,900000,{'BTC':103.})
    assert out is not None,msg
    assert out.sl==old_stop
    assert out.dca_count==1


def test_dca_reject_invalid_stop_without_cash_changes():
    p=PaperAccount(Limits())
    pos,_=p.open('BTC',1,100,5,100.,95.,None,0,{})
    before=(p.cash,pos.entry,pos.qty,pos.total_margin,pos.sl,pos.dca_count)
    out,msg=p.add_dca('BTC',float('nan'),None,900000,{'BTC':97.})
    assert out is None and 'stop' in msg
    assert (p.cash,pos.entry,pos.qty,pos.total_margin,pos.sl,pos.dca_count)==before


def test_impossible_short_tp_is_removed_not_recorded():
    p=PaperAccount(Limits())
    pos,msg=p.open('BTC',-1,100,5,100.,105.,-500.,0,{})
    assert pos is not None,msg
    assert pos.tp is None
    for impossible in (float('nan'),float('inf'),0.,-1.):
        fresh=PaperAccount(Limits())
        pos,msg=fresh.open('BTC',-1,100,5,100.,105.,impossible,0,{})
        assert pos is not None,msg
        assert pos.tp is None


def test_classics_rules_only_disables_provider_regardless_schedule(tmp_path):
    state={}
    original=cli.DATA_DIR
    cli.DATA_DIR=str(tmp_path)
    try:
        with patch.dict(os.environ,{'DESK_CLASSICS_AI_MODE':'rules_only'}):
            assert cli.apply_claude_schedule(state,1800000000000,'2026-10-30') is False
        with patch.dict(os.environ,{'DESK_CLASSICS_AI_MODE':'unexpected'}):
            assert cli.apply_claude_schedule(state,1800000000000,'2026-10-30') is False
        with patch.dict(os.environ,{'DESK_CLASSICS_AI_MODE':'scheduled'}):
            assert cli.apply_claude_schedule(state,1800000000000,'2026-10-30') is True
    finally:
        cli.DATA_DIR=original


def test_reset_does_not_erase_history_or_brain(tmp_path):
    from unittest.mock import patch
    data=tmp_path
    original=(cli.DATA_DIR,cli.STATE_FILE)
    try:
        cli.DATA_DIR=str(data)
        cli.STATE_FILE=str(data/'state.json')
        acc=PaperAccount(cli.PORTFOLIO.limits)
        state={'main':acc.to_dict(),'run_no':1,'budget':{'spent':0.1}}
        for n,data_text in [('trade_history.jsonl','{"symbol":"BTC","net":4.0}\\n'),
                            ('lessons.md','remember\\n'),('errors.md','warning\\n'),
                            ('learning_log.jsonl','{"event":"old"}\\n')]:
            (data/n).write_text(data_text)
        originals={n:(data/n).read_bytes() for n in (
            'trade_history.jsonl','lessons.md','errors.md','learning_log.jsonl')}
        (data/'pause.flag').touch()
        (data/'reset_portfolio.flag').write_text('{"clear_lessons":true}')
        assert cli._check_portfolio_reset_flag(state) is True
        assert state['run_no']==2 and state['paused'] is True
        for n,b in originals.items():
            assert (data/n).read_bytes()==b
    finally:
        cli.DATA_DIR,cli.STATE_FILE=original


def test_single_close_produces_unconfirmed_verified_learning_inbox():
    import json
    from backend.tests.test_desk import _sandbox,_state_with_two_positions,_frozen_clock,NOW
    from director.manual_teaching import ManualLessons
    with _sandbox() as (folder,calls):
        state=_state_with_two_positions()
        cli.fetch_candles=lambda sym,bar='15m',limit=3:[[NOW,101,103,100,102.0,1.0]]
        with _frozen_clock(NOW+1000):
            with open(os.path.join(folder,'close_position.flag'),'w') as f:
                json.dump({'symbols':['BTC'],'ts':NOW+1000},f)
            assert cli._check_close_position_flag(state)
        assert 'BTC' not in cli.make_account(state).positions
        q=ManualLessons(folder).pending()
        assert len(q)==1 and q[0]['source']=='manual_user'
        assert q[0]['bot']==cli.PORTFOLIO.name
        assert not os.path.exists(os.path.join(folder,'lessons.md'))
        assert any(row.get('ev')=='close' for row in
                   (json.loads(line) for line in open(os.path.join(folder,'learning_log.jsonl'))))
