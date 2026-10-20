"""OPZIONE A (decisione di Alexander, 20/10/2026 16:30): quando il margine realmente disponibile e' sotto il
minimo di Bull (150 $), la nuova apertura si RIFIUTA invece di essere ridimensionata dal motore a 30-149 $.
La politica sta nel ciclo del bot (cli.margin_gate); il motore (PaperAccount.open) resta com'era, quindi Hawk
e Turbo non cambiano. Qui si provano: il cancello (puro), il ciclo vero (paper e LIVE con exchange finto),
la stessa formula del motore, split, tolleranze, Hawk invariato."""
import json
import os
import random
import sys
import tempfile
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault("DESK_MACRO_FETCH", "0")

import fake_bitget as fb  # noqa: E402
import test_desk as td  # noqa: E402   (mondo di candele e stub di Claude gia' collaudati)
from desk import brain, cli  # noqa: E402
from desk import live_connector as lc  # noqa: E402
from desk.engine import PaperAccount  # noqa: E402

NOW = td.NOW
T = 1_800_000_000_000
SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX", "DOT", "LINK", "UNI", "ATOM"]
BULL, HAWK = cli._make_bull_config(), cli._make_hawk_config()


def _dec(sym, margin, action="open_long", lev=10, retrace=None):
    d = {"symbol": sym, "action": action, "confidence": 85, "leverage": lev, "margin_usd": margin,
         "stop_loss_pct": 0.01, "take_profit_pct": 0.025, "reason": "test", "trade_type": "medio",
         "dca_sl_pct": 0, "dca_tp_pct": 0}
    if retrace is not None:
        d["split_retrace_pct"] = retrace
    return d


class Rig:
    """Un vero run_cycle con candele e Claude finti, per il portafoglio indicato (paper, oppure LIVE su exchange finto)."""

    def __init__(self, cfg, decisions, live=False):
        import desk.market_context as _mc
        self.cfg = cfg
        self.d = tempfile.mkdtemp()
        self.calls = 0
        world = td._world(n=700)
        self.fake = None
        self._mc = _mc
        self._saved = (cli.fetch_candles, _mc.fetch_all_context, brain.call_claude, cli.call_claude, cli.PORTFOLIO,
                       cli.LIVE, cli.STATE_FILE, cli.DATA_DIR, cli._TRADING_ENABLED_FILE, cli._DAILY_LOSS_LIMIT)
        cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
        _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
        self.decisions = decisions

        def stub(system, user, max_tokens=1100, timeout=60):
            self.calls += 1
            return json.dumps({"decisions": self.decisions, "note": "t"}), {"input_tokens": 2000, "output_tokens": 150}

        brain.call_claude = stub
        cli.call_claude = stub
        cli.PORTFOLIO = cfg
        cli.STATE_FILE = os.path.join(self.d, "state_v2.json")
        cli.DATA_DIR = self.d
        if live:
            last = {s: float(a[-1][4]) for s, a in world.items()}
            self.fake = fb.FakeBitget(pos_mode=fb.ONE_WAY, symbols={s: 0.001 for s in cli.SYMBOLS},
                                      prices={f"{s}/USDT:USDT": p for s, p in last.items()})
            cli.LIVE = lc.LiveConnector(data_dir=self.d, client=self.fake, live=True, sleep=lambda s: None, scale=1.0)
            cli._TRADING_ENABLED_FILE = os.path.join(self.d, "trading_enabled.json")
            with open(cli._TRADING_ENABLED_FILE, "w") as f:
                json.dump({"enabled": True}, f)
        os.environ["ANTHROPIC_API_KEY"] = "test"
        self.state = cli.load_state(cli.STATE_FILE)

    def cycle(self, k=0):
        cli.run_cycle(self.state, NOW + k * cli.HOUR_MS)
        cli.save_state(self.state, cli.STATE_FILE)
        assert self.calls >= 1, "Claude finto non e' stato consultato: il test non verifica nulla"

    def acc(self):
        return cli.make_account(self.state)

    def events(self, name):
        p = os.path.join(self.d, "learning_log.jsonl")
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()] if os.path.exists(p) else []
        return [r for r in rows if r.get("ev") == name]

    def close(self):
        (cli.fetch_candles, self._mc.fetch_all_context, brain.call_claude, cli.call_claude, cli.PORTFOLIO,
         cli.LIVE, cli.STATE_FILE, cli.DATA_DIR, cli._TRADING_ENABLED_FILE, cli._DAILY_LOSS_LIMIT) = self._saved
        os.environ.pop("ANTHROPIC_API_KEY", None)


