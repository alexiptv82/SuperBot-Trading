"""AI in ombra: prove delle parti singole (spesa, client, indicatori, lettura delle risposte, controllore, dimensionamento)."""
import calendar
import io
import json
import math
import os
import random
import sys
import time
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_shadow_helpers as H  # noqa: E402,F401  (aggiunge backend/ al percorso)

from director.ai_shadow import budget, decisions, deepseek, features, prompt  # noqa: E402
from director.ai_shadow.config import Config, config_hash  # noqa: E402

CFG = Config()


def ts(y, mo, d, h, mi=0):
    return calendar.timegm((y, mo, d, h, mi, 0)) * 1000


# ------------------------------------------------------------------ spesa
def test_peak_hours_utc_weekdays_only():
    assert budget.is_peak(ts(2026, 10, 19, 2))          # lunedi 02:00
    assert budget.is_peak(ts(2026, 10, 23, 9, 59))      # venerdi 09:59
    assert not budget.is_peak(ts(2026, 10, 23, 10))     # venerdi 10:00
    assert not budget.is_peak(ts(2026, 10, 19, 5))      # lunedi 05:00
    assert not budget.is_peak(ts(2026, 10, 24, 2))      # sabato 02:00
    assert not budget.is_peak(ts(2026, 10, 19, 4))      # il picco finisce alle 04:00


def test_cost_follows_the_published_price_list():
    off = ts(2026, 10, 24, 12)
    assert budget.cost_usd("deepseek-flash", off, 100, 1000, 500) == pytest.approx((100 * 0.003 + 1000 * 0.15 + 500 * 0.60) / 1e6)
    pk = ts(2026, 10, 19, 7)
    assert budget.cost_usd("deepseek-flash", pk, 100, 1000, 500) == pytest.approx((100 * 0.006 + 1000 * 0.30 + 500 * 1.20) / 1e6)


def test_daily_cap_blocks_a_call_whose_worst_case_would_exceed_it(tmp_path):
    b = budget.Budget(str(tmp_path / "s.jsonl"), 0.01, 12.0, 1.25)
    now = ts(2026, 10, 24, 12)
    ok, why, worst = b.check("deepseek-flash", now, 14000, 2200)
    assert ok and worst < 0.01
    b.record("deepseek-flash", now, 0, 0, 0, False, "x", est_cost=0.0098)      # spesa gia' vicina al tetto
    ok, why, _ = b.check("deepseek-flash", now, 14000, 2200)
    assert not ok and why == "tetto giornaliero"


def test_monthly_cap_blocks_even_when_the_day_is_free(tmp_path):
    b = budget.Budget(str(tmp_path / "s.jsonl"), 0.50, 0.02, 1.25)
    b.record("deepseek-flash", ts(2026, 10, 3, 12), 0, 0, 0, False, "x", est_cost=0.0190)   # altro giorno, stesso mese
    ok, why, _ = b.check("deepseek-flash", ts(2026, 10, 24, 12), 14000, 2200)
    assert not ok and why == "tetto mensile"
    ok, _, _ = b.check("deepseek-flash", ts(2026, 11, 2, 12), 14000, 2200)             # mese nuovo: libero
    assert ok


def test_spend_survives_a_restart_and_a_damaged_line_does_not_reset_it(tmp_path):
    p = str(tmp_path / "s.jsonl")
    now = ts(2026, 10, 24, 12)
    b = budget.Budget(p, 0.5, 12.0)
    b.record("deepseek-flash", now, 1000, 2000, 400, True, "ok")
    spent = b.spent_day(now)
    assert spent > 0
    with open(p, "a") as f:
        f.write("{riga rovinata\n")
    b2 = budget.Budget(p, 0.5, 12.0)
    assert b2.spent_day(now) == pytest.approx(spent) and b2.bad_lines == 1


