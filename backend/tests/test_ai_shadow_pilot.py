"""AI in ombra: cicli completi con candele finte e modello finto (nessuna rete, nessuna chiave vera)."""
import glob
import gzip
import json
import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_shadow_helpers as H  # noqa: E402
from ai_shadow_helpers import I0, KEY, opn, make, now_for, path, read_jsonl  # noqa: E402

from director.ai_shadow import healthcheck, report  # noqa: E402
from director.ai_shadow.config import Config  # noqa: E402
from director.ai_shadow.deepseek import ModelError  # noqa: E402
from director.ai_shadow.pilot import Pilot  # noqa: E402

SLIP = 1.0002          # 2 bp


def quiet_btc(world, rows):
    """BTC piatto a 100 fino alla barra I0 compresa, poi le barre indicate (o,h,l,c)."""
    world.flat("BTC", I0, 100.0)
    path(world, "BTC", I0 + 1, rows)


OPEN_BTC = {"market_read": "rialzo", "decisions": [opn("BTC", 1, 99.0, 102.0)]}


def run(pilot, i):
    return pilot.run_once(now_for(i))


# ------------------------------------------------------------------ primo ciclo
def test_first_cycle_calls_the_model_once_and_writes_every_file(tmp_path):
    pilot, world, model, cfg = make(tmp_path)
    line = run(pilot, I0)
    assert len(model.calls) == 1 and model.calls[0]["key"] == KEY
    assert line["decision"]["called"] and line["bars_ok"] == 26 and line["stale"] == []
    u = model.calls[0]["user"]
    assert "ACCOUNT: equity 1000.00" in u and "MARKETS (26):" in u and u.count("\n") > 30
    for name in ("state.json", "status.json", "spend.jsonl"):
        assert os.path.exists(tmp_path / name), name
    assert glob.glob(str(tmp_path / "cycles-*.jsonl")) and glob.glob(str(tmp_path / "prompts-*.jsonl.gz"))
    st = json.load(open(tmp_path / "status.json"))
    assert st["mode"] == "ombra" and st["applied"] is False and st["spend"]["day_usd"] > 0
    assert st["model"]["calls_ok"] == 1 and st["symbols_ok"] == 26


def test_prompt_log_is_readable_and_has_the_prompt_but_not_the_key(tmp_path):
    pilot, *_ = make(tmp_path)
    run(pilot, I0)
    f = glob.glob(str(tmp_path / "prompts-*.jsonl.gz"))[0]
    rec = json.loads(gzip.open(f, "rt").readline())
    assert "MARKETS (26)" in rec["user"] and rec["prompt_version"] == "p1" and KEY not in json.dumps(rec)


def test_the_same_bar_is_decided_only_once(tmp_path):
    pilot, world, model, cfg = make(tmp_path)
    run(pilot, I0)
    line = pilot.run_once(now_for(I0) + 60_000)         # stesso intervallo di barra, un minuto dopo
    assert len(model.calls) == 1 and line["decision"]["skip"] == "barra_gia_decisa"


# ------------------------------------------------------------------ apertura e uscite
def test_an_order_is_filled_at_the_next_bar_open_not_at_the_decision_price(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.6, 100.0, 100.3)])
    run(pilot, I0)
    assert not pilot.acc.positions and len(pilot.state["pending"]) == 1
    line = run(pilot, I0 + 1)
    pos = pilot.acc.positions["BTC"]
    assert pos.entry == pytest.approx(100.0 * SLIP) and pos.open_ms == H.T0 + (I0 + 1) * H.BAR
    assert pos.source == "ai-deepseek" and pos.sl == 99.0 and pos.tp == 102.0
    fill = [e for e in line["events"] if e["ev"] == "fill"][0]
    assert fill["lev"] == 10 and fill["risk_usd"] == pytest.approx(10.0, rel=0.03) and fill["margin"] < 100.0
    assert pilot.state["pending"] == []


