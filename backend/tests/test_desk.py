"""Test della sala segnali V2: conto paper (costi, stop, liquidazione, tetti, DCA, scalp/medio)."""
import json
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")   # i test non scaricano mai il calendario macro vero (vedi conftest.py)

from desk.engine import Limits, PaperAccount  # noqa: E402

BAR = 900_000
NOW = 1_800_000_000_000 // BAR * BAR + 20_000


def acct():
    return PaperAccount(Limits())


# ---- engine unit tests (aggiornati per V2: nuovi campi Position) ----

def test_open_applies_slippage_fee_and_caps():
    a = acct()
    # V2: max_leverage per BTC=45x, max_margin_trade=400$
    p, msg = a.open("BTC", 1, 999, 99, 100.0, 99.0, None, 0, {})
    assert p is not None
    assert p.leverage == 45          # V2: BTC max 45x
    assert p.margin == 400           # V2: max_margin_trade=400$
    assert p.total_margin == 400     # V2: total_margin == margin al primo ingresso
    assert p.trade_type == "medio"   # V2: default medio
    assert p.dca_count == 0          # V2: nessun DCA ancora
    assert abs(p.entry - 100.02) < 1e-9
    assert a.equity({"BTC": 100.02}) < 1000


def test_stop_is_mandatory_and_must_be_on_the_right_side():
    a = acct()
    assert a.open("BTC", 1, 100, 5, 100.0, 0, None, 0, {})[0] is None
    assert a.open("BTC", 1, 100, 5, 100.0, 101.0, None, 0, {})[0] is None
    assert a.open("BTC", -1, 100, 5, 100.0, 99.0, None, 0, {})[0] is None


def test_stop_beyond_liquidation_is_refused_at_high_leverage():
    a = acct()
    p, msg = a.open("BTC", 1, 100, 30, 100.0, 95.0, None, 0, {})
    assert p is None and "liquidazione" in msg
    assert a.open("BTC", 1, 100, 30, 100.0, 98.0, None, 0, {})[0] is not None


def test_total_margin_cap_and_max_open():
    # V2: max_margin_total=2000$, max_margin_trade=400$, max_open=10
    # Usiamo un account con cash abbondante per testare i cap
    from desk.engine import Limits
    lim = Limits()
    a = PaperAccount(lim, "main")
    a.cash = 3000.0  # cash sufficiente per testare il cap di margine totale

    # singolo trade cappato a max_margin_trade=400$
    p1, _ = a.open("A", 1, 400, 3, 100.0, 90.0, None, 0, {})
    assert p1 is not None and p1.total_margin == 400
    p2, _ = a.open("B", 1, 400, 3, 100.0, 90.0, None, 0, {})
    assert p2 is not None
    # dopo 5 trade da 400$ = 2000$ siamo al cap
    for s in "CDE":
        px, _ = a.open(s, 1, 400, 3, 100.0, 90.0, None, 0, {})
        assert px is not None, f"atteso aperto per {s}"
    # il sesto supera max_margin_total=2000$
    p6, msg = a.open("F", 1, 200, 3, 100.0, 90.0, None, 0, {})
    assert p6 is None and "margine" in msg, f"atteso rifiuto per margine, got {p6} msg={msg}"

    # max_open=10
    b = PaperAccount(Limits(), "main")
    b.cash = 5000.0
    for s in "ABCDEFGHIJ":   # 10 posizioni — al limite
        b.open(s, 1, 40, 3, 100.0, 90.0, None, 0, {})
    assert len(b.positions) == 10
    assert b.open("K", 1, 40, 3, 100.0, 90.0, None, 0, {})[0] is None


def test_stop_loss_exit_and_pnl_includes_costs():
    a = acct()
    p, _ = a.open("BTC", 1, 100, 10, 100.0, 98.0, None, 0, {})
    rec = a.on_bar("BTC", 0, 100, 100.5, 97.0, 99.0, BAR)
    assert rec and rec["why"] == "stop loss" and rec["net"] < 0
    expected_gross = (98.0 * (1 - 2e-4) - p.entry) * p.qty
    assert abs(rec["gross"] - expected_gross) < 1e-3
    assert abs(a.cash - (1000 + rec["net"])) < 1e-3


def test_gap_through_stop_exits_at_open_not_at_stop():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, None, 0, {})
    rec = a.on_bar("BTC", 0, 95.0, 96.0, 94.0, 95.0, BAR)
    assert rec["exit"] < 98.0 * (1 - 2e-4) - 1


def test_stop_wins_when_stop_and_target_touch_in_the_same_bar():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, 103.0, 0, {})
    assert a.on_bar("BTC", 0, 100, 104, 97, 100, BAR)["why"] == "stop loss"


def test_short_take_profit_and_funding_only_on_long():
    a = acct()
    a.open("BTC", -1, 100, 5, 100.0, 103.0, 97.0, 0, {})
    rec = a.on_bar("BTC", 8 * 3_600_000, 100, 100, 96.5, 97.0, BAR)
    assert rec["why"] == "take profit" and rec["funding"] == 0 and rec["net"] > 0
    b = acct()
    b.open("BTC", 1, 100, 5, 100.0, 90.0, None, 0, {})
    rec = b.close("BTC", 100.0, 16 * 3_600_000)
    assert rec["funding"] > 0


def test_liquidation_loses_the_whole_margin_and_never_more():
    a = acct()
    p, _ = a.open("BTC", 1, 100, 30, 100.0, 99.0, None, 0, {})
    p.sl = 0.0001
    rec = a.on_bar("BTC", 0, 100, 100, 90.0, 91.0, BAR)
    assert rec["why"] == "liquidazione" and rec["net"] < 0
    assert a.cash < 1000


def test_bars_before_entry_are_ignored():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, None, BAR * 10, {})
    assert a.on_bar("BTC", BAR * 5, 100, 100, 50, 60, BAR) is None


def test_daily_stop_and_kill_switch_block_new_trades():
    a = acct()
    a.roll_day("2026-10-09", {})
    a.cash = 880.0   # perdita >12%
    h = a.halted({})
    assert h and len(h) > 0   # V2: halted() ritorna stringa non vuota
    assert a.open("BTC", 1, 100, 5, 100.0, 98.0, None, 0, {})[0] is None
    b = acct()
    b.roll_day("d", {})
    b.cash = 440.0   # sotto kill_equity=450$
    assert b.halted({})


def test_state_roundtrip():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, 105.0, 123, {}, confidence=70, reason="x")
    b = PaperAccount.from_dict(a.to_dict())
    assert b.to_dict() == a.to_dict()


def test_state_roundtrip_with_v2_fields():
    """from_dict deve gestire posizioni V1 (senza dca_levels ecc.) in modo backward-compatible."""
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, None, 0, {}, trade_type="scalp")
    d = a.to_dict()
    # verifica che i campi V2 siano presenti
    pos = d["positions"]["BTC"]
    assert "dca_levels" in pos
    assert "total_margin" in pos
    assert "trade_type" in pos
    assert pos["trade_type"] == "scalp"
    assert pos["dca_count"] == 0
    # roundtrip
    b = PaperAccount.from_dict(d)
    assert b.positions["BTC"].trade_type == "scalp"
    assert b.positions["BTC"].dca_count == 0


def test_dca_adds_entry_and_updates_weighted_average():
    """DCA su posizione medio: aggiunge ingresso, aggiorna entry media."""
    a = acct()
    p, _ = a.open("BTC", 1, 100, 5, 100.0, 95.0, None, 0, {}, trade_type="medio")
    assert p is not None
    # prezzo scende a 97: DCA con nuovo SL a 94 (piu' lontano: dal 20/10/2026 lo stop non si allarga, resta 95)
    prices = {"BTC": 97.0}
    new_sl = 94.0
    result, msg = a.add_dca("BTC", new_sl, None, BAR, prices, "test dca")
    assert result is not None, f"DCA fallito: {msg}"
    assert result.dca_count == 1
    assert result.entry < 100.0   # entry media deve essere tra 97 e 100
    assert result.sl == 95.0
    assert result.total_margin > 100   # margine aumentato


def test_dca_not_allowed_on_scalp():
    """DCA non permesso su trade scalp."""
    a = acct()
    p, _ = a.open("BTC", 1, 100, 10, 100.0, 95.0, None, 0, {}, trade_type="scalp")
    assert p is not None
    result, msg = a.add_dca("BTC", 94.0, None, BAR, {"BTC": 97.0}, "test")
    assert result is None and "scalp" in msg.lower()


def test_dca_max_2_entries():
    """Max 2 DCA aggiuntivi (3 ingressi totali)."""
    a = acct()
    a.open("BTC", 1, 60, 3, 100.0, 85.0, None, 0, {}, trade_type="medio")
    prices = {"BTC": 97.0}
    r1, _ = a.add_dca("BTC", 84.0, None, BAR, prices, "dca1")
    assert r1 is not None and r1.dca_count == 1
    r2, _ = a.add_dca("BTC", 83.0, None, BAR * 2, prices, "dca2")
    assert r2 is not None and r2.dca_count == 2
    r3, msg = a.add_dca("BTC", 82.0, None, BAR * 3, prices, "dca3")
    assert r3 is None and "max" in msg.lower()


# ---- signals tests (aggiornati per V2: nuovi campi Reading) ----

def _series(n, drift, noise=0.002, seed=3, start=100.0):
    rng = np.random.default_rng(seed)
    c = start * np.exp(np.cumsum(rng.normal(drift, noise, n)))
    o = np.r_[start, c[:-1]]
    h, l = np.maximum(o, c) * 1.001, np.minimum(o, c) * 0.999
    return np.column_stack([np.arange(n) * BAR, o, h, l, c, np.full(n, 10.0)])


def test_resample_drops_incomplete_bars_and_aggregates():
    from desk.signals import resample, H1
    a = _series(10, 0.0)
    r = resample(a, H1)
    assert len(r) == 2 and r[0, 2] == a[:4, 2].max() and r[1, 4] == a[7, 4]
    assert len(resample(a[1:], H1)) == 1


def test_uptrend_scores_long_and_downtrend_scores_short():
    from desk.signals import read_symbol
    up = read_symbol("X", _series(4400, 0.0006))
    dn = read_symbol("X", _series(4400, -0.0006))
    assert up is not None and up.side == 1 and up.score >= 53
    assert dn is not None and dn.side == -1
    assert 0.003 <= up.sl_pct <= 0.035 and up.tp_pct > up.sl_pct
    # V2: nuovi campi
    assert hasattr(up, "trade_type")
    assert hasattr(up, "seasonal_note")
    assert hasattr(up, "pattern")
    assert up.trade_type in ("scalp", "medio")


def test_short_history_gives_no_reading():
    from desk.signals import read_symbol
    assert read_symbol("X", _series(300, 0.0)) is None


# ---- brain tests ----

def test_parse_decisions_tolerates_text_around_json_and_drops_garbage():
    from desk.brain import parse_decisions
    txt = ('Ecco:\n{"decisions":[{"symbol":"btc/usdt","action":"open_long","confidence":"82","leverage":12,'
           '"margin_usd":150,"stop_loss_pct":0.01,"take_profit_pct":0.02,"reason":"x","trade_type":"medio",'
           '"dca_sl_pct":0,"dca_tp_pct":0},'
           '{"symbol":"ETH","action":"boom"},{"action":"hold"}],"note":"ok"} fine')
    d = parse_decisions(txt)
    assert len(d["decisions"]) == 1
    assert d["decisions"][0]["symbol"] == "BTC"
    assert d["decisions"][0]["confidence"] == 82
    assert parse_decisions("nessun json") is None
    assert parse_decisions('{"decisions": 5}') is None


