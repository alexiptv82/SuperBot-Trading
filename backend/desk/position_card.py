"""Proposal A: sidecar-compatible lifecycle cost metrics. Pure, no writes/orders."""
import math


def metrics(pos, price, now_ms, closed, limits):
    reference=pos.margin+sum(d['margin'] for d in pos.dca_levels)
    realized=sum(r['net'] for r in closed if r.get('id')==pos.id and r.get('symbol')==pos.symbol
                 and r.get('open_ms')==pos.open_ms and r.get('partial') is True)
    fill=price*(1-pos.side*limits.slip_bp_side/10000)
    funding=(pos.qty*pos.entry*limits.funding_bp_8h_long/10000*max(0,now_ms-pos.open_ms)/28800000
             if pos.side==1 else 0.)
    net=realized+pos.side*(fill-pos.entry)*pos.qty-pos.fee_open-pos.qty*fill*limits.fee_bp_side/10000-funding
    risk=pos.risk_plan_usd
    distance=pos.entry0*pos.r_dist
    price_r=pos.side*(price-pos.entry0)/distance if distance>0 else None
    best=pos.px_hi if pos.side==1 else pos.px_lo
    mfe=max(0.,pos.side*(best-pos.entry0)/distance) if best>0 and distance>0 else None
    result={'tp':pos.tp,'total_margin':pos.total_margin,'reference_margin':reference,
            'roi_net_pct':net/reference*100 if reference>0 else None,
            'r_net':net/risk if risk>0 else None,
            'mfe_price_R_upper_bound':mfe,
            'giveback_price_R_upper_bound':max(0.,mfe-price_r) if mfe is not None and price_r is not None else None,
            'observed_peak_net_roi_pct':None,'giveback_net_roi_pp':None,
            'roi_definition':'lifecycle_net_over_initial_plus_DCA_reference_margin',
            'r_definition':'lifecycle_net_over_initial_planned_risk',
            'peak_limit':'bar_extrema_upper_bound_not_executable_net_peak'}
    for k,v in result.items():
        if isinstance(v,float) and not math.isfinite(v):result[k]=None
    return result
