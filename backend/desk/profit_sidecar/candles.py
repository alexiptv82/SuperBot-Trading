"""Public Bitget 15m candles (no API keys). Observation only.

Bitget stamps each row with the candle OPEN time and the newest row is the candle still forming.
Bar.close_ms in the profit package is the exclusive close, so close_ms = open + 15 minutes, and
features.extract drops any bar whose close_ms is after the evaluation clock (the forming one).

That timestamp semantic is an assumption about an external API that this build could not exercise
(no network from the build sandbox). It is therefore CHECKED on every download: the newest row must
be the candle that contains the evaluation clock, or the one just before it. If the exchange ever
stamps close times instead, every download freezes with `candle_clock_mismatch`: a shifted series
is never fed to the Profit Manager silently.
"""
import json
import urllib.request

from ..profit.features import Bar
from .common import Freeze

BASE = "https://api.bitget.com"
INTERVAL_MS = 900_000


def fetch_bars(symbol, *, asof_ms, limit=40, opener=urllib.request.urlopen, base=BASE):
    sym = str(symbol).upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    url = f"{base}/api/v2/mix/market/candles?symbol={sym}&productType=USDT-FUTURES&granularity=15m&limit={limit}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read())
    except Exception:
        raise Freeze("candles_unavailable") from None
    if not isinstance(payload, dict) or payload.get("code") != "00000" or not isinstance(payload.get("data"), list):
        raise Freeze("candles_rejected")
    try:
        rows = sorted({int(float(r[0])): r for r in payload["data"]}.items())
        bars = tuple(Bar(opened + INTERVAL_MS, float(r[1]), float(r[2]), float(r[3]), float(r[4])) for opened, r in rows)
    except (ValueError, TypeError, IndexError):
        raise Freeze("candles_malformed") from None
    if not bars:
        raise Freeze("candles_empty")
    containing = asof_ms - asof_ms % INTERVAL_MS
    newest_open = bars[-1].close_ms - INTERVAL_MS
    if newest_open not in (containing, containing - INTERVAL_MS):
        raise Freeze("candle_clock_mismatch")
    return bars
