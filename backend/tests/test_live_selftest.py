"""La prova di collegamento (live_selftest) eseguita contro l'exchange finto: deve funzionare in one-way e in
hedge, fermarsi se qualcosa non va e lasciare SEMPRE l'account piatto e senza stop rimasti."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_bitget as fb  # noqa: E402
from desk import live_connector as lc  # noqa: E402
from desk import live_selftest as st  # noqa: E402
from desk.cli import SYMBOLS  # noqa: E402


def rig(pos_mode=fb.ONE_WAY):
    prices = {f"{s}/USDT:USDT": 0.5 + i for i, s in enumerate(SYMBOLS)}
    fake = fb.FakeBitget(pos_mode=pos_mode, symbols={s: 0.001 for s in SYMBOLS}, prices=prices)
    conn = lc.LiveConnector(data_dir=tempfile.mkdtemp(), client=fake, live=True, sleep=lambda s: None)
    st.STEPS.clear()
    return fake, conn


def test_selftest_passes_end_to_end_in_one_way_and_hedge():
    for mode in (fb.ONE_WAY, fb.HEDGE):
        fake, conn = rig(mode)
        rc = st.main(["--yes-real-money", "--symbol", "XRP", "--margin", "3", "--lev", "5"], conn=conn)
        bad = [(n, d) for n, ok, d in st.STEPS if not ok]
        assert rc == 0 and not bad, (mode, bad)
        assert fake.legs == {} and fake.plans == []          # account piatto e senza stop rimasti


def test_selftest_refuses_without_explicit_confirmation_and_with_big_amounts():
    fake, conn = rig()
    assert st.main(["--symbol", "XRP"], conn=conn) == 2 and fake.orders == []
    assert st.main(["--yes-real-money", "--margin", "50"], conn=conn) == 2 and fake.orders == []


def test_selftest_stops_if_the_account_already_has_positions():
    fake, conn = rig()
    fake.put_position("BTC", 1, 0.01)
    assert st.main(["--yes-real-money"], conn=conn) == 1
    assert fake.orders == [] and fake.leg("BTC", 1)["qty"] == 0.01   # non tocca quello che c'e'


def test_selftest_failure_midway_still_leaves_the_account_flat():
    fake, conn = rig()
    fake.ignore_leverage = True                                      # la leva non si applica: l'apertura va rifiutata
    rc = st.main(["--yes-real-money", "--symbol", "XRP"], conn=conn)
    assert rc == 1 and fake.legs == {} and fake.plans == []
    fake2, conn2 = rig()
    orig = fake2._apply
    state = {"n": 0}

    def flaky(sym, req):                                             # il 3o ordine (l'aggiunta) viene rifiutato
        state["n"] += 1
        if state["n"] == 4:
            raise fb.ccxt.ExchangeError("rifiutato")
        return orig(sym, req)
    fake2._apply = flaky
    rc2 = st.main(["--yes-real-money", "--symbol", "XRP"], conn=conn2)
    assert rc2 == 1 and fake2.legs == {} and fake2.plans == []       # pulizia garantita anche a meta' strada
