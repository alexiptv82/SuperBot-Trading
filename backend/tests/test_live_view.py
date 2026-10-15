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
LIVE_SINCE_MS = int(NOW * 1000) - 30 * 86_400_000      # il live e' partito 30 giorni prima di NOW


def _write(d, name, obj):
    with open(os.path.join(d, name), "w") as f:
        json.dump(obj, f)


def _live_hb(d, **extra):
    """Heartbeat di un bot che gira DAVVERO in live: solo cosi' la pagina Live mostra i suoi numeri."""
    _write(d, "heartbeat.json", {"ts": NOW - 2.0, "exec_mode": "live",
                                 "live_since_ms": LIVE_SINCE_MS, **extra})


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
        p = lv.build_portfolio(d, "1000", "25", "live", now=NOW)
        assert p["capital_usdt"] == 1000.0
        assert p["daily_loss_limit_usdt"] == 250.0                       # per bot, non sulla somma
        assert p["daily_limit_hit"] is False


def test_portfolio_limit_hit_exactly_at_limit():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        _live_hb(d)
        _write_history(d, [_trade(1, -250.0, MIDNIGHT_MS + 1000)])
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert p["daily_pnl"] == -250.0 and p["daily_limit_hit"] is True   # come il bot: <= -limite
        _write_history(d, [_trade(1, -249.99, MIDNIGHT_MS + 1000)])
        assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["daily_limit_hit"] is False


def test_portfolio_ignores_yesterday_for_the_limit_but_not_for_total():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        _live_hb(d)
        _write_history(d, [_trade(1, -400.0, MIDNIGHT_MS - 3_600_000), _trade(2, 20.0, MIDNIGHT_MS + 10)])
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert p["daily_pnl"] == 20.0 and p["daily_limit_hit"] is False
        assert p["total_pnl"] == -380.0 and p["total_closed"] == 2


def test_portfolio_bad_capital_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as d:
        for bad in (None, "", "abc", "0", "-5"):
            p = lv.build_portfolio(d, bad, bad, "live", now=NOW)
            assert p["capital_usdt"] == lv.DEFAULT_CAPITAL
            assert p["daily_loss_limit_usdt"] == lv.DEFAULT_CAPITAL * lv.DEFAULT_LOSS_PCT / 100


def test_portfolio_positions_and_missing_data():
    with tempfile.TemporaryDirectory() as d:
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)                     # nessun file del bot
        assert p["available"] is False and p["positions"] == [] and p["bot_mode"] is None
        assert p["trading_enabled"] is False
        _live_hb(d)
        _write(d, "state_v2.json", {"cycle": 3, "main": {"positions": {
            "ETH": {"side": -1, "entry": 3000.0, "leverage": 5, "total_margin": 100.0, "sl": 3100.0,
                    "tp": 2800.0, "trade_type": "scalp", "open_ms": LIVE_SINCE_MS + 1},
            "rotto": "non e' un dict"}}})
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert p["available"] is True and p["open_positions"] == 1
        assert p["positions"][0]["symbol"] == "ETH" and p["positions"][0]["margin"] == 100.0


def test_bot_mode_comes_from_heartbeat_not_from_secrets():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["bot_mode"] is None          # bot senza battito
        _write(d, "heartbeat.json", {"ts": NOW - 12.0})                               # codice vecchio: niente exec_mode
        assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["bot_mode"] is None
        _write(d, "heartbeat.json", {"ts": NOW - 12.0, "exec_mode": "paper"})
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert p["bot_mode"] == "paper" and p["heartbeat_age_s"] == 12.0
        _write(d, "heartbeat.json", {"ts": NOW - 2.0, "exec_mode": "live"})
        assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["bot_mode"] == "live"


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


