"""Synthetic tests, no network, no GitHub Actions, no bot connection."""
from __future__ import annotations

import csv
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from research.brain_counterfactual import ledger as L

T = 1_800_000_000_000  # divisible by 60_000


def journal(path: Path, extra=()):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE v3_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, portfolio_id TEXT, run_id TEXT, kind TEXT, occurred_at_ms INTEGER, payload_json TEXT)')
    events = [
        ('d1', 'brain_decision', T, dict(kind='OPEN', status='APPROVED', symbol='BTCUSDT', regime='EXPANSION')),
        ('d2', 'brain_decision', T + L.M1, dict(kind='NO_TRADE', status='RISK_REJECTED', symbol='ETHUSDT')),
        ('d3', 'brain_decision', T + 2*L.M1, dict(kind='NO_TRADE', status='DRAFT', symbol='BTCUSDT')),
        ('d4', 'brain_decision', T + 3*L.M1, dict(kind='OPEN', status='APPROVED', symbol='BTCUSDT')),
        ('o1', 'paper_open', T+3, dict(position_id='p1', decision_event_id='d1', symbol='BTCUSDT', side=-1)),
        ('c1', 'paper_close', T+10*L.M1, dict(position_id='p1', symbol='BTCUSDT', side=-1, realized_pnl='25.3')),
    ] + list(extra)
    for eid, kind, t, p in events:
        db.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,payload_json) VALUES (?, 'brain','run-1',?,?,?)", (eid, kind,t, json.dumps(p)))
    db.commit(); db.close()


def candles(path: Path, symbol='BTCUSDT', n=1600, behavior='up'):
    f = path / symbol / '1m.csv'
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open('w', newline='') as g:
        w = csv.writer(g); w.writerow(('open_time_ms','open','high','low','close','volume'))
        for i in range(n):
            if behavior == 'up' and i >= 1:
                o, hi, lo, cl = 100, 103, 99.9, 102
            else:
                o, hi, lo, cl = 100, 100.1, 99.9, 100
            w.writerow((T+i*L.M1,str(o),str(hi),str(lo),str(cl),'10'))
    return f


def test_ledger_counts_evidence_is_readonly(tmp_path):
    db = tmp_path/'journal.db'; journal(db)
    data = tmp_path/'candles'; candles(data); candles(data, 'ETHUSDT')
    prior = db.read_bytes()
    rows, summary = L.build(db, 'run-1', data)
    assert db.read_bytes() == prior
    assert summary['decision_count'] == 4
    assert summary['executed_decision_count'] == 1
    assert summary['approved_without_open_unknown_cause'] == 1
    assert summary['unknown_side_count'] == 3
    assert rows[0]['side_origin'] == 'verified_paper_open'
    assert rows[0]['observed_side'] == -1
    assert rows[0]['opening']['realized_pnl_usdt'] == '25.3'
    assert rows[1]['observed_side'] is None
    assert rows[1]['hypothetical_only']['0']['SHORT']['status'] == 'RESOLVED'
    assert rows[3]['opening_state'] == 'APPROVED_NOT_OPENED_CAUSE_UNKNOWN'
    assert summary['orders_sent'] == 0


def test_observer_unique_only_and_no_trade_no_side(tmp_path):
    db = tmp_path/'journal.db'; journal(db)
    p = tmp_path/'props.jsonl'
    records=[{'ts_ms': T+L.M1, 'symbol':'ETHUSDT','kind':'OPEN','side':-1},
             {'ts_ms': T+2*L.M1,'symbol':'BTCUSDT','kind':'OPEN','side':-1},
             {'ts_ms':T+3*L.M1,'symbol':'BTCUSDT','kind':'OPEN','side':1},
             {'ts_ms':T+3*L.M1,'symbol':'BTCUSDT','kind':'OPEN','side':-1}]
    p.write_text('\n'.join(json.dumps(x) for x in records)+'\n')
    dcs, _, _ = L.snapshot(db,'run-1')
    L.annotate(dcs,L.observer_map(p,dcs))
    assert dcs[1]['observed_side'] == -1
    assert dcs[1]['side_origin'] == 'unique_observer_ts_symbol'
    assert dcs[2]['observed_side'] is None  # model NO_TRADE
    assert dcs[3]['observed_side'] is None  # duplicate observer


