#!/usr/bin/env python3
"""Offline deterministic mirror diagnostics. Input is private; output only aggregates."""
import argparse
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np


def mirror(a):
    b=np.array(a,dtype=float,copy=True)
    if b.ndim!=2 or b.shape[1]!=6 or not np.isfinite(b).all() or np.any(b[:,1:5]<=0):raise ValueError('invalid_bars')
    b[:,1]=1/a[:,1];b[:,2]=1/a[:,3];b[:,3]=1/a[:,2];b[:,4]=1/a[:,4]
    return b


def exact_mcnemar(b,c):
    n=b+c
    return 1. if n==0 else min(1.,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/(1<<n))


def run_series(module,items,seasonal):
    original=module.get_seasonal
    if not seasonal:module.get_seasonal=lambda *_,**__:SimpleNamespace(long_bonus=0,short_bonus=0,note='')
    pairs=[]
    try:
        for item in items:
            data={k:np.asarray(item[k],dtype=float) for k in ('arr15','daily','four_hour')}
            fn=module.read_symbol
            def evaluate(mirrored):
                arr={k:mirror(v) if mirrored else v for k,v in data.items()}
                kwargs={'daily':arr['daily']}
                if 'four_hour' in inspect.signature(fn).parameters:kwargs['four_hour']=arr['four_hour']
                return fn(item['symbol'],arr['arr15'],item['now_ms'],**kwargs)
            a,b=evaluate(False),evaluate(True)
            if a is None or b is None:raise ValueError('insufficient_pair_coverage')
            threshold=60 if item['symbol'] in ('BTC','ETH','XAU','XAG') else 63
            pairs.append((a,b,threshold))
    finally:module.get_seasonal=original
    diffs=[a.long_score-b.short_score for a,b,_ in pairs]+[a.short_score-b.long_score for a,b,_ in pairs]
    original_long=[a.side==1 and a.score>=t for a,_,t in pairs]
    mirrored_short=[b.side==-1 and b.score>=t for _,b,t in pairs]
    discord_b=sum(x and not y for x,y in zip(original_long,mirrored_short))
    discord_c=sum(y and not x for x,y in zip(original_long,mirrored_short))
    original_short=[a.side==-1 and a.score>=t for a,_,t in pairs]
    mirrored_long=[b.side==1 and b.score>=t for _,b,t in pairs]
    reverse_b=sum(x and not y for x,y in zip(original_short,mirrored_long))
    reverse_c=sum(y and not x for x,y in zip(original_short,mirrored_long))
    n=len(pairs)
    return {'n_pairs':n,'seasonality': 'on' if seasonal else 'off',
        'score_difference_mean':sum(diffs)/len(diffs) if diffs else None,
        'score_difference_mean_absolute':sum(abs(x) for x in diffs)/len(diffs) if diffs else None,
        'score_difference_max_absolute':max(map(abs,diffs),default=None),
        'score_exact_mirror_fraction':sum(x==0 for x in diffs)/len(diffs) if diffs else None,
        'original_long_score_threshold_rate':sum(a.long_score>=t for a,_,t in pairs)/n if n else None,
        'original_short_score_threshold_rate':sum(a.short_score>=t for a,_,t in pairs)/n if n else None,
        'mirrored_long_score_threshold_rate':sum(b.long_score>=t for _,b,t in pairs)/n if n else None,
        'mirrored_short_score_threshold_rate':sum(b.short_score>=t for _,b,t in pairs)/n if n else None,
        'selected_original_long_rate':sum(original_long)/n if n else None,
        'selected_mirrored_short_rate':sum(mirrored_short)/n if n else None,
        'mcnemar_short_vs_mirrored_long':{'b':reverse_b,'c':reverse_c,'nominal_exact_p':exact_mcnemar(reverse_b,reverse_c)},
        'mcnemar_long_vs_mirrored_short':{'b':discord_b,'c':discord_c,'nominal_exact_p':exact_mcnemar(discord_b,discord_c)},
        'inference':'descriptive_pairs_not_independent_no_confirmatory_claim'}


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--baseline-source',required=True)
    p.add_argument('--proposal-source',default='backend/desk/signals.py');args=p.parse_args()
    try:
        raw=Path(args.input).read_bytes();data=json.loads(raw)
        assert set(data)=={'schema','series'} and data['schema']==1 and len(data['series'])<=1000
        assert all(x.get('kind') in ('real','synthetic') for x in data['series'])
        out={'schema':1,'scope':'mirror_pair_diagnostic_not_strategy_performance',
             'input_sha256':hashlib.sha256(raw).hexdigest(),'results':{}}
        for label,path in (('baseline',args.baseline_source),('proposal',args.proposal_source)):
            module=load_module(path,'mirror_'+label)
            out[label+'_sha256']=hashlib.sha256(Path(path).read_bytes()).hexdigest()
            out['results'][label]={kind:[run_series(module,[x for x in data['series'] if x['kind']==kind],on)
                                       for on in (False,True)] for kind in ('synthetic','real')}
        print(json.dumps(out,sort_keys=True,allow_nan=False))
    except Exception:
        print('MIRROR_BLOCKED=invalid_input_or_runtime',file=sys.stderr);return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