def _gate_refusals(rig):
    return [c["symbol"] for c in rig.events("candidate") if c.get("status") == "rifiutata:margine_sotto_minimo"]


def _fill(limits, margin, n):
    a = PaperAccount(limits)
    for s in SYMS[:n]:
        p, msg = a.open(s, 1, margin, 10, 100.0, 97.0, 110.0, T, {}, trade_type="medio")
        assert p is not None, msg
    return a


# ---------------------------------------------------------------- configurazione
def test_only_bull_refuses_below_the_minimum_and_hawk_is_untouched():
    assert BULL.refuse_below_min_margin is True and HAWK.refuse_below_min_margin is False
    assert BULL.guardrail_min_margin == 150.0 and HAWK.guardrail_min_margin == 50.0   # minimi invariati
    h = PaperAccount(HAWK.limits)
    h.cash = 20.0                                                      # margine disponibile ~19 $: Hawk non rifiuta per questo
    assert cli.margin_room(h) < HAWK.guardrail_min_margin and cli.margin_gate(h, HAWK) is None


# ---------------------------------------------------------------- cancello puro
def test_gate_refuses_the_seventh_150_and_the_fourth_after_three_300():
    a = _fill(BULL.limits, 150, 6)
    assert cli.margin_room(a) < 150 and cli.margin_gate(a, BULL) is not None
    b = _fill(BULL.limits, 300, 3)
    assert abs(cli.margin_room(b) - 89.87) < 0.01 and "89.87" in cli.margin_gate(b, BULL)


def test_gate_is_open_at_exactly_150_and_closed_just_below():
    for total, expect_open in ((150.0, True), (149.9999999999, True), (149.99, False), (149.0, False), (151.0, True)):
        a = PaperAccount(replace(BULL.limits, max_margin_total=total))
        assert (cli.margin_gate(a, BULL) is None) == expect_open, total
    # stesso confine ma dal lato della cassa (cassa*0.95): 157,8947368... * 0.95 = 150 a meno dell'errore di arrotondamento
    for cash, expect_open in ((150 / 0.95, True), (150 / 0.95 - 0.0001, False)):
        a = PaperAccount(BULL.limits)
        a.cash = cash
        assert (cli.margin_gate(a, BULL) is None) == expect_open, cash


def test_closing_a_position_frees_margin_and_a_new_150_entry_is_possible_again():
    a = _fill(BULL.limits, 150, 6)
    assert cli.margin_gate(a, BULL) is not None
    assert a.close("BTC", 100.0, T + 60_000, "test") is not None
    assert cli.margin_gate(a, BULL) is None
    p, msg = a.open("ADA", 1, 150, 10, 100.0, 97.0, 110.0, T + 120_000, {}, trade_type="medio")
    assert p is not None and p.total_margin == 150.0, msg          # non ridotto: il margine liberato basta


def test_gate_room_is_exactly_what_the_engine_would_grant():
    """La formula del cancello e quella di PaperAccount.open non devono divergere: per sequenze casuali di richieste
    (con limiti che fanno prevalere ogni termine del minimo) il margine concesso dal motore e' min(richiesto, room)."""
    rng = random.Random(20261020)
    checked = 0
    for _ in range(300):
        lim = replace(BULL.limits, max_margin_total=rng.choice([300.0, 450.0, 700.0, 1000.0]),
                      max_margin_trade=rng.choice([200.0, 350.0]), max_open=12)
        a = PaperAccount(lim)
        for s in SYMS:
            room = cli.margin_room(a)
            req = rng.choice([60.0, 100.0, 150.0, 220.0, 300.0, 350.0])
            p, msg = a.open(s, 1, req, 10, 100.0, 97.0, 110.0, T, {}, trade_type="medio")
            if room >= lim.min_margin:
                assert p is not None, (room, req, msg)
                assert abs(p.total_margin - min(req, room)) < 1e-9, (p.total_margin, req, room)
                checked += 1
            else:
                assert p is None
    assert checked > 500


# ---------------------------------------------------------------- ciclo vero (paper)
def test_cycle_seventh_150_is_refused_with_no_fee_and_no_cash_change():
    decs = [_dec(s, 150) for s in SYMS[:7]]
    rig = Rig(BULL, decs)
    try:
        rig.cycle(0)
        acc = rig.acc()
        assert len(acc.positions) == 6 and all(p.total_margin == 150.0 for p in acc.positions.values())
        refused = _gate_refusals(rig)
        assert len(refused) == 1 and refused[0] not in acc.positions and refused[0] in SYMS[:7]
        assert abs(acc.margin_in_use() - 900.0) < 1e-9
        fees = sum(p.fee_open for p in acc.positions.values())
        assert abs(acc.cash - (1000.0 - 900.0 - fees)) < 1e-6          # il rifiutato non ha tolto nulla
        assert not any(c.get("status", "").startswith("rifiutata:margine disponibile") for c in rig.events("candidate"))
    finally:
        rig.close()