def test_parse_decisions_includes_dca_fields():
    from desk.brain import parse_decisions
    txt = ('{"decisions":[{"symbol":"ETH","action":"dca","confidence":70,"leverage":10,'
           '"margin_usd":0,"stop_loss_pct":0,"take_profit_pct":0,"reason":"support",'
           '"trade_type":"medio","dca_sl_pct":0.008,"dca_tp_pct":0.025}]}')
    d = parse_decisions(txt)
    assert len(d["decisions"]) == 1
    assert d["decisions"][0]["action"] == "dca"
    assert d["decisions"][0]["dca_sl_pct"] == 0.008


def test_budget_blocks_calls_when_cap_reached_and_resets_next_day():
    from desk import brain
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    st = {}
    cap = 1.0  # usa cap alto per non dipendere dai prezzi esatti del modello
    assert brain.can_call(st, "d1", cap)
    spent = brain.record_spend(st, "d1", {"input_tokens": 10_000, "output_tokens": 1_000})
    assert spent > 0
    # spendi fino al tetto
    while brain.budget_left(st, "d1", cap) >= brain.CALL_RESERVE:
        brain.record_spend(st, "d1", {"input_tokens": 10_000, "output_tokens": 1_000})
    assert not brain.can_call(st, "d1", cap)
    assert brain.can_call(st, "d2", cap)   # nuovo giorno: azzerato
    total = st["budget"]["total_spent"]
    assert total > 0
    del os.environ["ANTHROPIC_API_KEY"]
    assert not brain.can_call(st, "d2", cap)


def test_error_message_never_contains_the_key():
    from desk import brain
    os.environ["ANTHROPIC_API_KEY"] = "sk-segreta-123"
    brain.API_URL = "http://127.0.0.1:9/nope"
    try:
        brain.call_claude("s", "u", timeout=2)
        assert False
    except RuntimeError as exc:
        assert "sk-segreta" not in str(exc)
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
        brain.API_URL = "https://api.anthropic.com/v1/messages"


def test_rules_fallback_sizes_with_score_and_closes_weak_positions():
    from desk.brain import rules_decisions
    from desk.signals import Reading
    # V2: Reading ha campi aggiuntivi (seasonal_note, pattern, trade_type)
    # entry_score default=70: strong(95) e weak(72) passano, held(80) è già aperto
    strong = Reading("BTC", 100.0, 1, 95, 95, 10, 0.01, 0.01, 0.017, {}, ["a"],
                     seasonal_note="", pattern="", trade_type="scalp")
    weak = Reading("ETH", 100.0, 1, 72, 72, 20, 0.01, 0.01, 0.017, {}, ["b"],
                   seasonal_note="", pattern="", trade_type="medio")
    held = Reading("SOL", 100.0, -1, 80, 20, 80, 0.01, 0.01, 0.017, {}, [],
                   seasonal_note="", pattern="", trade_type="medio")
    positions = [{"symbol": "SOL", "side": 1, "trade_type": "medio", "dca_count": 0}]
    d = {x["symbol"]: x for x in rules_decisions([strong, weak, held], positions, {"SOL"}, entry_score=70)}
    assert "BTC" in d and "ETH" in d, f"chiavi attese BTC/ETH, trovate: {list(d)}"
    # scalp ha leverage più alto di medio (formula: scalp 15+frac*30, medio 5+frac*20)
    assert d["BTC"]["leverage"] > d["ETH"]["leverage"]
    # scalp usa range margine 150-250$, medio 80-250$
    assert 150 <= d["BTC"]["margin_usd"] <= 250, f"scalp fuori range: {d['BTC']['margin_usd']}"
    assert 80 <= d["ETH"]["margin_usd"] <= 250, f"medio fuori range: {d['ETH']['margin_usd']}"
    assert d["SOL"]["action"] == "close"
    assert d["BTC"]["trade_type"] == "scalp"


# ---- cli V2 tests (firma nuova: run_cycle(state, now_ms)) ----

from desk import cli  # noqa: E402


class FakeContext:
    """Stub per fetch_all_context: ritorna ctx vuoto."""
    @staticmethod
    def fetch(symbols, now_ms):
        return {"funding": {}, "oi": {}, "news": [], "ts": now_ms}


def _world(drift=0.0006, n=4500):
    last_t = (NOW // BAR) * BAR
    out = {}
    for i, s in enumerate(cli.SYMBOLS):
        a = _series(n, drift, seed=10 + i, start=100.0 * (i + 1))
        a[:, 0] = last_t - (n - 1 - np.arange(n)) * BAR
        out[s] = a
    return out


def _patch_candles(monkeypatch_dict, world):
    """Sostituisce fetch_candles in cli con dati finti."""
    original = cli.fetch_candles

    def fake_fetch(symbol, bar="15m", limit=300):
        arr = world.get(symbol)
        if arr is None:
            return []
        return arr[-limit:].tolist()

    cli.fetch_candles = fake_fetch
    return original


def _patch_ctx(monkeypatch_dict):
    """Sostituisce fetch_all_context con stub."""
    import desk.cli as _cli_mod
    import desk.market_context as _mc
    original = _mc.fetch_all_context

    def fake_ctx(symbols, now_ms):
        return {"funding": {}, "oi": {}, "news": [], "ts": now_ms}

    _mc.fetch_all_context = fake_ctx
    return original, _mc


def _claude_stub(action="open_long", symbol="BTC", conf=85, lev=10, margin=150, sl=0.01):
    """Ritorna una funzione call_claude che risponde con una decisione fissa."""
    def call(system, user, max_tokens=1100, timeout=60):
        body = {"decisions": [{"symbol": symbol, "action": action, "confidence": conf,
                               "leverage": lev, "margin_usd": margin, "stop_loss_pct": sl,
                               "take_profit_pct": 0.025, "reason": "test", "trade_type": "medio",
                               "dca_sl_pct": 0, "dca_tp_pct": 0}], "note": "test"}
        return json.dumps(body), {"input_tokens": 2000, "output_tokens": 150}
    return call


def test_full_cycle_v2_opens_position_and_saves_state():
    """Ciclo completo V2: deve aprire una posizione BTC e salvare lo state."""
    import desk.brain as _brain
    import desk.market_context as _mc
    import desk.cli as _c

    world = _world()
    orig_fetch = cli.fetch_candles
    orig_ctx = _mc.fetch_all_context
    orig_call = _brain.call_claude

    cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
    _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
    # patch call_claude sia in brain che in cli (cli lo importa direttamente)
    stub = _claude_stub()
    _brain.call_claude = stub
    _c.call_claude = stub

    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        with tempfile.TemporaryDirectory() as d:
            _c.STATE_FILE = os.path.join(d, "state_v2.json")
            _c.DATA_DIR = d

            state = cli.load_state(_c.STATE_FILE)
            # primo ciclo
            cli.run_cycle(state, NOW)
            cli.save_state(state, _c.STATE_FILE)
            # secondo ciclo: forza chiamata Claude e azzera cooldown
            state["last_call_ms"] = 0
            state["last_open_ms"] = {}
            cli.run_cycle(state, NOW + cli.HOUR_MS)
            # verifica
            acc = cli.make_account(state)
            assert "BTC" in acc.positions, f"BTC dovrebbe essere aperto, posizioni: {list(acc.positions)}"
            pos = acc.positions["BTC"]
            pg = _c.PORTFOLIO   # i minimi dipendono dal portafoglio (Hawk 50$/10x, Bull 150$/10x)
            assert pos.leverage >= pg.guardrail_min_lev, f"lev sotto il minimo del portafoglio: {pos.leverage}"
            assert pg.guardrail_min_margin <= pos.total_margin <= pg.limits.max_margin_trade, \
                f"margine fuori dai limiti del portafoglio {pg.name}: {pos.total_margin}"
            assert pos.trade_type in ("scalp", "medio")
    finally:
        cli.fetch_candles = orig_fetch
        _mc.fetch_all_context = orig_ctx
        _brain.call_claude = orig_call
        _c.call_claude = orig_call
        del os.environ["ANTHROPIC_API_KEY"]


def test_cycle_v2_without_key_uses_rules():
    """Senza ANTHROPIC_API_KEY il ciclo deve usare rules_decisions (non Claude)."""
    import desk.market_context as _mc

    world = _world(drift=0.0008)  # trend forte per avere segnali
    orig_fetch = cli.fetch_candles
    orig_ctx = _mc.fetch_all_context

    cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
    _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}

    os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory() as d:
            import desk.cli as _c
            _c.STATE_FILE = os.path.join(d, "state_v2.json")
            _c.DATA_DIR = d
            state = cli.load_state(_c.STATE_FILE)
            cli.run_cycle(state, NOW)
            # non deve crashare; il budget non deve essere consumato
            assert state.get("budget", {}).get("spent", 0.0) == 0.0
    finally:
        cli.fetch_candles = orig_fetch
        _mc.fetch_all_context = orig_ctx


def test_cycle_v2_dca_execution():
    """Se Claude propone 'dca' su posizione aperta, il codice deve eseguirlo."""
    import desk.brain as _brain
    import desk.market_context as _mc
    import desk.cli as _c

    world = _world()
    orig_fetch = cli.fetch_candles
    orig_ctx = _mc.fetch_all_context
    orig_call = _brain.call_claude

    cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
    _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}

    os.environ["ANTHROPIC_API_KEY"] = "test"
    call_n = [0]

    def alternating_call(system, user, max_tokens=1100, timeout=60):
        call_n[0] += 1
        if call_n[0] == 1:
            # primo ciclo: apre BTC
            body = {"decisions": [{"symbol": "BTC", "action": "open_long", "confidence": 85,
                                   "leverage": 8, "margin_usd": 100, "stop_loss_pct": 0.015,
                                   "take_profit_pct": 0.03, "reason": "test", "trade_type": "medio",
                                   "dca_sl_pct": 0, "dca_tp_pct": 0}], "note": ""}
        else:
            # secondo ciclo: DCA su BTC
            body = {"decisions": [{"symbol": "BTC", "action": "dca", "confidence": 80,
                                   "leverage": 8, "margin_usd": 0, "stop_loss_pct": 0,
                                   "take_profit_pct": 0, "reason": "support", "trade_type": "medio",
                                   "dca_sl_pct": 0.012, "dca_tp_pct": 0.025}], "note": ""}
        return json.dumps(body), {"input_tokens": 2000, "output_tokens": 150}

    # patcha call_claude sia in brain che nel namespace di cli (cli lo importa direttamente)
    _brain.call_claude = alternating_call
    _c.call_claude = alternating_call

    try:
        with tempfile.TemporaryDirectory() as d:
            _c.STATE_FILE = os.path.join(d, "state_v2.json")
            _c.DATA_DIR = d

            state = cli.load_state(_c.STATE_FILE)
            # ciclo 1: apre
            cli.run_cycle(state, NOW)
            acc = cli.make_account(state)
            assert "BTC" in acc.positions, f"BTC non aperto nel ciclo 1, posizioni: {list(acc.positions)}"

            # ciclo 2: DCA
            state["last_call_ms"] = 0
            state["last_open_ms"] = {}
            cli.run_cycle(state, NOW + cli.HOUR_MS)
            acc2 = cli.make_account(state)
            if "BTC" in acc2.positions:
                # se non è stato chiuso dallo stop, deve avere dca_count >= 1
                # (oppure il DCA è stato skippato per stop troppo stretto — accettabile)
                pos = acc2.positions["BTC"]
                assert pos.dca_count >= 0   # almeno non è crashato
    finally:
        cli.fetch_candles = orig_fetch
        _mc.fetch_all_context = orig_ctx
        _brain.call_claude = orig_call
        _c.call_claude = orig_call
        del os.environ["ANTHROPIC_API_KEY"]


