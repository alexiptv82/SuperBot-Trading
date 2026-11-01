"""One-shot REAL public Bitget REST+WS with AUTHENTIC pinned frozen V6.1.1.

Only synthetic PAPER wallets in TemporaryDirectory. Deliberately no broker
imports, private API, real account paths or durable trade actions. This is
a laboratory integration test, not a trading strategy profitability trial.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile

from long_shadow_live_public_synthetic_wallet_smoke import (
    _synthetic_wallets, _fresh_books_after_rest,
)
from long_shadow_rest_closed import RestClosedOverlay, public_candles, FeedNotReady
from long_shadow_stream import ObservedFeed
from long_shadow_observer import evaluate_observation
from long_shadow_observer_runner import publish_observation
from long_shadow_readonly import read_dashboard
from long_shadow_offline_probe import frozen_engine, PINNED_ENGINE_SHA256
from research_materialize_frozen_long_v611 import materialize_for_research


def main():
    # Verify and materialize source BEFORE any network I/O.
    with tempfile.TemporaryDirectory(prefix='long-frozen-v611-original-live-public-') as tmp:
        root=Path(tmp)
        original=materialize_for_research(root)
        engine=frozen_engine(original)  # second independent pinned SHA check
        if engine.VERSION!='3.0.0':
            raise ValueError('frozen_version_mismatch')

        ws=ObservedFeed()
        ws.reset(1)
        candles=RestClosedOverlay(ws)
        status=candles.refresh(public_candles)
        if status.get('closed_series')!=8:
            raise FeedNotReady('incomplete_public_rest_closed_series')
        context,now,frames=_fresh_books_after_rest(ws,candles)
        if len(context)!=2:
            raise FeedNotReady('both_public_books1_quotes_not_observed')

        wallets=_synthetic_wallets(root/'synthetic_wallets',now)
        result=evaluate_observation(
            feed=candles,now_ms=now,roots=wallets,brain_source='free',
            engine=engine,enabled=True)
        diagnostic=root/'research_output'
        diagnostic.mkdir(mode=0o700)
        publish_observation(result,diagnostic)
        view=read_dashboard(roots=wallets,shadow_dir=diagnostic,
                            brain_source='free',now_ms=now)

        records=result['records']
        if (len(records)!=12 or
                result['engine_evaluated'] is not True or
                result['frozen_engine_sha256']!=PINNED_ENGINE_SHA256 or
                result['can_execute_orders'] or
                result['orders_created']!=0 or result['paper_eligible'] or
                view['can_execute_orders'] or view['enabled'] is not False or
                len(view.get('consumers',{}))!=3 or
                any(v['wallet_status']!='ok' for v in view['consumers'].values()) or
                any(v['advisory_status']!='unverified_external_record'
                    for v in view['consumers'].values())):
            raise AssertionError('original_engine_pipeline_gate_failed')
        for record in records:
            if (record['authority']!='advisory_only' or
                    record['can_execute_orders'] is not False or
                    record['engine_sha256']!=PINNED_ENGINE_SHA256 or
                    record['decision'] not in ('CANDIDATE','NO_TRADE') or
                    record['engine_data_grade']!='execution' or
                    record['engine_data_cutoff_ms'] is None or
                    record['wallet_as_of_ms']!=now or
                    record['reasons'] and any(
                        reason.startswith(('DATA_UNAVAILABLE','DATA_NOT_READY','ENGINE_'))
                        for reason in record['reasons'])):
                raise AssertionError('original_engine_data_or_authority_gate_failed')
        if not view['consumers']['hawk']['positions']['BTCUSDT']['short_open']:
            raise AssertionError('synthetic_hawk_short_lost')
        if not view['consumers']['bull']['positions']['ETHUSDT']['long_open']:
            raise AssertionError('synthetic_bull_long_lost')

        # Never expose prices, balances or wallet location in CI logs.
        output={
            'schema':'long-shadow-REAL-frozen-v611-public-live-synthetic-e2e-v1',
            'status':'PASS',
            'source':'REAL_BITGET_PUBLIC_REST_AND_WS',
            'engine':'AUTHENTIC_FROZEN_V611_SHA256_PINNED',
            'engine_sha256':PINNED_ENGINE_SHA256,
            'authentic_frozen_engine_evaluated':True,
            'wallets':'THREE_TEMPORARY_SYNTHETIC_ONLY',
            'rest_closed_series':status['closed_series'],
            'books1_ack_count':2,'books1_observed_frames':frames,
            'evaluations':len(records),
            'decisions':dict(Counter(r['decision'] for r in records)),
            'reasons':dict(Counter(v for r in records for v in r['reasons'])),
            'consumer_count':len(view['consumers']),
            'orders_created':0,'wallets_modified':False,
            'paper_eligible':False,
            'remaining_gates':[
                'REAL_BRAIN_RUNTIME_OWNER_UNKNOWN','REAL_WALLETS_NOT_ACCESSED',
                'LONG_MTF_H24_NOT_PROVEN','ECONOMIC_EDGE_NOT_PROVEN',
            ],
        }
        print(json.dumps(output,sort_keys=True,allow_nan=False),flush=True)


if __name__=='__main__':
    main()
