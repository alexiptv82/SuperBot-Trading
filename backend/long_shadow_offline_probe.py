"""Manually invoked OFFLINE frozen LONG shadow evaluation.

Reads the verified Bitget capture and authoritative read-only wallets.
Writes advisory-only research output to a NEW separate folder.
No WebSocket, broker, trading endpoints, API keys, or production write paths.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from long_shadow_capture_context import startup_contexts
from long_shadow_readonly import wallet_snapshot

PINNED_ENGINE_SHA256='36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72'
CONSUMERS=('hawk','bull','brain')
SETUPS=('CONTINUATION','REVERSAL')

def frozen_engine(engine_file):
    path=Path(engine_file)
    if not path.is_file() or path.is_symlink():
        raise ValueError('frozen_engine_missing_or_symlink')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=PINNED_ENGINE_SHA256:
        raise ValueError('frozen_engine_sha_mismatch')
    spec=importlib.util.spec_from_file_location('frozen_long_engine_shadow_only',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

def evaluate_capture(*, capture_zip, engine_file, roots, brain_source=None):
    """Return audit, not orders. No implicit fake wallet on unavailable data."""
    contexts=startup_contexts(capture_zip)
    engine=frozen_engine(engine_file)
    records=[]
    for symbol,ctx in sorted(contexts.items()):
        as_of=ctx['quote']['available_at_ms']
        for consumer in CONSUMERS:
            state=wallet_snapshot(consumer,roots=roots,brain_source=brain_source,now_ms=as_of)
            if state['status']!='ok':
                records.append({'schema':'long-shadow-record-v1','consumer':consumer,
                    'authority':'advisory_only','observation_only':True,'as_of_ms':as_of,
                    'symbol':symbol,'setup':'CONTINUATION','decision':'NO_TRADE',
                    'reasons':['WALLET_UNAVAILABLE'],'wallet_status':'unavailable',
                    'can_execute_orders':False,'research_only':True})
                continue
            wallet=state['snapshot']
            flags={'long_open':False,'short_open':False}
            for p in wallet['positions']:
                if p['symbol']==symbol and p['status']=='OPEN':
                    flags['long_open'] |= p['side']=='LONG'
                    flags['short_open'] |= p['side']=='SHORT'
            for setup in SETUPS:
                context={**ctx,'long_open':flags['long_open'],'short_open':flags['short_open']}
                result=engine.evaluate_long(context,as_of,engine.Parameters(
                    mode='advisory' if consumer=='brain' else 'shadow',setup=setup))
                if result.get('authority')!='advisory_only' or any(
                        result.get(k) is not False for k in
                        ('may_authorize_entry','may_block_entry','may_modify_scores','may_execute_exit')):
                    raise ValueError('engine_authority_contract_failed')
                decision=result['decision']
                if decision not in ('CANDIDATE','NO_TRADE'):
                    raise ValueError('unexpected_engine_decision')
                records.append({'schema':'long-shadow-record-v1','consumer':consumer,
                    'authority':'advisory_only','observation_only':True,'as_of_ms':as_of,
                    'symbol':symbol,'setup':setup,'decision':decision,
                    'reasons':result['reasons'][:12],
                    'wallet_status':'ok','can_execute_orders':False,
                    'research_only':True,'live_close_ack_observed':False})
    return {'schema':'long-shadow-offline-probe-v1','input_mode':'recorded_capture_startup_only',
            'engine_sha256':PINNED_ENGINE_SHA256,'engine_running_online':False,
            'orders_created':0,'paper_eligible':False,'records':records}

def write_new_output(result, directory):
    path=Path(directory)
    if path.exists():
        raise FileExistsError('refuse overwrite of existing output folder')
    path.mkdir(parents=True)
    # Staging archive only, never a production execution command.
    (path/'offline_probe.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for consumer in CONSUMERS:
        subset=[r for r in result['records'] if r['consumer']==consumer]
        if subset:
            # Choosing one newest record for the display-only API contract.
            current=max(subset,key=lambda r:(r['as_of_ms'],r['symbol'],r['setup']))
            (path/(consumer+'.json')).write_text(json.dumps(current,allow_nan=False)+'\n')

def main():
    p=argparse.ArgumentParser(description='Offline-only LONG shadow. No orders or network.')
    p.add_argument('--capture',required=True)
    p.add_argument('--frozen-engine',required=True)
    p.add_argument('--hawk-wallet',required=True)
    p.add_argument('--bull-wallet',required=True)
    p.add_argument('--brain-wallet',required=True)
    p.add_argument('--brain-source',choices=['pilot','free'])
    p.add_argument('--output',required=True,help='NEW research folder; never a wallet folder')
    a=p.parse_args()
    roots={'hawk':a.hawk_wallet,'bull':a.bull_wallet,'brain':a.brain_wallet}
    out=Path(a.output).resolve()
    if any(out == Path(v).resolve() or Path(v).resolve() in out.parents for v in roots.values()):
        p.error('output must not be within a wallet folder')
    result=evaluate_capture(capture_zip=a.capture,engine_file=a.frozen_engine,
                            roots=roots,brain_source=a.brain_source)
    write_new_output(result,out)
    print(json.dumps({'records':len(result['records']),
       'orders_created':0,'paper_eligible':False,
       'wallet_unavailable':sum(r['wallet_status']!='ok' for r in result['records'])}))

if __name__=='__main__':
    main()
