"""CLI-level PAPER-only integration against synthetic temporary files.

No exchange/API calls. Exercises real save_state, bot command consumption,
journal recovery and UTC rollover with the existing CLI wiring.
"""
import copy
import json
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

from desk import cli
from desk.capital_runtime import initial_capital, rollover_today
from desk.capital_journal import PaperCapitalJournal, _canonical
from desk.capital_manager import CapitalInvariantError


KEY="123e4567-e89b-42d3-a456-426614174000"


def configure(monkeypatch,folder):
    monkeypatch.setenv("DESK_CAPITAL_V1","paper")
    monkeypatch.setenv("DESK_MODE","paper")
    monkeypatch.setattr(cli,"DATA_DIR",str(folder))
    monkeypatch.setattr(cli,"STATE_FILE",str(folder/"state_v2.json"))
    monkeypatch.setattr(cli,"LIVE",SimpleNamespace(_live=False))
    today=datetime.now(timezone.utc).date()
    yesterday=(today-timedelta(days=1)).strftime("%Y-%m-%d")
    account={
      "name":"main","cash":1120.0,"positions":{},"closed":[],"next_id":4,
      "day":yesterday,"day_start_equity":1000.0,
      "limits":{"start_equity":1000.0,"max_open":10,"max_margin_trade":100.0,
                "max_margin_total":1000.0,"daily_stop":0.12,"kill_equity":450.0}
    }
    base={"main":account,"run_no":7,"budget":{"spent":0.4},"lessons_day":yesterday}
    (folder/"state_v2.json").write_bytes(_canonical(base)+b"\n")
    return base


def test_real_cli_save_and_manual_bot_ack_is_one_transaction(tmp_path,monkeypatch):
    original=configure(monkeypatch,tmp_path)
    st=cli.load_state(cli.STATE_FILE)
    assert st==original
    today=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    st["capital"]=initial_capital(st["main"],today)
    # Simulate previous UTC day as reference for one validated rollover.
    st["capital"]["day"]["utc_day"]=original["main"]["day"]
    cli.save_state(st,cli.STATE_FILE)
    timestamp=int(datetime.strptime(today,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)+5
    assert rollover_today(st,timestamp,{})
    cli.save_state(st,cli.STATE_FILE)
    assert st["main"]["cash"]==1000
    assert st["capital"]["vault"]["balance"]=="120.00"
    version=st["capital"]["revision"]
    request={"kind":"manual_vault_withdraw","portfolio":cli.PORTFOLIO.name,
             "idempotency_key":KEY,"amount":"50.00","expected_revision":version}
    (tmp_path/"vault_transfer_request.json").write_text(json.dumps(request))
    assert cli._process_vault_request(st)
    assert not (tmp_path/"vault_transfer_request.json").exists()
    assert st["main"]["cash"]==1050
    assert st["capital"]["vault"]["balance"]=="70.00"
    assert st["capital"]["receipts"][KEY]["status"]=="completed"
    assert st["main"]["closed"]==original["main"]["closed"]
    assert st["run_no"]==original["run_no"]
    j=PaperCapitalJournal(str(tmp_path),cli.PORTFOLIO.name)
    assert j.recover()==st
    (tmp_path/"vault_transfer_request.json").write_text(json.dumps(request))
    assert cli._process_vault_request(st)  # duplicate after a simulated ACK loss
    assert st["main"]["cash"]==1050
    assert st["capital"]["vault"]["balance"]=="70.00"


def test_cli_recover_corrupt_journal_fails_closed(tmp_path,monkeypatch):
    configure(monkeypatch,tmp_path)
    st=cli.load_state(cli.STATE_FILE)
    st["capital"]=initial_capital(st["main"],
                                   datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    cli.save_state(st,cli.STATE_FILE)
    path=tmp_path/"capital-v1-journal.jsonl"
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(CapitalInvariantError):
        cli.load_state(cli.STATE_FILE)
    assert (tmp_path/"state_v2.json").exists()


def test_close_history_outbox_is_durable_idempotent(tmp_path,monkeypatch):
    configure(monkeypatch,tmp_path)
    st=cli.load_state(cli.STATE_FILE)
    st["capital"]=initial_capital(st["main"],
                                   datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    cli.save_state(st,cli.STATE_FILE)
    event={"id":3,"close_ms":int(time.time()*1000),"margin":70,"net":15,
           "symbol":"BTC","reason":"synthetic stop"}
    cli.record_close(st,event)
    assert len(st["capital"]["close_outbox"])==1
    cli.save_state(st,cli.STATE_FILE)
    assert st["capital"]["close_outbox"]==[]
    th=tmp_path/"trade_history.jsonl"
    lh=tmp_path/"learning_log.jsonl"
    assert len(th.read_text().splitlines())==1
    assert len(lh.read_text().splitlines())==1
    cli.record_close(st,event)  # a repeated delivery cannot duplicate sidecars
    cli.save_state(st,cli.STATE_FILE)
    assert len(th.read_text().splitlines())==1
    assert len(lh.read_text().splitlines())==1
    assert cli.load_state(cli.STATE_FILE)==st


def test_recovery_from_interrupted_temp_rename(tmp_path,monkeypatch):
    base=configure(monkeypatch,tmp_path)
    st=copy.deepcopy(base)
    st["capital"]=initial_capital(st["main"],
                                   datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    cli.save_state(st,cli.STATE_FILE)
    (tmp_path/"state_v2.json").write_bytes(_canonical(base)+b"\\n")
    temp=tmp_path/"state_v2.json.capital-v1-tmp"
    temp.write_text("{partial")
    assert cli.load_state(cli.STATE_FILE)==st
    assert not temp.exists()