def test_take_profit_closes_with_a_net_gain_and_is_journaled(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 102.5, 100.1, 102.2)])
    run(pilot, I0)
    run(pilot, I0 + 1)
    line = run(pilot, I0 + 2)
    assert "BTC" not in pilot.acc.positions
    tr = read_jsonl(tmp_path, "trades-")
    assert len(tr) == 1 and tr[0]["why"] == "take profit" and tr[0]["net"] > 0 and tr[0]["source"] == "ai-deepseek"
    assert tr[0]["account"] == "ai-deepseek" and tr[0]["net_r"] > 1.0
    assert pilot.state["closed_total"] == 1 and pilot.state["recent"][-1]["symbol"] == "BTC"
    assert any(e["ev"] == "exit" and e["why"] == "take profit" for e in line["events"])


def test_stop_wins_when_one_bar_touches_stop_and_target(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 102.5, 98.5, 100.0)])
    for i in (I0, I0 + 1, I0 + 2):
        run(pilot, i)
    tr = read_jsonl(tmp_path, "trades-")
    assert [t["why"] for t in tr] == ["stop loss"] and tr[0]["net"] < 0


def test_gap_through_the_stop_at_the_open_cancels_the_order(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(98.5, 99.0, 98.0, 98.8)])           # apre gia' sotto lo stop
    run(pilot, I0)
    line = run(pilot, I0 + 1)
    assert not pilot.acc.positions
    assert [e["why"] for e in line["events"] if e["ev"] == "ordine_respinto"] == ["livelli_dal_lato_sbagliato_all_apertura"]


def test_bad_reward_risk_at_the_real_open_cancels_the_order(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(101.5, 101.8, 101.2, 101.6)])       # il prezzo e' gia' quasi al target
    run(pilot, I0)
    line = run(pilot, I0 + 1)
    assert not pilot.acc.positions
    assert [e["why"] for e in line["events"] if e["ev"] == "ordine_respinto"] == ["rr_basso_all_apertura"]


def test_close_decision_exits_at_the_next_open(tmp_path):
    script = [OPEN_BTC, {"decisions": []}, {"decisions": [{"symbol": "BTC", "action": "CLOSE", "thesis": "tesi invalidata"}]}]
    pilot, world, model, cfg = make(tmp_path, script)
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.8, 100.0, 100.6), (100.8, 101.0, 100.5, 100.9),
                      (100.9, 101.0, 100.7, 100.9)])
    for i in (I0, I0 + 1, I0 + 2):
        run(pilot, i)
    assert "BTC" in pilot.acc.positions                       # deciso alla chiusura di I0+2, non ancora eseguito
    run(pilot, I0 + 3)
    assert "BTC" not in pilot.acc.positions
    tr = read_jsonl(tmp_path, "trades-")
    assert tr[0]["why"] == "ai: chiusura" and tr[0]["exit"] == pytest.approx(100.8 * (1 - 0.0002))   # apertura di I0+3


def test_move_stop_tightens_at_the_open_and_the_new_stop_is_used(tmp_path):
    script = [OPEN_BTC, {"decisions": []}, {"decisions": [{"symbol": "BTC", "action": "MOVE_STOP", "new_stop": 100.3}]}]
    pilot, world, model, cfg = make(tmp_path, script)
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 101.2, 100.5, 101.0), (101.0, 101.3, 100.8, 101.1),
                      (101.1, 101.2, 100.0, 100.1)])      # l'ultima barra rompe 100.3 ma non 99
    for i in (I0, I0 + 1, I0 + 2):
        run(pilot, i)
    assert pilot.acc.positions["BTC"].sl == 99.0              # deciso, non ancora eseguito
    run(pilot, I0 + 3)
    assert pilot.acc.positions["BTC"].sl == 100.3
    run(pilot, I0 + 4)
    tr = read_jsonl(tmp_path, "trades-")
    assert tr[0]["why"] == "stop loss" and tr[0]["exit"] == pytest.approx(100.3 * (1 - 0.0002))   # al nuovo stop (meno slip), non al vecchio (99)


