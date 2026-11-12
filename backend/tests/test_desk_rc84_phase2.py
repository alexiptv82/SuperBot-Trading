"""RC84 fase 2: tendenze 4h/1d vere su barre chiuse (o UNKNOWN), indicatori solo su candele chiuse, politica prudente,
classificazione consultiva del trend, confronto in ombra prompt/motore, S25 sempre spento senza opt-in.

Nessuna rete: le barre native 4h/1d sono costruite qui come le restituirebbe l'exchange (ultima barra in formazione).
"""
import json
import os
import sys

import numpy as np
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from desk import signals as S  # noqa: E402

M15, H1, H4, D1 = 900_000, 3_600_000, 14_400_000, 86_400_000
NOW = 1_794_441_600_000 + 2 * H1 + 7 * 60_000            # 12/11/2026 02:07 UTC: barre 4h/1d in formazione


def native_bars(now_ms, period, n, drift, start=100.0, seed=1, with_partial=True):
    """n barre CHIUSE allineate al periodo fino all'ultima chiusa prima di now, piu' quella in formazione."""
    rng = np.random.default_rng(seed)
    last_open = now_ms - now_ms % period - period            # apertura dell'ultima barra chiusa
    ts = last_open - (n - 1 - np.arange(n)) * period
    c = start * np.exp(np.cumsum(rng.normal(drift, 0.004, n)))
    o = np.r_[c[0], c[:-1]]
    rows = np.column_stack([ts, o, np.maximum(o, c) * 1.002, np.minimum(o, c) * 0.998, c, np.full(n, 100.0)])
    if with_partial:
        p = c[-1]
        rows = np.vstack([rows, [last_open + period, p, p, p, p, 1.0]])
    return rows


def native_htf(now_ms, direction):
    """Barre native 4h e 1d con tendenza netta nella direzione indicata (per le prove d'integrazione)."""
    return {"4h": native_bars(now_ms, H4, 400, 0.002 * direction), "1d": native_bars(now_ms, D1, 300, 0.004 * direction)}


def m15(now_ms, n, drift, seed=3, start=100.0):
    """Candele 15m fino a quella in formazione compresa (come la Bitget)."""
    rng = np.random.default_rng(seed)
    cur = now_ms - now_ms % M15
    ts = cur - (n - 1 - np.arange(n)) * M15
    c = start * np.exp(np.cumsum(rng.normal(drift, 0.0015, n)))
    o = np.r_[start, c[:-1]]
    return np.column_stack([ts, o, np.maximum(o, c) * 1.0005, np.minimum(o, c) * 0.9995, c, np.full(n, 10.0)])


# ------------------------------------------------------------------------------------------- P0 tendenze 4h/1d
def test_ema200_is_never_replaced_by_a_shorter_average():
    a = m15(NOW, 1000, -0.0002)                                # 1000 candele 15m = ~62 barre 4h
    r = S.read_symbol("X", a, NOW)
    assert r.facts["trend4h_state"] == "UNKNOWN" and "storia insufficiente" in r.facts["trend4h_why"]
    assert r.facts["ema50_200_4h"] == "UNKNOWN"
    assert r.side == 0                                          # politica prudente: nessuna apertura dalle regole
    assert not any(w.startswith("trend 4h (+") for w in r.why)


def test_native_closed_4h_bars_give_a_real_trend_and_the_open_bar_is_ignored():
    a = m15(NOW, 1000, 0.0)
    up = native_bars(NOW, H4, 400, 0.002)
    r = S.read_symbol("X", a, NOW, bars_4h=up)
    assert r.facts["trend4h_state"] == "UP" and r.facts["trend4h_bars"] == 400
    crazy = up.copy()
    crazy[-1, 1:5] = [1.0, 1.0, 1.0, 1.0]                      # barra in formazione assurda: non deve contare
    r2 = S.read_symbol("X", a, NOW, bars_4h=crazy)
    assert (r2.long_score, r2.short_score, r2.facts["trend4h_state"]) == (r.long_score, r.short_score, "UP")


