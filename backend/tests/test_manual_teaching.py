"""Paper-only manual teaching contract: no orders, no exchange, no auto-learning."""
import pytest
from director.manual_teaching import ManualLessons,batches,telegram_review,parse_review_command,REPLY_MS

NOW=1800000000000


def event(bot='hawk',symbol='ETH',position_id='42',closed=NOW,net=12.5,side=-1):
    return {'kind':'trade_closed','source':'manual_user','paper':True,
            'account_id':f'paper-{bot}', 'bot':bot,
            'position_id':position_id,'symbol':symbol,'side':side,
            'entry':100.,'close_price':98.,'leverage':5.,'margin':100.,
            'pnl_usd':net,'open_ms':closed-60000,'close_ms':closed}


def test_unverified_disappearance_or_stop_is_not_a_lesson(tmp_path):
    inbox=ManualLessons(tmp_path/'bot')
    bad=event();bad['source']='physical_protection'
    with pytest.raises(ValueError,match='unverified_manual_close'):
        inbox.register(event())
    with pytest.raises(ValueError,match='not_manual_paper_close'):
        inbox.register(bad,verified=True)
    wrong=event();wrong['paper']=False
    with pytest.raises(ValueError,match='not_manual_paper_close'):
        inbox.register(wrong,verified=True)
    assert not (tmp_path/'bot'/'learning_log.jsonl').exists()


def test_yes_appends_exactly_once_and_does_not_change_trading_logic(tmp_path):
    inbox=ManualLessons(tmp_path/'hawk')
    e=event()
    first=inbox.register(e,verified=True)
    assert first['new'] is True
    assert inbox.register(e,verified=True)['new'] is False
    waiting=inbox.pending()
    assert len(waiting)==1
    assert inbox.decide([first['event_id']],'yes',NOW+1000)==1
    assert not inbox.pending()
    logged=inbox._rows(inbox.learning)
    assert len(logged)==1 and logged[0]['user_intent']=='profit_ok_free_slot'
    assert logged[0]['training_applied'] is False
    assert 'Osservazione, non regola operativa' in inbox.lessons.read_text()
    assert inbox.lessons.read_text().count('manual-id:')==1
    with pytest.raises(ValueError,match='unavailable_manual_event'):
        inbox.decide([first['event_id']],'yes',NOW+2000)
    # Crash/restart replay repairs nothing twice.
    again=ManualLessons(tmp_path/'hawk')
    assert not again.pending()
    assert len(again._rows(again.learning))==1
    assert again.lessons.read_text().count('manual-id:')==1


def test_no_and_expiration_preserve_raw_only(tmp_path):
    inbox=ManualLessons(tmp_path/'bull')
    a=inbox.register(event(bot='bull',symbol='BTC',position_id='1'),verified=True)
    b=inbox.register(event(bot='bull',symbol='SOL',position_id='2'),verified=True)
    inbox.decide([a['event_id']],'no',NOW+20)
    assert inbox.expire(NOW+REPLY_MS+1)==1
    assert inbox._rows(inbox.learning)[0]['user_intent']=='unknown'
    assert inbox._rows(inbox.learning)[1]['user_intent']=='no_response'
    assert not inbox.lessons.exists()
    assert inbox.expire(NOW+REPLY_MS+2)==0


def test_batch_telegram_reply_scoped_to_correct_events(tmp_path):
    h=ManualLessons(tmp_path/'hawk');b=ManualLessons(tmp_path/'bull')
    h.register(event(symbol='ETH',position_id='a'),verified=True)
    b.register(event(bot='bull',symbol='BTC',position_id='b',closed=NOW+10000),verified=True)
    pending=h.pending()+b.pending()
    groups=batches(pending)
    assert len(groups)==1 and len(groups[0]['ids'])==2
    msg=telegram_review(groups[0])
    assert 'HAWK+BULL' in msg and 'PAPER' in msg
    assert 'ETH' in msg and 'BTC' in msg and '/insegna_si' in msg
    decision,ids=parse_review_command('/insegna_si '+groups[0]['group_id'],pending)
    assert decision=='yes' and ids==groups[0]['ids']
    assert parse_review_command('/insegna_no',pending)[0]=='no'
    h.register(event(symbol='DOGE',position_id='c',closed=NOW+400000),verified=True)
    with pytest.raises(ValueError,match='ambiguous_or_missing_review'):
        parse_review_command('/insegna_si',h.pending()+b.pending())


def test_profit_never_inferred_from_losing_trade(tmp_path):
    inbox=ManualLessons(tmp_path/'hawk')
    e=inbox.register(event(net=-5.),verified=True)
    inbox.decide([e['event_id']],'yes',NOW+1)
    assert inbox._rows(inbox.learning)[0]['user_intent']=='manual_close_other'
    assert not inbox.lessons.exists()


def test_expired_review_cannot_be_replayed(tmp_path):
    inbox=ManualLessons(tmp_path/'brain')
    e=inbox.register(event(bot='brain'),verified=True)
    with pytest.raises(ValueError,match='manual_response_expired'):
        inbox.decide([e['event_id']],'yes',NOW+REPLY_MS+1)
    assert inbox.expire(NOW+REPLY_MS+1)==1
    assert inbox._rows(inbox.learning)[0]['user_intent']=='no_response'