def test_partial_close_reduces_the_position(tmp_path):
    script = [OPEN_BTC, {"decisions": []}, {"decisions": [{"symbol": "BTC", "action": "PARTIAL_CLOSE", "close_fraction": 0.5}]}]
    pilot, world, model, cfg = make(tmp_path, script)
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.8, 100.0, 100.6), (100.8, 101.0, 100.5, 100.9),
                      (100.9, 101.0, 100.7, 100.9)])
    for i in (I0, I0 + 1, I0 + 2):
        run(pilot, i)
    margin_before = pilot.acc.positions["BTC"].total_margin
    run(pilot, I0 + 3)
    tr = read_jsonl(tmp_path, "trades-")
    assert tr and tr[0].get("partial") is True and tr[0]["fraction"] == 0.5
    assert pilot.acc.positions["BTC"].total_margin == pytest.approx(margin_before / 2)
    assert pilot.state["closed_total"] == 1


def test_flip_closes_and_opens_the_opposite_side_at_the_same_open(tmp_path):
    flip = {"decisions": [{"symbol": "BTC", "action": "CLOSE", "thesis": "inversione"},
                          opn("BTC", -1, 102.0, 98.0)]}
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC, {"decisions": []}, flip])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.8, 100.0, 100.6), (100.6, 100.7, 100.0, 100.1),
                      (100.0, 100.3, 99.8, 100.0)])
    for i in (I0, I0 + 1, I0 + 2, I0 + 3):
        run(pilot, i)
    pos = pilot.acc.positions["BTC"]
    assert pos.side == -1 and pos.open_ms == H.T0 + (I0 + 3) * H.BAR
    assert [t["why"] for t in read_jsonl(tmp_path, "trades-")] == ["ai: chiusura"]


def test_orders_older_than_one_bar_expire_after_downtime(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2)] * 5)
    run(pilot, I0)
    line = run(pilot, I0 + 3)                               # il container era fermo per 3 barre
    assert not pilot.acc.positions
    assert any(e["ev"] == "ordine_scaduto" for e in line["events"])


def test_stop_hit_on_a_bar_missed_during_downtime_is_still_recognized(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.3, 98.0, 98.5), (98.5, 98.9, 98.2, 98.6), (98.6, 98.8, 98.4, 98.6)])
    run(pilot, I0)
    run(pilot, I0 + 1)
    run(pilot, I0 + 4)                                       # le barre I0+2 e I0+3 non sono state viste in tempo reale
    tr = read_jsonl(tmp_path, "trades-")
    assert tr and tr[0]["why"] == "stop loss" and tr[0]["close_ms"] == H.T0 + (I0 + 3) * H.BAR


# ------------------------------------------------------------------ spesa e guasti del modello
def test_exhausted_budget_stops_the_calls_but_not_the_management_of_open_positions(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 102.5, 100.1, 102.2)])
    run(pilot, I0)
    tiny = replace(cfg, daily_cap_usd=0.001)
    pilot2, _, model2, _ = make(tmp_path, [], cfg=tiny, world=world)
    l1 = run(pilot2, I0 + 1)                                  # esegue l'ordine gia' deciso, ma non chiama il modello
    assert not model2.calls and l1["decision"]["skip"] == "spesa:tetto giornaliero" and "BTC" in pilot2.acc.positions
    run(pilot2, I0 + 2)
    assert "BTC" not in pilot2.acc.positions and not model2.calls     # il TP e' scattato senza modello


def test_the_daily_cap_is_never_exceeded_over_a_full_day(tmp_path):
    cfg = replace(Config(), daily_cap_usd=0.05)
    pilot, world, model, _ = make(tmp_path, cfg=cfg, usage={"hit": 0, "miss": 6000, "out": 1500, "reasoning": 0})
    for k in range(96):
        pilot.run_once(now_for(I0 - 48 + k))
    spent = pilot.budget.spent_day(now_for(I0))
    assert len(model.calls) < 96 and spent <= cfg.daily_cap_usd + 1e-9
    assert any(c["decision"].get("skip") == "spesa:tetto giornaliero" for c in read_jsonl(tmp_path, "cycles-"))