def test_call_without_usage_is_charged_the_conservative_estimate(tmp_path):
    b = budget.Budget(str(tmp_path / "s.jsonl"), 0.5, 12.0)
    now = ts(2026, 10, 24, 12)
    c = b.record("deepseek-flash", now, 0, 0, 0, False, "rete", est_cost=0.004)
    assert c == pytest.approx(0.004) and b.spent_day(now) == pytest.approx(0.004)


def test_worst_case_is_never_below_the_real_cost_of_a_worst_call():
    rnd = random.Random(3)
    for _ in range(200):
        chars = rnd.randint(2000, 60000)
        out = rnd.randint(1, 2200)
        now = rnd.choice([ts(2026, 10, 19, 7), ts(2026, 10, 24, 12)])
        worst = budget.worst_case_usd("deepseek-flash", now, chars, out, 1.25)
        real_in = int(chars / 2.0)                           # anche con 2 caratteri per token (molto sfavorevole)
        real = budget.cost_usd("deepseek-flash", now, 0, real_in, out) * 1.25
        if real_in <= int(chars / budget.CHARS_PER_TOKEN) + 1:
            assert worst >= real - 1e-12
    # un prompt tipico (14000 caratteri) costa nel caso peggiore molto meno del tetto giornaliero
    assert budget.worst_case_usd("deepseek-flash", ts(2026, 10, 19, 7), 14000, 2200, 1.25) < 0.01


def test_worst_case_always_uses_peak_prices_even_when_the_call_is_off_peak():
    sat, mon = ts(2026, 10, 24, 12), ts(2026, 10, 19, 7)          # sabato a mezzogiorno: fuori picco; lunedi alle 7: picco
    w_sat = budget.worst_case_usd("deepseek-flash", sat, 10000, 1000, 1.0)
    w_mon = budget.worst_case_usd("deepseek-flash", mon, 10000, 1000, 1.0)
    assert w_sat == pytest.approx(w_mon)
    assert w_sat == pytest.approx((4001 * 0.30 + 1000 * 1.20) / 1e6)       # tutto senza cache, risposta al massimo, prezzo di picco
    assert w_sat >= budget.cost_usd("deepseek-flash", mon, 0, 4001, 1000)


# ------------------------------------------------------------------ client DeepSeek
class Resp:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ok_payload(content='{"decisions":[]}', finish="stop", usage=None):
    return {"model": "deepseek-flash", "choices": [{"finish_reason": finish, "message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 5000, "prompt_cache_hit_tokens": 3000, "prompt_cache_miss_tokens": 2000,
                               "completion_tokens": 350, "completion_tokens_details": {"reasoning_tokens": 0}}}


def test_request_has_the_expected_shape_and_never_logs_the_key():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["data"], seen["hdr"], seen["timeout"] = req.full_url, json.loads(req.data), dict(req.header_items()), timeout
        return Resp(ok_payload())

    r = deepseek.call(CFG, "sk-abc", "SYS", "USER", opener=opener)
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["hdr"]["Authorization"] == "Bearer sk-abc"
    d = seen["data"]
    assert d["model"] == "deepseek-flash" and d["stream"] is False and d["max_tokens"] == 2200
    assert d["response_format"] == {"type": "json_object"} and d["thinking"] == {"type": "disabled"}
    assert d["messages"][0] == {"role": "system", "content": "SYS"} and d["messages"][1]["role"] == "user"
    assert r["usage"] == {"hit": 3000, "miss": 2000, "out": 350, "reasoning": 0}
    assert "sk-abc" not in json.dumps(d)


def test_thinking_mode_on_omits_the_disable_flag():
    from dataclasses import replace
    body = deepseek.build_body(replace(CFG, thinking=True), "s", "u")
    assert "thinking" not in body


def test_usage_fallback_when_cache_split_is_missing():
    assert deepseek.parse_usage({"prompt_tokens": 1000, "completion_tokens": 10}) == {"hit": 0, "miss": 1000, "out": 10, "reasoning": 0}
    assert deepseek.parse_usage(None) == {"hit": 0, "miss": 0, "out": 0, "reasoning": 0}


@pytest.mark.parametrize("code,kind", [(401, "auth"), (403, "auth"), (402, "balance"), (429, "rate"), (500, "server"),
                                       (503, "server"), (400, "format")])
def test_http_errors_are_classified(code, kind):
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b'{"error":"boom"}'))
    with pytest.raises(deepseek.ModelError) as e:
        deepseek.call(CFG, "sk-abc", "s", "u", opener=opener)
    assert e.value.kind == kind and e.value.status == code