def test_wallet_credentials_per_bot_use_only_that_bots_read_only_key():
    env = {
        "BITGET_RO_HAWK_API_KEY": "hk", "BITGET_RO_HAWK_SECRET_KEY": "hs", "BITGET_RO_HAWK_PASSPHRASE": "hp",
        "BITGET_RO_BULL_API_KEY": "bk", "BITGET_RO_BULL_SECRET_KEY": "bs", "BITGET_RO_BULL_PASSPHRASE": "bp",
    }
    assert lv.wallet_key_names("hawk") == ("BITGET_RO_HAWK_API_KEY", "BITGET_RO_HAWK_SECRET_KEY", "BITGET_RO_HAWK_PASSPHRASE")
    assert lv.wallet_key_names("Bull") == ("BITGET_RO_BULL_API_KEY", "BITGET_RO_BULL_SECRET_KEY", "BITGET_RO_BULL_PASSPHRASE")
    assert lv.wallet_credentials(env, "hawk") == ("hk", "hs", "hp")
    assert lv.wallet_credentials(env, "bull") == ("bk", "bs", "bp")
    # ne manca una sola di Bull -> niente per Bull, e NON si ripiega sulla chiave di Hawk
    assert lv.wallet_credentials({k: v for k, v in env.items() if k != "BITGET_RO_BULL_PASSPHRASE"}, "bull") is None
    # nemmeno sulla vecchia chiave a conto unico: mostrerebbe il saldo del conto sbagliato
    legacy = {"BITGET_RO_API_KEY": "a", "BITGET_RO_SECRET_KEY": "b", "BITGET_RO_PASSPHRASE": "c"}
    assert lv.wallet_credentials(legacy, "hawk") is None and lv.wallet_credentials(legacy, "bull") is None
    assert lv.wallet_credentials(legacy) == ("a", "b", "c")                 # senza bot: comportamento di prima
    # le chiavi di TRADING dei bot non si usano mai nell'app
    trading = {"BITGET_HAWK_API_KEY": "x", "BITGET_HAWK_SECRET_KEY": "y", "BITGET_HAWK_PASSPHRASE": "z",
               "BITGET_BULL_API_KEY": "x", "BITGET_BULL_SECRET_KEY": "y", "BITGET_BULL_PASSPHRASE": "z",
               "BITGET_API_KEY": "x", "BITGET_SECRET_KEY": "y", "BITGET_PASSPHRASE": "z"}
    assert lv.wallet_credentials(trading, "hawk") is None and lv.wallet_credentials(trading, "bull") is None


def test_combine_wallets_sums_only_when_every_bot_is_readable():
    ok_h = {"available": True, "total_usdt": 1000.0, "available_usdt": 900.0, "used_usdt": 100.0, "error": None}
    ok_b = {"available": True, "total_usdt": 1000.5, "available_usdt": 650.25, "used_usdt": 350.25, "error": None}
    both = lv.combine_wallets({"hawk": ok_h, "bull": ok_b})
    assert both["available"] is True and both["error"] is None
    assert (both["total_usdt"], both["available_usdt"], both["used_usdt"]) == (2000.5, 1550.25, 450.25)
    assert both["per_bot"]["hawk"] == ok_h and both["per_bot"]["bull"] == ok_b
    # un bot illeggibile: niente totale (sarebbe sbagliato), ma il dettaglio dell'altro resta
    part = lv.combine_wallets({"hawk": ok_h, "bull": {"available": False, "error": "chiave non configurata"}})
    assert part["available"] is False and "bull: chiave non configurata" in part["error"]
    assert "total_usdt" not in part and part["per_bot"]["hawk"]["total_usdt"] == 1000.0
    # entrambi illeggibili / niente
    both_bad = lv.combine_wallets({"hawk": {"available": False, "error": "e1"}, "bull": {"available": False, "error": "e2"}})
    assert both_bad["available"] is False and "hawk: e1" in both_bad["error"] and "bull: e2" in both_bad["error"]
    assert lv.combine_wallets({})["available"] is False
    assert lv.combine_wallets({"hawk": None, "bull": ok_b})["available"] is False