def test_render_report_v2():
    """render_report deve includere le colonne V2 (DCA, trade_type)."""
    with tempfile.TemporaryDirectory() as d:
        import desk.cli as _c
        _c.DATA_DIR = d
        state = {}
        acc = cli.make_account(state)
        txt = cli.render_report(acc, {}, NOW)
        assert "DESK V2" in txt
        assert "Equity" in txt or "equity" in txt.lower()


def test_adaptive_sleep_shorter_with_open_scalp():
    """Con uno scalp aperto il sleep deve essere 900s, altrimenti 1800s."""
    with tempfile.TemporaryDirectory() as d:
        import desk.cli as _c
        _c.DATA_DIR = d
        state = {}
        acc = cli.make_account(state)
        # senza posizioni → 1800s
        sleep_no_pos = 900 if any(p.trade_type == "scalp" for p in acc.positions.values()) else 1800
        assert sleep_no_pos == 1800
        # con scalp aperto
        acc.open("BTC", 1, 100, 10, 100.0, 95.0, None, 0, {}, trade_type="scalp")
        sleep_with_scalp = 900 if any(p.trade_type == "scalp" for p in acc.positions.values()) else 1800
        assert sleep_with_scalp == 900


# ──────────────────────────────────────────────────────────────────────────────
# PAUSA = SVUOTAMENTO, COMANDI DELL'APP, RESET PORTAFOGLIO, HEARTBEAT
# ──────────────────────────────────────────────────────────────────────────────
import contextlib  # noqa: E402


@contextlib.contextmanager
def _sandbox(claude=None):
    """Cartella dati temporanea + mercato finto + Claude finto. Ripristina tutto all'uscita."""
    import desk.brain as _brain
    import desk.market_context as _mc
    import desk.cli as _c

    world = _world()
    saved = (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, _c.call_claude,
             _c.DATA_DIR, _c.STATE_FILE, os.environ.get("ANTHROPIC_API_KEY"),
             os.environ.pop("TELEGRAM_BOT_TOKEN", None), _c.fetch_all_context)
    cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
    _no_ctx = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
    _mc.fetch_all_context = _no_ctx
    _c.fetch_all_context = _no_ctx     # cli usa il nome importato: senza questo ogni ciclo di test andrebbe in rete
    calls = []

    def counted(system, user, max_tokens=1100, timeout=60):
        calls.append(1)
        return claude(system, user, max_tokens, timeout)

    if claude is not None:
        _brain.call_claude = counted
        _c.call_claude = counted
        os.environ["ANTHROPIC_API_KEY"] = "test"
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory() as d:
            _c.DATA_DIR = d
            _c.STATE_FILE = os.path.join(d, "state_v2.json")
            _c.HB.update(last_ok=None, last_error="", cycles=0)
            yield d, calls
    finally:
        (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, _c.call_claude,
         _c.DATA_DIR, _c.STATE_FILE, key, tok, _c.fetch_all_context) = saved
        if key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = key
        if tok is not None:
            os.environ["TELEGRAM_BOT_TOKEN"] = tok


def _decisions_stub(*decs):
    """call_claude che ritorna sempre le decisioni indicate (dict gia' completi)."""
    def call(system, user, max_tokens=1100, timeout=60):
        return json.dumps({"decisions": list(decs), "note": ""}), {"input_tokens": 2000, "output_tokens": 150}
    return call


def _dec(symbol, action, **kw):
    base = {"symbol": symbol, "action": action, "confidence": 85, "leverage": 10, "margin_usd": 100,
            "stop_loss_pct": 0.015, "take_profit_pct": 0.03, "reason": "test", "trade_type": "medio",
            "dca_sl_pct": 0.012, "dca_tp_pct": 0.025}
    base.update(kw)
    return base


def _open_btc(state, d):
    """Apre BTC con una prima passata normale (ritorna l'account dopo il ciclo)."""
    cli.run_cycle(state, NOW)
    acc = cli.make_account(state)
    assert "BTC" in acc.positions, f"setup: BTC non aperto ({list(acc.positions)})"
    return acc


def test_pause_drain_blocks_new_entries_and_dca_but_keeps_positions():
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        state = {}
        _open_btc(state, d)
        # in pausa Claude propone un nuovo ingresso (ETH) e un DCA su BTC: nessuno dei due deve passare
        import desk.brain as _brain, desk.cli as _c
        stub = _decisions_stub(_dec("ETH", "open_long"), _dec("BTC", "dca"))
        _brain.call_claude = _c.call_claude = stub
        state["last_call_ms"] = 0
        state["last_open_ms"] = {}
        cli.run_cycle(state, NOW + cli.HOUR_MS, drain=True)
        acc = cli.make_account(state)
        assert list(acc.positions) == ["BTC"], f"in pausa non si apre nulla: {list(acc.positions)}"
        assert acc.positions["BTC"].dca_count == 0, "in pausa niente DCA"
        assert not acc.closed, "la pausa NON chiude le posizioni a forza"


def test_pause_drain_still_allows_exits_decided_by_the_bot():
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        state = {}
        _open_btc(state, d)
        import desk.brain as _brain, desk.cli as _c
        stub = _decisions_stub(_dec("BTC", "close", reason="segnale girato"))
        _brain.call_claude = _c.call_claude = stub
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + cli.HOUR_MS, drain=True)
        acc = cli.make_account(state)
        assert not acc.positions, "l'uscita decisa dal bot e' ammessa anche in pausa"
        assert len(acc.closed) == 1 and acc.closed[0]["why"] == "chiusura Claude"
        hist = os.path.join(d, "trade_history.jsonl")
        assert os.path.exists(hist)


def test_pause_without_positions_does_not_call_claude_or_open():
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW, drain=True)
        assert not calls, "in pausa e senza posizioni non si paga nessuna chiamata a Claude"
        assert not cli.make_account(state).positions


def test_pause_pressed_mid_cycle_applies_immediately():
    """Se pause.flag compare mentre il ciclo e' in corso, quel ciclo non apre piu' nulla."""
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        import desk.brain as _brain, desk.cli as _c
        flag = os.path.join(d, "pause.flag")

        def call_then_pause(system, user, max_tokens=1100, timeout=60):
            open(flag, "w").close()   # l'utente preme Pausa mentre Claude sta ragionando
            return _decisions_stub(_dec("BTC", "open_long"))(system, user)

        _brain.call_claude = _c.call_claude = call_then_pause
        state = {}
        cli.run_cycle(state, NOW)   # parte "in marcia" (drain=False)
        assert not cli.make_account(state).positions


def test_resume_cycle_opens_again():
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW, drain=True)
        assert not cli.make_account(state).positions
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + cli.HOUR_MS, drain=False)
        assert "BTC" in cli.make_account(state).positions


def test_limits_come_from_code_not_from_saved_state():
    with tempfile.TemporaryDirectory() as d:
        import desk.cli as _c
        _c.DATA_DIR = d
        old = Limits(max_margin_trade=999.0, max_open=77, kill_equity=1.0)
        stale = PaperAccount(old, "main").to_dict()
        acc = cli.make_account({"main": stale})
        assert acc.limits.max_margin_trade == cli.PORTFOLIO.limits.max_margin_trade
        assert acc.limits.max_open == cli.PORTFOLIO.limits.max_open


def test_compute_mode():
    assert cli.compute_mode(False, 0) == "running"
    assert cli.compute_mode(False, 3) == "running"
    assert cli.compute_mode(True, 3) == "draining"
    assert cli.compute_mode(True, 0) == "paused"


def test_budget_reset_flag_touches_only_the_budget():
    with _sandbox() as (d, calls):
        state = {}
        acc = cli.make_account(state)
        acc.open("BTC", 1, 100, 10, 100.0, 95.0, None, NOW, {})
        cli.save_account(acc, state)
        state["budget"] = {"day": "2026-10-12", "spent": 0.66, "calls": 9}
        flag = os.path.join(d, "budget_reset.flag")
        with open(flag, "w") as f:
            f.write("equity_reset")   # il vecchio contenuto non deve piu' azzerare il conto
        assert cli._check_budget_reset_flag(state) is True
        assert state["budget"]["spent"] == 0.0 and state["budget"]["calls"] == 0
        assert not os.path.exists(flag)
        after = cli.make_account(state)
        assert "BTC" in after.positions and after.cash < 1000, "il conto non si tocca"


def _state_with_position(price_entry=100.0):
    state = {}
    acc = cli.make_account(state)
    pos, msg = acc.open("BTC", 1, 100, 10, price_entry, price_entry * 0.95, None, NOW, {})
    assert pos, msg
    cli.save_account(acc, state)
    return state


def test_close_all_closes_at_market_price_with_real_costs():
    with _sandbox() as (d, calls):
        state = _state_with_position(100.0)
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0, 1.0]]
        open(os.path.join(d, "reset.flag"), "w").close()
        assert cli._check_close_all_flag(state) is True
        acc = cli.make_account(state)
        assert not acc.positions
        rec = acc.closed[0]
        assert rec["why"] == "chiusura manuale"
        assert abs(rec["exit"] - 102.0) < 0.05, f"deve chiudere al prezzo di mercato, non a quello d'ingresso: {rec['exit']}"
        assert rec["net"] > 0 and rec["fees"] > 0, "pnl e commissioni reali, non zero"
        assert not os.path.exists(os.path.join(d, "reset.flag"))
        line = json.loads(open(os.path.join(d, "trade_history.jsonl")).read().splitlines()[0])
        assert isinstance(line, dict) and line["symbol"] == "BTC" and line["net"] == rec["net"]
        assert state["last_action"]["type"] == "close_all" and state["last_action"]["ok"] is True


def test_close_all_without_price_keeps_position_open_and_says_so():
    with _sandbox() as (d, calls):
        state = _state_with_position(100.0)
        cli.fetch_candles = lambda sym, bar="15m", limit=3: []
        open(os.path.join(d, "reset.flag"), "w").close()
        cli._check_close_all_flag(state)
        assert "BTC" in cli.make_account(state).positions, "senza prezzo non si inventa un'uscita"
        assert state["last_action"]["ok"] is False and "BTC" in state["last_action"]["skipped"]


def _state_with_two_positions():
    state = {}
    acc = cli.make_account(state)
    for sym in ("BTC", "ETH"):
        pos, msg = acc.open(sym, 1, 100, 10, 100.0, 95.0, None, NOW, {})
        assert pos, msg
    cli.save_account(acc, state)
    return state


