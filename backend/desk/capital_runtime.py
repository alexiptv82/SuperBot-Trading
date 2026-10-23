"""PAPER capital lifecycle: migration, daily rollover and manual vault requests.

The bot is the only writer. No Bitget orders or transfers are ever issued here.
Every state change must be committed through PaperCapitalJournal.commit_snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import re
import time

from .capital_manager import (CapitalInvariantError, DayReference, start_day,
                              risk_view, latch_risk, add_capital_flow, dec, cents)
from .vault_manager import VaultState, rollover, settle_pending, manual_withdraw

SCHEMA = 1
DAY_MS = 86400000
BAR_MS = 900000
KEY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def utc_day(now_ms: int) -> str:
    return datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def initial_capital(account: dict, today: str) -> dict:
    """Additive migration. NO rollover, NO vault history inferred, NO reset."""
    day = str(account.get("day") or today)
    # Baseline legacy loss limit remains latched if a 12% stop is already reached.
    legacy_equity = dec(account.get("cash", 0))
    positions = account.get("positions") or {}
    if positions:
        # In absence of reliable prices always fail closed until first validated UTC boundary.
        legacy_equity += sum((dec(p.get("total_margin",p.get("margin",0))) for p in positions.values()),Decimal(0))
    previous_ref = dec(account.get("day_start_equity", legacy_equity))
    legacy_blocked = (legacy_equity <= previous_ref * Decimal("0.88"))
    dref = DayReference(day, previous_ref, Decimal("0"),
                        stop_latched=True)
    return {"schema_version": SCHEMA, "status": "ROLLOVER_PENDING",
            "revision": 0, "day": dref.to_dict(),
            "vault": VaultState().to_dict(), "receipts": {},
            "valuation": {"fresh": False, "unrealized": "0"},
            "excluded_external_funds": "0",
            "migration": {"legacy_day": day,
                          "legacy_stop_was_active": legacy_blocked,
                          "preserved_positions": len(positions)}}


def account_components(account: dict, prices: dict) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    cash = dec(account.get("cash", 0))
    positions=account.get("positions") or {}
    margin=Decimal(0)
    unrealized=Decimal(0)
    for symbol, p in positions.items():
        if symbol not in prices:
            raise CapitalInvariantError("missing position price at rollover boundary")
        px=dec(prices[symbol])
        if px <= 0:
            raise CapitalInvariantError("invalid position valuation")
        entry=dec(p.get("entry"))
        qty=dec(p.get("qty"))
        side=int(p.get("side"))
        if side not in (-1,1) or qty < 0 or entry <= 0:
            raise CapitalInvariantError("invalid position")
        margin += dec(p.get("total_margin",p.get("margin",0)))
        unrealized += Decimal(side)*(px-entry)*qty
    return cash,margin,unrealized,cash+margin+unrealized


def boundary_prices(candles: dict, positions: dict, boundary_ms: int) -> dict:
    """Only *closed* 15m candles ending exactly at midnight UTC are acceptable."""
    result={}
    for sym in positions:
        arr=candles.get(sym)
        if arr is None:
            arr=[]
        candidates=[x for x in arr if int(x[0])==boundary_ms-BAR_MS
                    and int(x[0])+BAR_MS==boundary_ms and dec(x[4])>0]
        if len(candidates)!=1:
            raise CapitalInvariantError("missing unique UTC boundary candle")
        result[sym]=float(candidates[0][4])
    return result


def rollover_today(state: dict, now_ms: int, candles: dict,
                   *, reserved_cash: object=0) -> bool:
    """Rollover for one UTC boundary with exact prior 15m-bar-close valuation.

    If positions existed, the caller must process all PRE-boundary protective
    bars first, then call here, and process all POST-boundary bars afterwards.
    For multi-day gaps fail closed; do not fabricate historical valuations.
    """
    capital=state.get("capital")
    if not isinstance(capital,dict) or capital.get("schema_version")!=SCHEMA:
        raise CapitalInvariantError("capital V1 not migrated")
    today=utc_day(now_ms)
    d=DayReference.from_dict(capital["day"])
    if d.utc_day==today and capital.get("status")=="READY":
        return False
    boundary=datetime.strptime(today,"%Y-%m-%d").replace(tzinfo=timezone.utc)
    old=datetime.strptime(d.utc_day,"%Y-%m-%d").replace(tzinfo=timezone.utc)
    if old>=boundary or boundary-old>timedelta(days=1):
        capital["status"]="RECONCILIATION_REQUIRED"
        return True
    ms=int(boundary.timestamp()*1000)
    acc=state.get("main") or {}
    positions=acc.get("positions") or {}
    try:
        px=boundary_prices(candles,positions,ms)
        cash,m,u,e=account_components(acc,px)
        vault=VaultState.from_dict(capital["vault"])
        # Pending split legs are commitments, not withdrawable cash.
        fee_bp=dec((acc.get("limits") or {}).get("fee_bp_side",6))
        committed=Decimal("0")
        for pos in positions.values():
            split=pos.get("pending_split") or {}
            if split:
                amount=dec(split.get("margin",0))
                leverage=dec(pos.get("leverage",1))
                committed += amount*(1+leverage*fee_bp/Decimal("10000"))
        tr=rollover(vault,utc_day=today,equity=e,cash=cash,
                    committed_margin=m,unrealized=u,
                    reserved_cash=dec(reserved_cash)+committed,
                    excluded_external_funds=capital.get("excluded_external_funds",0))
        acc["cash"]=float(cash+tr.cash_delta)
        cap_ref=start_day(today,e+tr.cash_delta)
        capital["vault"]=tr.state.to_dict()
        capital["day"]=cap_ref.to_dict()
        capital["status"]="READY"
        capital["valuation"]={"fresh":True,"unrealized":str(u),
                              "boundary_ms":ms}
        acc["day"]=today
        acc["day_start_equity"]=float(e+tr.cash_delta)
        return True
    except CapitalInvariantError:
        capital["status"]="ROLLOVER_PENDING"
        capital["valuation"]={"fresh":False,"unrealized":"0"}
        return True


def update_market_risk(state: dict, prices: dict, *, now_ms: int | None = None) -> bool:
    if now_ms is None:
        now_ms=int(time.time()*1000)
    capital=state.get("capital") or {}
    if capital.get("status")!="READY":
        return False
    acc=state.get("main") or {}
    try:
        ca,margin,unrealized,eq=account_components(acc,prices)
    except CapitalInvariantError:
        capital["valuation"]={"fresh":False,"unrealized":"0"}
        return True
    day=DayReference.from_dict(capital["day"])
    if day.utc_day != utc_day(now_ms):
        # No risk unlocking with a stale day; caller handles rollover.
        capital["status"]="ROLLOVER_PENDING"
        return True
    new=latch_risk(day,eq)
    capital["day"]=new.to_dict()
    capital["valuation"]={"fresh":True,"unrealized":str(unrealized),
                          "valuation_ms":now_ms}
    return True


def settle_after_close(state: dict, prices: dict, *, event_id: str) -> bool:
    capital=state.get("capital") or {}
    if capital.get("status")!="READY":
        return False
    acc=state.get("main") or {}
    cash,margin,u,e=account_components(acc,prices)
    vault=VaultState.from_dict(capital["vault"])
    if vault.pending_total<=0:
        return False
    tr=settle_pending(vault,equity=e,cash=cash,committed_margin=margin,
                      unrealized=u,event_id=event_id,
                      excluded_external_funds=capital.get("excluded_external_funds",0))
    if tr.reason=="already_applied" or (tr.cash_delta==0 and tr.state==vault):
        return False
    acc["cash"]=float(cash+tr.cash_delta)
    capital["vault"]=tr.state.to_dict()
    ref=DayReference.from_dict(capital["day"])
    capital["day"]=add_capital_flow(ref,tr.cash_delta).to_dict()
    return True


def withdraw_request(state: dict, request: dict, *, bot: str) -> dict:
    capital=state.get("capital") or {}
    if capital.get("status")!="READY" or bot not in ("hawk","bull"):
        raise CapitalInvariantError("capital not ready")
    if request.get("kind")!="manual_vault_withdraw" or request.get("portfolio")!=bot:
        raise CapitalInvariantError("invalid request kind or portfolio")
    event_id=request.get("idempotency_key")
    if not isinstance(event_id,str) or not KEY.fullmatch(event_id):
        raise CapitalInvariantError("invalid event id")
    amount=dec(request.get("amount"))
    receipt=(capital.get("receipts") or {}).get(event_id)
    if receipt:
        if dec(receipt["amount"])!=amount:
            raise CapitalInvariantError("event id reused for another amount")
        return receipt
    if int(request.get("expected_revision",-1))!=int(capital.get("revision",-1)):
        raise CapitalInvariantError("stale capital revision")
    vault=VaultState.from_dict(capital["vault"])
    tr=manual_withdraw(vault,amount,event_id=event_id,
                       expected_revision=vault.revision,paper_mode=True)
    acc=state.get("main") or {}
    acc["cash"]=float(dec(acc["cash"])+tr.cash_delta)
    capital["vault"]=tr.state.to_dict()
    capital["excluded_external_funds"]=str(dec(capital.get("excluded_external_funds",0))+amount)
    capital["day"]=add_capital_flow(DayReference.from_dict(capital["day"]),
                                    tr.cash_delta).to_dict()
    receipt={"status":"completed","amount":str(amount),"event_id":event_id,
             "reason":"manual_vault_withdraw"}
    capital.setdefault("receipts",{})[event_id]=receipt
    return receipt