def test_conflicting_observer_cannot_overwrite_executed_side(tmp_path):
    db=tmp_path/'journal.db'; journal(db)
    path=tmp_path/'prop.jsonl'; path.write_text(json.dumps({'ts_ms':T,'symbol':'BTCUSDT','kind':'OPEN','side':1})+'\n')
    dcs, _, _ = L.snapshot(db,'run-1')
    L.annotate(dcs,L.observer_map(path,dcs))
    assert dcs[0]['observed_side'] is None
    assert dcs[0]['side_conflict'] is True


def test_stop_vs_target_same_candle_favors_stop(tmp_path):
    # Both TP and SL touched within the very same closed minute.
    bars=[(T, Decimal('100'), Decimal('104'), Decimal('96'), Decimal('100'))]
    up=L.simulate(bars,T,1,0)
    down=L.simulate(bars,T,-1,0)
    assert up['status']=='RESOLVED' and up['reason']=='stop'
    assert down['reason']=='stop'
    assert Decimal(up['net_r']) < 0


def test_censored_not_fake_loss_or_win(tmp_path):
    f=candles(tmp_path/'candles', n=12, behavior='flat')
    b=L.minute_bars(f)
    assert L.simulate(b,T,1,0)['status']=='CENSORED'
    assert L.simulate(b,T+13*L.M1,1,0)['status']=='UNAVAILABLE'


def test_csv_gaps_invalid_and_no_future_data(tmp_path):
    f=candles(tmp_path/'candles', n=1600, behavior='flat')
    lines=f.read_text().splitlines(); f.write_text('\n'.join(lines[:100]+lines[101:])+'\n')
    bars=L.minute_bars(f)
    assert L.simulate(bars,T+98*L.M1,1,0)['status'] == 'CENSORED_GAP'
    f.write_text('open_time_ms,open,high,low,close,volume\n0,NaN,1,1,1,1\n')
    with pytest.raises(ValueError):
        L.minute_bars(f)


def test_orphan_open_is_not_falsely_attributed(tmp_path):
    db=tmp_path/'journal.db'; journal(db, [('o2','paper_open',T+5,dict(position_id='p2',decision_event_id='bad',symbol='BTCUSDT',side=-1))])
    dcs,_,orphan=L.snapshot(db,'run-1')
    assert len(orphan)==1
    assert dcs[0]['opening']['position_id']=='p1'


def test_main_refuses_output_into_journal_directory_and_overwrite(tmp_path,capsys):
    dbdir=tmp_path/'run'; dbdir.mkdir(); db=dbdir/'journal.db'; journal(db)
    data=tmp_path/'candles'; candles(data); candles(data,'ETHUSDT')
    args=['--journal',str(db),'--run-id','run-1','--candles-dir',str(data), '--out',str(dbdir/'out.jsonl')]
    with pytest.raises(SystemExit):L.main(args)
    args[-1]=str(tmp_path/'out.jsonl')
    L.main(args)
    assert (tmp_path/'out.jsonl').exists()
    with pytest.raises(FileExistsError):L.main(args)


def test_paired_summary_keeps_unknown_side_out_of_model_score(tmp_path):
    from research.brain_counterfactual.analysis import analyze
    db=tmp_path/'journal.db'; journal(db)
    folder=tmp_path/'candles'; candles(folder); candles(folder,'ETHUSDT')
    rows, _ = L.build(db,'run-1',folder)
    stats = analyze(rows,lag='1')
    assert stats['paired_n'] == 1
    assert stats['no_real_pnl_mixed_in'] is True
    assert stats['opening_state_counts']['APPROVED_NOT_OPENED_CAUSE_UNKNOWN'] == 1
    assert stats['model_minus_always_short_r'] == '0.0000'  # actual was short