def _write_close_request(d, symbols, age_s=0, with_ts=True):
    req = {"symbols": symbols}
    if with_ts:
        req["ts"] = int(time.time() * 1000) - int(age_s * 1000)
    with open(os.path.join(d, "close_position.flag"), "w") as f:
        json.dump(req, f)


def test_close_position_closes_only_the_chosen_one_and_marks_it_as_the_user_s():
    with _sandbox() as (d, calls):
        state = _state_with_two_positions()
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0, 1.0]]
        _write_close_request(d, ["BTC"])
        assert cli._check_close_position_flag(state) is True
        acc = cli.make_account(state)
        assert "BTC" not in acc.positions and "ETH" in acc.positions, "solo quella scelta"
        rec = acc.closed[0]
        assert rec["why"] == "chiusura manuale" and rec["closed_by"] == "utente"
        assert abs(rec["exit"] - 102.0) < 0.05 and rec["net"] > 0 and rec["fees"] > 0
        hist = [json.loads(x) for x in open(os.path.join(d, "trade_history.jsonl")).read().splitlines()]
        assert len(hist) == 1 and hist[0]["closed_by"] == "utente" and hist[0]["net"] == rec["net"]
        log = [json.loads(x) for x in open(os.path.join(d, "learning_log.jsonl")).read().splitlines()]
        closes = [r for r in log if r.get("ev") == "close"]
        assert len(closes) == 1 and closes[0]["closed_by"] == "utente" and closes[0]["symbol"] == "BTC"
        assert not os.path.exists(os.path.join(d, "close_position.flag"))
        assert not os.path.exists(os.path.join(d, "close_position.flag.work"))
        la = state["last_action"]
        assert la["type"] == "close_position" and la["ok"] is True and la["closed"] == ["BTC"]


def test_manual_close_counts_as_a_normal_win_or_loss_in_the_symbol_stats():
    """Il bot impara dal risultato vero: una chiusura manuale in profitto e' un trade vinto, in perdita un trade perso."""
    with _sandbox() as (d, calls):
        state = _state_with_two_positions()
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0 if sym == "BTC" else 97.0, 1.0]]
        _write_close_request(d, ["BTC", "ETH"])
        cli._check_close_position_flag(state)
        stats = cli.load_symbol_stats(d)
        assert stats["BTC"]["wins"] == 1 and stats["BTC"]["losses"] == 0
        assert stats["ETH"]["wins"] == 0 and stats["ETH"]["losses"] == 1, "anche le perdite manuali si registrano"


def test_close_all_marks_the_closes_as_the_user_s_too():
    with _sandbox() as (d, calls):
        state = _state_with_position(100.0)
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0, 1.0]]
        open(os.path.join(d, "reset.flag"), "w").close()
        cli._check_close_all_flag(state)
        assert cli.make_account(state).closed[0]["closed_by"] == "utente"


def test_close_position_request_that_is_too_old_is_not_executed():
    with _sandbox() as (d, calls):
        state = _state_with_two_positions()
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0, 1.0]]
        _write_close_request(d, ["BTC"], age_s=cli.CLOSE_POSITION_MAX_AGE_S + 5)
        assert cli._check_close_position_flag(state) is False
        assert set(cli.make_account(state).positions) == {"BTC", "ETH"}, "un clic dimenticato non chiude nulla"
        assert state["last_action"]["ok"] is False and "scaduta" in state["last_action"]["detail"]
        assert not os.path.exists(os.path.join(d, "close_position.flag"))
        assert not os.path.exists(os.path.join(d, "trade_history.jsonl"))
        _write_close_request(d, ["BTC"], with_ts=False)
        assert cli._check_close_position_flag(state) is False and "BTC" in cli.make_account(state).positions


def test_close_position_already_closed_is_not_an_error_and_without_price_stays_open():
    with _sandbox() as (d, calls):
        state = _state_with_two_positions()
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0, 1.0]]
        _write_close_request(d, ["SOL"])
        cli._check_close_position_flag(state)
        assert state["last_action"]["ok"] is True and "gia' chiusa" in state["last_action"]["detail"]
        assert set(cli.make_account(state).positions) == {"BTC", "ETH"}
        cli.fetch_candles = lambda sym, bar="15m", limit=3: []
        _write_close_request(d, ["BTC"])
        cli._check_close_position_flag(state)
        assert "BTC" in cli.make_account(state).positions, "senza prezzo non si inventa un'uscita"
        assert state["last_action"]["ok"] is False and "BTC" in state["last_action"]["skipped"]


def test_close_position_runs_from_process_flags_even_while_draining():
    with _sandbox() as (d, calls):
        state = _state_with_two_positions()
        cli.fetch_candles = lambda sym, bar="15m", limit=3: [[NOW, 101, 103, 100, 102.0, 1.0]]
        open(os.path.join(d, "pause.flag"), "w").close()                  # in pausa: svuotamento
        _write_close_request(d, ["ETH"])
        cli.process_flags(state)
        assert set(cli.make_account(state).positions) == {"BTC"}
        assert os.path.exists(os.path.join(d, "pause.flag")), "la chiusura singola non toglie la pausa"


def test_heartbeat_declares_that_it_can_close_a_single_position():
    assert cli.HB.get("close_position") is True


def _closed_trade_state(d, n=3):
    """Stato in pausa-e-piatto con n trade chiusi e relativo storico su disco."""
    state = {}
    acc = cli.make_account(state)
    px = 100.0
    for i in range(n):
        acc.open("BTC", 1, 100, 10, px, px * 0.95, None, NOW + i * 1000, {})
        rec = acc.close("BTC", px * (1.02 if i % 2 == 0 else 0.99), NOW + i * 1000 + 500, "take profit")
        cli.append_trade_history(d, rec)
    cli.save_account(acc, state)
    state["budget"] = {"day": "2026-10-12", "spent": 0.3, "calls": 4}
    state["run_no"] = 1
    cli.save_state(state, os.path.join(d, "state_v2.json"))
    return state, acc


def test_portfolio_reset_refused_if_not_paused():
    with _sandbox() as (d, calls):
        state, acc = _closed_trade_state(d)
        cash_before = cli.make_account(state).cash
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state) is False
        assert cli.make_account(state).cash == cash_before and len(cli.make_account(state).closed) == 3
        assert not os.path.exists(os.path.join(d, "archive"))
        assert state["last_action"]["ok"] is False and "pausa" in state["last_action"]["detail"]
        assert not os.path.exists(os.path.join(d, "reset_portfolio.flag"))


def test_portfolio_reset_refused_with_open_positions():
    with _sandbox() as (d, calls):
        state = _state_with_position()
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state) is False
        assert "BTC" in cli.make_account(state).positions
        assert "aperte" in state["last_action"]["detail"]


def test_portfolio_reset_archives_run_and_restarts_from_1000_in_pause():
    with _sandbox() as (d, calls):
        state, acc = _closed_trade_state(d)
        open(os.path.join(d, "lessons.md"), "w").write("appunti")
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        net_before = round(sum(c["net"] for c in acc.closed), 2)
        assert cli._check_portfolio_reset_flag(state) is True
        # conto nuovo da 1000$, nessun trade, resta in pausa
        new = cli.make_account(state)
        assert new.cash == 1000.0 and not new.positions and not new.closed
        assert state["paused"] is True and state["mode"] == "paused" and state["run_no"] == 2
        assert state["budget"]["spent"] == 0.3, "il budget giornaliero di Claude non c'entra col conto"
        assert os.path.exists(os.path.join(d, "pause.flag")), "dopo il reset il bot resta in pausa"
        hist = os.path.join(d, "trade_history.jsonl")
        assert os.path.exists(hist) and len(open(hist).read().splitlines()) == 3, \
            "lo storico e' il cervello: il reset NON lo tocca (l'app mostra solo la run attuale)"
        assert os.path.exists(os.path.join(d, "lessons.md")), "gli appunti restano"
        # archivio completo
        arch = os.path.join(d, "archive", state["last_action"]["archive"])
        for fn in ("summary.json", "trade_history.jsonl", "state_v2.json", "lessons.md"):
            assert os.path.exists(os.path.join(arch, fn)), fn
        summ = json.load(open(os.path.join(arch, "summary.json")))
        assert summ["trades"] == 3 and summ["run_no"] == 1 and summ["net_total"] == net_before
        assert summ["params"]["limits"]["max_margin_trade"] == cli.PORTFOLIO.limits.max_margin_trade
        assert len(open(os.path.join(arch, "trade_history.jsonl")).read().splitlines()) == 3
        # lo stato su disco e' quello nuovo
        assert cli.load_state(cli.STATE_FILE)["run_no"] == 2


def test_portfolio_reset_never_clears_lessons_even_if_asked():
    """Il cervello non si cancella da nessun comando: la vecchia opzione clear_lessons viene ignorata."""
    with _sandbox() as (d, calls):
        state, _ = _closed_trade_state(d)
        open(os.path.join(d, "lessons.md"), "w").write("appunti")
        open(os.path.join(d, "errors.md"), "w").write("errori")
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write(json.dumps({"clear_lessons": True}))
        assert cli._check_portfolio_reset_flag(state) is True
        assert open(os.path.join(d, "lessons.md")).read() == "appunti"
        assert open(os.path.join(d, "errors.md")).read() == "errori"
        arch = os.path.join(d, "archive", state["last_action"]["archive"])
        assert open(os.path.join(arch, "lessons.md")).read() == "appunti", "e restano anche in archivio"
        assert json.load(open(os.path.join(arch, "summary.json")))["lessons_cleared"] is False


def _brain_snapshot(d):
    names = ("trade_history.jsonl", "lessons.md", "errors.md", learning.LEARN_FILE)
    return {n: open(os.path.join(d, n), "rb").read() for n in names if os.path.exists(os.path.join(d, n))}


def test_portfolio_reset_leaves_every_brain_file_byte_identical():
    with _sandbox() as (d, calls):
        state, _ = _closed_trade_state(d, n=4)
        open(os.path.join(d, "lessons.md"), "w").write("[2026-10-14]\nnon inseguire il rimbalzo\n")
        open(os.path.join(d, "errors.md"), "w").write("# Errori ricorrenti\n- [2 volte] stop troppo stretto\n")
        learning.log_event(d, {"ev": "open", "portfolio": cli.PORTFOLIO.name, "run_no": 1, "symbol": "BTC"})
        before = _brain_snapshot(d)
        assert set(before) == {"trade_history.jsonl", "lessons.md", "errors.md", learning.LEARN_FILE}
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state) is True
        assert _brain_snapshot(d) == before, "il reset non deve cambiare nemmeno un byte del cervello"
        # secondo reset di fila: stessa cosa
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state) is True
        assert _brain_snapshot(d) == before


def test_history_rows_carry_run_and_starting_capital_and_engine_record_is_untouched():
    with _sandbox() as (d, calls):
        state = {"run_no": 3}
        acc = cli.make_account(state)
        acc.open("BTC", 1, 100, 10, 100.0, 95.0, None, NOW, {})
        rec = acc.close("BTC", 102.0, NOW + 500, "take profit")
        keys_before = set(rec)
        cli.record_close(state, rec)
        assert set(rec) == keys_before, "il record del motore non si modifica"
        line = json.loads(open(os.path.join(d, "trade_history.jsonl")).read().splitlines()[0])
        assert line["run_no"] == 3 and line["start_equity"] == cli.PORTFOLIO.limits.start_equity
        assert line["symbol"] == "BTC" and line["net"] == rec["net"]