def test_4h_trend_points_go_to_the_trend_side():
    a = m15(NOW, 1000, 0.0)
    up = S.read_symbol("X", a, NOW, bars_4h=native_bars(NOW, H4, 400, 0.002))
    dn = S.read_symbol("X", a, NOW, bars_4h=native_bars(NOW, H4, 400, -0.002))
    unk = S.read_symbol("X", a, NOW)
    assert up.long_score - unk.long_score == S.TREND_4H_POINTS
    assert dn.short_score - unk.short_score == S.TREND_4H_POINTS


def test_stale_or_wrong_timeframe_bars_are_unknown_not_a_trend():
    a = m15(NOW, 1000, 0.0)
    stale = native_bars(NOW - 3 * H4, H4, 400, 0.002)
    r = S.read_symbol("X", a, NOW, bars_4h=stale)
    assert r.facts["trend4h_state"] == "UNKNOWN" and "dati vecchi" in r.facts["trend4h_why"]
    wrong = m15(NOW, 2000, 0.001)                               # 15m spacciate per 4h
    r = S.read_symbol("X", a, NOW, bars_4h=wrong)
    assert r.facts["trend4h_state"] == "UNKNOWN" and "non coerenti" in r.facts["trend4h_why"]


def test_daily_trend_is_real_or_unknown_never_a_false_bear():
    a = m15(NOW, 1000, 0.0)
    # 35 barre giornaliere in forte rialzo: in RC84 sarebbe stato "trend 1d bear"; ora e' UNKNOWN
    r = S.read_symbol("X", a, NOW, bars_4h=native_bars(NOW, H4, 400, 0.002), bars_1d=native_bars(NOW, D1, 35, 0.02))
    assert r.facts["trend1d_state"] == "UNKNOWN" and "bear" not in r.facts["daily_trend"]
    r = S.read_symbol("X", a, NOW, bars_4h=native_bars(NOW, H4, 400, 0.002), bars_1d=native_bars(NOW, D1, 300, 0.004))
    assert r.facts["trend1d_state"] == "UP" and r.facts["daily_trend"] == "trend 1d bull"
    # policy: il 1d e' contesto (0 punti) finche' non viene deciso altrimenti
    assert S.DAILY_TREND_POINTS == 0 and not any(w.startswith("trend 1d") for w in r.why)


# --------------------------------------------------------------------------------------- P0 candele incomplete
def test_an_intrabar_spike_in_the_open_15m_candle_changes_nothing():
    a = m15(NOW, 1000, 0.0, seed=4)
    base = S.read_symbol("X", a, NOW, bars_4h=native_bars(NOW, H4, 400, 0.002))
    spiked = a.copy()
    spiked[-1, 2] = spiked[-1, 4] = a[:-1, 2].max() * 1.05       # la candela in corso rompe tutti i massimi
    r = S.read_symbol("X", spiked, NOW, bars_4h=native_bars(NOW, H4, 400, 0.002))
    assert (r.long_score, r.short_score, r.side, r.trade_type) == (base.long_score, base.short_score, base.side, base.trade_type)
    assert not any("rottura massimi" in w for w in r.why if w not in base.why)


def test_the_last_closed_hour_is_reported():
    a = m15(NOW, 1000, 0.0)
    r = S.read_symbol("X", a, NOW)
    assert r.facts["closed_asof_ms"] <= NOW and (NOW - r.facts["closed_asof_ms"]) < H1


# ------------------------------------------------------------------------------------ P1 classificazione consultiva
def _t(state, gap=0.02, above=0, slope=0):
    return {"state": state, "gap": gap, "closes_above_ema50": above, "ema50_slope": slope, "why": "x"}


@pytest.mark.parametrize("t4,t1d,up,want", [
    (_t("UNKNOWN"), _t("UNKNOWN"), True, "UNKNOWN"),
    (_t("UP", gap=0.001), _t("UP"), True, "RANGE"),
    (_t("UP"), _t("UP"), True, "CONTINUATION_UP"),
    (_t("DOWN", gap=-0.02), _t("DOWN"), False, "CONTINUATION_DOWN"),
    (_t("DOWN", gap=-0.02, above=-3, slope=-1), _t("DOWN"), True, "BOUNCE_UNCONFIRMED_UP"),
    (_t("DOWN", gap=-0.02, above=2, slope=1), _t("UNKNOWN"), True, "REVERSAL_CONFIRMED_UP"),
    (_t("DOWN", gap=-0.02, above=2, slope=1), _t("DOWN"), True, "BOUNCE_UNCONFIRMED_UP"),   # 1d contrario
    (_t("UP", gap=0.02, above=-2, slope=-1), _t("UNKNOWN"), False, "REVERSAL_CONFIRMED_DOWN"),
    (_t("UP", gap=0.02, above=1, slope=1), _t("UP"), False, "BOUNCE_UNCONFIRMED_DOWN"),
])
def test_trend_classification(t4, t1d, up, want):
    assert S.classify_trend(t4, t1d, up)[0] == want