def test_live_interlock_comes_from_the_heartbeat():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert p["live_interlock"] is None and p["live_pending_close"] == []        # nessun battito
        _write(d, "heartbeat.json", {"ts": NOW - 3.0, "exec_mode": "live", "live_interlock": None})
        assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["live_interlock"] is None
        _write(d, "heartbeat.json", {"ts": NOW - 3.0, "exec_mode": "live",
                                     "live_interlock": "posizioni su Bitget che il motore non conosce: ETH",
                                     "live_pending_close": ["BTC"]})
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert "ETH" in p["live_interlock"] and p["live_pending_close"] == ["BTC"]


def _paper_files(d):
    """Quello che scrive un bot paper: posizioni aperte e storico con guadagni finti."""
    _write(d, "state_v2.json", {"cycle": 9, "main": {"positions": {
        "ETH": {"side": 1, "entry": 3000.0, "leverage": 5, "total_margin": 100.0,
                "open_ms": LIVE_SINCE_MS + 1}}}})
    _write_history(d, [_trade(1, 512.35, MIDNIGHT_MS + 1000), _trade(2, 781.13, MIDNIGHT_MS - 3_600_000)])


def _assert_zeroed(p):
    assert p["real_data"] is False and p["available"] is False
    assert p["daily_pnl"] == 0.0 and p["total_pnl"] == 0.0 and p["daily_limit_hit"] is False
    assert p["open_positions"] == 0 and p["positions"] == [] and p["total_closed"] == 0
    assert p["cycle"] == 0 and p["halt"] is None
    assert p["live_interlock"] is None and p["live_pending_close"] == []


def test_paper_data_never_shown_when_server_is_not_live():
    with tempfile.TemporaryDirectory() as d:
        _paper_files(d)
        _live_hb(d)                                    # anche con un bot live: server in paper = niente numeri
        for mode in ("paper", "", None, "PAPER"):
            p = lv.build_portfolio(d, 1000, 25, mode, now=NOW)
            _assert_zeroed(p)
            assert p["paper_mode"] is True


def test_paper_data_never_shown_while_the_bot_is_not_running_live():
    """Il caso dello screenshot: DESK_MODE=live sul server, ma i bot sono ancora la versione paper."""
    with tempfile.TemporaryDirectory() as d:
        _paper_files(d)
        for hb in (None,                                              # nessun battito (bot fermo)
                   {"ts": NOW - 3.0},                                 # versione vecchia: niente exec_mode
                   {"ts": NOW - 3.0, "exec_mode": "paper"}):          # bot in paper
            if hb is not None:
                _write(d, "heartbeat.json", hb)
            p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
            _assert_zeroed(p)
            assert p["paper_mode"] is False                           # il server e' live: il motivo e' il bot
            assert p["capital_usdt"] == 1000.0 and p["daily_loss_limit_usdt"] == 250.0


def test_real_numbers_appear_only_with_server_live_and_bot_live():
    with tempfile.TemporaryDirectory() as d:
        _paper_files(d)
        _live_hb(d)
        p = lv.build_portfolio(d, 1000, 25, "  LIVE ", now=NOW)         # maiuscole/spazi non contano
        assert p["real_data"] is True and p["available"] is True and p["paper_mode"] is False
        assert p["live_since_ms"] == LIVE_SINCE_MS and p["scale"] == 1.0
        assert p["daily_pnl"] == 512.35 and p["total_pnl"] == 1293.48
        assert p["open_positions"] == 1 and p["total_closed"] == 2