def test_pause_flag_stops_the_calls(tmp_path):
    pilot, world, model, cfg = make(tmp_path)
    (tmp_path / "pause.flag").write_text("")
    line = run(pilot, I0)
    assert not model.calls and line["decision"]["skip"] == "pausa"


def test_missing_key_means_no_call_and_a_clear_reason(tmp_path):
    pilot, world, model, cfg = make(tmp_path, key="")
    line = run(pilot, I0)
    assert not model.calls and line["decision"]["skip"] == "chiave_assente"


def test_insufficient_balance_backs_off_six_hours_and_charges_the_estimate(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [ModelError("balance", "HTTP 402", status=402)])
    l0 = run(pilot, I0)
    assert l0["decision"]["error"] == "balance" and pilot.budget.spent_day(now_for(I0)) > 0
    l1 = run(pilot, I0 + 1)
    assert len(model.calls) == 1 and l1["decision"]["skip"].startswith("attesa_dopo_errori")
    run(pilot, I0 + 25)                                       # sei ore e un quarto dopo
    assert len(model.calls) == 2


def test_three_failures_in_a_row_back_off_thirty_minutes(tmp_path):
    errs = [ModelError("server", "HTTP 503", status=503)] * 3
    pilot, world, model, cfg = make(tmp_path, errs)
    for k in range(3):
        run(pilot, I0 + k)
    assert len(model.calls) == 3
    assert run(pilot, I0 + 3)["decision"]["skip"].startswith("attesa_dopo_errori")
    run(pilot, I0 + 5)
    assert len(model.calls) == 4 and pilot.state["model"]["fail_streak"] == 0


def test_an_unreadable_answer_still_counts_as_decided_and_paid(tmp_path):
    pilot, world, model, cfg = make(tmp_path, ["questo non e' json"])
    l0 = run(pilot, I0)
    assert l0["decision"]["parse_error"] == "nessun oggetto json" and pilot.budget.spent_day(now_for(I0)) > 0
    l1 = pilot.run_once(now_for(I0) + 30_000)
    assert len(model.calls) == 1 and l1["decision"]["skip"] == "barra_gia_decisa"


def test_missing_data_blocks_the_call_and_retries_the_download_once(tmp_path):
    sleeps = []
    pilot, world, model, cfg = make(tmp_path, sleeps=sleeps)
    world.fail = set(cfg.symbols[:10])
    line = run(pilot, I0)
    assert not model.calls and line["decision"]["skip"] == "dati_insufficienti:16" and 20 in sleeps
    assert len(line["stale"]) == 10


def test_a_late_bar_is_picked_up_by_the_retry(tmp_path):
    calls = {"n": 0}
    base_world = H.World(Config())

    def late_fetch(sym, tf, limit, now_ms):
        bars = base_world.fetch(sym, tf, limit, now_ms)
        if tf == "15m" and now_ms == now_for(I0):         # al primo tentativo manca la barra appena chiusa
            calls["n"] += 1
            return bars[:-1]
        return bars
    pilot, world, model, cfg = make(tmp_path, world=base_world, fetch=late_fetch)
    line = run(pilot, I0)
    assert line["bars_ok"] == 26 and len(model.calls) == 1 and calls["n"] == 26


# ------------------------------------------------------------------ riavvio, configurazione, segreti
def test_restart_keeps_positions_spend_and_does_not_duplicate_trade_logs(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 102.5, 100.1, 102.2), (102.2, 102.3, 102.0, 102.1)])
    run(pilot, I0)
    run(pilot, I0 + 1)
    spent = pilot.budget.spent_day(now_for(I0))
    p2, *_ = make(tmp_path, [], world=world)
    assert "BTC" in p2.acc.positions and p2.budget.spent_day(now_for(I0)) == spent       # la spesa non si azzera
    run(p2, I0 + 2)                                                                        # il TP scatta dopo il riavvio
    assert len(read_jsonl(tmp_path, "trades-")) == 1 and p2.state["closed_total"] == 1
    p3, *_ = make(tmp_path, [], world=world)
    run(p3, I0 + 3)
    assert len(read_jsonl(tmp_path, "trades-")) == 1 and p3.state["closed_total"] == 1   # nessun trade scritto due volte


