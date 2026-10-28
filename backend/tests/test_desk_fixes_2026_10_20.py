"""Correzioni del 20/10/2026: cronologia delle barre (A), barra in formazione (B), cambio di giorno (C),
stop del DCA (D), barra d'apertura (E), trend giornaliero e soglia del tier C."""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk.engine import Limits, PaperAccount  # noqa: E402
from desk import signals  # noqa: E402

BAR = 900_000
DAY = 86_400_000
T0 = 1_800_000_000_000 // BAR * BAR          # inizio di una barra
OPEN = T0 + 20_000                           # il ciclo apre 20 s dopo l'inizio della barra


def long_btc(a, tp=110.0, sl=95.0):
    p, msg = a.open("BTC", 1, 100, 10, 100.0, sl, tp, OPEN, {}, trade_type="medio")
    assert p is not None, msg
    return p


# ---------------- A: ogni barra si giudica una volta, con i livelli di quel momento

def test_lowered_tp_does_not_fire_on_past_bars():
    a = PaperAccount(Limits())
    long_btc(a)
    bars = [(T0, 100, 101, 99.5, 100.5), (T0 + BAR, 100.5, 106, 100.4, 105),
            (T0 + 2 * BAR, 105, 105.2, 101.8, 102)]
    for t, o, h, l, c in bars:
        assert a.on_bar("BTC", t, o, h, l, c, BAR) is None
    # chiusura parziale con TP abbassato a 104 dopo che il prezzo era gia' passato da 106
    now = T0 + 3 * BAR + 20_000
    assert a.partial_close("BTC", 102.0, now, 0.3, new_tp=104.0) is not None
    # il vecchio ciclo ripassava tutte le barre con il TP nuovo: chiusura "retroattiva" alla barra delle 106
    for t, o, h, l, c in bars:
        assert a.on_bar("BTC", t, o, h, l, c, BAR) is None
    assert "BTC" in a.positions
    # una barra SUCCESSIVA che tocca 104 chiude, con orario dopo la decisione
    rec = a.on_bar("BTC", T0 + 3 * BAR, 102, 104.5, 101.9, 104.2, BAR)
    assert rec is not None and rec["why"] == "take profit"
    assert rec["close_ms"] > now


def test_same_bar_is_never_judged_twice():
    a = PaperAccount(Limits())
    p = long_btc(a)
    a.on_bar("BTC", T0 + BAR, 100, 101, 99, 100.5, BAR)
    assert p.last_bar_ms == T0 + BAR
    # la stessa barra (o una precedente) con un minimo sotto lo stop non viene piu' giudicata
    assert a.on_bar("BTC", T0 + BAR, 100, 101, 90, 100.5, BAR) is None
    assert a.on_bar("BTC", T0, 100, 101, 90, 100.5, BAR) is None
    assert "BTC" in a.positions


# ---------------- E: la barra in cui nasce la posizione si controlla

def test_entry_bar_stop_is_checked():
    a = PaperAccount(Limits())
    long_btc(a)
    rec = a.on_bar("BTC", T0, 100, 100.2, 94.0, 94.5, BAR)
    assert rec is not None and rec["why"] == "stop loss"
    assert rec["close_ms"] == T0 + BAR


def test_entry_bar_closures_are_recognisable_from_the_record():
    """Le chiusure sulla barra d'apertura (approssimazione dichiarata) si contano dai record con hold_min <= 15,
    senza campi nuovi: la prima barra chiude entro la durata della barra, le successive oltre."""
    a = PaperAccount(Limits())
    long_btc(a)
    first = a.on_bar("BTC", T0, 100, 100.2, 94.0, 94.5, BAR)
    assert first["hold_min"] <= BAR / 60_000
    b = PaperAccount(Limits())
    long_btc(b)
    assert b.on_bar("BTC", T0, 100, 100.4, 99.6, 100.1, BAR) is None
    later = b.on_bar("BTC", T0 + BAR, 100.1, 100.2, 94.0, 94.5, BAR)
    assert later["hold_min"] > BAR / 60_000


def test_bar_at_time_zero_is_judged():
    a = PaperAccount(Limits())
    a.open("BTC", 1, 100, 10, 100.0, 95.0, None, 0, {})
    assert a.on_bar("BTC", 0, 100, 100.2, 94.0, 94.5, BAR)["why"] == "stop loss"