def test_network_errors_and_timeouts():
    for exc in (urllib.error.URLError("rete giu'"), TimeoutError("lento"), ConnectionResetError("reset")):
        def opener(req, timeout, exc=exc):
            raise exc
        with pytest.raises(deepseek.ModelError) as e:
            deepseek.call(CFG, "sk-abc", "s", "u", opener=opener)
        assert e.value.kind == "network"


def test_truncated_and_empty_and_garbage_answers_are_errors_but_keep_the_usage():
    with pytest.raises(deepseek.ModelError) as e:
        deepseek.call(CFG, "k", "s", "u", opener=lambda r, timeout: Resp(ok_payload(finish="length")))
    assert e.value.kind == "length" and e.value.usage["out"] == 350
    with pytest.raises(deepseek.ModelError) as e:
        deepseek.call(CFG, "k", "s", "u", opener=lambda r, timeout: Resp(ok_payload(content="  ")))
    assert e.value.kind == "format" and e.value.usage["miss"] == 2000
    with pytest.raises(deepseek.ModelError) as e:
        deepseek.call(CFG, "k", "s", "u", opener=lambda r, timeout: Resp(b"<html>502</html>"))
    assert e.value.kind == "format"


def test_the_key_is_scrubbed_even_if_the_server_echoes_it():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b'{"error":"bad key sk-LEAK-123"}'))
    with pytest.raises(deepseek.ModelError) as e:
        deepseek.call(CFG, "sk-LEAK-123", "s", "u", opener=opener)
    assert "sk-LEAK-123" not in str(e.value)


def test_missing_key_is_an_auth_error_without_any_request():
    def opener(req, timeout):
        raise AssertionError("non deve partire nessuna richiesta senza chiave")
    with pytest.raises(deepseek.ModelError) as e:
        deepseek.call(CFG, "", "s", "u", opener=opener)
    assert e.value.kind == "auth"


# ------------------------------------------------------------------ indicatori
def test_ema_rsi_atr_known_values():
    assert features.ema_series([1.0] * 10, 5)[-1] == pytest.approx(1.0)
    up = [float(i) for i in range(1, 40)]
    assert features.rsi(up) == pytest.approx(100.0)
    down = [float(i) for i in range(40, 1, -1)]
    assert features.rsi(down) == pytest.approx(0.0, abs=1e-9)
    bars = [(i, 100.0, 101.0, 99.0, 100.0, 1.0) for i in range(30)]
    assert features.atr_pct(bars) == pytest.approx(2.0)
    assert features.ema_series([1.0, 2.0], 5) == [None, None]


def test_pivots_are_confirmed_only_and_never_use_the_last_bars():
    # picco centrale alla barra 10 con 3 barre piu' basse per lato; l'ultima barra e' piu' alta di tutte ma non conferma nulla
    bars = [(i, 100.0, 100.0 + (5 if i == 10 else 0) + (50 if i == 19 else 0), 99.0, 100.0, 1.0) for i in range(20)]
    highs, lows = features.pivots(bars, 3)
    assert [t for t, _ in highs] == [10] and highs[0][1] == 105.0
    assert all(t <= 16 for t, _ in highs + lows)