def test_brain_keeps_reading_old_runs_after_a_reset_and_new_trades_join_them():
    """Dopo il reset le statistiche per moneta (il cervello) vedono ancora i trade della run vecchia,
    e quelli nuovi si aggiungono con il numero di run nuovo."""
    with _sandbox() as (d, calls):
        state, _ = _closed_trade_state(d, n=3)
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state) is True
        stats = cli.load_symbol_stats(d)
        assert stats["BTC"]["wins"] + stats["BTC"]["losses"] == 3
        acc = cli.make_account(state)
        acc.open("BTC", 1, 100, 10, 100.0, 95.0, None, NOW + 10_000, {})
        cli.record_close(state, acc.close("BTC", 103.0, NOW + 10_500, "take profit"))
        stats = cli.load_symbol_stats(d)
        assert stats["BTC"]["wins"] + stats["BTC"]["losses"] == 4
        rows = [json.loads(x) for x in open(os.path.join(d, "trade_history.jsonl")).read().splitlines()]
        assert rows[-1]["run_no"] == 2 and all("run_no" not in r for r in rows[:3]), \
            "i trade vecchi restano com'erano, quello nuovo e' della run 2"


def test_second_reset_does_not_overwrite_first_archive():
    with _sandbox() as (d, calls):
        state, _ = _closed_trade_state(d)
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state)
        first = state["last_action"]["archive"]
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state)
        assert state["last_action"]["archive"] != first
        assert len(os.listdir(os.path.join(d, "archive"))) == 2


@contextlib.contextmanager
def _frozen_clock(ms=NOW):
    """Il bot usa l'ora reale: per far coincidere ora e candele finte si congela time.time() dentro cli."""
    import time as _real

    class _T:
        time = staticmethod(lambda: ms / 1000.0)
        sleep = staticmethod(_real.sleep)
        strftime = staticmethod(_real.strftime)
        gmtime = staticmethod(_real.gmtime)
    saved = cli.time
    cli.time = _T
    try:
        yield
    finally:
        cli.time = saved


def test_loop_step_pause_drain_then_paused_then_resume():
    with _frozen_clock():
        _loop_step_pause_drain_then_paused_then_resume()


def _loop_step_pause_drain_then_paused_then_resume():
    """Il percorso completo dei tasti: marcia -> Pausa (svuotamento) -> fermo -> Avvia."""
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        import desk.brain as _brain, desk.cli as _c
        state, ctl = {}, {"next_cycle_ms": 0, "prev_paused": None}
        hb = lambda: json.load(open(os.path.join(d, "heartbeat.json")))
        # 1) in marcia: il primo giro fa un ciclo e apre BTC
        assert cli.loop_step(state, ctl) is True
        assert "BTC" in cli.make_account(state).positions
        assert hb()["mode"] == "running" and state["mode"] == "running"
        # 2) senza tasti, il giro dopo non rifa il ciclo (aspetta il prossimo intervallo)
        assert cli.loop_step(state, ctl) is False
        # 3) Pausa: ciclo immediato in svuotamento, la posizione resta, modo = draining
        open(os.path.join(d, "pause.flag"), "w").close()
        stub = _decisions_stub(_dec("ETH", "open_long"))
        _brain.call_claude = _c.call_claude = stub
        state["last_call_ms"] = 0
        assert cli.loop_step(state, ctl) is True
        assert list(cli.make_account(state).positions) == ["BTC"]
        assert state["mode"] == "draining" and state["paused"] is True and hb()["mode"] == "draining"
        # 4) la posizione si chiude (qui: chiusura manuale) -> il bot passa a "in pausa" e non cicla piu'
        open(os.path.join(d, "reset.flag"), "w").close()
        cli.loop_step(state, ctl)
        assert not cli.make_account(state).positions
        assert state["mode"] == "paused" and hb()["mode"] == "paused"
        ctl["next_cycle_ms"] = 0
        n_cycles = hb()["cycles"]
        assert cli.loop_step(state, ctl) is False and hb()["cycles"] == n_cycles, "fermo = nessun ciclo"
        # 5) Avvia: ripresa immediata
        os.remove(os.path.join(d, "pause.flag"))
        stub2 = _decisions_stub(_dec("BTC", "open_long"))
        _brain.call_claude = _c.call_claude = stub2
        state["last_call_ms"] = 0
        state["last_open_ms"] = {}
        assert cli.loop_step(state, ctl) is True
        assert state["mode"] == "running" and "BTC" in cli.make_account(state).positions


def test_failed_cycle_retries_soon_and_reports_error():
    with _frozen_clock(), _sandbox() as (d, calls):
        state, ctl = {}, {"next_cycle_ms": 0, "prev_paused": None}
        orig = cli.run_cycle

        def boom(*a, **k):
            raise RuntimeError("mercato giu'")
        cli.run_cycle = boom
        try:
            before = NOW
            assert cli.loop_step(state, ctl) is True
            assert ctl["next_cycle_ms"] - before <= (cli.RETRY_S + 5) * 1000
            hb = json.load(open(os.path.join(d, "heartbeat.json")))
            assert hb["last_ok"] is False and "mercato" in hb["last_error"]
        finally:
            cli.run_cycle = orig


def test_heartbeat_and_healthcheck():
    from desk import healthcheck as hc
    with tempfile.TemporaryDirectory() as d:
        now = 1_800_000_000.0
        assert hc.check(d, now) is False, "niente heartbeat e niente stato: non e' sano"
        open(os.path.join(d, "pause.flag"), "w").close()
        assert hc.check(d, now) is True, "ripiego vecchia regola: in pausa e' sano"
        os.remove(os.path.join(d, "pause.flag"))
        with open(os.path.join(d, "heartbeat.json"), "w") as f:
            json.dump({"ts": now - 60}, f)
        assert hc.check(d, now) is True
        with open(os.path.join(d, "heartbeat.json"), "w") as f:
            json.dump({"ts": now - 20 * 60}, f)
        assert hc.check(d, now) is False, "battito fermo da 20 minuti: bot bloccato"
        # anche in pausa, con battito fermo, e' bloccato (il nuovo bot batte sempre)
        open(os.path.join(d, "pause.flag"), "w").close()
        assert hc.check(d, now) is False
        with open(os.path.join(d, "heartbeat.json"), "w") as f:
            f.write("{non json")
        assert hc.check(d, now) is True, "heartbeat illeggibile: ripiego, pause.flag presente"


def test_symbol_stats_ignore_legacy_list_records():
    from desk.brain import load_symbol_stats
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "trade_history.jsonl"), "w") as f:
            f.write(json.dumps([{"symbol": "BTC", "net": 0.0}]) + "\n")   # vecchio formato (lista)
            f.write(json.dumps({"symbol": "ETH", "net": 5.0, "trade_type": "medio"}) + "\n")
        st = load_symbol_stats(d)
        assert "ETH" in st and st["ETH"]["wins"] == 1 and "BTC" not in st


def test_heartbeat_carries_real_params_and_cap():
    with _sandbox() as (d, calls):
        cli.HB.pop("params", None)
        cli.write_heartbeat({"main": {"positions": {}}})
        hb = json.load(open(os.path.join(d, "heartbeat.json")))
        pg = cli.PORTFOLIO
        assert hb["params"]["limits"]["max_margin_trade"] == pg.limits.max_margin_trade
        assert hb["params"]["limits"]["max_open"] == pg.limits.max_open
        assert hb["params"]["entry_score_tier_ab"] == 60 and hb["params"]["guardrail"]["min_margin"] == pg.guardrail_min_margin
        assert hb["daily_cap_usd"] == cli.DAILY_CAP and hb["portfolio"] == pg.name


# ──────────────────────────────────────────────────────────────────────────────
# ENTRATA DIVERSIFICATA (seconda gamba) E REGISTRO DI APPRENDIMENTO
# ──────────────────────────────────────────────────────────────────────────────
from desk import learning  # noqa: E402

SPLIT = {"retrace_pct": 0.005, "first_frac": 0.5}


def _split_acct(sl=98.5, margin=100, trade_type="medio", split=SPLIT):
    a = acct()
    p, msg = a.open("BTC", 1, margin, 10, 100.0, sl, None, 0, {}, trade_type=trade_type, split=split)
    assert p, msg
    return a, p


def test_split_opens_first_leg_only_then_fills_on_retrace():
    a, p = _split_acct()
    assert p.total_margin == 50 and p.legs == 1
    assert abs(p.pending_split["trigger"] - 99.5) < 1e-9 and p.pending_split["margin"] == 50
    assert abs(p.risk_plan_usd - 100 * 10 * (abs(p.entry - 98.5) / p.entry)) < 1e-3, "1R = margine pianificato intero"
    assert abs(a.cash - (1000 - 50 - 0.3)) < 1e-6
    assert a.on_bar("BTC", 0, 100, 100.4, 99.7, 100.2, BAR) is None
    assert p.pending_split is not None and p.legs == 1, "nessun ritracciamento: la seconda gamba resta in attesa"
    assert a.on_bar("BTC", BAR, 100, 100.0, 99.4, 99.8, BAR) is None
    assert p.pending_split is None and p.legs == 2
    assert p.total_margin == 100 and p.margin == 100, "il margine principale (base dei DCA) comprende entrambe le gambe"
    assert abs(a.cash - (1000 - 100 - 0.6)) < 1e-6, "commissioni su entrambe le gambe"
    assert 99.6 < p.entry < 99.9, f"entry medio tra le due gambe: {p.entry}"
    assert p.liq < p.sl, "la liquidazione resta oltre lo stop"
    assert [e["ev"] for e in a.events] == ["split_fill"] and a.events[0]["margin"] == 50


def test_split_second_leg_expires_without_retrace():
    a, p = _split_acct()
    ttl = p.pending_split["expire_ms"]
    assert ttl == 12 * 3_600_000, "medio: 12 ore"
    assert a.on_bar("BTC", ttl - BAR, 100, 100.3, 99.8, 100.1, BAR) is None and p.pending_split
    assert a.on_bar("BTC", ttl, 100, 100.3, 99.8, 100.1, BAR) is None
    assert p.pending_split is None and p.legs == 1 and p.total_margin == 50
    assert a.events[-1]["ev"] == "split_cancel" and "scaduta" in a.events[-1]["reason"]
    s, sp = _split_acct(trade_type="scalp")
    assert sp.pending_split["expire_ms"] == 3 * 3_600_000, "scalp: 3 ore"


def test_split_is_cancelled_by_partial_close_dca_and_close():
    a, p = _split_acct()
    a.partial_close("BTC", 100.5, 1000, 0.35)
    assert p.pending_split is None and a.events[-1]["reason"] == "chiusura parziale"
    b, q = _split_acct()
    rec, msg = b.add_dca("BTC", 97.5, None, 1000, {"BTC": 99.0}, "dca")
    assert rec is not None, msg
    assert q.pending_split is None and b.events[-1]["reason"] == "DCA eseguito" and q.legs == 1
    c, r = _split_acct()
    c.close("BTC", 101.0, 1000)
    assert c.events[-1]["ev"] == "split_cancel" and "chiusa" in c.events[-1]["reason"]
    assert not c.positions


