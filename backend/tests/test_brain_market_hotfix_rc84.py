"""Brain RC84 hotfix regressions. Offline, no VPS/model/network and no trading."""
import re
from decimal import Decimal

from backend.v3.lab_tools.fetch_candles import fetch_rows
from backend.v3.runner.contracts import parse_contract_rules

MS = 900_000
END = 1_750_000_000_000 // MS * MS


def _contract(symbol, max_lev):
    return {"symbol": symbol, "symbolStatus": "normal", "sizeMultiplier": "0.0001",
            "minTradeUSDT": "5", "maxLever": str(max_lev)}


def test_high_bitget_metadata_is_accepted_but_bad_above_200_rejected():
    inp = {"code": "00000", "data": [
        _contract("BTCUSDT", 150), _contract("ETHUSDT", 200),
        _contract("INVALIDUSDT", 201)]}
    rules = parse_contract_rules(inp, maintenance_fraction=Decimal("0.005"))
    assert rules["BTCUSDT"]["exchange_leverage_limit"] == 150
    assert rules["ETHUSDT"]["exchange_leverage_limit"] == 200
    assert "INVALIDUSDT" not in rules
    # Max leverage requested by Brain remains limited by a SEPARATE policy (20x-50x).


def _fake_history(start, end):
    return {t: [str(t), "100", "101", "99", "100", "2", "200"]
            for t in range(start, end + MS, MS)}


def _market_response(hist, calls, *, inclusive):
    def answer(url):
        query = dict(re.findall(r"(\w+)=([^&]+)", url.split("?", 1)[1]))
        a, b, n = (int(query[x]) for x in ("startTime", "endTime", "limit"))
        assert a % MS == b % MS == 0, "Bitget boundaries must align"
        assert n <= 200
        calls.append((a, b, n))
        rows = [hist[t] for t in sorted(hist) if a <= t <= b if inclusive or t < b]
        return {"code": "00000", "data": rows[-n:]}
    return answer


def test_sol_3000_15m_candles_recovered_with_aligned_pagination():
    start = END - 3000 * MS
    hist = _fake_history(start, END)
    calls = []
    rows = fetch_rows("SOLUSDT", start, END, candle_ms=MS,
                      get_json=_market_response(hist, calls, inclusive=False))
    assert len(rows) == 3000
    assert sorted(rows) == list(range(start, END, MS))
    assert len(calls) >= 15
    assert END not in rows


def test_inclusive_endpoint_does_not_lose_one_bar_per_200():
    start = END - 601 * MS
    hist = _fake_history(start, END)
    calls = []
    rows = fetch_rows("BTCUSDT", start, END, candle_ms=MS,
                      get_json=_market_response(hist, calls, inclusive=True))
    assert sorted(rows) == list(range(start, END, MS))
    assert len(calls) >= 4
    assert END not in rows


def test_missing_candle_remains_missing_and_never_interpolated():
    start = END - 210 * MS
    hist = _fake_history(start, END)
    missing = start + 75 * MS
    del hist[missing]
    rows = fetch_rows("ETHUSDT", start, END, candle_ms=MS,
                      get_json=_market_response(hist, [], inclusive=False))
    assert missing not in rows
    assert len(rows) == 209