def test_nearest_levels_are_sorted_distinct_and_on_the_right_side():
    bars = []
    for i in range(60):
        base = 100.0 + (3 if i % 12 == 6 else 0) - (3 if i % 12 == 0 and i else 0)
        bars.append((i, base, base + 1, base - 1, base, 1.0))
    sup, res = features.nearest_levels(100.0, bars, k=2, n=2)
    assert all(x < 100.0 for x in sup) and all(x > 100.0 for x in res)
    assert sup == sorted(sup, reverse=True) and res == sorted(res)
    assert len(set(round(x, 1) for x in sup + res)) == len(sup + res)


def test_summary_needs_enough_bars_and_has_no_nan():
    w = H.World(CFG)
    ok = features.summarize("BTC", {"15m": w.fetch("BTC", "15m", 300, H.now_for(H.I0)), "1h": w.fetch("BTC", "1h", 200, H.now_for(H.I0)),
                                    "4h": w.fetch("BTC", "4h", 120, H.now_for(H.I0)), "1d": w.fetch("BTC", "1d", 60, H.now_for(H.I0))})
    assert ok and ok["line"].startswith("BTC ") and "nan" not in ok["line"].lower() and "inf" not in ok["line"].lower()
    for part in ("15m:", "var 1h", "24h min-max", "1h:", "4h:", "1g:"):
        assert part in ok["line"]
    assert features.summarize("BTC", {"15m": ok and w.fetch("BTC", "15m", 30, H.now_for(H.I0))}) is None


def test_summary_uses_only_closed_bars_known_at_that_time():
    """Le stesse barre passate danno lo stesso riassunto anche se il mondo ha barre future diverse."""
    w1, w2 = H.World(CFG, seed=7), H.World(CFG, seed=7)
    for i in range(H.I0 + 1, H.I0 + 50):        # il futuro cambia
        w2.set_bar("BTC", i, 1.0, 2.0, 0.5, 1.5)
    now = H.now_for(H.I0)
    def s(w):
        return features.summarize("BTC", {tf: w.fetch("BTC", tf, 300, now) for tf in ("15m", "1h", "4h", "1d")})["line"]
    assert s(w1) == s(w2)


# ------------------------------------------------------------------ lettura delle risposte
def test_parse_accepts_fences_text_around_and_numeric_strings():
    txt = 'Ecco:\n```json\n{"market_read":"ok","decisions":[{"symbol":"btcusdt","action":"open_long","conviction":"72","stop_loss":"99","take_profit":102.5}]}\n```'
    read, items, err = decisions.parse_response(txt)
    assert err is None and read == "ok" and len(items) == 1
    it = items[0]
    assert it["symbol"] == "BTC" and it["action"] == "OPEN_LONG" and it["conviction"] == 72
    assert it["stop_loss"] == 99.0 and it["take_profit"] == 102.5 and not it.get("_err")


@pytest.mark.parametrize("txt,err", [("", "risposta vuota"), ("niente json", "nessun oggetto json"), ("{rotto", "nessun oggetto json"),
                                     ('{"a":1', "nessun oggetto json"), ('{"decisions":"x"}', "campo decisions mancante"),
                                     ('{"market_read":"x"}', "campo decisions mancante"), ("{ x }", "json non valido")])
def test_parse_errors(txt, err):
    assert decisions.parse_response(txt)[2] == err


def test_parse_flags_bad_items_and_ignores_nonfinite_numbers():
    txt = '{"decisions":[{"symbol":"BTC","action":"VENDI","conviction":80},"stringa",{"symbol":"ETH","action":"OPEN_LONG","conviction":NaN,"stop_loss":1e999}]}'
    _, items, err = decisions.parse_response(txt)
    assert err is None and items[0]["_err"] == "azione sconosciuta" and items[1]["_err"] == "voce non e' un oggetto"
    assert items[2]["conviction"] is None and items[2]["stop_loss"] is None


def test_parse_caps_the_number_of_items():
    txt = json.dumps({"decisions": [{"symbol": "BTC", "action": "HOLD"}] * 500})
    assert len(decisions.parse_response(txt)[1]) == decisions.MAX_ITEMS


