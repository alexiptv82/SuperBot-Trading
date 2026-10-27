"""Independent virtual account using the existing paper engine and close schema."""
import copy
import math
import time
from desk.engine import Limits, PaperAccount, max_leverage_for
from .learning import entry_context


def number(value, low, high):
    if isinstance(value,bool):
        raise ValueError("boolean_number")
    v = float(value)
    if not math.isfinite(v) or not low <= v <= high:
        raise ValueError("number_out_of_range")
    return v


class Portfolio:
    def __init__(self, state=None):
        self.account = PaperAccount.from_dict(copy.deepcopy(state)) if state is not None else PaperAccount(
            Limits(start_equity=1000,max_open=10,max_margin_trade=100,max_margin_total=1000,
                   max_dca_total=100,min_margin=1,fee_bp_side=6,slip_bp_side=2,
                   daily_stop=.20,kill_equity=450), "brain-paper")
        if self.account.name != "brain-paper" or self.account.limits.fee_bp_side != 6:
            raise ValueError("foreign_portfolio_state")
        # Explicit policy migration: stored Limits(.12) must not undo user .20.
        self.account.limits.daily_stop=.20
        self.daily=copy.deepcopy((state or {}).get("brain_daily",{}))

    def to_dict(self):
        return dict(self.account.to_dict(),brain_daily=copy.deepcopy(self.daily))

    def roll_day(self,now_ms,prices):
        a=self.account
        if any(s not in prices or not math.isfinite(float(prices[s])) or prices[s]<=0 for s in a.positions):
            return "daily_valuation_missing"
        day=time.strftime("%Y-%m-%d",time.gmtime(now_ms/1000))
        equity=a.equity(prices)
        if not self.daily or day>self.daily["day"]:
            reference=a.day_start_equity if not self.daily and a.day==day else equity
            self.daily={"policy_version":2,"day":day,"start_equity":reference,"stopped":False,"stop_logged":False}
        # Backwards clocks never release an existing latch.
        a.day=self.daily["day"];a.day_start_equity=self.daily["start_equity"]
        if equity<=self.daily["start_equity"]*.8:
            self.daily["stopped"]=True
        return "daily_stop_20pct" if self.daily["stopped"] else ""

    def halted(self,prices,now_ms):
        return self.roll_day(now_ms,prices) or self.account.halted(prices)

    def risk_at_stop(self, p):
        a = self.account
        exit_fill = p.sl*(1-p.side*a.limits.slip_bp_side/10000)
        gross = p.side*(exit_fill-p.entry)*p.qty
        return max(0.,-gross+p.fee_open+p.qty*exit_fill*.0006)

    def snapshot(self, prices, now_ms):
        a = self.account
        rows=[]
        for sym,p in sorted(a.positions.items()):
            px=prices.get(sym,p.entry)
            effective=px*(1-p.side*.0002)
            funding=p.qty*p.entry*a.limits.funding_bp_8h_long/10000*max(0,now_ms-p.open_ms)/28800000 if p.side==1 else 0.
            net=p.side*(effective-p.entry)*p.qty-p.fee_open-p.qty*effective*.0006-funding
            rows.append({"symbol":sym+"USDT","side":p.side,"entry":p.entry,"price":px,
                         "net_close_estimate":net,"net_margin_roi_pct":100*net/p.total_margin,
                         "age_minutes":max(0,now_ms-p.open_ms)/60000,"stop":p.sl,"tp":p.tp,
                         "risk_at_stop":self.risk_at_stop(p),"averages":p.dca_count,
                         "invalidation":p.features.get("invalidation","")})
        return {"equity":a.equity(prices),"cash":a.cash,"max_slots":10,"positions":rows,
                "halted":self.halted(prices,now_ms),"daily":copy.deepcopy(self.daily),
                "risk_max_pct":1,"fee_each_side":.0006}

    def open(self, sym, decision, px, now_ms, prices, context=None):
        a=self.account; side=1 if decision["action"]=="open_long" else -1
        size=number(decision["size_pct"],.01,1)*number(decision["conviction"],60,100)/100
        sl=number(decision["sl"],1e-12,1e15); tp=number(decision["tp"],1e-12,1e15)
        fill=px*(1+side*.0002)
        if not (sl<fill<tp if side==1 else tp<fill<sl):
            raise ValueError("gap_invalid_levels")
        atr=number(decision.get("_atr_1h"),1e-12,1e15)
        original_sl=sl
        if abs(px-sl)<.8*atr:
            sl=px-side*.8*atr
        if sl<=0 or abs(px-sl)/px>.08:
            raise ValueError("atr_stop_out_of_bounds")
        if abs(tp-fill)/abs(fill-sl)<1.5:
            raise ValueError("rr_below_1_5")
        exit_fill=sl*(1-side*.0002)
        risk_per_notional=abs(fill-exit_fill)/fill+.0006+.0006*exit_fill/fill
        notional=a.equity(prices)*.01*size/risk_per_notional
        dist=abs(fill-sl)/fill
        cap=min(max_leverage_for(sym),math.floor(1/(dist/a.limits.sl_liq_frac+a.limits.maint)))
        if cap<1:
            raise ValueError("liquidation_distance")
        lev=min(cap,max(1,math.ceil(notional/100)))
        margin=min(notional/lev,100,a.cash*.95,max(0,1000-a.margin_in_use()))
        p,msg=a.open(sym,side,margin,lev,px,sl,tp,now_ms,prices,
                     confidence=int(decision["conviction"]),reason=decision["reason"],
                     source="brain-deepseek",trade_type="medio",
                     features={"invalidation":decision["invalidation"],"market_phase":decision.get("market_phase",""),
                               "bull_scenario":decision.get("bull_scenario"),"bear_scenario":decision.get("bear_scenario"),
                               "verdict":decision.get("verdict"),
                               "learning_context":entry_context(context or {}, decision["_learning_model"], decision.get("_learning_refs", []), decision.get("_experience_refs", []), decision.get("_experience_bundle"))
                                   if "_learning_model" in decision else {}})
        if p is None:
            raise ValueError(msg)
        return {"kind":"open","symbol":sym,"risk":self.risk_at_stop(p),"position_id":p.id,
                "sl_requested":decision.get("_requested_sl",original_sl),"sl_applied":sl,
                "atr_adjusted":decision.get("_atr_adjusted",False) or sl!=original_sl}

    def average(self,sym,decision,px,now_ms,prices,context):
        a=self.account; p=a.positions.get(sym)
        if p is None or a.halted(prices):
            raise ValueError("average_missing_or_halted")
        trend="up" if p.side==1 else "down"
        if context.get("trend",{}).get("4h")!=trend or context.get("trend",{}).get("1d")!=trend:
            raise ValueError("average_macro_unconfirmed")
        atr=number(context.get("atr14_1h",decision.get("_atr_1h")),1e-12,1e15)
        if abs(px-p.sl)<.8*atr:
            raise ValueError("average_atr_floor_would_require_wider_stop")
        support=number(decision["support_level"],1e-12,1e15)
        observed=context["support_20h" if p.side==1 else "resistance_20h"]
        if abs(support-observed)/observed>.001 or abs(px-support)/px>.015:
            raise ValueError("average_not_at_observed_level")
        if not (p.sl<support<=px if p.side==1 else px<=support<p.sl):
            raise ValueError("support_broken_or_outside_stop")
        size=number(decision["size_pct"],.01,1)*number(decision["conviction"],60,100)/100
        # Existing engine controls adverse price, max two adds, fees and stop.
        candidate=PaperAccount.from_dict(copy.deepcopy(a.to_dict()))
        added,msg=candidate.add_dca(sym,p.sl,p.tp,now_ms,{**prices,sym:px},decision["reason"])
        if added is None:
            raise ValueError(msg)
        if added.total_margin>100 or candidate.margin_in_use()>1000:
            raise ValueError("average_margin_cap")
        trial=Portfolio(dict(candidate.to_dict(),brain_daily=self.daily))
        # All legs share the original stop budget. No hidden risk multiplication.
        if trial.risk_at_stop(added)>a.equity(prices)*.01*size+1e-8:
            raise ValueError("average_total_risk_cap")
        self.account=candidate
        added.features["invalidation"]=copy.deepcopy(decision["invalidation"])
        return {"kind":"average","symbol":sym,"risk":trial.risk_at_stop(added)}

    def apply(self,decision,px,now_ms,prices,context):
        # Transactional candidate: any rejection leaves the whole account unchanged.
        action=decision["action"]
        if action.startswith("open_") or action=="average":
            if self.halted(prices,now_ms):
                raise ValueError("exposure_halted")
        trial=Portfolio(self.to_dict()); a=trial.account
        sym=decision["symbol"]; action=decision["action"]; p=a.positions.get(sym)
        if action.startswith("open_"):
            event=trial.open(sym,decision,px,now_ms,prices,context)
        elif action=="average":
            event=trial.average(sym,decision,px,now_ms,prices,context)
        elif action in ("close","save_profit","partial_close"):
            if p is None:
                raise ValueError("missing_position")
            if action=="save_profit":
                row=trial.snapshot({**prices,sym:px},now_ms)["positions"]
                if next(r for r in row if r["symbol"]==sym+"USDT")["net_close_estimate"]<=0:
                    raise ValueError("save_profit_not_profitable")
            rec=a.partial_close(sym,px,now_ms,.5,why="brain: partial 50%") if action=="partial_close" else a.close(sym,px,now_ms,"brain: "+action)
            event={"kind":action,"symbol":sym,"trade":rec}
        elif action=="move_stop":
            ns=number(decision["new_stop"],1e-12,1e15)
            if p is None or not (p.sl<ns<px if p.side==1 else px<ns<p.sl):
                raise ValueError("stop_not_tighter")
            p.sl=ns; event={"kind":action,"symbol":sym}
        elif action=="hold":
            event={"kind":"hold","symbol":sym}
        else:
            raise ValueError("unknown_action")
        self.account=trial.account
        return event