def test_bar_ending_before_open_is_ignored():
    a = PaperAccount(Limits())
    long_btc(a)
    assert a.on_bar("BTC", T0 - BAR, 100, 100.2, 80.0, 94.5, BAR) is None
    assert "BTC" in a.positions


def test_legacy_position_keeps_old_behaviour_on_entry_bar():
    a = PaperAccount(Limits())
    long_btc(a)
    d = a.to_dict()
    del d["positions"]["BTC"]["last_bar_ms"]          # stato salvato da una versione precedente
    b = PaperAccount.from_dict(json.loads(json.dumps(d)))
    assert b.positions["BTC"].last_bar_ms == T0
    assert b.on_bar("BTC", T0, 100, 100.2, 94.0, 94.5, BAR) is None   # come prima: barra d'apertura saltata
    assert b.on_bar("BTC", T0 + BAR, 100, 100.2, 94.0, 94.5, BAR)["why"] == "stop loss"


def test_state_roundtrip_keeps_last_bar():
    a = PaperAccount(Limits())
    long_btc(a)
    a.on_bar("BTC", T0 + BAR, 100, 101, 99, 100.5, BAR)
    b = PaperAccount.from_dict(json.loads(json.dumps(a.to_dict())))
    assert b.positions["BTC"].last_bar_ms == T0 + BAR


# ---------------- D: il DCA non allarga lo stop

def medio_long_in_loss(sl=95.0):
    a = PaperAccount(Limits())
    a.open("ETH", 1, 100, 10, 100.0, sl, 110.0, OPEN, {}, trade_type="medio")
    return a


def test_dca_keeps_tighter_existing_stop():
    a = medio_long_in_loss(sl=95.0)
    pos, msg = a.add_dca("ETH", 90.0, None, OPEN + BAR, {"ETH": 97.0})
    assert pos is not None, msg
    assert pos.sl == 95.0
    assert "stop non allargato" in pos.reason


def test_dca_can_tighten_stop():
    a = medio_long_in_loss(sl=95.0)
    pos, msg = a.add_dca("ETH", 96.0, None, OPEN + BAR, {"ETH": 97.0})
    assert pos is not None and pos.sl == 96.0


def test_dca_short_keeps_tighter_stop():
    a = PaperAccount(Limits())
    a.open("ETH", -1, 100, 10, 100.0, 105.0, 90.0, OPEN, {}, trade_type="medio")
    pos, msg = a.add_dca("ETH", 110.0, None, OPEN + BAR, {"ETH": 103.0})
    assert pos is not None and pos.sl == 105.0


def test_dca_rejected_when_kept_stop_already_crossed():
    a = medio_long_in_loss(sl=95.0)
    pos, msg = a.add_dca("ETH", 90.0, None, OPEN + BAR, {"ETH": 94.0})
    assert pos is None and "stop" in msg
    assert a.positions["ETH"].dca_count == 0


# ---------------- C: cambio di giorno con i prezzi veri

def test_roll_day_uses_open_pnl():
    a = PaperAccount(Limits())
    long_btc(a)
    flat = a.equity({})
    a.roll_day("2027-01-16", {"BTC": 90.0})
    assert a.day_start_equity < flat


# ---------------- trend giornaliero

def daily_rows(n, start_ms, drift):
    px = 100.0 * np.cumprod(np.full(n, 1 + drift))
    return [[start_ms + i * DAY, p, p * 1.01, p * 0.99, p, 1000.0] for i, p in enumerate(px)]


