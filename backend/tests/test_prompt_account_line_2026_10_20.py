"""La riga CONTO del prompt dice a Claude i limiti VERI di ciascun bot (prima: '/2000$, /10' per tutti e due).
Decisione dell'utente 20/10/2026 14:11: budget $1000 per bot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk import brain, cli  # noqa: E402
from desk.engine import PaperAccount  # noqa: E402


def _conto_line(cfg, margin_open=0):
    acc = PaperAccount(cfg.limits)
    if margin_open:
        p, msg = acc.open("BTC", 1, margin_open, 10, 100.0, 97.0, 110.0, 1_800_000_000_000, {}, trade_type="medio")
        assert p is not None, msg
    snap = cli.account_snapshot(acc, acc.equity({"BTC": 100.0}), None)
    text = brain.build_prompt(snap, [], [], [], "")
    return next(l for l in text.splitlines() if l.startswith("CONTO:"))


def test_both_bots_have_a_thousand_dollar_budget_and_ten_slots():
    for cfg in (cli._make_hawk_config(), cli._make_bull_config()):
        line = _conto_line(cfg)
        assert "margine in uso 0/1000$" in line, line
        assert "posizioni 0/10" in line, line
        assert "2000" not in line, line


def test_line_follows_the_real_limits_of_each_portfolio():
    """Se i limiti cambiano, la riga cambia: non e' un testo fisso."""
    from dataclasses import replace
    cfg = cli._make_bull_config()
    cfg2 = replace(cfg, limits=replace(cfg.limits, max_margin_total=777.0, max_open=4))
    line = _conto_line(cfg2)
    assert "/777$" in line and "posizioni 0/4" in line, line


def test_line_shows_margin_in_use():
    line = _conto_line(cli._make_bull_config(), margin_open=200)
    assert "margine in uso 200/1000$" in line and "posizioni 1/10" in line, line


def test_snapshot_without_limits_invents_no_numbers():
    snap = {"equity": 1000.0, "cash": 1000.0, "margin": 0.0, "n_open": 2, "day_pnl": 0.0}
    line = brain.build_prompt(snap, [], [], [], "").splitlines()[0]
    assert "2000" not in line and "/10" not in line and "margine in uso 0$" in line and "posizioni 2," in line, line


def _run_real_cycle_and_get_prompt(cfg):
    """Fa girare un vero run_cycle (candele e Claude finti) col portafoglio indicato e restituisce il prompt inviato a Claude."""
    import json
    import tempfile
    import numpy as np
    import desk.market_context as mc
    from desk import cli as _c

    NOW = 1_800_000_000_000
    BAR = 15 * 60 * 1000
    last_t = (NOW // BAR) * BAR
    world = {}
    rng = np.random.default_rng(7)
    n = 4500
    for i, s in enumerate(_c.SYMBOLS):
        close = 100.0 * (i + 1) * np.cumprod(1 + 0.0004 + rng.normal(0, 0.003, n))
        a = np.zeros((n, 6))
        a[:, 0] = last_t - (n - 1 - np.arange(n)) * BAR
        a[:, 1] = close; a[:, 4] = close; a[:, 2] = close * 1.002; a[:, 3] = close * 0.998; a[:, 5] = 1000.0
        world[s] = a
    seen = []

    def stub(system, user, max_tokens=1100, timeout=60):
        seen.append(user)
        return json.dumps({"decisions": [], "note": "t"}), {"input_tokens": 100, "output_tokens": 10}

    saved = (_c.fetch_candles, mc.fetch_all_context, brain.call_claude, _c.call_claude, _c.PORTFOLIO,
             _c.STATE_FILE, _c.DATA_DIR)
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        _c.fetch_candles = lambda sym, bar="15m", limit=300: world.get(sym, np.zeros((0, 6)))[-limit:].tolist()
        mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
        brain.call_claude = stub
        _c.call_claude = stub
        _c.PORTFOLIO = cfg
        with tempfile.TemporaryDirectory() as d:
            _c.STATE_FILE = os.path.join(d, "state_v2.json")
            _c.DATA_DIR = d
            state = _c.load_state(_c.STATE_FILE)
            _c.run_cycle(state, NOW)
            state["last_call_ms"] = 0
            _c.run_cycle(state, NOW + _c.HOUR_MS)
    finally:
        (_c.fetch_candles, mc.fetch_all_context, brain.call_claude, _c.call_claude, _c.PORTFOLIO,
         _c.STATE_FILE, _c.DATA_DIR) = saved
        os.environ.pop("ANTHROPIC_API_KEY", None)
    return seen


def test_real_run_cycle_sends_claude_the_real_limits_of_each_bot():
    for cfg in (cli._make_hawk_config(), cli._make_bull_config()):
        prompts = _run_real_cycle_and_get_prompt(cfg)
        assert prompts, f"{cfg.name}: Claude non e' stato chiamato (il test non verifica nulla)"
        line = next(l for l in prompts[-1].splitlines() if l.startswith("CONTO:"))
        assert "margine in uso 0/1000$" in line and "posizioni 0/10" in line and "2000" not in line, (cfg.name, line)
