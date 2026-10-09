"""Test in-process del motore con i profili di rischio (portafogli virtuali
Conservativo / Aggressivo), dei costi del paper trading e delle impostazioni.

Exchange e segnali sono finti (nessuna rete); DB SQLite temporaneo.
Lanciare dalla cartella backend/:  python -m pytest tests/test_profiles_engine.py
"""
import asyncio
import base64
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

import pytest

# Ambiente PRIMA di importare l'app (config e database leggono env all'import).
# Se un altro file di test ha gia' importato database, vale il suo DB: i test
# qui sotto ripuliscono le tabelle che usano.
_TMP = tempfile.mkdtemp(prefix="sb-profiles-test-")
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "t.db"))
os.environ.setdefault("DASHBOARD_PASSWORD_B64", base64.b64encode(b"IniziALE-pw-2026").decode())
os.environ["TELEGRAM_BOT_TOKEN"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(_TMP)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

import auth  # noqa: E402
import bot_engine  # noqa: E402
import database  # noqa: E402
import risk_settings  # noqa: E402
import server  # noqa: E402
from bot_engine import bot  # noqa: E402
from config import config  # noqa: E402
from database import AuditLog, RiskSettings, SessionLocal, Trade  # noqa: E402

SYMBOL = "BTCUSDT"


class FakeExchange:
    """Exchange finto: prezzi controllati dal test, nessuna rete."""

    def __init__(self):
        self.prices = {SYMBOL: 100.0}
        self.created = []

    async def get_ohlcv(self, symbol, timeframe="1m", limit=100):
        step = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000}[timeframe]
        base = (int(time.time() * 1000) // step) * step
        return [[base - (limit - 1 - i) * step, 100.0, 100.5, 99.5, 100.0, 10.0] for i in range(limit)]

    async def get_ticker(self, symbol):
        return {"symbol": symbol, "price": self.prices[symbol], "bid": None, "ask": None,
                "volume": 0, "change_24h": 0}

    async def create_order(self, **kw):
        self.created.append(kw)
        # come l'exchange vero: un id diverso per ogni ordine (order_id e' univoco nel DB)
        return {"id": f"PAPER_{kw['symbol']}_{len(self.created)}", "client_order_id": "cid", "sl_order_id": None, "tp_order_id": None}

    async def close_position(self, symbol, side, quantity):
        return {}

    async def fetch_open_positions(self, symbols=None):
        return []


def analysis(signal="long", strength=90, trade_type="medium", atr=0.05):
    return {"signal": signal, "strength": strength, "trade_type": trade_type, "main_trend": "bullish",
            "indicators_1m": {"atr": atr, "rsi": 50.0}, "reasons": ["test"]}


def _wipe():
    db = SessionLocal()
    try:
        db.query(Trade).delete()
        db.query(AuditLog).delete()
        db.query(RiskSettings).delete()
        db.commit()
    finally:
        db.close()


def run(coro):
    return asyncio.run(coro)


async def cycle(symbol=SYMBOL):
    await bot._analyze_and_trade(symbol)
    await asyncio.sleep(0)


async def monitor():
    await bot._monitor_open_trades()
    await asyncio.sleep(0)


def rows():
    db = SessionLocal()
    try:
        return db.query(Trade).order_by(Trade.id).all()
    finally:
        db.close()


@pytest.fixture
def env(monkeypatch):
    fx = FakeExchange()
    state = {"analysis": analysis()}
    monkeypatch.setattr(bot_engine, "exchange", fx)
    monkeypatch.setattr(bot_engine.signal_engine, "analyze", lambda *a, **k: state["analysis"])
    monkeypatch.setattr(bot_engine.notifier, "enabled", False)
    for attr, value in (("TRADING_MODE", "paper"), ("IS_PAPER", True), ("RISK_MODE", "both"),
                        ("INITIAL_CAPITAL", 1000.0), ("MAX_OPEN_POSITIONS", 3),
                        ("MAX_DAILY_LOSS_PERCENT", 5.0), ("MAX_LEVERAGE", 10),
                        ("PAPER_FEE_BPS", 6.0), ("PAPER_SLIPPAGE_BPS", 2.0),
                        ("TRADING_PAIRS", [SYMBOL])):
        monkeypatch.setattr(config, attr, value)
    _wipe()
    bot._sync_active()
    bot._reload_state()
    yield fx, state
    _wipe()
    bot._reload_state()


# ── Apertura ─────────────────────────────────────────────────────────────────

def test_both_mode_opens_one_independent_trade_per_profile(env):
    fx, _ = env
    run(cycle())
    c = list(bot.portfolios["conservative"].open_trades.values())
    a = list(bot.portfolios["aggressive"].open_trades.values())
    assert len(c) == 1 and len(a) == 1 and len(fx.created) == 2
    assert c[0]["order_id"].endswith("-conservative") and a[0]["order_id"].endswith("-aggressive")
    assert c[0]["order_id"] != a[0]["order_id"]
    # forza 90 -> leva 6 (conservativo, max 10) e 16 (aggressivo, max 30)
    assert c[0]["leverage"] == 6 and a[0]["leverage"] == 16
    assert a[0]["quantity"] > c[0]["quantity"]
    # slippage avverso sull'ingresso e liquidazione stimata sotto l'ingresso (long)
    assert c[0]["entry_price"] == pytest.approx(100.02)
    assert c[0]["liq_price"] < c[0]["stop_loss"] < c[0]["entry_price"] or c[0]["liq_price"] < c[0]["entry_price"]
    db = rows()
    assert [r.profile for r in db] == ["conservative", "aggressive"]
    assert all(r.margin and r.liq_price and r.status == "open" for r in db)


def test_weak_signal_below_profile_threshold_opens_nothing(env):
    _, state = env
    state["analysis"] = analysis(strength=60)           # sotto la soglia 70 di entrambi i profili
    run(cycle())
    assert rows() == []


def test_mode_selects_which_portfolios_trade(env, monkeypatch):
    monkeypatch.setattr(config, "RISK_MODE", "aggressive")
    bot._sync_active()
    run(cycle())
    assert [r.profile for r in rows()] == ["aggressive"]
    assert bot.portfolios["conservative"].open_trades == {}


def test_symbol_already_open_is_not_opened_twice_in_the_same_portfolio(env):
    run(cycle())
    run(cycle())
    assert len(rows()) == 2


def test_max_open_positions_is_per_portfolio(env, monkeypatch):
    monkeypatch.setattr(config, "MAX_OPEN_POSITIONS", 1)
    fx, _ = env
    fx.prices["ETHUSDT"] = 100.0
    run(cycle(SYMBOL))
    run(cycle("ETHUSDT"))
    assert len(rows()) == 2                              # 1 per portafoglio, non 1 in totale


# ── Chiusura e costi ─────────────────────────────────────────────────────────

def test_take_profit_closes_both_with_fees_and_updates_capital(env):
    fx, _ = env
    run(cycle())
    fx.prices[SYMBOL] = 103.0                            # oltre il TP (102.4)
    run(monitor())
    db = rows()
    assert all(r.status == "closed" and r.close_reason == "tp" for r in db)
    c = next(r for r in db if r.profile == "conservative")
    # 2.0 unita' : ingresso 100.02, uscita al TP 102.4
    gross = 2.0 * (102.4 - 100.02)
    fees = 2.0 * 100.02 * 0.0006 + 2.0 * 102.4 * 0.0006
    assert c.gross_pnl == pytest.approx(gross, abs=1e-3)
    assert c.fees == pytest.approx(fees, abs=1e-3)
    assert c.pnl == pytest.approx(gross - fees, abs=1e-3)
    pf = bot.portfolios["conservative"]
    assert pf.capital == pytest.approx(1000.0 + c.pnl, abs=1e-3)
    assert pf.daily_pnl == pytest.approx(c.pnl, abs=1e-3)
    # il portafoglio aggressivo e' indipendente
    assert bot.portfolios["aggressive"].capital != pf.capital


def test_stop_loss_fills_with_adverse_slippage_and_costs(env):
    fx, _ = env
    run(cycle())
    fx.prices[SYMBOL] = 98.0                             # sotto lo stop (99.2), sopra la liquidazione
    run(monitor())
    for r in rows():
        assert r.close_reason == "sl"
        assert r.exit_price == pytest.approx(98.0 * (1 - 0.0002))
        assert r.pnl < 0 and r.fees > 0 and r.pnl < r.gross_pnl


def test_crash_beyond_liquidation_loses_margin_plus_entry_fee(env):
    fx, _ = env
    run(cycle())
    fx.prices[SYMBOL] = 50.0
    run(monitor())
    for r in rows():
        assert r.close_reason == "liq"
        entry_fee = r.quantity * r.entry_price * 0.0006
        assert r.pnl == pytest.approx(-(r.margin + entry_fee), abs=1e-3)
        assert r.fees == pytest.approx(entry_fee, abs=1e-3)


def test_short_trade_mirrors_long(env):
    fx, state = env
    state["analysis"] = analysis(signal="short")
    run(cycle())
    t = list(bot.portfolios["conservative"].open_trades.values())[0]
    assert t["side"] == "short" and t["entry_price"] == pytest.approx(99.98) and t["liq_price"] > t["entry_price"]
    fx.prices[SYMBOL] = 97.0                             # sotto il TP (97.6)
    run(monitor())
    r = next(x for x in rows() if x.profile == "conservative")
    assert r.close_reason == "tp" and r.pnl > 0


def test_close_all_positions_pays_costs_too(env):
    fx, _ = env
    run(cycle())
    fx.prices[SYMBOL] = 100.3
    closed = run(bot.close_all_positions(reason="manual_telegram"))
    assert closed == [SYMBOL, SYMBOL]
    for r in rows():
        assert r.status == "closed" and r.close_reason == "manual_telegram"
        assert r.exit_price == pytest.approx(100.3 * (1 - 0.0002))
        assert r.fees > 0


# ── Perdita giornaliera, giorno, ripristino ──────────────────────────────────

def test_daily_limit_pauses_only_that_portfolio_until_next_day(env):
    async def check():
        return bot._check_daily_limits()
    pf_c, pf_a = bot.portfolios["conservative"], bot.portfolios["aggressive"]
    pf_c.daily_pnl = -60.0                                # -6% con limite 5%
    assert run(check()) is False                          # l'altro puo' ancora operare
    assert [p.name for p in bot._tradable()] == ["aggressive"]
    pf_a.daily_pnl = -60.0
    assert run(check()) is True                           # ora sono tutti in pausa
    assert bot._tradable() == []
    # a mezzanotte UTC si riparte da zero
    for pf in (pf_c, pf_a):
        pf.day = (datetime.utcnow() - timedelta(days=1)).date()
    bot._roll_day()
    assert pf_c.daily_pnl == 0.0 and pf_c.halted_day is None
    assert [p.name for p in bot._tradable()] == ["conservative", "aggressive"]


def test_capital_open_trades_and_daily_pnl_are_rebuilt_from_db(env):
    fx, _ = env
    run(cycle())
    fx.prices[SYMBOL] = 103.0
    run(monitor())                                        # chiude i due trade in utile
    expected = bot.portfolios["conservative"].capital
    pnl_today = bot.portfolios["conservative"].daily_pnl
    run(cycle())                                          # riapre (prezzo 103)
    pf = bot.portfolios["conservative"]
    pf.capital, pf.daily_pnl, pf.open_trades = 0.0, 0.0, {}
    bot._reload_state()                                   # come dopo un riavvio
    assert pf.capital == pytest.approx(expected, abs=1e-3)
    assert pf.daily_pnl == pytest.approx(pnl_today, abs=1e-3)
    assert len(pf.open_trades) == 1
    t = list(pf.open_trades.values())[0]
    assert t["margin"] and t["liq_price"] and t["profile"] == "conservative"


def test_legacy_open_trade_is_still_closed_without_costs(env):
    fx, _ = env
    bot._save_trade({"order_id": "OLD1", "symbol": SYMBOL, "side": "long", "trade_type": "scalp",
                     "entry_price": 100.0, "quantity": 1.0, "leverage": 5,
                     "stop_loss": 99.0, "take_profit": 101.0})
    bot._reload_state()
    assert "OLD1" in bot.portfolios["legacy"].open_trades
    assert any(p["name"] == "legacy" for p in bot.get_status()["portfolios"])
    fx.prices[SYMBOL] = 101.5
    run(monitor())
    r = rows()[0]
    assert r.status == "closed" and r.close_reason == "tp"
    assert r.pnl == pytest.approx(1.5) and r.fees == 0.0
    assert not any(p["name"] == "legacy" for p in bot.get_status()["portfolios"])    # chiuso: sparisce


# ── Modalita' reale e stato ──────────────────────────────────────────────────

def test_live_mode_is_always_conservative_with_the_user_leverage_ceiling(env, monkeypatch):
    fx, _ = env
    monkeypatch.setattr(config, "TRADING_MODE", "live")
    monkeypatch.setattr(config, "IS_PAPER", False)
    monkeypatch.setattr(config, "MAX_LEVERAGE", 5)
    monkeypatch.setattr(config, "RISK_MODE", "both")      # in reale viene ignorato
    assert bot._effective_mode() == "conservative"
    bot._sync_active()
    assert [n for n, p in bot.portfolios.items() if p.active] == ["conservative"]
    assert bot._effective_profile(bot.portfolios["conservative"]).max_lev == 5
    run(cycle())
    (r,) = rows()
    assert r.profile == "conservative" and r.leverage <= 5
    assert r.entry_price == 100.0 and r.liq_price is None          # niente slippage simulato in reale
    assert fx.created[0]["leverage"] <= 5


def test_status_reports_each_portfolio(env):
    run(cycle())
    s = bot.get_status()
    assert s["risk_mode"] == "both"
    assert [p["name"] for p in s["portfolios"]] == ["conservative", "aggressive"]
    assert s["open_positions"] == 2 and s["capital"] == pytest.approx(2000.0)
    assert all("paused" in p and "fees_paid" in p for p in s["portfolios"])


# ── Impostazioni (API) ───────────────────────────────────────────────────────

@pytest.fixture
def api(env):
    auth.init_auth()
    # Se un altro file di test ha cambiato/scaduto la password, riparte da una
    # password "appena cambiata" cosi' il token di sessione e' valido.
    auth._update_settings(password_changed_at=datetime.utcnow())
    return TestClient(server.app), {"Authorization": f"Bearer {auth.create_session_token('full')}"}


def _risk_body(**extra):
    return {"max_leverage": 10, "max_daily_loss_percent": 5, "max_open_positions": 3, **extra}


def test_config_lists_profiles_and_costs(api):
    client, h = api
    cfg = client.get("/api/bot/config", headers=h).json()
    assert cfg["risk_mode"] == "both" and cfg["effective_risk_mode"] == "both"
    assert cfg["risk_modes"] == ["conservative", "aggressive", "both"]
    assert cfg["profiles"]["aggressive"]["max_leverage"] == 30
    assert cfg["profiles"]["conservative"]["max_leverage"] == 10
    assert cfg["paper_costs"] == {"fee_bps": 6.0, "slippage_bps": 2.0}


def test_risk_mode_is_saved_applied_and_persisted(api):
    client, h = api
    r = client.put("/api/bot/config/risk", headers=h, json=_risk_body(risk_mode="aggressive"))
    assert r.status_code == 200 and r.json()["applied"]["risk_mode"] == "aggressive"
    assert config.RISK_MODE == "aggressive"
    assert client.get("/api/bot/status", headers=h).json()["risk_mode"] == "aggressive"
    db = SessionLocal()
    try:
        assert db.query(RiskSettings).first().risk_mode == "aggressive"
    finally:
        db.close()
    # dopo un riavvio (config ricaricata da .env) il valore salvato torna
    config.RISK_MODE = "both"
    risk_settings.load_overrides()
    assert config.RISK_MODE == "aggressive"


def test_old_client_without_risk_mode_keeps_the_current_mode(api):
    client, h = api
    client.put("/api/bot/config/risk", headers=h, json=_risk_body(risk_mode="conservative"))
    r = client.put("/api/bot/config/risk", headers=h, json=_risk_body(max_open_positions=2))
    assert r.status_code == 200
    assert config.RISK_MODE == "conservative" and r.json()["applied"]["risk_mode"] == "conservative"


def test_invalid_risk_mode_is_rejected_and_nothing_is_saved(api):
    client, h = api
    before = config.RISK_MODE
    r = client.put("/api/bot/config/risk", headers=h, json=_risk_body(max_leverage=7, risk_mode="folle"))
    assert r.status_code == 400
    assert config.RISK_MODE == before and config.MAX_LEVERAGE == 10


def test_trades_and_performance_expose_profile_costs(api):
    client, h = api
    run(cycle())
    env_fx = bot_engine.exchange
    env_fx.prices[SYMBOL] = 103.0
    run(monitor())
    trades = client.get("/api/trades", headers=h).json()
    assert {t["profile"] for t in trades} == {"conservative", "aggressive"}
    assert all(t["fees"] > 0 and t["gross_pnl"] > t["pnl"] for t in trades)
    perf = client.get("/api/performance", headers=h).json()
    assert set(perf["by_profile"]) == {"conservative", "aggressive"}
    assert perf["total_fees"] == pytest.approx(sum(t["fees"] for t in trades), abs=0.02)
    assert set(perf["equity_by_profile"]) == {"conservative", "aggressive"}
    assert perf["by_profile"]["aggressive"]["label"] == "Aggressivo"


def test_open_trades_endpoint_includes_profile_label(api):
    client, h = api
    run(cycle())
    open_trades = client.get("/api/trades/open", headers=h).json()
    assert sorted(t["profile_label"] for t in open_trades) == ["Aggressivo", "Conservativo"]


# ── Migrazione di un DB vecchio ──────────────────────────────────────────────

def test_old_database_gets_the_new_columns_without_losing_data(monkeypatch, tmp_path):
    path = tmp_path / "old.db"
    old = create_engine(f"sqlite:///{path}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE trades (id INTEGER PRIMARY KEY, order_id VARCHAR, symbol VARCHAR, "
                          "side VARCHAR, entry_price FLOAT, quantity FLOAT, leverage INTEGER, "
                          "stop_loss FLOAT, take_profit FLOAT, pnl FLOAT, status VARCHAR, "
                          "client_order_id VARCHAR, sl_order_id VARCHAR, tp_order_id VARCHAR)"))
        conn.execute(text("CREATE TABLE risk_settings (id INTEGER PRIMARY KEY, max_leverage INTEGER, "
                          "max_daily_loss_percent FLOAT, max_open_positions INTEGER, updated_at DATETIME)"))
        conn.execute(text("INSERT INTO trades (order_id, symbol, side, pnl, status) VALUES ('X1', 'BTCUSDT', 'long', 1.5, 'closed')"))
        conn.execute(text("INSERT INTO risk_settings (id, max_leverage) VALUES (1, 7)"))
    monkeypatch.setattr(database, "engine", old)
    database._migrate_add_missing_columns()
    insp = inspect(old)
    assert {"profile", "margin", "liq_price", "gross_pnl", "fees"} <= {c["name"] for c in insp.get_columns("trades")}
    assert "risk_mode" in {c["name"] for c in insp.get_columns("risk_settings")}
    with old.connect() as conn:
        assert conn.execute(text("SELECT pnl, profile FROM trades WHERE order_id = 'X1'")).fetchone() == (1.5, None)
        assert conn.execute(text("SELECT max_leverage, risk_mode FROM risk_settings")).fetchone() == (7, None)
    database._migrate_add_missing_columns()        # idempotente
