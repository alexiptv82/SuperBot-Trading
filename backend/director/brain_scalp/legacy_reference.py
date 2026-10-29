"""Advisory projection of a frozen classical reading; never an order or veto.

The caller supplies a Reading produced by the pinned scorer on causal inputs.
This module validates provenance and projects both scores, not confidence.
It does not execute the scorer, query a wallet, change a plan or retrain an AI.
"""
from dataclasses import asdict,is_dataclass
import math

REFERENCE_SOURCE_SHA='9fa667ff1103f037bec06f9131996366d27370c4'
SOURCE_HASHES={
    'signals.py':'3c398e4be0335896b30f09426e5d8567cefd064907290b71b13860b8d54ec5bf',
    'seasonal.py':'47c12da1abbe51be0c826fc03b7609af40407e2e101911ded3444def5d6912c7',
}
FACT_KEYS=('rsi1h','ema20_50_1h','ema50_200_4h','roc24h',
           'atr1h_pct','vol_ratio','daily_trend')


def _number(value,low,high):
    if (isinstance(value,bool) or not isinstance(value,(int,float)) or
            not math.isfinite(value) or not low<=value<=high):
        raise ValueError('invalid_reference_number')
    return float(value)


def build_reference(reading,*,source_sha,source_hashes,observed_ms,
                    now_ms,max_age_ms):
    """Return nonbinding AI context; a stale/malformed reference is rejected.

    observed_ms is the market observation's time, not a new timestamp minted
    after delayed analysis. Fresh entry quotes and execution guards remain
    separate. The caller must verify the hashes of the scorer it actually ran;
    matching metadata alone cannot prove that a supplied reading was computed.
    No trade outcomes or unrecognised input fields are forwarded to an AI.
    """
    if source_sha!=REFERENCE_SOURCE_SHA or source_hashes!=SOURCE_HASHES:
        raise ValueError('unverified_reference_source')
    if any(type(x)!=int or x<=0 for x in (observed_ms,now_ms,max_age_ms)):
        raise ValueError('invalid_reference_clock')
    if not 0<=now_ms-observed_ms<=max_age_ms:
        raise ValueError('stale_or_future_reference')
    if is_dataclass(reading) and not isinstance(reading,type):
        reading=asdict(reading)
    if not isinstance(reading,dict):
        raise ValueError('reference_not_object')
    symbol=reading.get('symbol')
    if (not isinstance(symbol,str) or not 1<=len(symbol)<=20 or
            not symbol.isascii() or not symbol.isalnum()):
        raise ValueError('invalid_reference_symbol')
    price=_number(reading.get('price'),1e-12,1e12)
    long_score=_number(reading.get('long_score'),0,100)
    short_score=_number(reading.get('short_score'),0,100)
    side=reading.get('side')
    if type(side)!=int or side not in (-1,0,1):
        raise ValueError('invalid_reference_side')
    expected=1 if long_score>short_score else -1 if short_score>long_score else 0
    if side!=expected:
        raise ValueError('inconsistent_reference_side')
    facts=reading.get('facts',{})
    reasons=reading.get('why',[])
    if not isinstance(facts,dict):
        raise ValueError('invalid_reference_facts')
    if (not isinstance(reasons,list) or len(reasons)>30 or
            any(not isinstance(x,str) or len(x)>500 for x in reasons)):
        raise ValueError('invalid_reference_reasons')
    projected={}
    for key in FACT_KEYS:
        if key not in facts:
            continue
        value=facts[key]
        if isinstance(value,str) and len(value)<=300:
            projected[key]=value
        elif type(value) in (int,float):
            projected[key]=_number(value,-1e12,1e12)
        else:
            raise ValueError('invalid_reference_fact')
    return {
        'schema_version':1,'kind':'classical_technical_reference',
        'authority':'advisory_only','execution_permission':False,
        'source_sha':source_sha,'source_hashes':dict(SOURCE_HASHES),
        'caller_verified_source_required':True,
        'observed_ms':observed_ms,'age_ms':now_ms-observed_ms,
        'symbol':symbol,'observed_price':price,
        'direction_scores':{'LONG':long_score,'SHORT':short_score},
        'legacy_preferred_side':{1:'LONG',-1:'SHORT',0:'NEUTRAL'}[side],
        'selected_side_reasons':list(reasons),
        'opposite_side_reasons_available':False,
        'features':projected,
        'cautions':[
            'Scores are not calibrated win probabilities.',
            'The frozen scorer can favour SHORT on equal indicator values.',
            'Legacy EMA warmup and daily trend require independent review.',
            'Reasons describe only the side selected by the legacy scorer.',
            'Both regimes and LONG need separate out-of-sample evaluation.',
            'This context cannot authorise an order or bypass execution guards.',
        ],
    }