def test_closed_daily_drops_forming_bar_and_rejects_gaps():
    now = T0
    first = (now // DAY - 250) * DAY
    rows = daily_rows(251, first, 0.001)          # l'ultima e' il giorno in corso
    arr = signals.closed_daily(rows, now)
    assert len(arr) == 250 and arr[-1, 0] + DAY <= now
    gap = rows[:100] + rows[101:]
    assert len(signals.closed_daily(gap, now)) == 0
    assert len(signals.closed_daily([["x"]], now)) == 0
    assert len(signals.closed_daily([], now)) == 0


def series15(n, end_open_ms, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * 1.001
    lo = np.minimum(o, c) * 0.999
    t = end_open_ms - (n - 1 - np.arange(n)) * BAR
    return np.c_[t, o, h, lo, c, np.full(n, 10.0)]


def test_daily_trend_present_with_real_daily_bars():
    now = T0 + 20_000
    arr15 = series15(1000, T0 - BAR)
    up = signals.closed_daily(daily_rows(260, (now // DAY - 260) * DAY, 0.003), now)
    down = signals.closed_daily(daily_rows(260, (now // DAY - 260) * DAY, -0.003), now)
    none = signals.read_symbol("SOL", arr15, now)
    r_up = signals.read_symbol("SOL", arr15, now, daily=up)
    r_dn = signals.read_symbol("SOL", arr15, now, daily=down)
    assert none.facts["daily_trend"] == ""
    assert "bull" in r_up.facts["daily_trend"] and "bear" in r_dn.facts["daily_trend"]
    assert r_up.long_score == min(100, none.long_score + 15)
    assert r_dn.short_score == min(100, none.short_score + 15)


def test_daily_trend_absent_with_short_history():
    now = T0 + 20_000
    arr15 = series15(1000, T0 - BAR)
    short = signals.closed_daily(daily_rows(120, (now // DAY - 120) * DAY, -0.003), now)
    r = signals.read_symbol("SOL", arr15, now, daily=short)
    assert r.facts["daily_trend"] == ""


def test_live_price_is_used_for_price_checks():
    """Il prezzo vivo (barra in formazione) resta quello di prima per il confronto con l'EMA50: gli indicatori
    invece si calcolano solo sulle barre chiuse."""
    now = T0 + 20_000
    arr15 = series15(1000, T0 - BAR)
    hi = signals.read_symbol("SOL", arr15, now, price=1e9)
    lo = signals.read_symbol("SOL", arr15, now, price=1e-9)
    assert hi.price == 1e9
    assert hi.long_score - lo.long_score == 8 and lo.short_score - hi.short_score == 8


# ---------------- cli: soglia, barre chiuse, cache giornaliera, ordine del ciclo

from desk import cli  # noqa: E402
from test_desk import _legacy_open


def test_tier_thresholds():
    assert cli.tier_entry_score("BTC") == 60 and cli.tier_entry_score("eth") == 60
    assert cli.tier_entry_score("SOL") == 70


def test_prompts_state_the_same_altcoin_threshold_as_the_code():
    """Il testo dato a Claude (Hawk e Bull) non deve mai dire una soglia diversa da quella applicata dal codice."""
    from desk import brain
    thr = cli.TIER_C_ENTRY_SCORE
    for prompt in (brain.SYSTEM, brain.SYSTEM_BULL):
        assert f"TIER C (altcoin, tutto il resto): confidenza >= {thr}/100" in prompt
    assert "apri solo se confidenza >= 75 per altcoin, >= 65 per TIER A" in brain.SYSTEM_BULL
    assert "confidenza >= 65/100" not in brain.SYSTEM


def test_closed_bars_drops_forming_bar():
    arr = series15(10, T0)
    out = cli.closed_bars(arr, T0 + 20_000)
    assert len(out) == 9 and out[-1, 0] == T0 - BAR
    assert len(cli.closed_bars(arr, T0 + BAR)) == 10


def test_classical_cycle_does_not_fetch_native_daily_history():
    # Golden baseline used the short 15m-derived daily context; no added 1d feed.
    import inspect
    assert "daily_bars(" not in inspect.getsource(cli.run_cycle)
    assert not hasattr(cli, "daily_bars")


def test_cycle_judges_bars_before_decisions():
    """Ciclo vero: posizione aperta, il prezzo era salito a 106 e torna a 102; Claude fa una chiusura parziale
    con TP a +2% (104,04). Prima la barra delle 106 veniva ripassata con il TP nuovo e la posizione si chiudeva
    "in take profit" nel passato. Ora resta aperta."""
    import desk.brain as _brain
    import desk.market_context as _mc

    now = T0 + 4 * BAR + 20_000
    rows = {s: np.array([[T0 - (60 - i) * BAR, 100, 100.1, 99.9, 100, 1] for i in range(60)])
            for s in cli.SYMBOLS}
    btc = [[T0, 100, 100.5, 99.8, 100.2, 1], [T0 + BAR, 100.2, 106, 100.1, 105, 1],
           [T0 + 2 * BAR, 105, 105.1, 101.9, 102.2, 1], [T0 + 3 * BAR, 102.2, 102.4, 101.8, 102, 1],
           [T0 + 4 * BAR, 102, 102.1, 101.9, 102, 1]]
    rows["BTC"] = np.vstack([rows["BTC"], np.array(btc, dtype=float)])

    def call(system, user, max_tokens=1100, timeout=60):
        body = {"decisions": [{"symbol": "BTC", "action": "partial_close", "confidence": 70, "leverage": 1,
                               "margin_usd": 0, "stop_loss_pct": 0, "take_profit_pct": 0.02,
                               "partial_close_fraction": 0.3, "partial_close_tp2_pct": 0.02,
                               "reason": "test", "trade_type": "medio", "dca_sl_pct": 0, "dca_tp_pct": 0}],
                "note": "test"}
        return json.dumps(body), {"input_tokens": 10, "output_tokens": 10}

    saved = (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude, cli.STATE_FILE,
             cli.DATA_DIR)
    cli.fetch_candles = lambda sym, bar="15m", limit=300: rows.get(sym, np.zeros((0, 6)))[-limit:].tolist()
    _mc.fetch_all_context = lambda syms, n: {"funding": {}, "oi": {}, "news": [], "ts": n}
    _brain.call_claude = call
    cli.call_claude = call
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        with tempfile.TemporaryDirectory() as d:
            cli.STATE_FILE = os.path.join(d, "state_v2.json")
            cli.DATA_DIR = d
            state = cli.load_state(cli.STATE_FILE)
            acc = cli.make_account(state)
            pos, msg = _legacy_open(acc, "BTC", 1, 100, 10, 100.0, 95.0, 110.0, OPEN, {}, trade_type="medio")
            assert pos is not None, msg
            state["main"] = acc.to_dict()
            state["last_call_ms"] = 0
            cli.run_cycle(state, now)
            after = cli.make_account(state)
            partials = [c for c in after.closed if c.get("partial")]
            assert partials, "la chiusura parziale di Claude doveva avvenire"
            assert "BTC" in after.positions, [c["why"] for c in after.closed]
            assert abs(after.positions["BTC"].tp - 102 * 1.02 * (1 - 0)) < 0.5
            assert after.positions["BTC"].last_bar_ms == T0 + 3 * BAR   # la barra in formazione non conta
    finally:
        (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude, cli.STATE_FILE,
         cli.DATA_DIR) = saved


def test_cycle_day_change_uses_open_pnl():
    """Al cambio di giorno UTC con una posizione in perdita, la base dello stop giornaliero include la perdita
    aperta (prima si calcolava ai prezzi d'ingresso: base piu' alta del vero)."""
    import desk.brain as _brain
    import desk.market_context as _mc

    now = T0 + 4 * BAR + 20_000
    rows = {s: np.array([[T0 - (60 - i) * BAR, 100, 100.1, 99.9, 100, 1] for i in range(65)])
            for s in cli.SYMBOLS}
    rows["BTC"] = np.array([[T0 - (60 - i) * BAR, 90, 90.1, 89.9, 90, 1] for i in range(65)])

    def call(system, user, max_tokens=1100, timeout=60):
        return json.dumps({"decisions": [], "note": "test"}), {"input_tokens": 10, "output_tokens": 10}

    saved = (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude, cli.STATE_FILE,
             cli.DATA_DIR)
    cli.fetch_candles = lambda sym, bar="15m", limit=300: rows.get(sym, np.zeros((0, 6)))[-limit:].tolist()
    _mc.fetch_all_context = lambda syms, n: {"funding": {}, "oi": {}, "news": [], "ts": n}
    _brain.call_claude = call
    cli.call_claude = call
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        with tempfile.TemporaryDirectory() as d:
            cli.STATE_FILE = os.path.join(d, "state_v2.json")
            cli.DATA_DIR = d
            state = cli.load_state(cli.STATE_FILE)
            acc = cli.make_account(state)
            pos, msg = _legacy_open(acc, "BTC", 1, 100, 3, 100.0, 80.0, None, T0 - 70 * BAR, {}, trade_type="medio")
            assert pos is not None, msg
            acc.day = "2000-01-01"
            flat = acc.equity({})
            state["main"] = acc.to_dict()
            cli.run_cycle(state, now)
            after = cli.make_account(state)
            assert "BTC" in after.positions
            assert after.day_start_equity < flat - 20, (after.day_start_equity, flat)
    finally:
        (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude, cli.STATE_FILE,
         cli.DATA_DIR) = saved
