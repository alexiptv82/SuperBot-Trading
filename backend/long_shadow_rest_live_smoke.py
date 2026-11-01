"""Public Bitget v3 REST candles smoke test (CI research; NO TRADING).

One pass, only eight unauthenticated HTTPS GET requests; 1m,15m,1H,4H for
BTCUSDT and ETHUSDT. No API keys, secrets, wallets or brokers. Only reports
transport response status, count, timestamps and checks; never logs prices
or any request/response body.

Unlike mocked unit tests, this verifies what Bitget actually returns on the
GitHub-hosted runner. Failure is surfaced, not hidden.
"""
from __future__ import annotations

import json
import sys
import time

from long_shadow_rest_closed import (
    INTERVALS, SYMBOLS, FeedNotReady, parse_closed_response, public_candles,
)


def run():
    results = []
    errors = []
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            began_ms = int(time.time() * 1000)
            try:
                payload, received_ms = public_candles(
                    symbol, interval, timeout_s=7)
                bars = parse_closed_response(
                    payload, symbol, interval,
                    started_ms=began_ms, received_ms=received_ms)
                latest = bars[-1]['close_ms']
                result = {
                    'symbol': symbol, 'interval': interval,
                    'status': 'PASS',
                    'closed_bars': len(bars),
                    'last_close_utc_ms': latest,
                    'observed_at_utc_ms': received_ms,
                    'latest_lag_seconds': round((received_ms - latest)/1000, 3),
                    'first_bar_available_at_utc_ms': bars[0]['available_at_ms'],
                }
            except (FeedNotReady, ValueError, TimeoutError) as exc:
                result = {
                    'symbol': symbol, 'interval': interval,
                    'status': 'FAIL',
                    'reason': str(exc)[:90],
                }
                errors.append(f"{symbol}/{interval}: {type(exc).__name__}: {str(exc)[:90]}")
            results.append(result)
            # Conservative rate budget, far below Bitget's 20req/s/IP.
            time.sleep(.25)

    report = {
        'schema': 'long-public-rest-live-smoke-v1',
        'read_only': True,
        'calls_attempted': len(results),
        'source': 'api.bitget.com/api/v3/market/candles',
        'orders_created': 0,
        'keys_used': False,
        'passed': len(errors) == 0 and len(results) == 8,
        'series': results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if errors:
        print('PUBLIC_REST_SMOKE_FAILED: ' + ' | '.join(errors),
              file=sys.stderr)
        return 2
    print('PUBLIC_REST_SMOKE_PASS: all 8 real Bitget series validated')
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
