"""Falco/Toro PAPER teaching bridge, gated by an authoritative saved close.

This module never executes trades and does NOT infer manual closures from
Bitget external positions. Only the existing 13/10 close-all writer supplies
its own completed close record after the updated wallet state was saved.
"""
import json
from pathlib import Path

from director.manual_teaching import ManualLessons,batches,telegram_review,parse_review_command


def to_attested_close(record,portfolio,run_no,*,persisted=False,remaining=None):
    if (persisted is not True or portfolio not in ('hawk','bull') or
        type(run_no)!=int or run_no<=0 or not isinstance(record,dict) or
        record.get('why')!='chiusura manuale' or record.get('partial') is True or
        record.get('account') not in (portfolio,'main') or not isinstance(remaining,dict) or
        record.get('symbol') in remaining):
        raise ValueError('unverified_classical_manual_close')
    return {
        'kind':'trade_closed','source':'manual_user','paper':True,
        'bot':portfolio,'account_id':f'desk-{portfolio}-paper-run-{run_no}',
        'position_id':record['id'],'symbol':record['symbol'],
        'side':record['side'],'entry':record['entry'],
        'close_price':record['exit'],'leverage':record['leverage'],
        'margin':record['margin'],'pnl_usd':record['net'],
        'open_ms':record['open_ms'],'close_ms':record['close_ms'],
    }


def record_verified_manual_closures(data_dir,portfolio,run_no,records,
                                    *,persisted=False,remaining=None):
    """Best effort only after account was saved. Never corrupt old histories.

    A non-attested record is ignored; user confirmations must still be
    processed separately. No learning happens automatically.
    """
    if persisted is not True or not isinstance(records,list):
        raise ValueError('wallet_not_persisted')
    store=ManualLessons(data_dir)
    ids=[]
    for record in records:
        event=to_attested_close(record,portfolio,run_no,persisted=True,
                                remaining=remaining)
        ids.append(store.register(event,verified=True)['event_id'])
    return ids


def review_groups(data_dir):
    return batches(ManualLessons(data_dir).pending())


def review_messages(data_dir):
    return [telegram_review(x) for x in review_groups(data_dir)]


def answer_review(data_dir,text,now_ms):
    store=ManualLessons(data_dir)
    choice,ids=parse_review_command(text,store.pending())
    return store.decide(ids,choice,now_ms)
