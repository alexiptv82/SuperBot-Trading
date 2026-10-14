"""Test del connettore live contro un exchange finto che usa il VERO ccxt 4.2.95 (vedi fake_bitget.py).

Ogni test e' uno scenario in cui il live potrebbe andare storto: ordini che Bitget rifiuterebbe,
letture fallite scambiate per "nessuna posizione", margine non isolato, leva non applicata, risposte in
timeout dopo l'esecuzione, posizioni estranee, chiusure parziali, ecc. Niente rete, niente chiavi.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_bitget as fb  # noqa: E402
from fake_bitget import ccxt  # noqa: E402
from desk import live_connector as lc  # noqa: E402

BTC = "BTC/USDT:USDT"


def mk(pos_mode=fb.ONE_WAY, **kw):
    fake = fb.FakeBitget(pos_mode=pos_mode, **kw)
    conn = lc.LiveConnector(data_dir=tempfile.mkdtemp(), client=fake, live=True, sleep=lambda s: None)
    return conn, fake


def orders_of(fake, kind):
    """Richieste ordine inviate (costruite dal vero ccxt), filtrate per tipo."""
    if kind == "open":
        return [o for o in fake.orders if "planType" not in o and "reduceOnly" not in o
                and o.get("tradeSide") != "Close"]
    if kind == "close":
        return [o for o in fake.orders if o.get("reduceOnly") == "YES" or o.get("tradeSide") == "Close"]
    return [o for o in fake.orders if "planType" in o]


# ---- apertura ---------------------------------------------------------------

def test_open_one_way_is_isolated_with_preset_stops_in_the_same_order():
    c, f = mk(fb.ONE_WAY)
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, tp=63000.0, ref_price=60000.0)
    assert ok, detail
    (req,) = orders_of(f, "open")
    assert req["marginMode"] == "isolated" and req["side"] == "buy" and "tradeSide" not in req
    assert req["presetStopLossPrice"] == "58000" and req["presetStopSurplusPrice"] == "63000"
    assert "planType" not in req                                   # un solo ordine: stop e TP agganciati
    leg = f.leg("BTC", 1)
    assert leg["qty"] == 0.01 and leg["margin_mode"] == "isolated" and leg["leverage"] == 10
    assert c.last_fill["real_qty"] == 0.01 and c.last_fill["avg"] == 60000.0 and c.last_fill["fee"] > 0
    # stop e TP esistono davvero sull'exchange appena la posizione e' aperta
    kinds = sorted(p["planType"] for p in f.plans)
    assert kinds == ["loss_plan", "profit_plan"]


def test_open_hedge_uses_tradeside_open_and_per_side_leverage():
    c, f = mk(fb.HEDGE)
    ok, detail = c.open("BTC", -1, 0.01, 8, sl=62000.0, tp=57000.0, ref_price=60000.0)
    assert ok, detail
    (req,) = orders_of(f, "open")
    assert req["tradeSide"] == "Open" and req["side"] == "sell" and req["marginMode"] == "isolated"
    assert f.leg("BTC", -1)["leverage"] == 8
    assert f.lev[BTC][-1] == 8                                     # leva dello short impostata, quella del long no
    assert f.lev[BTC][1] == 20


def test_open_without_take_profit_sends_only_the_stop():
    c, f = mk()
    ok, _ = c.open("BTC", 1, 0.01, 10, sl=58000.0, tp=None, ref_price=60000.0)
    assert ok
    (req,) = orders_of(f, "open")
    assert "presetStopLossPrice" in req and "presetStopSurplusPrice" not in req


def test_open_switches_symbol_to_isolated_and_rereads_before_trading():
    c, f = mk()
    assert f.margin.get(BTC, "crossed") == "crossed"
    ok, _ = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert ok and f.margin[BTC] == "isolated"
    # ordine delle operazioni: prima impostazioni e rilettura, poi l'ordine
    names = f.names()
    assert names.index("set_margin_mode") < names.index("set_leverage") < names.index("create_order")
    assert names.count("fetch_leverage") >= 2                      # letto prima e RILETTO dopo


def test_open_refused_when_isolated_cannot_be_set():
    c, f = mk()
    f.ignore_margin_mode = True
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "ISOLATO" in detail
    assert f.orders == [] and f.legs == {}                          # nessun ordine partito


def test_open_refused_when_leverage_is_not_applied():
    c, f = mk()
    f.ignore_leverage = True
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "leva" in detail
    assert f.orders == [] and f.legs == {}


def test_open_refused_when_a_position_already_exists_on_the_symbol():
    c, f = mk()
    f.put_position("BTC", 1, 0.5)                                   # posizione estranea
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "gia' una posizione" in detail
    assert f.orders == [] and f.leg("BTC", 1)["qty"] == 0.5


def test_open_refused_below_contract_minimum_and_min_value():
    c, f = mk()
    ok, detail = c.open("BTC", 1, 0.00003, 10, sl=58000.0, ref_price=60000.0)   # tronca a 0 / sotto il minimo
    assert not ok and "minimo" in detail and f.orders == []
    ok, detail = c.open("BTC", 1, 0.0001, 10, sl=58000.0, ref_price=1.0)        # valore 0,0001$ < 5$
    assert not ok and "minimo" in detail and f.orders == []


def test_open_rounds_quantity_down_never_up():
    c, f = mk()
    ok, _ = c.open("BTC", 1, 0.01239999, 10, sl=58000.0, ref_price=60000.0)
    assert ok and f.leg("BTC", 1)["qty"] == 0.0123


def test_open_unknown_symbol_refused():
    c, f = mk()
    ok, detail = c.open("MATIC", 1, 10.0, 5, sl=0.5, ref_price=1.0)
    assert not ok and "non disponibile" in detail and f.orders == []


def test_open_requires_a_stop_loss():
    c, f = mk()
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=None, ref_price=60000.0)
    assert not ok and "stop" in detail and f.orders == []


def test_open_refused_when_position_mode_is_unknown():
    c, f = mk()
    f.reported_pos_mode = None                                      # Bitget non riporta la modalita'
    os.environ.pop("DESK_LIVE_POS_MODE", None)
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "modalita' posizione" in detail and f.orders == []
    os.environ["DESK_LIVE_POS_MODE"] = fb.ONE_WAY                   # override esplicito dell'utente
    try:
        ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
        assert ok, detail
    finally:
        os.environ.pop("DESK_LIVE_POS_MODE", None)


def test_open_closes_immediately_if_exchange_opened_cross_anyway():
    c, f = mk()
    f.force_order_margin = "crossed"                                # l'exchange ignora il margine isolato
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "NON conforme" in detail
    assert f.legs == {}                                             # chiusa subito
    assert c.open_blocked()                                         # e le nuove aperture si fermano
    ok2, detail2 = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok2 and "bloccate" in detail2


def test_open_with_wrong_leverage_on_the_position_is_closed():
    c, f = mk()
    orig = f._open

    def sneaky(sym, side, size, px, req):                           # la posizione nasce con leva 50 invece di 10
        orig(sym, side, size, px, req)
        f.legs[(sym, side)]["leverage"] = 50
    f._open = sneaky
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "NON conforme" in detail and f.legs == {}


def test_open_error_with_no_fill_is_a_clean_failure():
    c, f = mk()
    f.errors["create_order"] = [ccxt.InsufficientFunds("saldo insufficiente")]
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok and "saldo" in detail and f.legs == {}
    assert f.count("create_order") == 1                              # errore non transitorio: niente retry


def test_open_timeout_after_the_order_went_through_is_recovered_not_duplicated():
    c, f = mk()
    f.errors["create_order"] = [ccxt.RequestTimeout("timeout")]
    f.fill_after_error = True                                       # Bitget ha eseguito, la risposta si e' persa
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert ok, detail
    assert f.leg("BTC", 1)["qty"] == 0.01                            # UNA sola posizione, non duplicata
    # il retry riusa lo stesso clientOid: l'exchange lo rifiuta come duplicato invece di raddoppiare
    ids = {o["clientOid"] for o in orders_of(f, "open")}
    assert len(ids) == 1


def test_open_when_the_position_cannot_be_read_back_blocks_and_fails():
    c, f = mk()
    calls = {"n": 0}
    real = f.fetch_positions

    def flaky(symbols=None, params=None):
        calls["n"] += 1
        if calls["n"] >= 2:                                         # la 1a lettura (pre-controllo) va, poi no
            f.calls.append("fetch_positions")
            raise ccxt.NetworkError("rete giu'")
        return real(symbols, params)
    f.fetch_positions = flaky
    ok, detail = c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    assert not ok
    assert c.open_blocked() or "rileggere" in detail or "controlla" in detail or "lettura" in detail


# ---- una lettura fallita non e' "nessuna posizione" ---------------------------

def test_failed_read_is_never_mistaken_for_flat():
    c, f = mk()
    f.put_position("BTC", 1, 0.5)
    f.sticky["fetch_positions"] = ccxt.NetworkError("rete giu'")
    try:
        c.snapshot()
        assert False, "doveva sollevare LiveError"
    except lc.LiveError:
        pass
    try:
        c.fetch_positions()
        assert False, "doveva sollevare LiveError"
    except lc.LiveError:
        pass
    ok, detail = c.close("BTC", 1)
    assert not ok and f.orders == []                                # niente ordine "alla cieca"
    assert c.reconcile({})[0].startswith("[RICONCILIAZIONE] impossibile leggere")


# ---- chiusura -----------------------------------------------------------------

def test_close_uses_real_exchange_quantity_reduce_only_one_way():
    c, f = mk(fb.ONE_WAY)
    f.put_position("BTC", 1, 0.0123)
    ok, detail = c.close("BTC", 1, qty=999.0)                       # la qty del motore e' ignorata
    assert ok, detail
    (req,) = orders_of(f, "close")
    assert req["reduceOnly"] == "YES" and req["side"] == "sell" and req["size"] == "0.0123"
    assert f.legs == {}


def test_close_hedge_closes_the_right_leg_with_tradeside_close():
    c, f = mk(fb.HEDGE)
    f.put_position("BTC", 1, 0.02)
    f.put_position("ETH", -1, 1.5, entry=3000.0)
    ok, _ = c.close("ETH", -1)
    assert ok and f.leg("ETH", -1) is None and f.leg("BTC", 1)["qty"] == 0.02
    req = orders_of(f, "close")[0]
    assert req["tradeSide"] == "Close" and req["side"] == "sell"     # hedge: 'side' = direzione della posizione
    ok, _ = c.close("BTC", 1)
    assert ok and f.legs == {}
    assert orders_of(f, "close")[1]["side"] == "buy"


def test_close_when_exchange_is_already_flat_is_fine():
    c, f = mk()
    ok, detail = c.close("BTC", 1)
    assert ok and detail == "gia_chiusa" and f.orders == []


def test_close_refuses_to_touch_a_position_on_the_other_side():
    c, f = mk()
    f.put_position("BTC", -1, 0.5)
    ok, detail = c.close("BTC", 1)
    assert not ok and "non la tocco" in detail and f.orders == []


def test_close_reports_failure_when_something_is_left():
    c, f = mk()
    f.put_position("BTC", 1, 1.0)
    f.partial_close = 0.5                                           # l'exchange esegue solo meta'
    ok, detail = c.close("BTC", 1)
    assert not ok and "restano" in detail
    assert f.leg("BTC", 1)["qty"] == 0.5


def test_close_rejection_leaves_position_and_reports_error():
    c, f = mk()
    f.put_position("BTC", 1, 0.5)
    f.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    ok, detail = c.close("BTC", 1)
    assert not ok and f.leg("BTC", 1)["qty"] == 0.5


# ---- riduzione / aggiunta -------------------------------------------------------

def test_reduce_closes_a_fraction_of_the_real_quantity():
    c, f = mk()
    f.put_position("BTC", 1, 0.1)
    ok, detail = c.reduce("BTC", 1, 0.35)
    assert ok, detail
    assert abs(f.leg("BTC", 1)["qty"] - 0.065) < 1e-9
    assert orders_of(f, "close")[0]["reduceOnly"] == "YES"


def test_reduce_without_position_or_with_bad_fraction_fails_safely():
    c, f = mk()
    ok, _ = c.reduce("BTC", 1, 0.35)
    assert not ok and f.orders == []
    f.put_position("BTC", 1, 0.0002)
    ok, detail = c.reduce("BTC", 1, 0.05)                           # 0.00001 tronca a 0: non si invia
    assert not ok and f.orders == []


def test_add_requires_an_existing_position_and_keeps_isolated():
    c, f = mk()
    ok, detail = c.add("BTC", 1, 0.01, 10, sl=57000.0, ref_price=60000.0)
    assert not ok and "non c'e'" in detail and f.orders == []        # mai "riaprire" per sbaglio
    f.put_position("BTC", 1, 0.02)
    f.margin[BTC] = "isolated"
    ok, detail = c.add("BTC", 1, 0.01, 10, sl=57000.0, tp=64000.0, ref_price=60000.0)
    assert ok, detail
    req = orders_of(f, "open")[-1]
    assert req["marginMode"] == "isolated" and req["presetStopLossPrice"] == "57000"
    assert abs(f.leg("BTC", 1)["qty"] - 0.03) < 1e-9
    assert c.last_fill["added_qty"] == 0.01


def test_add_refused_when_exchange_position_is_on_the_other_side():
    c, f = mk()
    f.put_position("BTC", -1, 0.02)
    f.margin[BTC] = "isolated"
    ok, detail = c.add("BTC", 1, 0.01, 10, sl=57000.0, ref_price=60000.0)
    assert not ok and f.leg("BTC", -1)["qty"] == 0.02 and len(orders_of(f, "open")) == 0


# ---- stop e take profit che seguono il motore --------------------------------

def test_set_protection_places_new_levels_then_cancels_the_old_ones():
    c, f = mk(fb.ONE_WAY)
    ok, _ = c.open("BTC", 1, 0.01, 10, sl=58000.0, tp=63000.0, ref_price=60000.0)
    assert ok
    old_ids = {p["id"] for p in f.plans}
    ok, detail = c.set_protection("BTC", 1, 57000.0, 65000.0)
    assert ok, detail
    remaining = {(p["planType"], p["triggerPrice"]) for p in f.plans}
    assert remaining == {("pos_loss", 57000.0), ("pos_profit", 65000.0)}
    assert not (old_ids & {p["id"] for p in f.plans})                # i vecchi sono spariti
    assert all(p["holdSide"] == "buy" for p in f.plans)               # one-way: 'buy'/'sell'
    assert c.stale_protection == {}


def test_set_protection_hedge_uses_long_short_hold_side():
    c, f = mk(fb.HEDGE)
    c.open("BTC", -1, 0.01, 10, sl=62000.0, tp=57000.0, ref_price=60000.0)
    ok, _ = c.set_protection("BTC", -1, 61000.0, 56000.0)
    assert ok and all(p["holdSide"] == "short" for p in f.plans)


def test_set_protection_failure_keeps_the_old_levels_and_remembers_to_retry():
    c, f = mk()
    c.open("BTC", 1, 0.01, 10, sl=58000.0, tp=63000.0, ref_price=60000.0)
    before = {(p["planType"], p["triggerPrice"]) for p in f.plans}
    f.errors["create_order"] = [ccxt.ExchangeError("piano rifiutato")]
    ok, _ = c.set_protection("BTC", 1, 57000.0, 65000.0)
    assert not ok
    assert {(p["planType"], p["triggerPrice"]) for p in f.plans} == before   # protezione di prima intatta
    assert c.stale_protection == {"BTC": (57000.0, 65000.0)}


# ---- confronto motore / exchange --------------------------------------------------

class P:                                                             # posizione del motore, quanto basta
    def __init__(self, side, qty):
        self.side, self.qty = side, qty


def test_compare_flags_flat_foreign_and_mismatch():
    c, f = mk()
    f.put_position("BTC", 1, 0.0100)       # coincide
    f.put_position("ETH", -1, 2.0)         # estranea al motore
    f.put_position("DOGE", 1, 1000.0)      # lato opposto rispetto al motore
    snap = c.snapshot()
    eng = {"BTC": P(1, 0.0100), "DOGE": P(-1, 1000.0), "SOL": P(1, 3.0)}
    r = c.compare(eng, snap)
    assert r["flat"] == ["SOL"] and r["foreign"] == ["ETH"]
    assert [s for s, _ in r["mismatch"]] == ["DOGE"]


def test_compare_quantity_tolerance_and_big_difference():
    c, f = mk()
    f.put_position("BTC", 1, 0.0100)
    snap = c.snapshot()
    assert c.compare({"BTC": P(1, 0.01015)}, snap)["mismatch"] == []          # +1,5%: arrotondamento
    assert [s for s, _ in c.compare({"BTC": P(1, 0.02)}, snap)["mismatch"]] == ["BTC"]


def test_compare_gives_grace_to_a_position_just_opened_and_ignores_pending_close():
    c, f = mk()
    c._opened_at["BTC"] = 1000.0
    assert c.compare({"BTC": P(1, 0.01)}, {}, now=1005.0)["flat"] == []      # appena aperta: ancora non giudico
    assert c.compare({"BTC": P(1, 0.01)}, {}, now=1100.0)["flat"] == ["BTC"]
    f.put_position("ETH", 1, 1.0)
    c.pending_close["ETH"] = 1                                              # il motore l'ha chiusa, l'exchange no
    assert c.compare({}, c.snapshot())["foreign"] == []


def test_compare_flags_cross_margin_and_two_legs():
    c, f = mk(fb.HEDGE)
    f.put_position("BTC", 1, 0.01, margin_mode="crossed")
    f.put_position("ETH", 1, 1.0)
    f.put_position("ETH", -1, 1.0)
    r = c.compare({"BTC": P(1, 0.01), "ETH": P(1, 1.0)}, c.snapshot())
    assert sorted(s for s, _ in r["mismatch"]) == ["BTC", "ETH"]


# ---- paper: non tocca nulla --------------------------------------------------------

def test_paper_mode_is_a_no_op():
    c = lc.LiveConnector(data_dir=tempfile.mkdtemp(), live=False)
    assert c.open("BTC", 1, 0.01, 10, 58000.0, 63000.0) == (True, "paper")
    assert c.close("BTC", 1, 0.01) == (True, "paper")
    assert c.add("BTC", 1, 0.01, 10) == (True, "paper")
    assert c.reduce("BTC", 1, 0.5) == (True, "paper")
    assert c.set_protection("BTC", 1, 1.0, 2.0) == (True, "paper")
    assert c.fetch_positions() == [] and c.reconcile({"BTC": P(1, 1)}) == [] and c.open_blocked() is None


def test_every_order_is_logged_with_real_fill():
    c, f = mk()
    c.open("BTC", 1, 0.01, 10, sl=58000.0, ref_price=60000.0)
    c.close("BTC", 1)
    import json
    rows = [json.loads(x) for x in open(c._log, encoding="utf-8")]
    evs = [r["ev"] for r in rows]
    assert "open_attempt" in evs and "open_ok" in evs and "close_attempt" in evs and "close_ok" in evs
    ok_row = next(r for r in rows if r["ev"] == "open_ok")
    assert ok_row["fill"]["avg"] == 60000.0 and ok_row["fill"]["real_qty"] == 0.01
