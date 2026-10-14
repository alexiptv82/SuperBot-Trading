"""Test della vista live (live_view): P&L del giorno, limite di perdita, interruttore manuale.

Niente rete, niente bot: si costruiscono a mano i file che il bot scrive. Le regole controllate qui
devono restare uguali a quelle di backend/desk/cli.py (mezzanotte UTC, solo P&L realizzato,
interruttore spento di default).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live_view as lv  # noqa: E402

# 2027-01-15 12:00:00 UTC
NOW = 1_800_014_400.0
MIDNIGHT_MS = int(NOW // 86400 * 86400 * 1000)


def _write(d, name, obj):
    with open(os.path.join(d, name), "w") as f:
        json.dump(obj, f)


def _trade(i, net, close_ms):
    return {"id": i, "symbol": "BTC", "side": 1, "net": net, "close_ms": close_ms}


def _write_history(d, trades):
    with open(os.path.join(d, "trade_history.jsonl"), "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")


def test_utc_midnight_is_start_of_utc_day():
    assert lv.utc_midnight_ms(NOW) == MIDNIGHT_MS
    assert lv.utc_midnight_ms(NOW) % 86_400_000 == 0


def test_daily_pnl_counts_only_today_and_partials():
    trades = [
        _trade(1, -50.0, MIDNIGHT_MS - 1),          # ieri sera: non conta
        _trade(2, -30.0, MIDNIGHT_MS),              # esattamente a mezzanotte: conta
        _trade(3, 10.0, MIDNIGHT_MS + 3_600_000),
        {"id": 4, "net": None, "close_ms": MIDNIGHT_MS + 5},   # senza net: ignorato
    ]
    assert lv.daily_pnl(trades, NOW) == -20.0
    assert lv.total_pnl(trades) == -70.0


def test_trading_switch_is_off_by_default():
    with tempfile.TemporaryDirectory() as d:
        assert lv.read_trading_enabled(d) is False                       # file assente
        with open(os.path.join(d, lv.TRADING_FLAG), "w") as f:
            f.write("{non e' json")
        assert lv.read_trading_enabled(d) is False                       # file rovinato
        _write(d, lv.TRADING_FLAG, {"ts": 1})
        assert lv.read_trading_enabled(d) is False                       # manca il campo
        _write(d, lv.TRADING_FLAG, {"enabled": "perche' no"})
        assert lv.read_trading_enabled(d) is True                        # valore vero = acceso


def test_trading_switch_roundtrip_is_atomic():
    with tempfile.TemporaryDirectory() as d:
        sub = os.path.join(d, "nuova", "cartella")                       # la cartella puo' non esserci
        lv.write_trading_enabled(sub, True, now=NOW)
        assert lv.read_trading_enabled(sub) is True
        lv.write_trading_enabled(sub, False, now=NOW)
        assert lv.read_trading_enabled(sub) is False
        assert sorted(os.listdir(sub)) == [lv.TRADING_FLAG]              # nessun .tmp rimasto
        with open(os.path.join(sub, lv.TRADING_FLAG)) as f:
            assert json.load(f) == {"enabled": False, "ts": int(NOW * 1000)}


def test_portfolio_limit_is_capital_times_pct():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 7, "main": {"positions": {}}})
        p = lv.build_portfolio(d, "1000", "25", now=NOW)
        assert p["capital_usdt"] == 1000.0
        assert p["daily_loss_limit_usdt"] == 250.0                       # per bot, non sulla somma
        assert p["daily_limit_hit"] is False


def test_portfolio_limit_hit_exactly_at_limit():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        _write_history(d, [_trade(1, -250.0, MIDNIGHT_MS + 1000)])
        p = lv.build_portfolio(d, 1000, 25, now=NOW)
        assert p["daily_pnl"] == -250.0 and p["daily_limit_hit"] is True   # come il bot: <= -limite
        _write_history(d, [_trade(1, -249.99, MIDNIGHT_MS + 1000)])
        assert lv.build_portfolio(d, 1000, 25, now=NOW)["daily_limit_hit"] is False


def test_portfolio_ignores_yesterday_for_the_limit_but_not_for_total():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        _write_history(d, [_trade(1, -400.0, MIDNIGHT_MS - 3_600_000), _trade(2, 20.0, MIDNIGHT_MS + 10)])
        p = lv.build_portfolio(d, 1000, 25, now=NOW)
        assert p["daily_pnl"] == 20.0 and p["daily_limit_hit"] is False
        assert p["total_pnl"] == -380.0 and p["total_closed"] == 2


def test_portfolio_bad_capital_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as d:
        for bad in (None, "", "abc", "0", "-5"):
            p = lv.build_portfolio(d, bad, bad, now=NOW)
            assert p["capital_usdt"] == lv.DEFAULT_CAPITAL
            assert p["daily_loss_limit_usdt"] == lv.DEFAULT_CAPITAL * lv.DEFAULT_LOSS_PCT / 100


def test_portfolio_positions_and_missing_data():
    with tempfile.TemporaryDirectory() as d:
        p = lv.build_portfolio(d, 1000, 25, now=NOW)                     # nessun file del bot
        assert p["available"] is False and p["positions"] == [] and p["bot_mode"] is None
        assert p["trading_enabled"] is False
        _write(d, "state_v2.json", {"cycle": 3, "main": {"positions": {
            "ETH": {"side": -1, "entry": 3000.0, "leverage": 5, "total_margin": 100.0, "sl": 3100.0,
                    "tp": 2800.0, "trade_type": "scalp", "open_ms": 1},
            "rotto": "non e' un dict"}}})
        p = lv.build_portfolio(d, 1000, 25, now=NOW)
        assert p["available"] is True and p["open_positions"] == 1
        assert p["positions"][0]["symbol"] == "ETH" and p["positions"][0]["margin"] == 100.0


def test_bot_mode_comes_from_heartbeat_not_from_secrets():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        assert lv.build_portfolio(d, 1000, 25, now=NOW)["bot_mode"] is None          # bot senza battito
        _write(d, "heartbeat.json", {"ts": NOW - 12.0})                               # codice vecchio: niente exec_mode
        assert lv.build_portfolio(d, 1000, 25, now=NOW)["bot_mode"] is None
        _write(d, "heartbeat.json", {"ts": NOW - 12.0, "exec_mode": "paper"})
        p = lv.build_portfolio(d, 1000, 25, now=NOW)
        assert p["bot_mode"] == "paper" and p["heartbeat_age_s"] == 12.0
        _write(d, "heartbeat.json", {"ts": NOW - 2.0, "exec_mode": "live"})
        assert lv.build_portfolio(d, 1000, 25, now=NOW)["bot_mode"] == "live"


def test_wallet_credentials_use_only_the_read_only_key():
    full = {"BITGET_RO_API_KEY": " k ", "BITGET_RO_SECRET_KEY": "s", "BITGET_RO_PASSPHRASE": "p"}
    assert lv.wallet_credentials(full) == ("k", "s", "p")                  # spazi ai bordi tolti
    for missing in lv.WALLET_KEY_NAMES:                                    # ne manca una sola -> niente
        partial = {k: v for k, v in full.items() if k != missing}
        assert lv.wallet_credentials(partial) is None
    assert lv.wallet_credentials({**full, "BITGET_RO_SECRET_KEY": "  "}) is None
    # le chiavi di trading NON vanno mai usate dall'app, nemmeno se presenti
    trading_only = {"BITGET_API_KEY": "a", "BITGET_SECRET_KEY": "b", "BITGET_PASSPHRASE": "c"}
    assert lv.wallet_credentials(trading_only) is None
    assert lv.wallet_credentials({}) is None