def test_cycle_fourth_300_after_three_300_is_refused():
    decs = [_dec(s, 300) for s in SYMS[:4]]
    rig = Rig(BULL, decs)
    try:
        rig.cycle(0)
        acc = rig.acc()
        assert len(acc.positions) == 3 and all(p.total_margin == 300.0 for p in acc.positions.values())
        assert len(_gate_refusals(rig)) == 1
        assert acc.cash > 90.0                                         # niente micro-trade da ~90 $ che brucia la cassa
    finally:
        rig.close()


def test_cycle_margin_released_by_a_close_allows_the_next_cycle_to_open_again():
    decs = [_dec(s, 150) for s in SYMS[:7]]
    rig = Rig(BULL, decs)
    try:
        rig.cycle(0)
        acc = rig.acc()
        refused = _gate_refusals(rig)[0]
        victim = next(iter(acc.positions))
        acc.close(victim, acc.positions[victim].entry, NOW + 60_000, "test")   # chiusura in pareggio: il margine torna in cassa
        rig.state["main"] = acc.to_dict()                              # lo stato del bot con il margine liberato
        rig.state["last_open_ms"] = {}
        rig.state["last_call_ms"] = 0
        rig.decisions = [_dec(refused, 150)]                            # il ciclo dopo ripropone solo quello rifiutato
        rig.cycle(2)
        acc2 = rig.acc()
        assert refused in acc2.positions and acc2.positions[refused].total_margin == 150.0
    finally:
        rig.close()


def test_cycle_split_with_a_total_of_at_least_150_is_not_rejected_for_a_first_leg_under_150():
    rig = Rig(BULL, [_dec("BTC", 200, action="open_long_split", retrace=0.5)])
    try:
        rig.cycle(0)
        acc = rig.acc()
        assert "BTC" in acc.positions and _gate_refusals(rig) == []
        p = acc.positions["BTC"]
        assert p.total_margin <= 200.0 and (p.pending_split or p.total_margin == 200.0)
    finally:
        rig.close()


def test_cycle_split_proposal_is_refused_when_the_total_room_is_under_150():
    decs = [_dec(s, 150) for s in SYMS[:6]] + [_dec("ADA", 200, action="open_long_split", retrace=0.5)]
    rig = Rig(BULL, decs)
    try:
        rig.cycle(0)
        acc = rig.acc()
        assert len(acc.positions) == 6 and "ADA" not in acc.positions and _gate_refusals(rig) == ["ADA"]
    finally:
        rig.close()


def test_cycle_hawk_keeps_the_old_behaviour_tenth_entry_still_scaled_by_the_engine():
    decs = [_dec(s, 100) for s in SYMS[:10]]
    rig = Rig(HAWK, decs)
    try:
        rig.cycle(0)
        acc = rig.acc()
        margins = sorted(p.total_margin for p in acc.positions.values())
        assert len(acc.positions) == 10 and _gate_refusals(rig) == []
        assert margins[1:] == [100.0] * 9 and 85.0 < margins[0] < 95.0   # il 10mo ridotto dal motore, come prima
    finally:
        rig.close()


# ---------------------------------------------------------------- LIVE con exchange finto
def test_live_mocked_refused_proposal_sends_no_order_to_the_exchange():
    decs6 = [_dec(s, 150) for s in SYMS[:6]]
    base = Rig(BULL, decs6, live=True)
    try:
        base.cycle(0)
        n_orders_6, legs_6 = len(base.fake.orders), len(base.fake.legs)
        assert legs_6 == 6 and n_orders_6 >= 6
    finally:
        base.close()
    rig = Rig(BULL, decs6 + [_dec("ADA", 150)], live=True)
    try:
        rig.cycle(0)
        acc = rig.acc()
        assert len(acc.positions) == 6 and "ADA" not in acc.positions
        assert len(rig.fake.legs) == 6 and rig.fake.leg("ADA", 1) is None
        assert len(rig.fake.orders) == n_orders_6                      # nessun ordine in piu' per la proposta scartata
        assert _gate_refusals(rig) == ["ADA"]
    finally:
        rig.close()
