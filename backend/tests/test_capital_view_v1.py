"""Capital dashboard/queue tests. Synthetic temp files only; no user or VPS data."""
import json
from pathlib import Path
import pytest
from capital_view import (status, queue_manual_withdraw, transfer_status,
                          CapitalUnavailable)


KEY="123e4567-e89b-42d3-a456-426614174000"


def setup_account(root, *, enabled=True, balance="120"):
    state={
        "main":{"cash":900.0,"positions":{}},
        "capital":{"schema_version":1,"status":"READY","revision":3,
                   "day":{"utc_day":"2026-10-24","day_budget":"900",
                          "equity_at_boundary":"900","stop_latched":False},
                   "vault":{"balance":balance,"pending":[]},
                   "valuation":{"fresh":True,"unrealized":"0"},"receipts":{}}
    }
    hb={"version":"x123abc","capital_v1":enabled,"exec_mode":"paper"}
    (root/"state_v2.json").write_text(json.dumps(state))
    (root/"heartbeat.json").write_text(json.dumps(hb))


def test_fails_closed_without_bot_support(tmp_path):
    assert status(str(tmp_path),"hawk")["available"] is False
    setup_account(tmp_path,enabled=False)
    assert status(str(tmp_path),"hawk")["available"] is False
    with pytest.raises(CapitalUnavailable):
        queue_manual_withdraw(str(tmp_path),"hawk",
                             {"idempotency_key":KEY,"amount":"20","expected_revision":3})


def test_read_only_snapshot_and_bull_margin_percent(tmp_path):
    setup_account(tmp_path)
    st=status(str(tmp_path),"bull")
    assert float(st["operating_equity"])==900
    assert st["vault_balance"]=="120"
    assert float(st["total_equity"])==1020
    assert st["position_cap_pct"]=="25"
    assert st["day_budget"]=="900"
    assert st["can_withdraw"]


def test_request_queues_but_never_modifies_money(tmp_path,monkeypatch):
    setup_account(tmp_path)
    monkeypatch.setenv("DESK_MODE","paper")
    request={"idempotency_key":KEY,"amount":"50.00","expected_revision":3}
    a=queue_manual_withdraw(str(tmp_path),"hawk",request)
    assert a["queued"] and a["status"]=="pending"
    assert transfer_status(str(tmp_path),KEY)["status"]=="pending"
    assert status(str(tmp_path),"hawk")["vault_balance"]=="120"
    b=queue_manual_withdraw(str(tmp_path),"hawk",request)
    assert b==a
    with pytest.raises(CapitalUnavailable):
        queue_manual_withdraw(str(tmp_path),"hawk",
            {"idempotency_key":"123e4567-e89b-42d3-a456-426614174001","amount":"40",
             "expected_revision":3})


@pytest.mark.parametrize("amount",[-1,0,"NaN","Infinity","1.001","200","garbage"])
def test_bad_amount_rejected(tmp_path,monkeypatch,amount):
    setup_account(tmp_path)
    monkeypatch.setenv("DESK_MODE","paper")
    with pytest.raises(CapitalUnavailable):
        queue_manual_withdraw(str(tmp_path),"hawk",
            {"idempotency_key":KEY,"amount":amount,"expected_revision":3})


def test_live_mode_is_unsafe_even_with_capital_v1(tmp_path,monkeypatch):
    setup_account(tmp_path)
    monkeypatch.setenv("DESK_MODE","live")
    with pytest.raises(CapitalUnavailable):
        queue_manual_withdraw(str(tmp_path),"hawk",
            {"idempotency_key":KEY,"amount":"20","expected_revision":3})


def test_stale_revision_cannot_queue(tmp_path):
    setup_account(tmp_path)
    with pytest.raises(CapitalUnavailable):
        queue_manual_withdraw(str(tmp_path),"hawk",
            {"idempotency_key":KEY,"amount":"20","expected_revision":2})
    assert not (tmp_path/"vault_transfer_request.json").exists()


def test_stale_open_position_quote_disables_withdrawal(tmp_path):
    setup_account(tmp_path)
    source=tmp_path/"state_v2.json"
    st=json.loads(source.read_text())
    st["main"]["positions"]={"BTC":{"total_margin":100,"entry":100,"qty":10,"side":1}}
    st["main"]["cash"]=800
    st["capital"]["valuation"]={"fresh":True,"unrealized":"25","valuation_ms":1}
    source.write_text(json.dumps(st))
    result=status(str(tmp_path),"hawk")
    assert result["valuation_fresh"] is False
    assert result["operating_equity"] is None
    assert result["can_withdraw"] is False


def test_existing_desk_status_uses_v1_daily_risk_not_legacy_12pct(tmp_path):
    import desk_view as dv
    setup_account(tmp_path)
    source=tmp_path/"state_v2.json"
    st=json.loads(source.read_text())
    st["main"].update(cash=850,day_start_equity=1000,limits={
        "start_equity":1000,"daily_stop":0.12,"kill_equity":450,
        "max_margin_trade":350,"max_open":6})
    st["capital"]["day"].update(day_budget="1000",
         equity_at_boundary="1000",net_manual_and_vault_flow="0",
         stop_latched=False)
    source.write_text(json.dumps(st))
    hb=tmp_path/"heartbeat.json"
    hbdata=json.loads(hb.read_text())
    hbdata.update(capital_v1=True,exec_mode="paper",ts=9999999999)
    hb.write_text(json.dumps(hbdata))
    status=dv.build_status(str(tmp_path),"bull",now=9999999999)
    assert status["capital_v1"] is True
    assert status["halt"] is None  # -15% is not the newly approved 20% stop
    assert status["max_margin_trade"]==250
    assert status["can_reset"] is False
    assert status["vault_balance"]==120
    assert status["day_pnl"]==-150
    st["main"]["cash"]=790
    source.write_text(json.dumps(st))
    next_status=dv.build_status(str(tmp_path),"bull",now=9999999999)
    assert next_status["halt"]=="stop giornaliero raggiunto"