# ------------------------------------------------------------------ controllore
def snap(**kw):
    s = {"px": {"BTC": 100.0, "ETH": 50.0, "SOL": 20.0, "XRP": 1.0, "ADA": 0.5}, "positions": {}, "pending_open": set(),
         "universe": set(CFG.symbols), "halted": "", "bar_t": 1}
    s.update(kw)
    return s


def plan(items, **kw):
    return decisions.plan_cycle([dict(i, thesis="t", invalidate_if="") for i in items], CFG, snap(**kw))


def item(sym="BTC", act="OPEN_LONG", conv=75, sl=99.0, tp=102.0, **kw):
    d = {"symbol": sym, "action": act, "conviction": conv, "stop_loss": sl, "take_profit": tp, "close_fraction": None,
         "new_stop": None, "horizon_bars": 24}
    d.update(kw)
    return d


def reasons(results):
    return {r["symbol"] + ":" + r["action"]: r["reason"] for r in results}


def test_a_clean_long_and_short_are_accepted():
    orders, res = plan([item("BTC"), item("ETH", "OPEN_SHORT", sl=51.0, tp=48.0)])
    assert [o["symbol"] for o in orders] == ["BTC", "ETH"] and all(r["accepted"] for r in res)
    assert orders[0]["side"] == 1 and orders[1]["side"] == -1


@pytest.mark.parametrize("over,why", [
    ({"conv": 59}, "convinzione_bassa"), ({"conv": None}, "convinzione_bassa"),
    ({"sl": 101.0}, "livelli_dal_lato_sbagliato"), ({"tp": 99.5}, "livelli_dal_lato_sbagliato"),
    ({"sl": None}, "stop_mancante"), ({"tp": None}, "tp_mancante"),
    ({"sl": 99.9, "tp": 100.5}, "stop_troppo_vicino"), ({"sl": 90.0, "tp": 120.0}, "stop_troppo_lontano"),
    ({"sl": 99.0, "tp": 100.9}, "rr_basso")])
def test_rejections_carry_their_reason(over, why):
    orders, res = plan([item(**over)])
    assert not orders and res[0]["reason"] == "rifiutata:" + why


def test_short_mirror_rejections():
    assert plan([item("BTC", "OPEN_SHORT", sl=99.0, tp=98.0)])[1][0]["reason"] == "rifiutata:livelli_dal_lato_sbagliato"
    assert plan([item("BTC", "OPEN_SHORT", sl=101.0, tp=99.2)])[1][0]["reason"] == "rifiutata:rr_basso"


def test_unknown_symbol_open_position_halted_pending_and_no_data():
    assert plan([item("DOGEX")])[1][0]["reason"] == "rifiutata:simbolo_sconosciuto"
    assert plan([item("BTC")], positions={"BTC": {"side": 1, "sl": 98, "tp": 105, "entry": 99}})[1][0]["reason"] == "rifiutata:posizione_gia_aperta"
    assert plan([item("BTC")], halted="stop giornaliero")[1][0]["reason"] == "rifiutata:conto_fermo"
    assert plan([item("BTC")], pending_open={"BTC"})[1][0]["reason"] == "rifiutata:ordine_gia_in_attesa"
    assert plan([item("DOGE")], px={"BTC": 100.0})[1][0]["reason"] == "rifiutata:senza_dati_in_questo_ciclo"


def test_at_most_three_new_openings_per_cycle_most_convinced_first():
    items = [item(s, conv=c, sl=px * 0.99, tp=px * 1.02) for s, px, c in
             (("BTC", 100.0, 61), ("ETH", 50.0, 90), ("SOL", 20.0, 70), ("XRP", 1.0, 80), ("ADA", 0.5, 65))]
    orders, res = plan(items)
    assert [o["symbol"] for o in orders] == ["ETH", "XRP", "SOL"]
    assert reasons(res)["ADA:OPEN_LONG"] == "rifiutata:troppe_aperture_nel_ciclo"


