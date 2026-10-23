"""Durability and fail-closed unit tests with a synthetic on-disk state only."""
import copy
import json
from decimal import Decimal
import pytest
from desk.capital_journal import PaperCapitalJournal, _canonical
from desk.capital_manager import CapitalInvariantError


def sample():
    return {
        "main": {"cash": 1120.0, "positions": {}, "closed": [], "day": "2026-10-24"},
        "capital": {"revision": 0, "vault": {"balance": "0"}},
        "note": "untouched account state",
    }


def test_journal_commits_cash_and_vault_together(tmp_path):
    old=sample()
    (tmp_path/"state_v2.json").write_bytes(_canonical(old)+b"\n")
    new=copy.deepcopy(old)
    new["main"]["cash"]=1000.0
    new["capital"]["revision"]=1
    new["capital"]["vault"]["balance"]="120"
    journal=PaperCapitalJournal(str(tmp_path),"hawk")
    journal.commit(old,new,event_id="rollover:2026-10-24",expected_revision=0)
    assert journal.recover()==new
    assert json.loads((tmp_path/"state_v2.json").read_text())==new
    with pytest.raises(CapitalInvariantError):
        journal.commit(old,new,event_id="rollover:2026-10-24",expected_revision=0)


def test_journal_recovers_crash_after_durable_intent(tmp_path):
    old=sample()
    path=tmp_path/"state_v2.json"
    path.write_bytes(_canonical(old)+b"\n")
    new=copy.deepcopy(old)
    new["main"]["cash"]=1010.0
    new["capital"]["revision"]=1
    new["capital"]["vault"]["balance"]="110"
    j=PaperCapitalJournal(str(tmp_path),"bull")
    j.commit(old,new,event_id="rollover:A",expected_revision=0)
    # Synthetic crash: journal committed but state file is old. No live bot is touched.
    path.write_bytes(_canonical(old)+b"\n")
    assert j.recover()==new
    assert json.loads(path.read_text())==new


def test_journal_refuses_wrong_cash_conservation_and_trade_mutation(tmp_path):
    old=sample()
    (tmp_path/"state_v2.json").write_bytes(_canonical(old)+b"\n")
    j=PaperCapitalJournal(str(tmp_path),"hawk")
    new=copy.deepcopy(old)
    new["main"]["cash"]=1000
    new["capital"]["vault"]["balance"]="10"  # incorrect: cash decreased by 120
    new["capital"]["revision"]=1
    with pytest.raises(CapitalInvariantError):
        j.commit(old,new,event_id="x",expected_revision=0)
    assert not (tmp_path/"capital-v1-journal.jsonl").exists()
    new["capital"]["vault"]["balance"]="120"
    new["main"]["positions"]["BTC"]={"qty": 1}
    with pytest.raises(CapitalInvariantError):
        j.commit(old,new,event_id="x",expected_revision=0)


def test_journal_blocks_corruption_or_unrelated_state_change(tmp_path):
    old=sample()
    (tmp_path/"state_v2.json").write_bytes(_canonical(old)+b"\n")
    j=PaperCapitalJournal(str(tmp_path),"hawk")
    new=copy.deepcopy(old)
    new["main"]["cash"]=1000
    new["capital"]["vault"]["balance"]="120"
    new["capital"]["revision"]=1
    j.commit(old,new,event_id="x",expected_revision=0)
    (tmp_path/"capital-v1-journal.jsonl").write_text("garbage\n")
    with pytest.raises(CapitalInvariantError):
        j.recover()