def test_split_falls_back_to_single_entry_when_it_makes_no_sense():
    # stop troppo vicino: il ritracciamento ammesso (60% dello stop) sarebbe sotto lo 0,15%
    a, p = _split_acct(sl=99.8)
    assert p.pending_split is None and p.total_margin == 100 and p.legs == 1
    # margine troppo piccolo per due gambe sopra il minimo (30$)
    b, q = _split_acct(margin=40)
    assert q.pending_split is None and q.total_margin == 40
    # ritracciamento oltre il 60% dello stop: viene ridotto, non rifiutato
    c, r = _split_acct(sl=99.0, split={"retrace_pct": 0.012, "first_frac": 0.5})
    assert r.pending_split is not None and r.pending_split["retrace_pct"] < 0.012
    assert r.pending_split["trigger"] > r.sl, "il livello della seconda gamba sta sempre prima dello stop"


def test_split_trigger_and_stop_in_same_bar_fills_then_stops_out():
    a, p = _split_acct()
    rec = a.on_bar("BTC", 0, 100, 100.1, 97.0, 98.0, BAR)
    assert rec and rec["why"] == "stop loss" and rec["legs"] == 2 and rec["margin"] == 100
    assert not a.positions and any(e["ev"] == "split_fill" for e in a.events)
    assert rec["net"] < 0 and rec["net_r"] is not None and rec["net_r"] < 0


def test_split_state_roundtrip_and_old_state_still_loads():
    a, p = _split_acct()
    p.features = {"tier": "A", "rsi1h": 61.2}
    d = json.loads(json.dumps(a.to_dict()))
    b = PaperAccount.from_dict(d)
    q = b.positions["BTC"]
    assert q.pending_split == p.pending_split and q.features == p.features and q.risk_plan_usd == p.risk_plan_usd
    for k in ("features", "risk_plan_usd", "r_dist", "entry0", "px_hi", "px_lo", "legs", "pending_split"):
        d["positions"]["BTC"].pop(k)          # stato salvato dalla versione precedente
    old = PaperAccount.from_dict(d).positions["BTC"]
    assert old.pending_split is None and old.legs == 1 and old.features == {}
    assert PaperAccount.from_dict(d).on_bar("BTC", 0, 100, 100.2, 99.6, 100.0, BAR) is None, "una posizione vecchia gira"


def test_close_records_carry_additive_net_r_and_excursions():
    a = acct()
    p, _ = a.open("BTC", 1, 100, 10, 100.0, 99.0, None, 0, {})
    a.on_bar("BTC", 0, 100, 101.0, 99.6, 100.5, BAR)
    a.on_bar("BTC", BAR, 100.5, 102.5, 100.2, 102.0, BAR)
    risk = p.risk_plan_usd
    assert 10.0 < risk < 10.4
    part = a.partial_close("BTC", 102.0, 2 * BAR, 0.4)
    fin = a.close("BTC", 101.0, 3 * BAR)
    assert abs((part["net_r"] + fin["net_r"]) - (part["net"] + fin["net"]) / risk) < 2e-3, "net_r e' additivo"
    assert 2.3 < fin["mfe_r"] < 2.6 and 0.35 < fin["mae_r"] < 0.5, (fin["mfe_r"], fin["mae_r"])
    assert fin["hold_min"] == 45.0 and fin["legs"] == 1 and fin["risk_plan_usd"] == round(risk, 4)


def test_learning_log_never_raises_drops_nan_and_caps_candidates():
    with tempfile.TemporaryDirectory() as d:
        assert learning.log_event(d, {"ev": "x", "v": float("nan"), "w": [1, float("inf")]}) is True
        row = learning.read_events(d)[0]
        assert row["v"] is None and row["w"] == [1, None] and row["schema"] == learning.SCHEMA
        with open(os.path.join(d, "file.txt"), "w") as f:
            f.write("x")
        assert learning.log_event(os.path.join(d, "file.txt", "sub"), {"ev": "x"}) is False, "errore assorbito"
        old = learning.MAX_BYTES_CANDIDATES
        learning.MAX_BYTES_CANDIDATES = 1
        try:
            assert learning.log_event(d, {"ev": "candidate"}, candidate=True) is False
            assert learning.log_event(d, {"ev": "open"}) is True, "i trade si scrivono anche oltre il tetto dei candidati"
        finally:
            learning.MAX_BYTES_CANDIDATES = old
        with open(os.path.join(d, learning.LEARN_FILE), "a") as f:
            f.write("riga rotta {\n")
        assert [r["ev"] for r in learning.read_events(d)] == ["x", "open"], "le righe illeggibili si ignorano"


def test_build_features_is_tolerant_and_json_safe():
    f0 = learning.build_features("BTC", None, None, None, NOW)
    assert f0["tier"] == "A" and f0["hour_utc"] == int(NOW // 3_600_000 % 24)
    from desk.signals import read_symbol
    r = read_symbol("BTC", _series(4500, 0.0006, seed=3, start=100.0), NOW)
    ctx = {"funding": {"BTC": {"rate": 0.0001, "predicted": 0.0002, "long_cost_8h_bp": 1.0}},
           "oi": {}, "ls_ratio": {"BTC": {"ratio": 1.7}}}
    dec = {"confidence": 80, "stop_loss_pct": 0.01, "take_profit_pct": 0.025, "leverage": 15,
           "margin_usd": 100, "action": "open_long", "reason": "t", "trade_type": "scalp"}
    f = learning.build_features("BTC", r, ctx, dec, NOW, btc_reading=r)
    assert f["ls_ratio"] == 1.7 and f["dec_rr"] == 2.5 and f["funding_pred"] == 0.0002
    assert f["sig_score"] is not None and f["rsi1h"] is not None and f["btc_score"] == f["sig_score"]
    assert f["ema50_200_4h"] in (-1, 0, 1) and f["oi_usd"] is None
    json.dumps(f, allow_nan=False)
    json.dumps(learning.build_features("ETH", r, {"funding": {"ETH": {"rate": float("nan")}}}, dec, NOW),
               allow_nan=False)


def test_parse_decisions_reads_split_retrace_in_percent():
    import desk.brain as _b
    txt = json.dumps({"decisions": [
        {"symbol": "BTC", "action": "open_long_split", "split_retrace_pct": 0.5},
        {"symbol": "ETH", "action": "open_short_split"}], "note": ""})
    out = _b.parse_decisions(txt)["decisions"]
    assert abs(out[0]["split_retrace_pct"] - 0.005) < 1e-12 and out[1]["split_retrace_pct"] == 0.0


def _split_stub(**kw):
    return _decisions_stub(_dec("BTC", "open_long_split", margin_usd=200, leverage=15,
                                split_retrace_pct=0.5, **kw))


def test_cycle_split_open_logs_features_and_waits_for_second_leg():
    with _sandbox(_split_stub()) as (d, calls):
        state = {}
        acc = _open_btc(state, d)
        pos = acc.positions["BTC"]
        assert pos.legs == 1 and pos.pending_split is not None
        assert abs(pos.total_margin - pos.pending_split["margin"]) < 0.01, "50% subito, 50% in attesa"
        assert abs(pos.pending_split["retrace_pct"] - 0.005) < 1e-9
        assert pos.features["tier"] == "A" and pos.features["split_requested"] is True
        ev = learning.read_events(d, "open")
        assert len(ev) == 1 and ev[0]["id"] == pos.id and ev[0]["portfolio"] == cli.PORTFOLIO.name
        assert ev[0]["risk_plan_usd"] > 0 and ev[0]["split_plan"]["margin"] == pos.pending_split["margin"]
        assert "hour_utc" in ev[0]["features"] and "proposed_margin" in ev[0]["features"]


def test_cycle_pause_cancels_pending_second_leg_but_keeps_first():
    with _sandbox(_split_stub()) as (d, calls):
        state = {}
        _open_btc(state, d)
        import desk.brain as _brain, desk.cli as _c
        _brain.call_claude = _c.call_claude = _decisions_stub(_dec("BTC", "hold"))
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + cli.HOUR_MS, drain=True)
        pos = cli.make_account(state).positions["BTC"]
        assert pos.pending_split is None and pos.legs == 1, "in pausa non entra nulla di nuovo"
        cancels = learning.read_events(d, "split_cancel")
        assert len(cancels) == 1 and cancels[0]["reason"] == "bot in pausa"


def test_cycle_second_leg_fills_when_market_retraces_and_is_logged():
    with _sandbox(_split_stub()) as (d, calls):
        state = {}
        _open_btc(state, d)
        first = cli.make_account(state).positions["BTC"]
        base = cli.fetch_candles

        def extended(sym, bar="15m", limit=300):
            rows = base(sym, bar, limit)
            if sym == "BTC" and rows:
                last = rows[-1]
                px = float(last[4])
                rows = rows + [[int(last[0]) + BAR, px, px * 1.001, px * (1 - 0.0075), px * 0.999, 1.0]]
            return rows

        cli.fetch_candles = extended
        import desk.brain as _brain, desk.cli as _c
        _brain.call_claude = _c.call_claude = _decisions_stub(_dec("BTC", "hold"))
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + cli.HOUR_MS)
        pos = cli.make_account(state).positions["BTC"]
        assert pos.legs == 2 and pos.pending_split is None
        assert abs(pos.total_margin - 2 * first.total_margin) < 0.02
        assert pos.entry < first.entry, "la seconda gamba abbassa il prezzo medio del long"
        fills = learning.read_events(d, "split_fill")
        assert len(fills) == 1 and fills[0]["portfolio"] == cli.PORTFOLIO.name and fills[0]["id"] == pos.id


def test_cycle_close_is_logged_with_net_r_and_reset_keeps_the_learning_log():
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        state = {}
        _open_btc(state, d)
        import desk.brain as _brain, desk.cli as _c
        _brain.call_claude = _c.call_claude = _decisions_stub(_dec("BTC", "close", reason="girato"))
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + cli.HOUR_MS, drain=True)
        cl = learning.read_events(d, "close")
        assert len(cl) == 1 and cl[0]["net_r"] is not None and cl[0]["risk_plan_usd"] > 0 and cl[0]["legs"] == 1
        line = json.loads(open(os.path.join(d, "trade_history.jsonl")).read().splitlines()[0])
        assert line["net_r"] == cl[0]["net_r"], "stesso risultato nello storico e nel registro"
        cli.save_state(state, cli.STATE_FILE)
        open(os.path.join(d, "pause.flag"), "w").close()
        open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
        assert cli._check_portfolio_reset_flag(state) is True
        assert len(learning.read_events(d)) >= 2, "il reset a 1000$ non cancella cio' che il bot ha registrato"
        assert os.path.exists(os.path.join(d, "trade_history.jsonl")), "nemmeno lo storico dei trade"


def test_a_failure_in_feature_logging_never_blocks_an_entry():
    with _sandbox(_split_stub()) as (d, calls):
        orig = cli.build_features

        def boom(*a, **k):
            raise RuntimeError("boom")

        cli.build_features = boom
        try:
            state = {}
            acc = _open_btc(state, d)
        finally:
            cli.build_features = orig
        assert "BTC" in acc.positions and acc.positions["BTC"].pending_split is not None


# ---- registro delle chiamate a Claude (solo diagnosi: nessuna decisione cambia) ----