def test_slots_are_counted_with_open_positions_and_pending():
    pos = {s: {"side": 1, "sl": 1.0, "tp": 9.0, "entry": 2.0} for s in ["DOT", "LINK", "UNI", "ATOM", "LTC", "BCH", "APT", "ARB", "OP"]}
    orders, res = plan([item("BTC"), item("ETH", sl=49.5, tp=51.0)], positions=pos)
    assert len(orders) == 1 and orders[0]["symbol"] == "BTC"           # 9 aperte: ne entra una sola
    assert reasons(res)["ETH:OPEN_LONG"] == "rifiutata:slot_pieni"


def test_flip_close_then_open_opposite_is_allowed_and_frees_the_slot():
    pos = {"BTC": {"side": 1, "sl": 98.0, "tp": 105.0, "entry": 99.0}}
    orders, res = plan([item("BTC", "CLOSE"), item("BTC", "OPEN_SHORT", sl=101.0, tp=97.0)], positions=pos)
    assert [o["kind"] for o in orders] == ["close", "open"] and all(r["accepted"] for r in res)


def test_move_stop_only_tightens_and_never_goes_past_price():
    long_pos = {"BTC": {"side": 1, "sl": 98.0, "tp": 105.0, "entry": 99.0}}
    assert plan([item("BTC", "MOVE_STOP", new_stop=99.0)], positions=long_pos)[0][0]["new_stop"] == 99.0
    for ns in (97.0, 98.0, 100.0, 101.0, None):            # allarga, uguale, = prezzo, oltre il prezzo, mancante
        assert not plan([item("BTC", "MOVE_STOP", new_stop=ns)], positions=long_pos)[0], ns
    short_pos = {"BTC": {"side": -1, "sl": 102.0, "tp": 95.0, "entry": 101.0}}
    assert plan([item("BTC", "MOVE_STOP", new_stop=101.0)], positions=short_pos)[0][0]["new_stop"] == 101.0
    for ns in (103.0, 102.0, 100.0, 99.0):
        assert not plan([item("BTC", "MOVE_STOP", new_stop=ns)], positions=short_pos)[0], ns


def test_close_partial_hold_need_a_position_and_a_sane_fraction():
    pos = {"BTC": {"side": 1, "sl": 98.0, "tp": 105.0, "entry": 99.0}}
    assert plan([item("ETH", "CLOSE")], positions=pos)[1][0]["reason"] == "rifiutata:nessuna_posizione"
    assert not plan([item("BTC", "PARTIAL_CLOSE", close_fraction=0.95)], positions=pos)[0]
    assert not plan([item("BTC", "PARTIAL_CLOSE", close_fraction=0.05)], positions=pos)[0]
    assert plan([item("BTC", "PARTIAL_CLOSE", close_fraction=0.5)], positions=pos)[0][0]["fraction"] == 0.5
    assert plan([item("BTC", "HOLD")], positions=pos)[0] == []
    assert plan([item("BTC", "CLOSE"), item("BTC", "CLOSE")], positions=pos)[1][1]["reason"] == "rifiutata:gia_in_chiusura"


def test_bad_items_never_reach_the_orders():
    orders, res = decisions.plan_cycle([{"_err": "azione sconosciuta", "symbol": "BTC", "action": "X"}], CFG, snap())
    assert not orders and res[0]["reason"] == "rifiutata:azione sconosciuta"


# ------------------------------------------------------------------ dimensionamento
SZ = dict(slip_bp=2.0, maint=0.005, sl_liq_frac=0.75)


def test_one_percent_risk_at_the_stop():
    margin, lev, risk = decisions.size_position(CFG, 1000.0, 1, 100.0, 99.0, 45, **SZ)
    assert lev == 10 and 97 < margin < 99 and risk == pytest.approx(10.0, rel=0.02)