def test_classification_never_changes_scores_or_side():
    a = m15(NOW, 1000, 0.0)
    b4 = native_bars(NOW, H4, 400, -0.002)
    r = S.read_symbol("X", a, NOW, bars_4h=b4)
    orig = S.classify_trend
    try:
        S.classify_trend = lambda *x: ("REVERSAL_CONFIRMED_UP", "forzato")
        r2 = S.read_symbol("X", a, NOW, bars_4h=b4)
    finally:
        S.classify_trend = orig
    assert (r2.long_score, r2.short_score, r2.side) == (r.long_score, r.short_score, r.side)


# ------------------------------------------------------------------------------- cli: rete 4h/1d, gate, ombra
@pytest.fixture
def cli_mod(monkeypatch):
    from desk import cli
    cli._HTF_CACHE.clear()
    yield cli
    cli._HTF_CACHE.clear()


def test_htf_bars_are_fetched_once_per_closed_bar_and_errors_keep_none(cli_mod):
    calls = []

    def fetch(sym, gran, limit):
        calls.append(gran)
        return native_bars(NOW, H4, 300, 0.001).tolist()

    def page(sym, gran, start, end):
        calls.append(gran)
        return [r for r in native_bars(NOW, D1, 400, 0.001).tolist() if start <= r[0] < end]
    out = cli_mod.fetch_htf("BTC", NOW, fetch, page)
    assert calls[0] == "4H" and set(calls[1:]) == {"1Dutc"} and len(out["4h"]) == 300   # la barra in formazione e' esclusa
    n = len(calls)
    cli_mod.fetch_htf("BTC", NOW + 15 * 60_000, fetch, page)        # stessa barra 4h e stesso giorno: niente rete
    assert len(calls) == n
    later = NOW + H4
    cli_mod.fetch_htf("BTC", later, lambda s, g, l: (calls.append(g), native_bars(later, H4, 300, 0.001).tolist())[1], page)
    assert calls[n:] == ["4H"]                                      # solo il 4h e' cambiato
    cli_mod.htf_budget_reset()
    out = cli_mod.fetch_htf("ETH", NOW, lambda s, g, l: [], lambda *a: None)
    assert out["4h"] is None and out["1d"] is None and out["status"] == {"4h": "errore_api", "1d": "errore_api"}


def test_policy_shadow_reports_prompt_contract_gaps_without_blocking(cli_mod):
    hawk, bull = cli_mod._make_hawk_config(), cli_mod._make_bull_config()
    d = {"stop_loss_pct": 0.01, "take_profit_pct": 0.0, "confidence": 80, "margin_usd": 80, "leverage": 20}
    assert any(v.startswith("tp_assente") for v in cli_mod.policy_shadow_violations(d, hawk, "SOL"))
    d.update(take_profit_pct=0.016)
    assert any(v.startswith("rr_1.60") for v in cli_mod.policy_shadow_violations(d, hawk, "SOL"))
    d.update(take_profit_pct=0.03, confidence=72)
    v = cli_mod.policy_shadow_violations(d, bull, "SOL")
    assert any(x.startswith("confidenza_72_sotto_75") for x in v) and any(x.startswith("tp_3.00%") for x in v)
    assert any(x.startswith("guardrail_alza_margine_leva") for x in v)          # 80$ < 150$ minimi Toro
    assert cli_mod.policy_shadow_violations(dict(d, take_profit_pct=0.06, confidence=80, margin_usd=200,
                                                 leverage=15), bull, "SOL") == []


