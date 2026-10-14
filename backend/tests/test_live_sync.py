"""Test del collegamento motore <-> exchange (live_sync) con il VERO motore (PaperAccount) e un exchange
finto che usa il vero ccxt (fake_bitget.py). Ogni azione del motore deve avere il suo riflesso
sull'exchange, e ogni divergenza deve finire in uno stato sicuro. Nessun parametro di strategia viene toccato.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_bitget as fb  # noqa: E402
from fake_bitget import ccxt  # noqa: E402
from desk import live_connector as lc  # noqa: E402
from desk import live_sync as ls  # noqa: E402
from desk.engine import Limits, PaperAccount  # noqa: E402

NOW = 1_800_000_000_000
BAR = 900_000
LIM = Limits(start_equity=1000, max_margin_trade=100, max_margin_total=1000, max_open=10, kill_equity=450,
             daily_stop=0.12)


def world(pos_mode=fb.ONE_WAY):
    fake = fb.FakeBitget(pos_mode=pos_mode)
    conn = lc.LiveConnector(data_dir=tempfile.mkdtemp(), client=fake, live=True, sleep=lambda s: None)
    acc = PaperAccount(LIM, "main")
    alerts = []
    return acc, conn, fake, alerts


def open_btc(acc, conn, side=1, split=None, price=60000.0, margin=100, lev=10, sl=None, tp=None):
    sl = sl or (price * 0.97 if side == 1 else price * 1.03)
    tp = tp or (price * 1.05 if side == 1 else price * 0.95)
    pos, msg = acc.open("BTC", side, margin, lev, price, sl, tp, NOW, {"BTC": price}, split=split)
    assert pos, msg
    ok, detail = ls.open_on_exchange(conn, pos, price)
    return pos, ok, detail


def test_open_mirrors_engine_quantity_and_stops():
    acc, conn, fake, _ = world()
    pos, ok, detail = open_btc(acc, conn)
    assert ok, detail
    leg = fake.leg("BTC", 1)
    assert abs(leg["qty"] - pos.qty) <= 0.0002 and leg["margin_mode"] == "isolated" and leg["leverage"] == 10
    sl = [p for p in fake.plans if p["planType"] == "loss_plan"][0]["triggerPrice"]
    assert abs(sl - pos.sl) < 0.11                                   # lo stop del motore e' quello dell'exchange


def test_rejected_open_rolls_the_engine_back_completely():
    acc, conn, fake, _ = world()
    cash0 = acc.cash
    fake.errors["create_order"] = [ccxt.InsufficientFunds("saldo")]
    pos, ok, detail = open_btc(acc, conn)
    assert not ok
    ls.rollback_open(acc, pos)
    assert acc.positions == {} and abs(acc.cash - cash0) < 1e-9 and fake.legs == {}


def test_dca_is_mirrored_and_exchange_stops_follow_the_engine():
    acc, conn, fake, _ = world()
    pos, ok, _ = open_btc(acc, conn)
    assert ok
    px = 59000.0
    before = ls.snapshot_position(acc, "BTC")
    res, msg = acc.add_dca("BTC", 57000.0, 64000.0, NOW + 1, {"BTC": px}, "test")
    assert res, msg
    ok, detail = ls.dca_on_exchange(conn, acc, "BTC", before, px)
    assert ok, detail
    assert abs(fake.leg("BTC", 1)["qty"] - acc.positions["BTC"].qty) <= 0.0004
    levels = {(p["planType"], p["triggerPrice"]) for p in fake.plans}
    assert ("pos_loss", 57000.0) in levels and ("pos_profit", 64000.0) in levels
    assert not any(t == "loss_plan" and v == pos.sl for t, v in levels)   # niente vecchio stop rimasto


def test_rejected_dca_restores_the_engine_exactly():
    acc, conn, fake, _ = world()
    open_btc(acc, conn)
    snap = ls.snapshot_position(acc, "BTC")
    qty0, cash0, sl0, dca0 = acc.positions["BTC"].qty, acc.cash, acc.positions["BTC"].sl, 0
    before = ls.snapshot_position(acc, "BTC")
    res, _ = acc.add_dca("BTC", 57000.0, 64000.0, NOW + 1, {"BTC": 59000.0}, "test")
    assert res and acc.positions["BTC"].qty > qty0
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    ok, detail = ls.dca_on_exchange(conn, acc, "BTC", before, 59000.0)
    assert not ok
    p = acc.positions["BTC"]
    assert p.qty == qty0 and acc.cash == cash0 and p.sl == sl0 and p.dca_count == dca0
    assert snap is not None and abs(fake.leg("BTC", 1)["qty"] - qty0) <= 0.0002   # exchange invariato


def test_partial_close_reduces_the_real_position_by_the_same_fraction():
    acc, conn, fake, _ = world()
    pos, ok, _ = open_btc(acc, conn)
    q0 = fake.leg("BTC", 1)["qty"]
    ok, detail = ls.partial_on_exchange(conn, pos, 0.35)
    assert ok, detail
    assert abs(fake.leg("BTC", 1)["qty"] - q0 * 0.65) <= 0.0002
    # tosatura come il motore: 0.99 diventa 0.95
    ok, _ = ls.partial_on_exchange(conn, pos, 0.99)
    assert ok and fake.leg("BTC", 1)["qty"] < q0 * 0.65 * 0.06


def test_partial_failure_is_reported_so_the_engine_is_left_untouched():
    acc, conn, fake, _ = world()
    pos, ok, _ = open_btc(acc, conn)
    q0 = fake.leg("BTC", 1)["qty"]
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    ok, _ = ls.partial_on_exchange(conn, pos, 0.35)
    assert not ok and fake.leg("BTC", 1)["qty"] == q0


def test_engine_stop_closes_what_is_left_on_the_exchange():
    acc, conn, fake, alerts = world()
    pos, ok, _ = open_btc(acc, conn)
    assert ok
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 57500, 57600, BAR)        # tocca lo stop del motore
    assert rec and rec["why"] == "stop loss"
    note = ls.after_bar(conn, acc, "BTC", None, rec, alert=alerts.append, now_ms=NOW)
    assert note is None and fake.legs == {} and rec["live"]["closed_qty"] > 0   # esito reale accanto al simulato
    assert conn.pending_close == {}


def test_engine_exit_when_exchange_already_stopped_out_needs_no_order():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    fake.legs.clear()                                                    # lo stop dell'exchange e' gia' scattato
    n_orders = len(fake.orders)
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 57500, 57600, BAR)
    assert ls.after_bar(conn, acc, "BTC", None, rec, alert=alerts.append, now_ms=NOW) is None
    assert len(fake.orders) == n_orders and conn.pending_close == {}


def test_failed_exit_is_retried_and_blocks_new_openings_meanwhile():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 57500, 57600, BAR)
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    note = ls.after_bar(conn, acc, "BTC", None, rec, alert=alerts.append, now_ms=NOW)
    assert note and "non e' riuscita" in note and alerts
    assert conn.pending_close == {"BTC": 1} and fake.leg("BTC", 1)       # il motore ha chiuso, l'exchange no
    res = ls.sync(conn, acc, {"BTC": 57600.0}, NOW + 2, alert=alerts.append)   # al giro dopo: ritenta e ci riesce
    assert fake.legs == {} and conn.pending_close == {} and res["interlock"] is None


def test_failed_exit_that_keeps_failing_blocks_openings():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 57500, 57600, BAR)
    fake.sticky["create_order"] = ccxt.ExchangeError("rifiutato")
    ls.after_bar(conn, acc, "BTC", None, rec, alert=alerts.append, now_ms=NOW)
    res = ls.sync(conn, acc, {}, NOW + 2, alert=alerts.append)
    assert res["interlock"] and "BTC" in res["interlock"] and conn.open_blocked()


def test_split_second_leg_is_mirrored():
    acc, conn, fake, alerts = world()
    pos, ok, _ = open_btc(acc, conn, split={"retrace_pct": 0.005, "first_frac": 0.5}, margin=100)
    assert ok and pos.pending_split
    q1 = fake.leg("BTC", 1)["qty"]
    before = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 59600, 59650, BAR)        # scende al ritracciamento
    assert rec is None and acc.positions["BTC"].legs == 2
    assert ls.after_bar(conn, acc, "BTC", before, rec, alert=alerts.append, now_ms=NOW) is None
    assert abs(fake.leg("BTC", 1)["qty"] - acc.positions["BTC"].qty) <= 0.0004
    assert fake.leg("BTC", 1)["qty"] > q1 * 1.5


def test_rejected_second_leg_is_undone_and_not_retried_every_candle():
    acc, conn, fake, alerts = world()
    pos, ok, _ = open_btc(acc, conn, split={"retrace_pct": 0.005, "first_frac": 0.5})
    qty1, cash1 = acc.positions["BTC"].qty, acc.cash
    before = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 59600, 59650, BAR)
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    note = ls.after_bar(conn, acc, "BTC", before, rec, alert=alerts.append, now_ms=NOW)
    assert note and "annullata" in note
    p = acc.positions["BTC"]
    assert p.qty == qty1 and acc.cash == cash1 and p.legs == 1 and p.pending_split is None


def test_stop_and_second_leg_in_the_same_candle_closes_the_real_position():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn, split={"retrace_pct": 0.005, "first_frac": 0.5})
    before = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 57400, 57500, BAR)        # tocca ritracciamento E stop
    assert rec and rec["why"] == "stop loss"
    assert ls.after_bar(conn, acc, "BTC", before, rec, alert=alerts.append, now_ms=NOW) is None
    assert fake.legs == {}                                               # chiusa la quantita' REALE (una gamba sola)


# ---- riallineamento ----------------------------------------------------------------

def test_sync_closes_in_engine_what_the_exchange_already_closed():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    conn._opened_at.clear()                                              # non e' appena aperta
    fake.legs.clear()                                                    # stop scattato sull'exchange
    res = ls.sync(conn, acc, {"BTC": 58000.0}, NOW + 5, alert=alerts.append)
    assert [r["why"] for r in res["closed"]] == ["chiusa su Bitget"] and acc.positions == {}
    assert res["interlock"] is None and not conn.open_blocked()


def test_sync_start_of_cycle_never_changes_the_engine():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    conn._opened_at.clear()
    fake.legs.clear()
    res = ls.sync(conn, acc, {}, NOW + 5, close_engine=False, alert=alerts.append)
    assert res["closed"] == [] and "BTC" in acc.positions and conn.open_blocked()


def test_sync_just_opened_position_gets_grace_time():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    fake.legs.clear()                                                    # (l'elenco posizioni non la mostra ancora)
    res = ls.sync(conn, acc, {}, NOW, alert=alerts.append)
    assert res["closed"] == [] and "BTC" in acc.positions


def test_foreign_position_blocks_openings_and_is_never_touched():
    acc, conn, fake, alerts = world()
    fake.put_position("ETH", -1, 2.0, entry=3000.0)                      # aperta a mano o dall'altro bot
    res = ls.sync(conn, acc, {}, NOW, alert=alerts.append)
    assert "ETH" in res["interlock"] and conn.open_blocked()
    assert fake.leg("ETH", -1)["qty"] == 2.0 and fake.orders == []        # non tocca nulla
    assert alerts and "BLOCCATE" in alerts[0]
    ok, detail = conn.open("BTC", 1, 0.01, 10, 58000.0, 63000.0, ref_price=60000.0)
    assert not ok and "bloccate" in detail and fake.orders == []
    fake.legs.clear()                                                    # l'utente la chiude: il blocco si toglie da solo
    res = ls.sync(conn, acc, {}, NOW + 1, alert=alerts.append)
    assert res["interlock"] is None and not conn.open_blocked() and "rimosso" in alerts[-1]


def test_unreadable_exchange_blocks_openings_and_changes_nothing():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    conn._opened_at.clear()
    fake.sticky["fetch_positions"] = ccxt.NetworkError("giu'")
    res = ls.sync(conn, acc, {}, NOW + 5, alert=alerts.append)
    assert res["closed"] == [] and "BTC" in acc.positions                 # lettura fallita != posizione chiusa
    assert res["interlock"] and "lettura" in res["interlock"] and conn.open_blocked()


def test_quantity_mismatch_and_opposite_side_block_without_touching():
    acc, conn, fake, alerts = world()
    open_btc(acc, conn)
    conn._opened_at.clear()
    fake.leg("BTC", 1)["qty"] *= 3                                       # sull'exchange c'e' molto di piu'
    res = ls.sync(conn, acc, {}, NOW + 5, alert=alerts.append)
    assert res["interlock"] and "quantita'" in res["interlock"] and res["closed"] == []
    assert fake.orders and len(fake.orders) == 1                          # solo l'apertura originale


def test_stale_protection_is_retried_with_the_current_engine_levels():
    acc, conn, fake, alerts = world()
    pos, ok, _ = open_btc(acc, conn)
    conn._opened_at.clear()
    fake.errors["create_order"] = [ccxt.ExchangeError("piano rifiutato")]
    assert conn.set_protection("BTC", 1, 57000.0, 64000.0)[0] is False and "BTC" in conn.stale_protection
    pos.sl, pos.tp = 56500.0, 65500.0                                    # nel frattempo il motore ha cambiato livelli
    ls.sync(conn, acc, {}, NOW + 5, alert=alerts.append)
    assert conn.stale_protection == {}
    assert {(p["planType"], p["triggerPrice"]) for p in fake.plans} == {("pos_loss", 56500.0), ("pos_profit", 65500.0)}


def test_paper_mode_sync_is_a_no_op():
    conn = lc.LiveConnector(data_dir=tempfile.mkdtemp(), live=False)
    acc = PaperAccount(LIM, "main")
    assert ls.sync(conn, acc, {}, NOW) == {"closed": [], "interlock": None, "notes": []}
    assert ls.after_bar(conn, acc, "BTC", None, {"side": 1}) is None


def test_hedge_account_end_to_end_open_dca_exit():
    acc, conn, fake, alerts = world(fb.HEDGE)
    pos, ok, detail = open_btc(acc, conn, side=-1)
    assert ok, detail
    before = ls.snapshot_position(acc, "BTC")
    res, msg = acc.add_dca("BTC", 62500.0, 56000.0, NOW + 1, {"BTC": 61000.0}, "test")
    assert res, msg
    ok, detail = ls.dca_on_exchange(conn, acc, "BTC", before, 61000.0)
    assert ok, detail
    rec = acc.on_bar("BTC", NOW + 2, 61000, 63000, 60900, 62900, BAR)    # sale oltre lo stop del motore
    assert rec and rec["why"] == "stop loss"
    assert ls.after_bar(conn, acc, "BTC", None, rec, alert=alerts.append, now_ms=NOW) is None
    assert fake.legs == {}
