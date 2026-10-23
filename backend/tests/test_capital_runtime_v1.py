"""Synthetic end-to-end capital PAPER accounting, UTC boundary and migration tests."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import copy
import json
import pytest
from desk.capital_runtime import (initial_capital, utc_day, boundary_prices,
                                  rollover_today, settle_after_close, withdraw_request,
                                  update_market_risk)
from desk.capital_journal import PaperCapitalJournal, _canonical
from desk.capital_manager import CapitalInvariantError, DayReference, risk_view


def millis(day):
    return int(datetime.strptime(day,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)


def state(cash=1000, positions=None, day="2026-10-23"):
    account={"name":"main","cash":cash,"positions":positions or {},"closed":[],
             "day":day,"day_start_equity":1000,"next_id":4,
             "limits":{"start_equity":1000,"daily_stop":0.12}}
    return {"main":account,"run_no":42,"budget":{"spent":0.5},
            "last_prices":{},"learning_reference":"UNTOUCHED"}


def migrate(st):
    st["capital"]=initial_capital(st["main"],"2026-10-23")
    assert st["capital"]["status"]=="ROLLOVER_PENDING"
    assert st["capital"]["vault"]["balance"]=="0"
    assert st["run_no"]==42 and st["learning_reference"]=="UNTOUCHED"
    return st


def position():
    return {"symbol":"BTC","margin":100,"total_margin":100,"side":1,
            "entry":100,"qty":10,"open_ms":millis("2026-10-23")-3600000}


def test_migration_preserves_existing_positions_history_and_budget():
    st=state(900,{"BTC":position()})
    old=copy.deepcopy(st)
    migrate(st)
    for key in old:
        assert st[key]==old[key]


def test_utc_00_boundary_with_open_position_creates_pending_not_cash():
    st=migrate(state(900,{"BTC":position()}))
    bar=[millis("2026-10-24")-900000,100,116,99,115,1000]
    changed=rollover_today(st,millis("2026-10-24")+2000,{"BTC":[bar]})
    assert changed and st["capital"]["status"]=="READY"
    assert st["capital"]["vault"]["balance"]=="0"
    assert Decimal(st["capital"]["vault"]["pending"][0]["remaining"])==150
    assert st["main"]["positions"]["BTC"]==position()
    assert st["main"]["cash"]==900
    assert st["capital"]["day"]["utc_day"]=="2026-10-24"
    assert st["capital"]["day"]["day_budget"]=="1000.00"


def test_missing_candle_or_two_day_gap_fails_closed():
    st=migrate(state(900,{"BTC":position()}))
    rollover_today(st,millis("2026-10-24")+2500,{})
    assert st["capital"]["status"]=="ROLLOVER_PENDING"
    assert st["capital"]["vault"]["balance"]=="0"
    st2=migrate(state(1000))
    rollover_today(st2,millis("2026-10-25"),{})
    assert st2["capital"]["status"]=="RECONCILIATION_REQUIRED"


def test_boundary_bar_must_be_exact_not_live_price():
    stamp=millis("2026-10-24")
    with pytest.raises(CapitalInvariantError):
        boundary_prices({"BTC":[[stamp,100,101,99,101,1]]},
                        {"BTC":position()},stamp)


def test_pnl_is_neutral_to_realized_vault_and_manual_injection():
    st=migrate(state(1120))
    rollover_today(st,millis("2026-10-24")+1,{})
    assert st["capital"]["vault"]["balance"]=="120.00"
    assert st["main"]["cash"]==1000
    assert st["capital"]["day"]["day_budget"]=="1000.00"
    key="123e4567-e89b-42d3-a456-426614174000"
    before=copy.deepcopy(st)
    req={"kind":"manual_vault_withdraw","portfolio":"hawk",
         "idempotency_key":key,"amount":"50","expected_revision":st["capital"]["revision"]}
    receipt=withdraw_request(st,req,bot="hawk")
    assert receipt["status"]=="completed"
    assert st["main"]["cash"]==1050 and st["capital"]["vault"]["balance"]=="70.00"
    assert risk_view(DayReference.from_dict(st["capital"]["day"]),1050).day_pnl==0
    receipt2=withdraw_request(st,req,bot="hawk")
    assert receipt2==receipt and st["main"]["cash"]==1050
    assert before["learning_reference"]==st["learning_reference"]


def test_pending_closes_plus120_then_journal_commits_trade_then_vault(tmp_path):
    st=migrate(state(900,{"BTC":position()}))
    path=tmp_path/"state_v2.json"
    before=copy.deepcopy(st)
    # Durable migration occurs as a single journaled snapshot.
    uninitialized={k:v for k,v in st.items() if k!="capital"}
    path.write_bytes(_canonical(uninitialized)+b"\n")
    j=PaperCapitalJournal(str(tmp_path),"hawk")
    st=j.commit_snapshot(st,event_id="capital:migrate:1")
    rollover_today(st,millis("2026-10-24")+1,
                   {"BTC":[[millis("2026-10-24")-900000,100,116,99,115,12]]})
    st=j.commit_snapshot(st,event_id="capital:rollover:2026-10-24")
    # Model the engine closing the trade: margin returned +120 net profit.
    st["main"]["positions"]={}
    st["main"]["cash"]=1120.0
    st["main"]["closed"]=[{"net":120,"id":3}]
    st=j.commit_snapshot(st,event_id="trade:close:3")
    assert settle_after_close(st,{},event_id="close:3")
    st=j.commit_snapshot(st,event_id="capital:settle:3")
    assert st["main"]["cash"]==1000
    assert st["capital"]["vault"]["balance"]=="120.00"
    assert j.recover()==st
    assert st["learning_reference"]=="UNTOUCHED"
    assert st["main"]["closed"][0]["net"]==120


def test_recovery_snapshot_intent_after_crash_and_refusal_of_corruption(tmp_path):
    path=tmp_path/"state_v2.json"
    st=state(1000)
    path.write_bytes(_canonical(st)+b"\n")
    migrated=migrate(copy.deepcopy(st))
    j=PaperCapitalJournal(str(tmp_path),"bull")
    after=j.commit_snapshot(migrated,event_id="capital:migrate:1")
    path.write_bytes(_canonical(st)+b"\n")  # simulate power loss after journal append
    assert j.recover()==after
    raw=(tmp_path/"capital-v1-journal.jsonl").read_bytes()
    (tmp_path/"capital-v1-journal.jsonl").write_bytes(raw[:-3])
    with pytest.raises(CapitalInvariantError):
        j.recover()


def test_daily_stop_latched_and_vault_topup_does_not_unlock():
    st=migrate(state(1000))
    rollover_today(st,millis("2026-10-24")+10,{})
    st["main"]["cash"]=800
    update_market_risk(st,{},now_ms=millis("2026-10-24")+12)
    assert st["capital"]["day"]["stop_latched"]
    st["capital"]["vault"]["balance"]="100"
    key="123e4567-e89b-42d3-a456-426614174001"
    req={"kind":"manual_vault_withdraw","portfolio":"hawk","idempotency_key":key,
         "amount":"50","expected_revision":st["capital"]["revision"]}
    withdraw_request(st,req,bot="hawk")
    assert DayReference.from_dict(st["capital"]["day"]).stop_latched
    assert risk_view(DayReference.from_dict(st["capital"]["day"]),850).stop_latched