def test_the_s25_entry_gate_still_requires_the_toro_opt_in():
    src = open(os.path.join(BACKEND, "desk", "cli.py"), encoding="utf-8").read()
    assert ('s25_new_entries = (PORTFOLIO.name == "bull" and\n'
            '                               os.getenv("DESK_S25_TORO_ENTRY_APPROVED") == "1"\n'
            '                               and not explicit_claude_no_trade)') in src
    assert 'if not LIVE._live and os.environ.get("DESK_LONG_S25") == "1":   # strategia long S25' in src


# --------------------------------------------------------------------------- integrazione: il ciclo vero
from test_long_s25 import sandbox, _cycle_candles, _with_new_hour, _install  # noqa: E402,F401


def _proposal(**kw):
    d = {"symbol": "ETH", "action": "open_long", "trade_type": "scalp", "confidence": 99, "leverage": 15,
         "margin_usd": 80.0, "stop_loss_pct": 0.01, "take_profit_pct": 0.03, "reason": "prova fase 2"}
    d.update(kw)
    return d


def _run(cli, monkeypatch, state, decisions, htf):
    a15, sig = _cycle_candles()
    a15b, now, _ = _with_new_hour(a15, sig)
    _install(cli, monkeypatch, a15b)
    monkeypatch.setattr(cli, "fetch_htf", lambda sym, now_ms, fetch=None: htf(now_ms))
    monkeypatch.setattr(cli, "apply_claude_schedule", lambda *args: False)
    monkeypatch.setattr(cli, "rules_decisions", lambda *args, **kw: [dict(d) for d in decisions])
    monkeypatch.setattr(cli, "PORTFOLIO", cli._make_hawk_config())
    cli.run_cycle(state, now)
    return now


def _learning(d):
    path = os.path.join(d, "learning_log.jsonl")
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def test_unknown_4h_trend_blocks_new_entries_from_any_source(sandbox, monkeypatch, capsys):
    cli, d = sandbox
    state = {}
    _run(cli, monkeypatch, state, [_proposal()], lambda now: {"4h": None, "1d": None})
    assert cli.make_account(state).positions == {}
    assert "[TREND_UNKNOWN] ETH" in capsys.readouterr().out
    assert any(e.get("ev") == "candidate" and e.get("status") == "trend_sconosciuto" for e in _learning(d))


def test_known_trend_opens_and_records_the_state_and_the_shadow_audit(sandbox, monkeypatch, capsys):
    cli, d = sandbox
    state = {}
    _run(cli, monkeypatch, state, [_proposal(take_profit_pct=0.0)], lambda now: native_htf(now, 1))
    pos = cli.make_account(state).positions
    assert list(pos) == ["ETH"]                                    # l'ombra registra ma non blocca: come in RC84
    out = capsys.readouterr().out
    assert "[POLICY_SHADOW:HAWK] ETH" in out and "tp_assente" in out
    opened = [e for e in _learning(d) if e.get("ev") == "open"]
    f = opened[-1]["features"]
    assert f["trend4h_state"] == "UP" and f["trend_state"] and any(v.startswith("tp_assente") for v in f["policy_shadow"])


def test_exits_and_closes_are_not_gated_by_the_trend_state(sandbox, monkeypatch):
    cli, d = sandbox
    state = {}
    _run(cli, monkeypatch, state, [_proposal()], lambda now: native_htf(now, 1))
    assert list(cli.make_account(state).positions) == ["ETH"]
    # ciclo successivo con 4h sconosciuta: la chiusura decisa passa comunque
    a15, sig = _cycle_candles()
    a15b, now, _ = _with_new_hour(a15, sig)
    monkeypatch.setattr(cli, "fetch_htf", lambda sym, now_ms, fetch=None: {"4h": None, "1d": None})
    monkeypatch.setattr(cli, "rules_decisions", lambda *a, **k: [{"symbol": "ETH", "action": "close", "trade_type": "scalp",
                                                                 "confidence": 0, "leverage": 1, "margin_usd": 0,
                                                                 "stop_loss_pct": 0, "take_profit_pct": 0,
                                                                 "reason": "chiusura", "dca_sl_pct": 0, "dca_tp_pct": 0}])
    cli.run_cycle(state, now + 15 * 60_000)
    assert cli.make_account(state).positions == {}
    hist = [json.loads(l) for l in open(os.path.join(d, "trade_history.jsonl"))]
    assert hist and hist[-1]["symbol"] == "ETH" and not hist[-1].get("partial")