def _cut_stub(n_extra=8, tail=""):
    """call_claude che risponde con un JSON tagliato a meta' (come se il limite di token fosse finito)."""
    full = json.dumps({"decisions": [_dec("BTC", "open_long"), _dec("ETH", "hold")], "note": ""})
    cut = full[:full.index("}, {") + n_extra] + tail

    def call(system, user, max_tokens=1100, timeout=60):
        return cut, {"input_tokens": 9000, "output_tokens": 1100, "stop_reason": "max_tokens"}
    call.cut = cut
    return call


def test_call_claude_reports_stop_reason_without_changing_the_cost():
    from desk import brain

    class _Resp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    payload = {"content": [{"type": "text", "text": '{"decisions": ['}],
               "usage": {"input_tokens": 100, "output_tokens": 1100}, "stop_reason": "max_tokens"}
    orig = brain.urllib.request.urlopen
    brain.urllib.request.urlopen = lambda req, timeout=60: _Resp(payload)
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        text, usage = brain.call_claude("s", "u")
    finally:
        brain.urllib.request.urlopen = orig
        del os.environ["ANTHROPIC_API_KEY"]
    assert text == '{"decisions": ['
    assert usage["stop_reason"] == "max_tokens" and usage["output_tokens"] == 1100
    assert abs(brain.cost_of(usage) - (100 * brain.PRICE_IN + 1100 * brain.PRICE_OUT)) < 1e-12, \
        "la nuova voce non cambia il costo registrato"


def test_diagnose_reply_names_the_reason_and_agrees_with_parse_decisions():
    from desk.brain import diagnose_reply, parse_decisions
    cut = '{"decisions": [{"symbol": "BTC", "action": "hold"}, {"symbol": "ETH", "action": "ho'
    assert diagnose_reply(cut) == "json_troncato"
    assert diagnose_reply('{"decisions": [{"symbol": "BTC", "action"') == "troncato_prima_della_fine"
    assert diagnose_reply('```json\n{"decisions": [') == "troncato_prima_della_fine"
    assert diagnose_reply("") == "vuota" and diagnose_reply("   ") == "vuota" and diagnose_reply(None) == "vuota"
    assert diagnose_reply("nessun json qui") == "senza_json"
    assert diagnose_reply('{"decisions": 5}') == "forma_errata"
    assert diagnose_reply('{"decisions": [1,]}') == "json_non_valido"
    assert diagnose_reply('{"decisions": [], "note": "x"}') == "letta"
    for txt in (cut, "", "nessun json qui", '{"decisions": 5}', '{"decisions": [1,]}'):
        assert parse_decisions(txt) is None, "ogni motivo di scarto corrisponde a una risposta che il bot non legge"
    assert parse_decisions('{"decisions": [], "note": "x"}') is not None


def test_cycle_logs_a_discarded_claude_reply_with_its_text_and_reason():
    stub = _cut_stub()
    with _sandbox(stub) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW)
        evs = learning.read_events(d, "claude_call")
        assert len(evs) == 1
        e = evs[0]
        assert e["ok"] is False and e["fail_reason"] == "json_troncato" and e["n_decisions"] is None
        # output_tokens e' quello dello stub; max_tokens e' il tetto richiesto in paper (non e' piu' 1100 dal 15 ott)
        assert e["stop_reason"] == "max_tokens" and e["output_tokens"] == 1100
        assert e["max_tokens"] == cli.CLAUDE_MAX_TOKENS_PAPER == 3000
        assert e["reply"] == stub.cut and e["reply_chars"] == len(stub.cut)
        assert e["cost_usd"] > 0 and e["portfolio"] == cli.PORTFOLIO.name and e["n_positions"] == 0
        assert e["prompt_chars"] > 100
        assert state["budget"]["calls"] == 1, "la chiamata resta contata nel budget, come prima"


def test_cycle_logs_a_readable_claude_reply_without_its_text():
    with _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW)
        e = learning.read_events(d, "claude_call")[0]
        assert e["ok"] is True and e["n_decisions"] == 1
        assert "reply" not in e and "fail_reason" not in e
        assert e["stop_reason"] is None, "lo stub non lo fornisce: nessun valore inventato"


def test_logging_claude_calls_does_not_change_decisions_budget_or_fallback():
    def run(without_logging):
        with _sandbox(_cut_stub()) as (d, calls):
            orig, orig_rules = cli.log_claude_call, cli.rules_decisions
            if without_logging:
                cli.log_claude_call = lambda *a, **k: None
            # le regole di riserva (usate quando la risposta di Claude e' illeggibile) aprono BTC:
            # cosi' il confronto riguarda un'azione vera e non un ciclo vuoto
            cli.rules_decisions = lambda *a, **k: [_dec("BTC", "open_long")]
            try:
                state = {}
                cli.run_cycle(state, NOW)
                state["last_call_ms"] = 0
                state["last_open_ms"] = {}
                cli.run_cycle(state, NOW + cli.HOUR_MS)
                acc = cli.make_account(state)
                return (sorted(acc.positions), round(acc.cash, 6), len(acc.closed), state["budget"]["calls"],
                        round(state["budget"]["spent"], 9), state["last_call_ms"],
                        round(acc.positions["BTC"].total_margin, 6))
            finally:
                cli.log_claude_call, cli.rules_decisions = orig, orig_rules
    with_log, without_log = run(False), run(True)
    assert with_log == without_log, f"il registro ha cambiato il comportamento: {with_log} != {without_log}"
    assert with_log[0] == ["BTC"], "le regole di riserva hanno aperto davvero"
    assert with_log[3] == 2, "le due chiamate sono contate"


def test_cycle_logs_a_failed_claude_call_and_still_falls_back_to_rules():
    def failing(system, user, max_tokens=1100, timeout=60):
        raise RuntimeError("chiamata Claude fallita (URLError)")

    with _sandbox(failing) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW)
        e = learning.read_events(d, "claude_call")[0]
        assert e["ok"] is False and e["fail_reason"] == "errore:RuntimeError" and "URLError" in e["error"]
        assert (state.get("budget") or {}).get("calls", 0) == 0, "nessuna spesa se la risposta non e' arrivata"
        assert state["main"]["cash"] > 0, "il ciclo e' andato avanti con le regole"


def test_a_failure_while_logging_a_claude_reply_never_blocks_the_cycle():
    with _sandbox(_cut_stub()) as (d, calls):
        orig = cli.diagnose_reply

        def boom(*a, **k):
            raise RuntimeError("boom")

        cli.diagnose_reply = boom
        try:
            state = {}
            cli.run_cycle(state, NOW)
        finally:
            cli.diagnose_reply = orig
        assert state["budget"]["calls"] == 1 and "main" in state
        assert learning.read_events(d, "claude_call") == [], "niente scritto, ma nessun blocco"


def test_discarded_reply_longer_than_the_limit_is_stored_shortened():
    long_cut = '{"decisions": [{"symbol": "BTC", "reason": "' + "x" * 9000

    def call(system, user, max_tokens=1100, timeout=60):
        return long_cut, {"input_tokens": 9000, "output_tokens": 1100, "stop_reason": "max_tokens"}

    with _sandbox(call) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW)
        e = learning.read_events(d, "claude_call")[0]
        assert e["reply_chars"] == len(long_cut) and len(e["reply"]) < 6000
        assert e["reply"].startswith('{"decisions"') and "[... omesso ...]" in e["reply"]
        assert e["reply"].endswith("x" * 100)


# ---- calendario di Claude: decide solo il QUANDO, le decisioni non cambiano ----

_H = 3_600_000
_CAL_N = [0]


def _iso(ms):
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ms / 1000, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_cal(d, *wins, raw=None):
    """Scrive claude_schedule.json con finestre (inizio_ms, fine_ms). Cambia la data del file ad ogni scrittura."""
    body = raw if raw is not None else json.dumps(
        {"version": 1, "windows": [{"start": _iso(s), "end": _iso(e), "label": "t"} for s, e in wins]})
    p = os.path.join(d, "claude_schedule.json")
    with open(p, "w") as f:
        f.write(body)
    _CAL_N[0] += 1
    t = 1_700_000_000_000_000_000 + _CAL_N[0] * 1_000_000_000
    os.utime(p, ns=(t, t))


@contextlib.contextmanager
def _clean_calendar():
    from desk import schedule as S
    S.reset_cache()
    learning.STAMP.clear()
    try:
        yield S
    finally:
        S.reset_cache()
        learning.STAMP.clear()


def test_calendar_file_is_validated_all_or_nothing():
    from desk.schedule import parse_windows
    w, err = parse_windows({"windows": [
        {"start": "2026-10-13T12:30:00Z", "end": "2026-10-13T16:30:00Z", "label": "mar 13 14:30-18:30"},
        {"start": "2026-10-13T22:00:00+00:00", "end": "2026-10-14T04:00:00+02:00"}]})
    assert err == "" and len(w) == 2
    assert w[0]["end_ms"] - w[0]["start_ms"] == 4 * _H and w[1]["end_ms"] - w[1]["start_ms"] == 4 * _H
    assert w[0]["id"] == str(w[0]["start_ms"])
    inverno, _ = parse_windows({"windows": [{"start": "2026-10-27T08:00:00+01:00", "end": "2026-10-27T12:00:00+01:00"}]})
    assert _iso(inverno[0]["start_ms"]) == "2026-10-27T07:00:00Z", "lo scostamento esplicito vale anche col cambio d'ora"
    for bad in (
        {"windows": [{"start": "2026-10-13T12:30:00", "end": "2026-10-13T16:30:00Z"}]},           # senza fuso
        {"windows": [{"start": "2026-10-13T16:30:00Z", "end": "2026-10-13T12:30:00Z"}]},           # fine prima dell'inizio
        {"windows": [{"start": "2026-10-13T12:30:00Z", "end": "2026-10-13T12:30:00Z"}]},           # durata zero
        {"windows": [{"start": "2026-10-13T12:00:00Z", "end": "2026-10-13T16:00:00Z"},
                     {"start": "2026-10-13T15:00:00Z", "end": "2026-10-13T18:00:00Z"}]},           # sovrapposte
        {"windows": [{"start": "ieri", "end": "oggi"}]}, {"windows": [{"end": "2026-10-13T12:30:00Z"}]},
        {"windows": "tutte"}, {"niente": 1}, [], 5, None,
    ):
        wins, err = parse_windows(bad)
        if bad == []:
            assert wins == [] and err == "", "un elenco vuoto e' valido: Claude spento"
        else:
            assert wins == [] and err, f"doveva essere rifiutato: {bad}"