def test_config_change_keeps_the_account_and_leaves_a_note(tmp_path):
    pilot, world, model, cfg = make(tmp_path, [OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.6, 100.0, 100.3)])
    run(pilot, I0)
    run(pilot, I0 + 1)
    cfg2 = replace(cfg, risk_pct=0.5)
    p2, _, _, _ = make(tmp_path, [], cfg=cfg2, world=world)
    line = run(p2, I0 + 2)
    assert "BTC" in p2.acc.positions and any(e["ev"] == "nota" and "config_cambiata" in e["why"] for e in line["events"])


def test_the_account_has_the_same_limits_as_hawk_and_the_engine_costs(tmp_path):
    pilot, *_ = make(tmp_path)
    L = pilot.acc.limits
    assert (L.max_open, L.max_margin_trade, L.max_margin_total, L.start_equity, L.kill_equity, L.daily_stop) == \
        (10, 100.0, 1000.0, 1000.0, 450.0, 0.12)
    assert (L.fee_bp_side, L.slip_bp_side) == (6.0, 2.0)


def test_the_key_never_reaches_any_file_even_if_a_client_error_echoes_it(tmp_path):
    leaky = ModelError("format", "risposta strana " + KEY)
    pilot, world, model, cfg = make(tmp_path, [leaky, OPEN_BTC])
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.6, 100.0, 100.3)])
    for i in (I0, I0 + 1, I0 + 2):
        run(pilot, i)
    hits = []
    for root, _, files in os.walk(str(tmp_path)):
        for f in files:
            p = os.path.join(root, f)
            data = gzip.open(p, "rb").read() if f.endswith(".gz") else open(p, "rb").read()
            if KEY.encode() in data:
                hits.append(f)
    assert hits == []


# ------------------------------------------------------------------ salute e riepilogo
def test_healthcheck_needs_a_recent_heartbeat_and_real_data(tmp_path):
    pilot, *_ = make(tmp_path)
    run(pilot, I0)
    root = tmp_path.parent / (tmp_path.name + "_root")
    os.makedirs(root / "ai")
    (root / "ai" / "status.json").write_text((tmp_path / "status.json").read_text())
    now = now_for(I0)
    assert healthcheck.healthy(str(root), now + 60_000)
    assert not healthcheck.healthy(str(root), now + 30 * 60_000)                # battito vecchio
    st = json.loads((root / "ai" / "status.json").read_text())
    st["last_success_ms"] = now - 3_600_000                                       # gira ma non scarica dati
    (root / "ai" / "status.json").write_text(json.dumps(st))
    assert not healthcheck.healthy(str(root), now + 60_000)
    assert not healthcheck.healthy(str(tmp_path / "vuoto"), now)


def test_report_summarizes_trades_spend_and_rejections(tmp_path):
    script = [{"decisions": [opn("BTC", 1, 99.0, 102.0, conv=40)]},
              {"decisions": [opn("BTC", 1, 99.0, 103.0)]}]                   # 2a decisione a 100.2: RR 2,3, ben sopra la soglia
    pilot, world, model, cfg = make(tmp_path, script)
    quiet_btc(world, [(100.0, 100.4, 99.6, 100.2), (100.2, 100.6, 100.0, 100.3), (100.3, 103.6, 100.2, 103.4)])
    for i in (I0, I0 + 1, I0 + 2, I0 + 3):
        run(pilot, i)
    root = tmp_path.parent / (tmp_path.name + "_r2")
    os.makedirs(root)
    os.symlink(str(tmp_path), str(root / "ai"))
    text = report.build(str(root), now_for(I0 + 3))
    assert "AI IN OMBRA" in text and "spesa oggi" in text and "convinzione_bassa" in text and "take profit" in text
    assert "trade chiusi 1" in text and KEY not in text