def _mixed_files(d):
    """Stessi file del bot: roba del simulatore (aperta PRIMA del live) e roba vera (aperta DOPO)."""
    before, after = LIVE_SINCE_MS - 86_400_000, LIVE_SINCE_MS + 3_600_000
    _write(d, "state_v2.json", {"cycle": 9, "main": {"positions": {
        "ETH": {"side": 1, "entry": 3000.0, "leverage": 5, "total_margin": 100.0, "open_ms": before},
        "SOL": {"side": -1, "entry": 150.0, "leverage": 10, "total_margin": 60.0, "open_ms": after}}}})
    _write_history(d, [
        {"id": 1, "net": 700.0, "open_ms": before, "close_ms": MIDNIGHT_MS + 5},           # finto, chiuso oggi
        {"id": 2, "net": 40.0, "open_ms": after, "close_ms": MIDNIGHT_MS + 10},            # vero, chiuso oggi
        {"id": 3, "net": -10.0, "open_ms": after + 1000, "close_ms": MIDNIGHT_MS - 60_000},  # vero, ieri
    ])


def test_live_page_counts_only_what_was_opened_after_live_started():
    with tempfile.TemporaryDirectory() as d:
        _mixed_files(d)
        _live_hb(d)
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
        assert p["total_closed"] == 2 and p["total_pnl"] == 30.0 and p["daily_pnl"] == 40.0   # il +700 finto no
        assert [r["symbol"] for r in p["positions"]] == ["SOL"] and p["open_positions"] == 1   # ETH finta no


def test_live_page_shows_zero_when_live_start_is_unknown():
    with tempfile.TemporaryDirectory() as d:
        _mixed_files(d)
        for extra in ({"live_since_ms": None}, {"live_since_ms": 0}, {"live_since_ms": "boh"}):
            _live_hb(d, **extra)
            p = lv.build_portfolio(d, 1000, 25, "live", now=NOW)
            assert p["real_data"] is True and p["live_since_ms"] is None
            assert p["total_pnl"] == 0.0 and p["daily_pnl"] == 0.0
            assert p["positions"] == [] and p["total_closed"] == 0                             # niente numeri incerti


def test_live_page_converts_engine_amounts_to_the_real_scale():
    """Il motore ragiona su 1000$; con 500$ assegnati gli ordini veri sono la meta': i numeri mostrati pure."""
    with tempfile.TemporaryDirectory() as d:
        _mixed_files(d)
        _live_hb(d, capital_scale=0.5)
        p = lv.build_portfolio(d, 500, 25, "live", now=NOW)
        assert p["scale"] == 0.5 and p["capital_usdt"] == 500.0 and p["daily_loss_limit_usdt"] == 125.0
        assert p["daily_pnl"] == 20.0 and p["total_pnl"] == 15.0
        assert p["positions"][0]["margin"] == 30.0                                             # 60$ motore -> 30$ veri
        for bad in (0, -1, "x", None):                                                        # scala illeggibile: 1
            _live_hb(d, capital_scale=bad)
            assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["scale"] == 1.0


def test_daily_limit_uses_real_scaled_loss():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        _write_history(d, [{"id": 1, "net": -200.0, "open_ms": LIVE_SINCE_MS + 1, "close_ms": MIDNIGHT_MS + 1000}])
        _live_hb(d, capital_scale=0.5)                       # -200 del motore = -100 veri
        p = lv.build_portfolio(d, 500, 25, "live", now=NOW)   # limite 125$ veri
        assert p["daily_pnl"] == -100.0 and p["daily_limit_hit"] is False
        _write_history(d, [{"id": 1, "net": -250.0, "open_ms": LIVE_SINCE_MS + 1, "close_ms": MIDNIGHT_MS + 1000}])
        assert lv.build_portfolio(d, 500, 25, "live", now=NOW)["daily_limit_hit"] is True   # -125 = limite


