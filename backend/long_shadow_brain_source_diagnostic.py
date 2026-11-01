"""Read-only Brain wallet-format attestation; never guesses the ACTIVE service.

Both historical Brain implementations may exist on disk after a migration.
An available/syntactically valid wallet is NOT proof that a corresponding
process is the currently running owner. Report ONLY source-kind/freshness
state: no funds, positions, paths, symbols, prompts or credentials.

No Docker execution, no account mutation, no trading imports.
"""
from __future__ import annotations

import argparse
import json
import time

from long_shadow_readonly import wallet_snapshot


def inspect_brain_sources(*, brain_free_dir, brain_pilot_dir,
                          now_ms=None, max_age_ms=120_000):
    now=int(time.time()*1000) if now_ms is None else now_ms
    if type(now) is not int or now<=0 or type(max_age_ms) is not int or not 1_000<=max_age_ms<=600_000:
        raise ValueError('invalid_diagnostic_clock_or_freshness')
    outcomes={}
    for source,path in (('free',brain_free_dir),('pilot',brain_pilot_dir)):
        if not isinstance(path,str) or not path.strip():
            outcomes[source]={'status':'NOT_CONFIGURED'}
            continue
        item=wallet_snapshot('brain',roots={'brain':path},
                             now_ms=now,fresh_ms=max_age_ms,
                             brain_source=source)
        outcomes[source]={
            'status':'FORMAT_AND_HEARTBEAT_OK' if item['status']=='ok'
                     else 'NOT_VERIFIED'}
    passing=[k for k,v in outcomes.items() if v['status']=='FORMAT_AND_HEARTBEAT_OK']
    status=('MULTIPLE_VALID_SOURCES_AMBIGUOUS' if len(passing)>1 else
            'SINGLE_VALID_SOURCE_NOT_RUNTIME_CONFIRMED' if passing else
            'NO_VALID_SOURCE')
    return {
        'schema':'long-shadow-brain-runtime-source-diagnostic-v1',
        'status':status,'observed_at_ms':now,'sources':outcomes,
        'valid_source_count':len(passing),
        'format_verified':len(passing)==1,
        'active_process_owner_confirmed':False,
        'may_autoselect_brain_source':False,
        'balances_exposed':False,'positions_exposed':False,
        'wallet_modified':False,'can_execute_orders':False,
        'note':'Requires independent operator confirmation of the running Brain process before connecting any writer or advisor.',
    }


def main():
    parser=argparse.ArgumentParser(description='Brain read-only format diagnostic; NO ORDERS')
    parser.add_argument('--brain-free-dir',required=True)
    parser.add_argument('--brain-pilot-dir',required=True)
    parser.add_argument('--max-age-seconds',type=int,default=120)
    args=parser.parse_args()
    result=inspect_brain_sources(
        brain_free_dir=args.brain_free_dir,
        brain_pilot_dir=args.brain_pilot_dir,
        max_age_ms=args.max_age_seconds*1000)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['valid_source_count']==1 else 2


if __name__=='__main__':
    raise SystemExit(main())
