"""Frozen LONG engine + public captured feed + authoritative PAPER wallet.

This is a **pure read-only advisor**. No order APIs, broker connections, paid
AI calls, production hooks, or trading side effects. This module deliberately
does not start itself. A collector/CLI must be separately configured.

Causal protection: evaluate at the trusted receipt-clock time, using only
observed snapshots and a fresh bid/ask. The frozen engine independently checks
all timeframe staleness; live kline updates are never promoted to closes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from long_shadow_stream import FeedNotReady, SYMBOLS
from long_shadow_readonly import wallet_snapshot
from long_shadow_offline_probe import frozen_engine, PINNED_ENGINE_SHA256

CONSUMERS = ('hawk', 'bull', 'brain')
SETUPS = ('CONTINUATION', 'REVERSAL')
AUTHORITY_FLAGS = ('may_authorize_entry', 'may_block_entry',
                   'may_modify_scores', 'may_execute_exit')
MAX_RECEIPT_SKEW_MS = 3_000
WALLET_MAX_AGE_MS = 30_000


def _no_trade(consumer, symbol, setup, as_of_ms, reason, wallet_status):
    return {
        'schema': 'long-shadow-record-v1', 'consumer': consumer,
        'symbol': symbol, 'setup': setup,
        'decision': 'NO_TRADE', 'reasons': [reason],
        'authority': 'advisory_only', 'observation_only': True,
        'as_of_ms': as_of_ms, 'wallet_status': wallet_status,
        'source': 'public_capture_research_only',
        'research_only': True, 'can_execute_orders': False,
        'live_close_ack_observed': False,
        'engine_sha256': PINNED_ENGINE_SHA256,
    }


def _validate_clock(feed, now_ms):
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError('invalid_trusted_clock')
    observed = feed.last_receipt_ms
    if type(observed) is not int:
        raise FeedNotReady('no_market_frame_received')
    if not 0 <= now_ms - observed <= MAX_RECEIPT_SKEW_MS:
        raise FeedNotReady('market_receipt_stale_or_future')


def _wallet_flags(snapshot, symbol):
    if not isinstance(snapshot, dict) or snapshot.get('account_id') not in CONSUMERS:
        raise ValueError('invalid_wallet_identity')
    positions = snapshot.get('positions')
    if not isinstance(positions, list):
        raise ValueError('wallet_positions_missing')
    found = set()
    for position in positions:
        if not isinstance(position, dict):
            raise ValueError('malformed_wallet_position')
        if position.get('symbol') != symbol:
            continue
        if position.get('status') != 'OPEN' or position.get('side') not in ('LONG', 'SHORT'):
            raise ValueError('invalid_wallet_position')
        found.add(position['side'])
    return {'long_open': 'LONG' in found, 'short_open': 'SHORT' in found}


def evaluate_observation(*, feed, now_ms, roots, brain_source=None,
                         engine=None, enabled=False):
    """Build an advisory-only result for each account/symbol/setup.

    The explicit enabled switch never confers trading authority. The trusted
    clock is caller supplied; the CLI must pass wall-clock time, never a
    historical frame timestamp when consuming archived captures.
    """
    if type(enabled) is not bool:
        raise ValueError('enabled_must_be_boolean')
    if not isinstance(roots, dict):
        raise ValueError('wallet_roots_missing')
    # A frozen engine must be provided only by the SHA-checked loader.
    # When disabled, do not load or run any engine.
    if enabled and engine is None:
        raise ValueError('engine_not_loaded')
    records = []
    for consumer in CONSUMERS:
        wallet = wallet_snapshot(
            consumer, roots=roots, now_ms=now_ms, fresh_ms=WALLET_MAX_AGE_MS,
            brain_source=brain_source)
        for symbol in SYMBOLS:
            for setup in SETUPS:
                if not enabled:
                    records.append(_no_trade(
                        consumer, symbol, setup, now_ms, 'SHADOW_DISABLED', wallet['status']))
                    continue
                if wallet['status'] != 'ok':
                    records.append(_no_trade(
                        consumer, symbol, setup, now_ms, 'WALLET_UNAVAILABLE', 'unavailable'))
                    continue
                try:
                    _validate_clock(feed, now_ms)
                    context = feed.context(symbol, now_ms)
                    flags = _wallet_flags(wallet['snapshot'], symbol)
                    # Never allow the feed, an AI model, or another consumer to
                    # supply/override authoritative position-open flags.
                    context = {**context, **flags}
                    p = engine.Parameters(
                        mode='advisory' if consumer == 'brain' else 'shadow',
                        setup=setup)
                    result = engine.evaluate_long(context, now_ms, p)
                    if (result.get('authority') != 'advisory_only' or
                            any(result.get(k) is not False for k in AUTHORITY_FLAGS) or
                            result.get('mode') != p.mode or
                            result.get('setup') != setup or
                            result.get('symbol') != symbol or
                            result.get('decision') not in ('CANDIDATE', 'NO_TRADE')):
                        raise ValueError('engine_authority_or_identity_failed')
                    reasons = result.get('reasons')
                    if (not isinstance(reasons, list) or
                            not all(isinstance(x, str) and len(x) < 100 for x in reasons)):
                        raise ValueError('engine_reasons_invalid')
                    records.append({
                        **_no_trade(consumer, symbol, setup, now_ms, 'SETUP_ABSENT', 'ok'),
                        'decision': result['decision'],
                        'reasons': reasons[:12],
                        'engine_data_grade': result.get('data_grade'),
                        'engine_data_cutoff_ms': result.get('data_cutoff_ms'),
                    })
                except (FeedNotReady, ValueError) as exc:
                    reason = str(exc)
                    if not isinstance(exc, FeedNotReady):
                        reason = 'ENGINE_OR_WALLET_CONTRACT_ERROR'
                    records.append(_no_trade(
                        consumer, symbol, setup, now_ms,
                        'DATA_NOT_READY:' + reason[:70]
                        if isinstance(exc, FeedNotReady) else reason, 'ok'))
    return {
        'schema': 'long-shadow-observer-v1',
        'evaluation_time_utc': datetime.fromtimestamp(
            now_ms / 1000, tz=timezone.utc).isoformat(),
        'as_of_ms': now_ms, 'mode': 'research_observation_only',
        'frozen_engine_sha256': PINNED_ENGINE_SHA256,
        'engine_evaluated': enabled,
        'can_execute_orders': False, 'orders_created': 0,
        'wallets_modified': False, 'paper_eligible': False,
        'records': records,
    }


def observed_result(*, feed, now_ms, roots, brain_source=None,
                    frozen_engine_path=None, enabled=False):
    """Entry point with SHA-pinned loader, no programmatic exchange actions."""
    engine = frozen_engine(frozen_engine_path) if enabled else None
    return evaluate_observation(
        feed=feed, now_ms=now_ms, roots=roots, brain_source=brain_source,
        engine=engine, enabled=enabled)
