"""Every AI call sees the same mandate and up to ten actual completed trades."""
import json
from .mandate import SYSTEM
from .config import Config,max_leverage
from .execution import equity,margin

def build(state,markets,contracts,context,recent,seeds,kind,now,cfg=Config()):
    # Only fixed, provenance-labelled seeds join the cacheable prefix.
    system=SYSTEM+'\nHistorical non-binding data:\n'+json.dumps(seeds,sort_keys=True,ensure_ascii=False)
    quotes={s:x['quote'] for s,x in markets.items() if x.get('quote')}
    eq,complete=equity(state,quotes)
    symbols=cfg.symbols if kind=='full' else tuple(state['positions'])
    readings={s:{k:v for k,v in markets.get(s,{'status':'unavailable'}).items() if k!='bars'} for s in symbols}
    physical={s:{**contracts.get(s,{}),'operator_max_leverage':max_leverage(s),
                 'liquidation_buffer':cfg.liquidation_buffer} for s in symbols}
    payload={'ts_ms':now,'kind':kind,
        'execution_costs':{'taker_fee_per_side':cfg.fee_rate,
                           'slippage_assumption_per_side':cfg.slippage,
                           'roundtrip_friction_on_notional':2*(cfg.fee_rate+cfg.slippage),
                           'additional_spread_and_funding':'unknown_not_zero',
                           'estimate_net_pnl_before_entry':True},
        'sizing_preference_nonbinding':{'typical_margin_usd':[200,350],
            'leverage':'choose from actual risk and instrument limits; no required minimum',
            'objective':'net trading profit after costs, not a trade quota'},
        'account':{'cash':state['cash'],'equity':eq if complete else None,
        'margin':margin(state),'margin_remaining':cfg.max_margin-margin(state),
        'free_slots':cfg.max_slots-len(state['positions']),'positions':state['positions']},
        'markets':readings,'instrument_constraints':physical,'market_context_nonbinding':context,
        'last_10_completed_trades':recent[-10:],'memory_is_not_retraining':True,
        'missing_data_is_not_zero':True}
    return system,json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False)