def test_tight_stop_is_limited_by_the_asset_leverage_and_risk_drops_instead_of_growing():
    margin, lev, risk = decisions.size_position(CFG, 1000.0, 1, 100.0, 99.75, 25, **SZ)
    assert lev == 25 and margin == CFG.max_margin_trade and risk < 10.0


def test_stop_beyond_liquidation_is_refused():
    margin, why, risk = decisions.size_position(CFG, 1000.0, 1, 100.0, 10.0, 25, **SZ)
    assert margin is None and why == "stop_oltre_la_liquidazione"


def test_risk_never_exceeds_the_plan_and_respects_the_engine_rules():
    from desk.engine import Limits
    L = Limits()
    rnd = random.Random(11)
    for _ in range(500):
        side = rnd.choice([1, -1])
        fill = rnd.uniform(0.01, 90000)
        dist = rnd.uniform(0.0025, 0.08)
        sl = fill * (1 - side * dist)
        eq = rnd.uniform(450, 1500)
        tier = rnd.choice([25, 30, 45])
        r = decisions.size_position(CFG, eq, side, fill, sl, tier, L.slip_bp_side, L.maint, L.sl_liq_frac)
        if r[0] is None:
            continue
        margin, lev, risk = r
        assert 1 <= lev <= tier and margin <= CFG.max_margin_trade + 1e-9
        assert risk <= eq * CFG.risk_pct / 100.0 * 1.0001
        fill_eff = fill * (1 + side * L.slip_bp_side / 1e4)
        d = abs(fill_eff - sl) / fill_eff
        assert d <= L.sl_liq_frac * (1 / lev - L.maint) + 1e-12      # lo stop resta dentro la liquidazione


# ------------------------------------------------------------------ testi e configurazione
def test_system_prompt_is_pinned_to_the_prompt_version():
    """Se questo fallisce hai cambiato il testo fisso per il modello: alza `prompt_version` in config.py e aggiorna
    l'impronta qui sotto. Cosi' il registro sa sempre quale testo ha prodotto quali decisioni."""
    import hashlib
    assert hashlib.sha256(prompt.SYSTEM.encode()).hexdigest()[:12] == "57992d764164"
    assert CFG.prompt_version == "p1"
    for forbidden in ("margin_usd", "leverage\":"):
        assert forbidden not in prompt.SYSTEM            # l'AI non puo' nemmeno proporre importi o leva


def test_user_prompt_contains_account_positions_and_markets_and_no_secrets():
    acc = {"equity": 1000.0, "cash": 900.0, "margin": 100.0, "max_margin": 1000.0, "n_open": 1, "max_open": 10, "day_pnl_pct": 0.5, "halted": ""}
    pos = [{"symbol": "BTC", "side": 1, "entry": "100.0", "px": "101.0", "pnl_pct": 1.0, "r": 1.0, "sl": "99.0", "tp": "103.0", "age_min": 45, "mfe_r": 1.2}]
    u = prompt.build_user(H.now_for(H.I0), acc, pos, [], "calmo", ["BTC 101.0 | ..."], ["SOL"])
    assert "ACCOUNT: equity 1000.00" in u and "BTC LONG entry 100.0" in u and "NO DATA THIS CYCLE FOR: SOL" in u
    assert "MARKETS (1):" in u and "Answer with the JSON object only." in u


def test_config_hash_changes_with_any_value_and_the_caps_are_the_users_decision():
    from dataclasses import replace
    assert config_hash(CFG) != config_hash(replace(CFG, risk_pct=2.0))
    assert CFG.daily_cap_usd == 0.50 and CFG.monthly_cap_usd == 12.0
    h = {"max_open": 10, "max_margin_trade": 100.0, "max_margin_total": 1000.0, "start_equity": 1000.0}
    assert all(getattr(CFG, k) == v for k, v in h.items())       # stessi limiti di Hawk: confronto alla pari


def test_symbols_match_the_bots():
    pytest.importorskip("numpy")
    from desk import cli
    assert tuple(cli.SYMBOLS) == CFG.symbols