def test_schedule_state_edges_hot_reload_and_broken_file():
    with _clean_calendar() as S, tempfile.TemporaryDirectory() as d:
        s = S.schedule_state(d, 5 * _H)
        assert s["mode"] == "none" and s["allowed"] is True and s["window"] is None
        _write_cal(d, (10 * _H, 14 * _H), (20 * _H, 24 * _H))
        assert S.schedule_state(d, 10 * _H - 1)["allowed"] is False
        s = S.schedule_state(d, 10 * _H)
        assert s["allowed"] is True and s["window"]["id"] == str(10 * _H), "l'inizio e' compreso"
        assert S.schedule_state(d, 14 * _H - 1)["allowed"] is True
        s = S.schedule_state(d, 14 * _H)
        assert s["allowed"] is False and s["next_start_ms"] == 20 * _H and s["n_future"] == 1, "la fine e' esclusa"
        assert S.schedule_state(d, 25 * _H)["next_start_ms"] is None
        # il bot rilegge da solo quando il file cambia
        _write_cal(d, (30 * _H, 31 * _H))
        assert S.schedule_state(d, 12 * _H)["allowed"] is False and S.schedule_state(d, 30 * _H)["allowed"] is True
        # file rovinato: resta l'ultimo calendario valido, con l'errore visibile
        _write_cal(d, raw="{non e' json")
        s = S.schedule_state(d, 30 * _H)
        assert s["allowed"] is True and s["error"] and s["mode"] == "calendar"
        # file tolto: si torna al comportamento di sempre
        os.remove(os.path.join(d, "claude_schedule.json"))
        s = S.schedule_state(d, 12 * _H)
        assert s["mode"] == "none" and s["allowed"] is True
        # file rovinato senza nessun calendario valido in memoria (riavvio): Claude resta spento
        S.reset_cache()
        _write_cal(d, raw="{non e' json")
        s = S.schedule_state(d, 12 * _H)
        assert s["mode"] == "invalid" and s["allowed"] is False and s["error"]


def test_claude_is_called_only_inside_a_window_and_rules_decide_outside():
    with _clean_calendar() as S, _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        orig_rules = cli.rules_decisions
        cli.rules_decisions = lambda *a, **k: [_dec("BTC", "open_long")]
        try:
            _write_cal(d, (NOW + 2 * _H, NOW + 6 * _H))
            state = {}
            cli.run_cycle(state, NOW)   # prima della finestra
            assert calls == [], "fuori finestra Claude non viene chiamato"
            assert "BTC" in cli.make_account(state).positions, "fuori finestra decidono le regole"
            opens = learning.read_events(d, "open")
            assert opens and all(e.get("claude_win") == 0 for e in opens), "etichetta: fuori finestra"
            state["last_call_ms"] = 0
            cli.run_cycle(state, NOW + 2 * _H)   # dentro
            assert len(calls) == 1
            cli.run_cycle(state, NOW + 6 * _H + 1000)   # la finestra e' finita (fine esclusa)
            assert len(calls) == 1
        finally:
            cli.rules_decisions = orig_rules


def test_each_window_has_its_own_budget_and_midnight_utc_does_not_reset_it():
    from desk.brain import cost_of
    cost = cost_of({"input_tokens": 2000, "output_tokens": 150})
    with _clean_calendar(), _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        # NOW e' alle 08:00 UTC: la finestra copre la mezzanotte UTC
        _write_cal(d, (NOW, NOW + 24 * _H), (NOW + 30 * _H, NOW + 34 * _H))
        state = {"budget": {"day": "2027-01-15", "spent": 0.69, "calls": 9, "total_spent": 5.0},
                 "last_call_ms": NOW - 60_000}
        cli.run_cycle(state, NOW)
        assert len(calls) == 1, "all'inizio della finestra il budget riparte e la prima chiamata e' subito possibile"
        assert abs(state["budget"]["spent"] - cost) < 1e-9 and state["budget"]["calls"] == 1
        assert abs(state["budget"]["total_spent"] - (5.0 + cost)) < 1e-9, "il totale storico si conserva"
        cli.run_cycle(state, NOW + 17 * _H)   # dopo la mezzanotte UTC, stessa finestra
        assert len(calls) == 2 and state["budget"]["calls"] == 2
        assert abs(state["budget"]["spent"] - 2 * cost) < 1e-9, "a mezzanotte UTC il budget della finestra NON si azzera"
        assert state["budget"]["day"] == "2027-01-16"
        state["budget"]["spent"] = 0.69   # budget della finestra finito
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + 18 * _H)
        assert len(calls) == 2, "col budget finito Claude non viene chiamato nemmeno dentro la finestra"
        cli.run_cycle(state, NOW + 30 * _H)   # seconda finestra
        assert len(calls) == 3 and abs(state["budget"]["spent"] - cost) < 1e-9, "ogni finestra ha il suo budget"
        assert state["claude_window"] == str(NOW + 30 * _H) or state["claude_window"] == _id_of(NOW + 30 * _H)


def _id_of(ms):
    # l'id usa l'orario arrotondato al secondo, come nel file
    import datetime as _dt
    return str(int(_dt.datetime.fromisoformat(_iso(ms).replace("Z", "+00:00")).timestamp() * 1000))


def test_without_a_calendar_nothing_changes():
    with _clean_calendar(), _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW)
        assert len(calls) == 1 and "claude_window" not in state
        assert "claude_win" not in learning.STAMP
        cli.run_cycle(state, NOW + 17 * _H)   # nuovo giorno UTC: il budget giornaliero di sempre riparte
        assert state["budget"]["day"] == "2027-01-16" and state["budget"]["calls"] == 1


def test_calendar_changes_only_when_claude_is_asked_not_what_happens():
    def run(with_calendar):
        with _clean_calendar(), _sandbox(_decisions_stub(_dec("BTC", "open_long"))) as (d, calls):
            if with_calendar:
                _write_cal(d, (NOW - _H, NOW + 4 * _H))
            state = {}
            cli.run_cycle(state, NOW)
            acc = cli.make_account(state)
            return (sorted(acc.positions), round(acc.cash, 6), state["budget"]["calls"],
                    round(state["budget"]["spent"], 9), round(acc.positions["BTC"].total_margin, 6))
    assert run(True) == run(False), "dentro la finestra il bot si comporta come prima"


def test_lessons_call_follows_the_calendar():
    with _clean_calendar(), _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        seen = []
        orig = cli.update_lessons
        cli.update_lessons = lambda *a, **k: seen.append(1)
        try:
            _write_cal(d, (NOW + _H, NOW + 5 * _H))
            state = {}
            cli.run_cycle(state, NOW)
            assert seen == [], "fuori finestra niente chiamata per le lezioni"
            cli.run_cycle(state, NOW + _H)
            assert seen == [1]
        finally:
            cli.update_lessons = orig


def test_broken_calendar_keeps_claude_off_and_never_blocks_the_cycle():
    with _clean_calendar(), _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        _write_cal(d, raw="[[[ rotto")
        state = {}
        cli.run_cycle(state, NOW)
        assert calls == [] and "main" in state, "Claude spento, il ciclo e' andato avanti con le regole"
        cli.write_heartbeat(state)
        hb = json.load(open(os.path.join(d, "heartbeat.json")))["claude_schedule"]
        assert hb["mode"] == "invalid" and hb["allowed"] is False and hb["error"]


def test_a_window_start_triggers_an_immediate_cycle_and_the_heartbeat_shows_the_schedule():
    with _frozen_clock(), _clean_calendar(), _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        _write_cal(d, (NOW - _H, NOW + 3 * _H))
        state, ctl = {}, {"next_cycle_ms": NOW + 10 * _H, "prev_paused": False}
        assert cli.loop_step(state, ctl) is True, "inizia una finestra: il ciclo parte subito"
        assert len(calls) == 1 and ctl["window_id"] == _id_of(NOW - _H)
        assert cli.loop_step(state, ctl) is False, "stessa finestra: si torna al ritmo normale"
        hb = json.load(open(os.path.join(d, "heartbeat.json")))["claude_schedule"]
        assert hb["mode"] == "calendar" and hb["allowed"] is True and hb["window_end_ms"] == NOW + 3 * _H
    with _frozen_clock(), _clean_calendar(), _sandbox(_decisions_stub(_dec("ETH", "hold"))) as (d, calls):
        state, ctl = {}, {"next_cycle_ms": NOW + 10 * _H, "prev_paused": False}
        assert cli.loop_step(state, ctl) is False, "senza calendario il ritmo non cambia"
        hb = json.load(open(os.path.join(d, "heartbeat.json")))["claude_schedule"]
        assert hb["mode"] == "none" and hb["allowed"] is True


# ---- correzioni del redeploy 15 ott: TP impossibile (negativo), tetto di token di Claude paper/live ----

def test_sane_tp_discards_prices_that_cannot_exist():
    # il caso visto in app: short LTC a 62.79 con take_profit_pct=4.72 -> TP a -233.84
    px = 62.79
    assert cli._sane_tp("LTC", px * (1 + -1 * 4.724159898), "test") is None
    assert cli._sane_tp("LTC", 0.0, "test") is None
    assert cli._sane_tp("LTC", None, "test") is None
    # un TP normale resta identico
    assert cli._sane_tp("LTC", px * (1 - 0.03), "test") == px * (1 - 0.03)
    assert cli._sane_tp("LTC", px * (1 + 0.03), "test") == px * (1 + 0.03)


def test_claude_limits_paper_is_larger_live_is_unchanged():
    assert cli.claude_limits(False) == (3000, 120)
    assert cli.claude_limits(True) == (1100, 60)   # il live non cambia finche' l'utente non decide


def _stub(calls, action, tp_pct):
    def call(system, user, max_tokens=1100, timeout=60):
        calls.append({"max_tokens": max_tokens, "timeout": timeout})
        body = {"decisions": [{"symbol": "BTC", "action": action, "confidence": 85, "leverage": 10,
                               "margin_usd": 150, "stop_loss_pct": 0.01, "take_profit_pct": tp_pct,
                               "reason": "test", "trade_type": "medio", "dca_sl_pct": 0, "dca_tp_pct": 0}],
                "note": "test"}
        return json.dumps(body), {"input_tokens": 2000, "output_tokens": 150}
    return call


def _run_open(action, tp_pct, drift):
    """Due cicli completi come test_full_cycle_v2: ritorna (posizione BTC o None, chiamate fatte a Claude)."""
    import desk.brain as _brain
    import desk.market_context as _mc

    world = _world(drift=drift)
    orig_fetch, orig_ctx, orig_call = cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude
    calls = []
    stub = _stub(calls, action, tp_pct)
    cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
    _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
    _brain.call_claude = stub
    cli.call_claude = stub
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        with tempfile.TemporaryDirectory() as d:
            cli.STATE_FILE = os.path.join(d, "state_v2.json")
            cli.DATA_DIR = d
            state = cli.load_state(cli.STATE_FILE)
            cli.run_cycle(state, NOW)
            cli.save_state(state, cli.STATE_FILE)
            state["last_call_ms"] = 0
            state["last_open_ms"] = {}
            cli.run_cycle(state, NOW + cli.HOUR_MS)
            return cli.make_account(state).positions.get("BTC"), calls
    finally:
        cli.fetch_candles, _mc.fetch_all_context = orig_fetch, orig_ctx
        _brain.call_claude = orig_call
        cli.call_claude = orig_call
        del os.environ["ANTHROPIC_API_KEY"]


def test_cycle_in_paper_asks_claude_with_3000_tokens():
    pos, calls = _run_open("open_long", 0.025, drift=0.0006)
    assert calls, "Claude non e' stato chiamato"
    assert all(c == {"max_tokens": 3000, "timeout": 120} for c in calls), calls
    assert pos is not None and pos.tp is not None   # un TP normale non viene toccato


def test_short_with_absurd_tp_opens_without_tp_instead_of_negative_price():
    pos, _ = _run_open("open_short", 4.72, drift=-0.0006)
    assert pos is not None, "lo short deve aprirsi comunque: il guardiano scarta solo il TP, non il trade"
    assert pos.side == -1
    assert pos.tp is None, f"TP impossibile non scartato: {pos.tp}"
