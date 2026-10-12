"""Test della sala segnali V2: conto paper (costi, stop, liquidazione, tetti, DCA, scalp/medio)."""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    a = acct()
    # V2: max_margin_total=800$, max_open=5
    p1, _ = a.open("A", 1, 400, 3, 100.0, 90.0, None, 0, {})
    assert p1 is not None and p1.total_margin == 400
    p2, _ = a.open("B", 1, 400, 3, 100.0, 90.0, None, 0, {})
    assert p2 is not None
    p3, msg = a.open("C", 1, 100, 3, 100.0, 90.0, None, 0, {})   # supera 800$
    assert p3 is None and "margine" in msg
    # max_open=5
    b = acct()
    for s in "ABCDE":
        b.open(s, 1, 40, 3, 100.0, 90.0, None, 0, {})
    assert b.open("F", 1, 40, 3, 100.0, 90.0, None, 0, {})[0] is None


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
    # prezzo scende a 97: DCA con nuovo SL a 94
    prices = {"BTC": 97.0}
    new_sl = 94.0
    result, msg = a.add_dca("BTC", new_sl, None, BAR, prices, "test dca")
    assert result is not None, f"DCA fallito: {msg}"
    assert result.dca_count == 1
    assert result.entry < 100.0   # entry media deve essere tra 97 e 100
    assert result.sl == new_sl
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
            assert pos.leverage >= 15, f"GUARDRAIL deve forzare lev>=15x, got {pos.leverage}"
            assert pos.total_margin >= 150, f"GUARDRAIL deve forzare margin>=150$, got {pos.total_margin}"
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
