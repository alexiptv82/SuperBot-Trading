"""A2c - regole dei contratti Bitget: parser rigido e tabella con ricarico. Nessuna rete."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.v3.runner.contracts import CONTRACTS_URL, ContractRules, parse_contract_rules

D = Decimal
MAINT = D("0.005")


def _c(symbol="BTCUSDT", **kw):
    base = {"symbol": symbol, "symbolStatus": "normal", "sizeMultiplier": "0.0001", "minTradeUSDT": "5",
            "maxLever": "125"}
    base.update(kw)
    return base


def _ok(*items):
    return {"code": "00000", "msg": "success", "data": list(items)}


def test_parse_builds_exact_rules():
    t = parse_contract_rules(_ok(_c(), _c("ETHUSDT", sizeMultiplier="0.01", minTradeUSDT="5.5", maxLever="100")),
                             maintenance_fraction=MAINT)
    assert t == {
        "BTCUSDT": {"exchange_leverage_limit": 125, "quantity_step": D("0.0001"), "minimum_notional": D("5"),
                    "maintenance_fraction": MAINT},
        "ETHUSDT": {"exchange_leverage_limit": 100, "quantity_step": D("0.01"), "minimum_notional": D("5.5"),
                    "maintenance_fraction": MAINT}}
    assert type(t["BTCUSDT"]["exchange_leverage_limit"]) is int


@pytest.mark.parametrize("bad", [
    _c(symbolStatus="maintain"), _c(symbolStatus=None), _c(symbol=""), _c(symbol=5), _c(sizeMultiplier="0"),
    _c(sizeMultiplier="-1"), _c(sizeMultiplier=0.01), _c(sizeMultiplier="x"), _c(sizeMultiplier="NaN"),
    _c(sizeMultiplier=None), _c(minTradeUSDT="-1"), _c(minTradeUSDT=None), _c(minTradeUSDT="Infinity"),
    _c(maxLever="0"), _c(maxLever="126"), _c(maxLever="10.5"), _c(maxLever=10), _c(maxLever=None), "x", None,
    {"symbol": "BTCUSDT"}])
def test_a_malformed_or_inactive_contract_is_dropped_and_good_ones_survive(bad):
    t = parse_contract_rules(_ok(bad, _c("ETHUSDT")), maintenance_fraction=MAINT)
    assert list(t) == ["ETHUSDT"]


def test_boundary_values_are_accepted():
    t = parse_contract_rules(_ok(_c(maxLever="1", minTradeUSDT="0"), _c("B", maxLever="125")),
                             maintenance_fraction=MAINT)
    assert t["BTCUSDT"]["exchange_leverage_limit"] == 1 and t["BTCUSDT"]["minimum_notional"] == D("0")
    assert t["B"]["exchange_leverage_limit"] == 125


def test_duplicate_symbol_keeps_the_first():
    t = parse_contract_rules(_ok(_c(maxLever="10"), _c(maxLever="50")), maintenance_fraction=MAINT)
    assert t["BTCUSDT"]["exchange_leverage_limit"] == 10


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"code": "40001", "data": []}, {"code": "00000"},
                                     {"code": "00000", "data": "x"}, _ok(), _ok(_c(symbolStatus="off")),
                                     {"code": 0, "data": [_c()]}])
def test_an_unexpected_response_is_refused(payload):
    with pytest.raises(ValueError) as e:
        parse_contract_rules(payload, maintenance_fraction=MAINT)
    assert str(e.value) == "invalid_contracts"


@pytest.mark.parametrize("m", [D("-0.1"), D("1"), D("2"), 0.005, "0.005", D("NaN"), D("Infinity"), None])
def test_maintenance_fraction_must_be_a_decimal_in_range(m):
    with pytest.raises(ValueError) as e:
        parse_contract_rules(_ok(_c()), maintenance_fraction=m)
    assert str(e.value) == "invalid_maintenance_fraction"
    with pytest.raises(ValueError):
        ContractRules(lambda u: _ok(_c()), maintenance_fraction=m)


def test_zero_maintenance_fraction_is_allowed():
    assert parse_contract_rules(_ok(_c()), maintenance_fraction=D("0"))["BTCUSDT"]["maintenance_fraction"] == D("0")


class _Feed:
    def __init__(self, *responses):
        self.responses, self.urls = list(responses), []

    def __call__(self, url):
        self.urls.append(url)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def test_rules_table_loads_once_and_reloads_after_the_interval():
    feed = _Feed(_ok(_c(maxLever="10")), _ok(_c(maxLever="20")))
    cr = ContractRules(feed, maintenance_fraction=MAINT, refresh_ms=3_600_000)
    assert cr("BTCUSDT") is None                                  # prima del primo caricamento
    assert cr.load(1_000_000) is True and cr("BTCUSDT")["exchange_leverage_limit"] == 10
    assert cr.load(1_000_000 + 3_599_999) is True and len(feed.urls) == 1
    assert cr.load(1_000_000 + 3_600_000) is True and cr("BTCUSDT")["exchange_leverage_limit"] == 20
    assert feed.urls == [CONTRACTS_URL, CONTRACTS_URL]
    assert cr("XYZUSDT") is None


def test_failed_reload_keeps_the_last_good_table_and_retries_next_time():
    feed = _Feed(_ok(_c(maxLever="10")), RuntimeError("rete"), _ok(_c(maxLever="30")))
    cr = ContractRules(feed, maintenance_fraction=MAINT, refresh_ms=60_000)
    assert cr.load(1_000_000) is True
    assert cr.load(1_000_000 + 60_000) is False and cr("BTCUSDT")["exchange_leverage_limit"] == 10
    assert cr.load(1_000_000 + 61_000) is True and cr("BTCUSDT")["exchange_leverage_limit"] == 30


def test_first_load_failure_leaves_no_rules_and_malformed_response_counts_as_failure():
    for resp in (RuntimeError("rete"), {"code": "40001", "data": []}, _ok(_c(symbolStatus="off"))):
        cr = ContractRules(_Feed(resp), maintenance_fraction=MAINT)
        assert cr.load(5_000_000) is False and cr("BTCUSDT") is None


def test_returned_rules_are_copies():
    cr = ContractRules(_Feed(_ok(_c())), maintenance_fraction=MAINT)
    cr.load(5_000_000)
    cr("BTCUSDT")["quantity_step"] = D("99")
    assert cr("BTCUSDT")["quantity_step"] == D("0.0001")


@pytest.mark.parametrize("r", [59_999, 0, -1, True, 1.5, "60000", None])
def test_bad_refresh_interval(r):
    with pytest.raises(ValueError, match="invalid_refresh"):
        ContractRules(lambda u: _ok(_c()), maintenance_fraction=MAINT, refresh_ms=r)


@pytest.mark.parametrize("now", [0, -1, True, 1.5, None])
def test_bad_now(now):
    with pytest.raises(ValueError, match="invalid_now"):
        ContractRules(lambda u: _ok(_c()), maintenance_fraction=MAINT).load(now)
