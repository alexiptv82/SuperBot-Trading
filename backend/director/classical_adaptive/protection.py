"""One-minute PAPER protection, independent of model latency or API budget.

Bar exits retain the classical engine's stop-first OHLC approximation. The
entry-containing minute is excluded; observed quote exits use the observed
price plus engine costs. Missing prices never manufacture a fill.
"""
import math

MINUTE=60000


def series(rows, now_ms):
    if not isinstance(rows,list) or len(rows)<3:
        raise ValueError("missing_fast_series")
    bars=[]
    for raw in rows:
        if len(raw)<6:raise ValueError("invalid_fast_bar")
        b=[float(x) for x in raw[:6]]
        if not all(math.isfinite(x) for x in b) or b[0]%MINUTE or min(b[1:5])<=0 or b[5]<0 or b[2]<max(b[1],b[4]) or b[3]>min(b[1],b[4]):
            raise ValueError("invalid_fast_bar")
        if bars and b[0]-bars[-1][0]!=MINUTE:raise ValueError("fast_series_gap")
        bars.append(b)
    if not 0<=now_ms-bars[-1][0]<2*MINUTE:
        raise ValueError("stale_or_future_fast_quote")
    return bars


def close_estimate(account,p,price,now_ms):
    l=account.limits
    fill=price*(1-p.side*l.slip_bp_side/10000)
    fee=p.qty*fill*l.fee_bp_side/10000
    funding=p.qty*p.entry*l.funding_bp_8h_long/10000*max(0,now_ms-p.open_ms)/28800000 if p.side==1 else 0.
    costs=p.fee_open+fee+funding+p.qty*abs(price-fill)
    net=p.side*(fill-p.entry)*p.qty-p.fee_open-fee-funding
    return net,costs


def manage(account,sym,rows,now_ms,profit=True,paused=False):
    bars=series(rows,now_ms);p=account.positions.get(sym)
    if p is None:return None
    if paused:account.cancel_split(sym,"brain: operator pause",now_ms)
    closed=[b for b in bars if b[0]+MINUTE<=now_ms and b[0]>=math.ceil(p.open_ms/MINUTE)*MINUTE]
    # A long outage beyond the fetch window is surfaced, never presented as a
    # complete reconstruction. Current-price protection still remains possible.
    gap=bool(closed and closed[0][0]>max(p.last_bar_ms+MINUTE,math.ceil(p.open_ms/MINUTE)*MINUTE))
    rec=None
    for b in closed:
        rec=account.on_bar(sym,int(b[0]),*b[1:5],MINUTE)
        if rec:return {"trade":rec,"coverage_gap":gap,"source":"classical_engine_1m"}
    p=account.positions.get(sym)
    if p is None:return None
    price=bars[-1][4]
    p.px_hi=max(p.px_hi,price);p.px_lo=min(p.px_lo,price)
    if p.side*(price-p.liq)<=0:
        rec=account.close(sym,p.liq,now_ms,"liquidazione")
    elif p.side*(price-p.sl)<=0:
        rec=account.close(sym,price,now_ms,"brain: observed_quote_stop")
    elif p.tp is not None and p.side*(price-p.tp)>=0:
        rec=account.close(sym,price,now_ms,"brain: observed_quote_target")
    elif profit and len(closed)>=3:
        # Experimental local adaptation: two closed minutes against the trade,
        # and useful NET proceeds greater than estimated transaction costs.
        # No fixed ROI target, no forced 5/15-minute holding deadline.
        weak=all(p.side*(closed[i][4]-closed[i-1][4])<=0 for i in (-1,-2))
        net,costs=close_estimate(account,p,price,now_ms)
        if weak and net>costs:
            rec=account.close(sym,price,now_ms,"brain: net_profit_momentum_weakened")
    return {"trade":rec,"coverage_gap":gap,"source":"local_adaptive_protection","price":price}
