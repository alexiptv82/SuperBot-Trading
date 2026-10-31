"""Injected DeepSeek/Claude analysis, never wallet execution or HTTP.

Callbacks accept (system, user). Existing DeepSeek returns a content/usage dict;
existing Claude returns (text, usage). No callback is selected automatically.
A live supervisor must reserve API budget and keep protection ticks independent.
"""
from dataclasses import dataclass
from .ai_context import decode,encode,SYSTEM,request_payload

PLAN_KEYS={'symbol','side','trigger','trigger_price','stop','target','margin',
           'leverage','ttl_ms','hold_max_ms','protect_after_usd','take_net_usd',
           'reason','invalidation','breakeven_after_usd','trail_bps','scale_out',
           'invalidate_price'}
REVIEW_FLAGS={'timing_uncertain','timeframe_conflict'}


def parse_reply(text,request):
    raw=decode(text)
    if (not isinstance(raw,dict) or raw.get('context_id')!=request.context_id or
            not isinstance(raw.get('plans'),list) or len(raw['plans'])>32 or
            not isinstance(raw.get('assessments'),list)):
        raise ValueError('invalid_ai_context_reply')
    summary=raw.get('summary','')
    if not isinstance(summary,str) or len(summary)>1200:raise ValueError('invalid_ai_summary')
    candidates=decode(request.payload_json)['candidates']
    allowed={c['symbol'] for c in candidates}
    seen=set();assessments=[]
    for a in raw['assessments']:
        if not isinstance(a,dict) or not isinstance(a.get('symbol'),str):
            raise ValueError('invalid_ai_assessment')
        sym=a['symbol']
        if sym not in allowed or sym in seen:raise ValueError('invalid_ai_assessment')
        if a.get('decision') not in ('LONG','SHORT','HOLD'):
            raise ValueError('invalid_ai_assessment')
        if any(not isinstance(a.get(k),str) or not 1<=len(a[k])<=800
               for k in ('long_case','short_case')):
            raise ValueError('invalid_ai_assessment')
        flags=a.get('review_flags',[])
        if (not isinstance(flags,list) or len(flags)>2 or
                any(not isinstance(f,str) or f not in REVIEW_FLAGS for f in flags)):
            raise ValueError('invalid_review_flags')
        assessments.append({k:a[k] for k in ('symbol','long_case','short_case','decision')} |
                           {'review_flags':sorted(set(flags))})
        seen.add(sym)
    if seen!=allowed:raise ValueError('missing_bidirectional_assessment')
    # Plan validation remains independent in accept_ai_plans (Group4).
    # Do not let one malformed plan discard otherwise valid proposals.
    plans=[{k:v for k,v in p.items() if k in PLAN_KEYS} if isinstance(p,dict) else p
           for p in raw['plans']]
    return {'context_id':request.context_id,'plans':plans,
            'assessments':assessments,'summary':summary}


def review_reasons(request,reply):
    candidates={c['symbol']:c for c in decode(request.payload_json)['candidates']}
    flags={a['symbol']:a['review_flags'] for a in reply['assessments']}
    reasons=set()
    for plan in reply['plans']:
        if not isinstance(plan,dict) or not isinstance(plan.get('symbol'),str):continue
        sym=plan['symbol'];side=plan.get('side')
        if (sym not in candidates or isinstance(side,bool) or
                not isinstance(side,(int,float)) or side not in (-1,1)):continue
        reasons.update(sym+':'+flag for flag in flags.get(sym,[]))
        ref=candidates[sym]['classical_reference']
        if ref['status']=='available':
            old=ref['value']['legacy_preferred_side']
            if old in ('LONG','SHORT') and old!=('LONG' if side==1 else 'SHORT'):
                reasons.add(sym+':reference_disagrees')
    return tuple(sorted(reasons))


def _unpack(value):
    usage={}
    if isinstance(value,tuple) and len(value)==2:
        text,usage=value
    elif isinstance(value,dict):
        if value.get('error'):
            from .provider_health import ProviderFailure
            code={'balance':'balance','auth':'auth','missing_key':'auth','rate':'rate',
                  'provider_http':'http','provider_network_or_format':'network'}.get(value['error'],'unavailable')
            raise ProviderFailure(code)
        if value.get('finish_reason') in ('length','max_tokens'):
            raise ValueError('provider_truncated')
        text,usage=value.get('content'),value.get('usage') or {}
    else:text=value
    if not isinstance(usage,dict):raise ValueError('invalid_provider_usage')
    if usage.get('stop_reason') in ('max_tokens','length'):
        raise ValueError('provider_truncated')
    keys=('prompt_tokens','completion_tokens','input_tokens','output_tokens',
          'prompt_cache_hit_tokens','prompt_cache_miss_tokens')
    safe={k:usage[k] for k in keys
          if type(usage.get(k))==int and 0<=usage[k]<=10000000}
    return text,safe


@dataclass(frozen=True)
class AIAnalysis:
    context_id:str
    status:str
    primary_json:str|None=None
    final_json:str|None=None
    reviewed:bool=False
    review_reasons:tuple=()
    usage_json:str='{}'
    failure_code:str|None=None


def evaluate(request,primary_call,reviewer_call=None):
    """Analyse outside the wallet tick; admission uses a later fresh timestamp."""
    request_payload(request)
    if not callable(primary_call):raise ValueError('explicit_primary_callback_required')
    usage={}
    try:
        text,tokens=_unpack(primary_call(SYSTEM,request.payload_json))
        usage['deepseek']=tokens
        first=parse_reply(text,request)
    except Exception as exc:
        from .provider_health import failure_code
        return AIAnalysis(request.context_id,'primary_failed',usage_json=encode(usage),
                          failure_code=failure_code(exc))
    reasons=review_reasons(request,first)
    first_json=encode(first)
    if not reasons:
        return AIAnalysis(request.context_id,'ready',first_json,first_json,
                          usage_json=encode(usage))
    if not callable(reviewer_call):
        return AIAnalysis(request.context_id,'review_required',first_json,
                          review_reasons=reasons,usage_json=encode(usage))
    try:
        # Same immutable context; the primary proposal is untrusted evidence.
        reviewer_payload=decode(request.payload_json)
        reviewer_payload['primary_proposal']=first
        reviewer_payload['review_reasons']=list(reasons)
        text,tokens=_unpack(reviewer_call(
            SYSTEM+'\nYou are the selective Claude reviewer. Reassess both sides; '
            'return corrected conditional plans or HOLD. The same context_id '
            'and execution constraints still apply.',encode(reviewer_payload)))
        usage['claude']=tokens
        final=parse_reply(text,request)
    except Exception as exc:
        from .provider_health import failure_code
        return AIAnalysis(request.context_id,'review_failed',first_json,
                          review_reasons=reasons,usage_json=encode(usage),
                          failure_code=failure_code(exc))
    return AIAnalysis(request.context_id,'ready',first_json,encode(final),
                      True,reasons,encode(usage))
