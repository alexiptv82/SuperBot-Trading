"""Offline regression of DeepSeek credit monitoring. No external API calls."""
from decimal import Decimal
import json
import urllib.error

from director.brain_free.balance import (
    check_balance, low_balance_threshold, credit_alert, unavailable_message,
)
from director.brain_free.runtime import Runtime

NOW=1800000000000


class Response:
    def __init__(self, body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read(self,n):return self.body[:n]


def test_exact_provider_attribution_in_telegram_text():
    assert "DeepSeek non disponibile: credito esaurito (balance)" in unavailable_message("balance")
    assert "limite di chiamate (rate limit)" in unavailable_message("rate")
    assert "chiave API non valida (auth)" in unavailable_message("auth")
    assert "provider_http" in unavailable_message("provider_http")
    assert "segreto" not in unavailable_message("segreto\\nunsafe")


def test_api_balance_get_has_bearer_but_never_returns_key():
    requests=[]
    def fake(req,timeout):
        requests.append((req,timeout))
        return Response(json.dumps({"is_available":True,"balance_infos":[
            {"currency":"CNY","total_balance":"9.12"},
            {"currency":"USD","total_balance":"1.30"},
        ]}).encode())
    v=check_balance("synthetic-secret",opener=fake)
    assert v["status"]=="ok"
    assert v["usd_balance"]==Decimal("1.30")
    assert v["is_available"] is True
    assert requests[0][0].full_url=="https://api.deepseek.com/user/balance"
    assert requests[0][0].get_method()=="GET"
    assert requests[0][0].get_header("Authorization")=="Bearer synthetic-secret"
    assert requests[0][1]<=8
    assert "synthetic-secret" not in str(v)
    assert credit_alert(v,Decimal("2")) is not None
    assert credit_alert(v,Decimal("1")) is None


def test_currency_mismatch_is_not_a_fake_usd_alert():
    result=check_balance("key",opener=lambda *_a,**_kw:Response(
        b'{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"0.02"}]}'))
    assert result["status"]=="ok" and result["usd_balance"] is None
    assert credit_alert(result,Decimal("2")) is None


def test_invalid_response_network_and_threshold_fail_open():
    for payload in (b'{"is_available":"yes","balance_infos":[]}',
                    b'{"is_available":true,"balance_infos":[{"currency":"USD","total_balance":"NaN"}]}',
                    b'{"is_available":true,"balance_infos":[{"currency":"USD","total_balance":"1"},{"currency":"USD","total_balance":"2"}]}',
                    b'invalid json'):
        result=check_balance("fake",opener=lambda *_a,**_kw:Response(payload))
        assert result=={"status":"unavailable"}
        assert credit_alert(result,Decimal("2")) is None
    assert check_balance("",opener=lambda *_a,**_kw:(_ for _ in ()).throw(AssertionError())) == {"status":"missing_key"}
    assert check_balance("fake",opener=lambda *_a,**_kw:(_ for _ in ()).throw(TimeoutError()))=={"status":"unavailable"}
    for raw in ("0","NaN","-1","garbage"):
        try:low_balance_threshold(raw)
        except ValueError:pass
        else:raise AssertionError(raw)


def test_unavailable_credit_warns_even_without_usd():
    v={"status":"ok","is_available":False,"usd_balance":None}
    assert "non disponibile" in credit_alert(v,Decimal("2"))


def test_runtime_low_credit_durable_and_throttled(tmp_path):
    from backend.tests.test_brain_free import market,contract
    calls=[]
    def balance(_key):
        calls.append(1)
        return {"status":"ok","is_available":True,"usd_balance":Decimal("0.40")}
    # No provider HTTP: model response and balance read are synthetic.
    r=Runtime(tmp_path/"brain",True,api_key="synthetic",
              model_call=lambda *args:{"error":"balance","usage":None},
              balance_call=balance)
    try:
        r.activate(NOW,market())
        r.step(market(NOW),{"BTC":contract()},{},NOW)
        r.balance_future.result(timeout=3)
        r.step(market(NOW+5000),{"BTC":contract()},{},NOW+5000)
        rows=[x[0] for x in r.store.db.execute("SELECT body FROM outbox").fetchall()]
        assert any("Credito DeepSeek basso:" in x for x in rows)
        assert any("DeepSeek non disponibile: credito esaurito" in x for x in rows)
        assert len([x for x in rows if "Credito DeepSeek basso:" in x])==1
        assert len(calls)==1
        state=r.store.load()
        assert state["deepseek_credit_monitor"]["last_alert_ms"]==NOW+5000
        state["deepseek_credit_monitor"]["calls_since_check"]=50
        r.store.commit(state)
        r._poll_balance(NOW+10000)
        r.balance_future.result(timeout=3)
        r._poll_balance(NOW+15000)
        rows=[x[0] for x in r.store.db.execute("SELECT body FROM outbox").fetchall()]
        assert len([x for x in rows if "Credito DeepSeek basso:" in x])==1
        assert len(calls)==2
    finally:r.close()


def test_failed_monitor_never_blocks_protection(tmp_path):
    from backend.tests.test_brain_free import market,contract
    def broken(_):raise RuntimeError("secret")
    r=Runtime(tmp_path/"brain",True,api_key="synthetic",
              model_call=lambda *args:{"error":"rate","usage":None},balance_call=broken)
    try:
        r.activate(NOW,market())
        r.step(market(NOW),{"BTC":contract()},{},NOW)
        r.balance_future.result(timeout=3) if not r.balance_future.exception(timeout=3) else None
        result=r.step(market(NOW+5000),{"BTC":contract()},{},NOW+5000)
        assert result["heartbeat_ms"]==NOW+5000
        assert r.store.load()["deepseek_credit_monitor"]["last_status"]=="unavailable"
        out=str(r.store.db.execute("SELECT body FROM outbox").fetchall())
        assert "secret" not in out
    finally:r.close()
