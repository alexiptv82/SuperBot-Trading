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
    payload={'ts_ms':now,'kind':kind,'account':{'cash':state['cash'],'equity':eq if complete else None,
        'margin':margin(state),'margin_remaining':cfg.max_margin-margin(state),
        'free_slots':cfg.max_slots-len(state['positions']),'positions':state['positions']},
        'markets':readings,'instrument_constraints':physical,'market_context_nonbinding':context,
        'last_10_completed_trades':recent[-10:],'memory_is_not_retraining':True,
        'missing_data_is_not_zero':True}
    return system,json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False)