# ── posizioni vere di BitGet + stop/take profit del bot ───────────────────────
def _ccxt_position(symbol="BTC/USDT:USDT", side="long", total="0.01", entry="60000", mark="61000",
                   upl="10", margin="60", lev="10", liq="54500", ctime="1799999000000", **extra):
    """Una posizione come la restituisce ccxt per Bitget (stesso schema di parse_position)."""
    info = {"symbol": symbol.split("/")[0] + "USDT", "holdSide": side, "total": total, "openPriceAvg": entry,
            "markPrice": mark, "unrealizedPL": upl, "marginSize": margin, "leverage": lev,
            "liquidationPrice": liq, "cTime": ctime}
    info.update(extra)
    return {"symbol": symbol, "side": side, "contracts": float(total), "contractSize": 1.0,
            "entryPrice": float(entry), "markPrice": float(mark), "unrealizedPnl": float(upl),
            "liquidationPrice": float(liq), "leverage": float(lev), "timestamp": int(ctime),
            "initialMargin": float(margin) * 1.0, "info": info}


def test_real_positions_are_normalized_from_the_ccxt_shape():
    rows = lv.normalize_real_positions([
        _ccxt_position(),
        _ccxt_position("ETH/USDT:USDT", side="short", total="0.5", entry="3000", mark="2900", upl="50",
                       margin="150", lev="10", liq="3290"),
        _ccxt_position("XRP/USDT:USDT", total="0"),               # quantita' zero: saltata
        "non e' un dizionario",
    ])
    assert [r["symbol"] for r in rows] == ["BTC", "ETH"]
    btc, eth = rows
    assert btc["side"] == 1 and btc["entry"] == 60000.0 and btc["price"] == 61000.0 and btc["qty"] == 0.01
    assert btc["pnl"] == 10.0 and btc["margin"] == 60.0 and btc["pnl_pct"] == 16.67 and btc["leverage"] == 10
    assert btc["liq"] == 54500.0 and btc["open_ms"] == 1799999000000
    assert eth["side"] == -1 and eth["pnl"] == 50.0 and eth["pnl_pct"] == 33.33


def test_real_positions_tolerate_missing_and_broken_fields():
    p = {"symbol": "SOL/USDT:USDT", "info": {"holdSide": "long", "total": "2", "openPriceAvg": "bad"}}
    (row,) = lv.normalize_real_positions([p])
    assert row["symbol"] == "SOL" and row["qty"] == 2.0 and row["entry"] is None
    assert row["pnl"] == 0.0 and row["pnl_pct"] is None and row["margin"] == 0.0 and row["liq"] is None
    assert lv.normalize_real_positions(None) == [] and lv.normalize_real_positions([]) == []


def _bot_state(d, scale_positions=None, last_prices=None):
    pos = scale_positions or {"BTC": {"side": 1, "entry": 60000.0, "qty": 0.01, "total_margin": 60.0,
                                      "leverage": 10, "sl": 57000.0, "tp": 66000.0, "trade_type": "scalp",
                                      "dca_count": 1, "open_ms": LIVE_SINCE_MS + 5}}
    _write(d, "state_v2.json", {"cycle": 4, "last_prices": last_prices or {}, "main": {"positions": pos}})


def test_live_positions_are_the_real_ones_enriched_with_the_bots_stops():
    with tempfile.TemporaryDirectory() as d:
        _bot_state(d)
        _live_hb(d)
        real = {"available": True, "error": None, "positions": lv.normalize_real_positions([_ccxt_position()])}
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW, real_positions=real)
        assert p["positions_source"] == "bitget" and p["positions_error"] is None and p["open_positions"] == 1
        pos = p["positions"][0]
        assert pos["source"] == "bitget" and pos["confirmed"] is True and pos["in_bot"] is True
        assert pos["price"] == 61000.0 and pos["pnl"] == 10.0 and pos["margin"] == 60.0     # numeri veri di BitGet
        assert pos["sl"] == 57000.0 and pos["tp"] == 66000.0 and pos["trade_type"] == "scalp" and pos["dca_count"] == 1
        assert pos["open_ms"] == LIVE_SINCE_MS + 5, "l'apertura e' quella registrata dal bot"
        assert p["unrealized_pnl"] == 10.0


