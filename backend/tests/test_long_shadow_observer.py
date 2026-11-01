"""Advisory observer tests; no exchange, no API tokens, no wallet writes."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from long_shadow_observer import evaluate_observation, observed_result


NOW = 1793549782400
ROOTS = {'hawk': '/scratch/hawk', 'bull': '/scratch/bull',
         'brain': '/scratch/brain'}


def wallet(name='hawk', positions=None):
    return {'status': 'ok', 'snapshot': {'account_id': name, 'as_of_ms': NOW,
            'positions': positions if positions is not None else []}}


def valid_engine(*, decision='NO_TRADE', override=None):
    def evaluate(context, at, p):
        output = {
            'authority': 'advisory_only', 'mode': p.mode, 'setup': p.setup,
            'symbol': context['symbol'], 'decision': decision,
            'reasons': ['SETUP_ABSENT'] if decision == 'NO_TRADE' else [],
            'may_authorize_entry': False, 'may_block_entry': False,
            'may_modify_scores': False, 'may_execute_exit': False,
            'data_grade': 'analysis', 'data_cutoff_ms': at-60_000,
        }
        if override:
            output.update(override)
        return output
    return SimpleNamespace(Parameters=lambda **kwargs: SimpleNamespace(**kwargs),
                           evaluate_long=Mock(side_effect=evaluate))


def feed(*, with_data=True, ts=NOW):
    def context(symbol, at):
        if not with_data:
            from long_shadow_stream import FeedNotReady
            raise FeedNotReady('missing_timeframe_snapshot')
        return {'symbol': symbol, 'bars': {'1m': []},
                'quote': {'bid': 100, 'ask': 100.1,
                          'available_at_ms': at}, 'long_open': True,
                'short_open': True}
    return SimpleNamespace(last_receipt_ms=ts, context=Mock(side_effect=context))


class ObserverContracts(unittest.TestCase):
    def test_all_3_consumers_and_2_symbols_and_2_setups(self):
        engine = valid_engine()
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer, **kw: wallet(consumer)):
            report = evaluate_observation(
                feed=feed(), now_ms=NOW, roots=ROOTS, engine=engine,
                enabled=True, brain_source='free')
        self.assertEqual(len(report['records']), 12)
        self.assertEqual(len(engine.evaluate_long.call_args_list), 12)
        self.assertEqual(report['orders_created'], 0)
        self.assertFalse(report['paper_eligible'])
        self.assertTrue(all(r['authority'] == 'advisory_only'
                            and not r['can_execute_orders']
                            for r in report['records']))

    def test_consumer_mode_classics_vs_brain(self):
        modes = []
        engine = valid_engine()
        def wrapper(ctx, at, p):
            modes.append((ctx['symbol'], p.mode))
            return {'authority': 'advisory_only', 'symbol': ctx['symbol'],
                    'setup': p.setup, 'mode': p.mode, 'decision': 'NO_TRADE',
                    'reasons': ['SETUP_ABSENT'], 'may_authorize_entry':False,
                    'may_block_entry':False, 'may_modify_scores':False,
                    'may_execute_exit':False}
        engine.evaluate_long.side_effect = wrapper
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer, **kw: wallet(consumer)):
            evaluate_observation(feed=feed(), now_ms=NOW, roots=ROOTS,
                                 engine=engine, enabled=True)
        self.assertEqual([m for sym,m in modes].count('shadow'), 8)
        self.assertEqual([m for sym,m in modes].count('advisory'), 4)

    def test_feed_position_flags_always_overwritten(self):
        contexts = []
        engine = valid_engine()
        def evaluate(ctx, at, p):
            contexts.append((p.mode,ctx['long_open'],ctx['short_open']))
            return {'authority': 'advisory_only', 'symbol': ctx['symbol'],
                    'setup': p.setup, 'mode': p.mode, 'decision': 'NO_TRADE',
                    'reasons': [], 'may_authorize_entry': False,
                    'may_block_entry': False, 'may_modify_scores': False,
                    'may_execute_exit': False}
        engine.evaluate_long.side_effect = evaluate
        def wallet_for(c, **kw):
            return wallet(c,[{'symbol':'BTCUSDT','side':'SHORT','status':'OPEN'}]
                          if c == 'hawk' else [])
        with patch('long_shadow_observer.wallet_snapshot', side_effect=wallet_for):
            evaluate_observation(feed=feed(), now_ms=NOW, roots=ROOTS,
                                 engine=engine, enabled=True)
        self.assertTrue(all(m == 'shadow' and not lg and sh
                            for m, lg, sh in contexts[:2]))
        self.assertTrue(all(not lg and not sh for m,lg,sh in contexts[4:]))

    def test_stale_wallet_never_calls_engine_for_that_account(self):
        engine = valid_engine(decision='CANDIDATE')
        def wallets(c, **kw):
            return {'status':'unavailable'} if c == 'brain' else wallet(c)
        with patch('long_shadow_observer.wallet_snapshot', side_effect=wallets):
            report = evaluate_observation(feed=feed(), now_ms=NOW,
                                          roots=ROOTS, engine=engine, enabled=True)
        brain=[r for r in report['records'] if r['consumer']=='brain']
        self.assertEqual({r['decision'] for r in brain},{'NO_TRADE'})
        self.assertEqual({r['reasons'][0] for r in brain},{'WALLET_UNAVAILABLE'})
        self.assertEqual(engine.evaluate_long.call_count,8)

    def test_disabled_never_runs_engine(self):
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer,**kw: wallet(consumer)):
            report=evaluate_observation(feed=feed(with_data=False),
                                        now_ms=NOW,roots=ROOTS,engine=None)
        self.assertFalse(report['engine_evaluated'])
        self.assertTrue(all(r['reasons']==['SHADOW_DISABLED'] for r in report['records']))

    def test_missing_data_fails_closed(self):
        engine=valid_engine(decision='CANDIDATE')
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer,**kw: wallet(consumer)):
            result=evaluate_observation(feed=feed(with_data=False),
                    now_ms=NOW, roots=ROOTS, engine=engine,enabled=True)
        self.assertEqual(engine.evaluate_long.call_count,0)
        self.assertTrue(all(r['decision']=='NO_TRADE' and
                            'missing_timeframe_snapshot' in r['reasons'][0]
                            for r in result['records']))

    def test_old_or_future_market_receipt_rejected(self):
        engine=valid_engine(decision='CANDIDATE')
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer,**kw: wallet(consumer)):
            for ts in (NOW-9000,NOW+2000):
                with self.subTest(ts=ts):
                    out=evaluate_observation(feed=feed(ts=ts),now_ms=NOW,
                        roots=ROOTS,engine=engine,enabled=True)
                    self.assertTrue(all(r['decision']=='NO_TRADE' for r in out['records']))
        self.assertEqual(engine.evaluate_long.call_count,0)

    def test_illicit_engine_permission_is_rejected_not_candidate(self):
        engine=valid_engine(decision='CANDIDATE',override={'may_authorize_entry':True})
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer,**kw: wallet(consumer)):
            out=evaluate_observation(feed=feed(),now_ms=NOW,
                                     roots=ROOTS,engine=engine,enabled=True)
        self.assertTrue(all(r['decision']=='NO_TRADE' and
                            r['reasons']==['ENGINE_OR_WALLET_CONTRACT_ERROR']
                            for r in out['records']))

    def test_wrong_symbol_or_mode_from_engine_cannot_be_published(self):
        for override in ({'symbol':'XRPUSDT'}, {'mode':'paper'},
                         {'decision':'open_long'}, {'setup':'WRONG'}):
            engine=valid_engine(decision='CANDIDATE',override=override)
            with patch('long_shadow_observer.wallet_snapshot',
                       side_effect=lambda consumer,**kw: wallet(consumer)):
                out=evaluate_observation(feed=feed(),now_ms=NOW,
                                         roots=ROOTS,engine=engine,enabled=True)
            self.assertTrue(all(r['decision']=='NO_TRADE' for r in out['records']))

    def test_unconfigured_brain_source_is_passed_without_guessing(self):
        seen=[]
        def fn(c,**kw):
            seen.append((c,kw['brain_source']))
            return wallet(c)
        with patch('long_shadow_observer.wallet_snapshot',side_effect=fn):
            evaluate_observation(feed=feed(),now_ms=NOW,roots=ROOTS,enabled=False)
        self.assertIn(('brain',None),seen)

    def test_frozen_engine_required_and_sha_guard_called(self):
        with self.assertRaisesRegex(ValueError,'engine_not_loaded'):
            evaluate_observation(feed=feed(), now_ms=NOW, roots=ROOTS,enabled=True)
        with patch('long_shadow_observer.frozen_engine',
                   side_effect=ValueError('frozen_engine_sha_mismatch')):
            with self.assertRaisesRegex(ValueError,'frozen_engine_sha_mismatch'):
                observed_result(feed=feed(),now_ms=NOW,roots=ROOTS,
                                frozen_engine_path='/tmp/tampered',enabled=True)

    def test_real_engine_style_no_trade_retains_authority_flags(self):
        engine=valid_engine()
        with patch('long_shadow_observer.wallet_snapshot',
                   side_effect=lambda consumer,**kw: wallet(consumer)):
            out=evaluate_observation(feed=feed(),now_ms=NOW,
                                     roots=ROOTS,engine=engine,enabled=True)
        self.assertTrue(all(r['decision']=='NO_TRADE' and
                            r['reasons']==['SETUP_ABSENT'] for r in out['records']))

if __name__ == '__main__':
    unittest.main()
