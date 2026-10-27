"""Real cli.run_cycle integration, isolated per profile; all IO synthetic."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

def block_network(event,args):
    if event in ("socket.connect","socket.getaddrinfo"):raise OSError("TEST_NETWORK_DISABLED")
sys.addaudithook(block_network)

from director.classical_adaptive.runtime import Session, configure
from director.classical_adaptive.feeds import Feeds

profile=sys.argv[1]
side=sys.argv[2] if len(sys.argv)>2 else "long"
market_side=sys.argv[3] if len(sys.argv)>3 else side
NOW=1793102400000+15000

with tempfile.TemporaryDirectory() as root:
    (Path(root)/"api_budget_baseline.json").write_text(json.dumps({"version":1,"mode":"paper","source_sha256":"0"*64,"by_day":{}}))
    os.environ["DEEPSEEK_API_KEY"]="fake-test-key"
    cli=configure(root,profile)
    cli.SYMBOLS=["BTC","ETH"]
    clock=[NOW];price=[100.]
    def candles(sym,bar="15m",limit=1000):
        ms=60000 if bar=="1m" else 900000
        end=clock[0]//ms*ms
        return [[end-(99-i)*ms,price[0],price[0]+.001,price[0]-.001,price[0],100] for i in range(100)]
    def reading(sym,*args,**kw):
        long=market_side=='long'
        return SimpleNamespace(symbol=sym,price=price[0],side=1 if long else -1,score=59,long_score=59 if long else 10,short_score=10 if long else 59,trade_type="scalp",
            sl_pct=.004,tp_pct=.008,atr_pct=.003,why=["synthetic"],seasonal_note="",pattern="",facts={"daily_trend":"trend 1d bull" if long else "trend 1d bear","ema50_200_4h":"su" if long else "giu"})
    answer={"decisions":[{"symbol":"ETH","action":"open_"+side,"margin_usd":200,"leverage":15,"confidence":95,
        "stop_loss_pct":.004,"take_profit_pct":.008,"reason":"synthetic current evidence","trade_type":"scalp"}]}
    def fake(*_):
        # The account writer must persist the exact selected input before
        # this background API call can begin.
        import sqlite3
        with sqlite3.connect(Path(root)/("brain-"+profile)/"brain.sqlite3") as db:
            records=[json.loads(row[0]) for row in db.execute("SELECT body FROM events WHERE kind='journal'")]
        inputs=[r['input'] for r in records if r.get('kind')=='adaptive_input']
        assert inputs and inputs[-1]['system']==_[2] and inputs[-1]['user']==_[3]
        return {"content":json.dumps(answer),"usage":{"hit":0,"miss":1,"out":1}}
    cli.fetch_candles=candles
    cli.read_symbol=reading
    cli.daily_bars=lambda *_:[]
    cli.four_hour_bars=lambda *_:[]
    cli.fetch_all_context=lambda *_:{"funding":{},"oi":{},"news":[],"ts":clock[0]}
    class Inline:
        def poll(self,symbols,required,now_ms):
            fast={s:{"rows":candles(s,"1m"),"received_ms":now_ms} for s in required}
            entry={"markets":{s:{"rows":candles(s),"daily":[],"four":[],"received_ms":now_ms} for s in symbols},
                   "context":{"funding":{},"oi":{},"news":[],"ts":now_ms}}
            return fast,entry
        def close(self):pass
    with patch("time.sleep",lambda *_:None),patch("time.time",lambda:clock[0]/1000):
        profile_root=Path(root)/('brain-'+profile);profile_root.mkdir()
        (profile_root/'pause.flag').write_text('release-warmup')
        s=Session(root,profile,cli,initialize=True,call=fake,feeds=Inline())
        try:
            clock[0]-=60000;s.step(clock[0])
            assert s.state['operator_paused'] is True
            assert not cli.make_account(s.state['desk']).positions
            assert s.provider.pending is None
            (profile_root/'pause.flag').unlink();clock[0]+=60000
            s.step(clock[0]);assert s.provider.pending is not None
            s.provider.pending["future"].result(2)
            clock[0]+=60000;s.step(clock[0])
            events=[json.loads(r[0]) for r in s.store.db.execute("SELECT body FROM events WHERE kind='journal'")]
            assert not [e for e in events if e.get("kind")=="entry_cycle_failed"],events[-3:]
            a=cli.make_account(s.state["desk"])
            if side!=market_side:
                assert 'ETH' not in a.positions,a.positions
                assert cli.REGIME_ON
                assert cli.HB['regime']['state']==('up' if market_side=='long' else 'down'),cli.HB['regime']
                assert any(e.get('kind')=='adaptive_advice' and e['decisions'][0]['action']=='open_'+side for e in events)
                print('REGIME_ENTRY_VETO=PASS')
                print('CLASSICAL_ADAPTIVE_PROBE=PASS')
                raise SystemExit(0)
            p=a.positions["ETH"]
            assert p.total_margin==(100 if profile=="hawk" else 200),p
            assert p.leverage==15,p
            assert p.source=="brain-deepseek",p
            assert s.state['desk']['last_price_times']['ETH']==clock[0]
            assert s.state['steps_completed']==3
            assert any(e.get('kind')=='adaptive_advice' and e['decisions'][0]['symbol']=='ETH' for e in events),events[-3:]
            assert p.features["learning_context"]["strategy_version"].startswith("classical-"+profile)
            assert a.name=="brain-"+profile
            before=copy.deepcopy(s.state)
            # Failure in the optional entry stage cannot undo financial state.
            original=cli.run_cycle
            def broken(state,*args,**kw):
                state["main"]["cash"]=0
                raise RuntimeError("synthetic")
            cli.run_cycle=broken
            clock[0]+=60000;status=s.step(clock[0])
            assert s.state["desk"]["main"]["cash"]==before["desk"]["main"]["cash"]
            assert status["decision_source"]=="classical_rules",status
            cli.run_cycle=original
            # Fail an authoritative close transaction: no trade/account change.
            s.store.db.execute("CREATE TRIGGER reject_close BEFORE INSERT ON events WHEN NEW.kind='trade' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
            s.store.db.commit();price[0]=99. if side=="long" else 101.;clock[0]+=60000
            try:s.step(clock[0]);raise AssertionError("expected transaction rejection")
            except __import__('sqlite3').IntegrityError:pass
            assert "ETH" in s.store.load()["desk"]["main"]["positions"]
            assert s.store.db.execute("SELECT count(*) FROM events WHERE kind='trade'").fetchone()[0]==0
            s.store.db.execute("DROP TRIGGER reject_close");s.store.db.commit()
            s.step(clock[0]);assert not cli.make_account(s.state["desk"]).positions
            assert s.store.db.execute("SELECT count(*) FROM events WHERE kind='trade'").fetchone()[0]==1
            closed=s.state["learning"]["completed_total"];assert closed==1,s.state["learning"]
            cash=s.state["desk"]["main"]["cash"]
        finally:s.close()
        # A restart reloads the existing balance/history; never initializes again.
        s=Session(root,profile,cli,call=fake,feeds=Inline())
        try:
            assert s.state["desk"]["main"]["cash"]==cash
            assert s.state["learning"]["completed_total"]==closed
            assert s.store.db.execute("SELECT count(*) FROM events WHERE kind='trade'").fetchone()[0]==1
        finally:s.close()
        # Losing/recreating the API ledger cannot silently release spent credit.
        import sqlite3
        with sqlite3.connect(Path(root)/"brain-api-budget.sqlite3") as db:db.execute("DELETE FROM reservations")
        try:Session(root,profile,cli,call=fake,feeds=Inline());raise AssertionError("budget reset accepted")
        except ValueError as exc:assert str(exc)=="spend_ledger_rollback_detected",exc
        # Unknown nonempty directories are not treated as a fresh $1000 account.
        bad=Path(root)/"other"/("brain-"+profile);bad.mkdir(parents=True);(bad/"state_v2.json").write_text("{}")
        previous=cli.DATA_DIR;cli.DATA_DIR=str(bad)
        try:
            try:Session(bad.parent,profile,cli,initialize=True);raise AssertionError("unexpected reset")
            except ValueError:pass
        finally:cli.DATA_DIR=previous
print("CLASSICAL_ADAPTIVE_PROBE=PASS")