def test_live_positions_flag_what_bitget_and_the_bot_disagree_on():
    with tempfile.TemporaryDirectory() as d:
        _bot_state(d)                                         # il bot crede di avere BTC
        _live_hb(d)
        real = {"available": True, "error": None,
                "positions": lv.normalize_real_positions([_ccxt_position("ETH/USDT:USDT", entry="3000", mark="3000",
                                                                         upl="0", margin="30")])}
        p = lv.build_portfolio(d, 1000, 25, "live", now=NOW, real_positions=real)
        by = {r["symbol"]: r for r in p["positions"]}
        assert by["ETH"]["in_bot"] is False and by["ETH"]["confirmed"] is True and by["ETH"]["sl"] is None
        assert by["BTC"]["confirmed"] is False and by["BTC"]["source"] == "bot", "BitGet non la mostra: non e' confermata"


def test_live_positions_fall_back_to_the_bots_numbers_and_say_why():
    with tempfile.TemporaryDirectory() as d:
        _bot_state(d, last_prices={"BTC": 61000.0})
        _live_hb(d, capital_scale=0.5)
        for real in (None, {"available": False, "error": "chiave BitGet di sola lettura non configurata"}):
            p = lv.build_portfolio(d, 500, 25, "live", now=NOW, real_positions=real)
            assert p["positions_source"] == "bot" and p["open_positions"] == 1
            pos = p["positions"][0]
            assert pos["source"] == "bot" and pos["price"] == 61000.0
            assert pos["margin"] == 30.0 and pos["qty"] == 0.005, "il motore e' in scala 0,5"
            assert pos["pnl"] == 5.0 and pos["pnl_pct"] == 16.67          # (61000-60000) * 0.005
        assert "non configurata" in p["positions_error"]
        # senza prezzo del bot il P&L non si inventa
        _bot_state(d, last_prices={})
        pos = lv.build_portfolio(d, 500, 25, "live", now=NOW)["positions"][0]
        assert pos["price"] is None and pos["pnl"] is None and pos["pnl_pct"] is None


def test_live_page_lists_the_last_five_closed_trades_in_real_scale_and_the_cycle_info():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "state_v2.json", {"cycle": 9, "main": {"positions": {}}})
        _write_history(d, [{"id": i, "symbol": "ETH", "side": -1, "net": float(i), "leverage": 10, "why": "take profit",
                            "open_ms": LIVE_SINCE_MS + i, "close_ms": LIVE_SINCE_MS + 1000 * i} for i in range(1, 8)])
        _live_hb(d, capital_scale=0.5, last_end_ms=NOW * 1000 - 60_000, next_cycle_ms=NOW * 1000 + 240_000,
                 last_ok=True)
        p = lv.build_portfolio(d, 500, 25, "live", now=NOW)
        rt = p["recent_trades"]
        assert [t["pnl"] for t in rt] == [3.5, 3.0, 2.5, 2.0, 1.5], "i 5 piu' recenti, risultato in scala 0,5"
        assert rt[0]["symbol"] == "ETH" and rt[0]["close_reason"] == "take profit" and rt[0]["side"] == -1
        assert p["bot_online"] is True and p["cycle_info"]["last_ok"] is True
        assert p["cycle_info"]["next_cycle_ms"] == int(NOW * 1000 + 240_000)


def test_bot_offline_and_skeleton_carry_the_new_fields():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "heartbeat.json", {"ts": NOW - 900, "exec_mode": "live", "live_since_ms": LIVE_SINCE_MS})
        _write(d, "state_v2.json", {"cycle": 1, "main": {"positions": {}}})
        assert lv.build_portfolio(d, 1000, 25, "live", now=NOW)["bot_online"] is False
    with tempfile.TemporaryDirectory() as d:
        z = lv.build_portfolio(d, 1000, 25, "paper", now=NOW)
        assert z["positions_source"] == "none" and z["recent_trades"] == [] and z["unrealized_pnl"] == 0.0
        assert z["bot_online"] is False and z["cycle_info"]["next_cycle_ms"] is None
