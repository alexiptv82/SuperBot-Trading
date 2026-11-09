"""A4 - prova end-to-end del Brain PAPER su candele registrate (finte) e un modello finto.

Si fingono SOLO i confini: Bitget (``get_json``, stesso formato di risposta) e il fornitore del modello
(``inner_transport``). Tutto il resto e' il codice vero: ``build_runner`` (feed, vista L5, analista L5, contatore e
tetto di spesa, motore, risk gate, mandato, esecutore PAPER, journal, monitor delle uscite, direttore, battito) e
``extract_outcomes`` per chiudere il giro: il Brain apre, il monitor chiude, l'esito e' legato alla decisione e alla
strategia dichiarata, e al giro dopo il modello vede il proprio tabellone.
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_feed_monitor import FakeBitget, _series
from backend.v3.brain_f3.providers import TransportResponse
from backend.v3.brain_market.params import TimeframeSpec, load_default_params
from backend.v3.features.indicators import Bar
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.config import load_default_config
from backend.v3.runner.runner import CYCLE_MS
from backend.v3.runner.exits import load_default_policy
from backend.v3.runner.wiring import (
    MINUTE_STORE_BARS, MandateFile, build_runner, main, make_verifier, mandate_template,
)

D = Decimal
RUN = "brain-e2e"
M = 60_000
H1 = 3_600_000
G = (1_800_000_000_000 // (4 * H1)) * (4 * H1)           # allineato a 15 m, 1 h e 4 h
VIEW = dataclasses.replace(
    load_default_params(),
    timeframes=(TimeframeSpec("15m", 900_000, 20), TimeframeSpec("1h", 3_600_000, 20),
                TimeframeSpec("4h", 14_400_000, 20)))
CONTRACTS = {"code": "00000", "msg": "success", "data": [
    {"symbol": s, "symbolStatus": "normal", "sizeMultiplier": "0.01", "minTradeUSDT": "5", "maxLever": "125"}
    for s in ("BTCUSDT", "ETHUSDT")]}
BTC_TP_MINUTE, ETH_STOP_MINUTE = 17, 21                   # minuti dopo G in cui il prezzo "colpisce"


def _minute_series(spike_minute: int, spike_high: str) -> list[Bar]:
    out = []
    for i in range(-180, 120):                            # da 3 ore prima a 2 ore dopo G
        high = D(spike_high) if i == spike_minute else D("100.1")
        out.append(Bar(G + i * M, D("100"), high, D("99.9"), D("100"), D("5")))
    return out


def _world():
    # le candele da 15 m partono da 105 (quelle da 1 m stanno a 100): il prezzo di ingresso deve venire dal minuto
    s15 = _series(G - 80 * 900_000, 80 + 16, 900_000, start_price=105)     # fino a G + 3 h 45
    out = {}
    for sym, minute, high in (("BTCUSDT", BTC_TP_MINUTE, "103.5"), ("ETHUSDT", ETH_STOP_MINUTE, "102.5")):
        out[sym] = {"1m": _minute_series(minute, high), "15m": s15, "1H": _series(G - 80 * H1, 80 + 4, H1),
                    "4H": _series(G - 80 * 4 * H1, 80 + 2, 4 * H1)}
    return out


def _get_json_factory():
    fake = FakeBitget({(s, g): bars for s, per in _world().items() for g, bars in per.items()})

    def get_json(url):
        if "/contracts" in url:
            return CONTRACTS
        return fake(url)
    return get_json


class FakeModel:
    """Un modello finto che legge il prezzo dalla richiesta: BTC long, ETH short, stop a 1 %."""

    def __init__(self):
        self.payloads: list[dict] = []

    def __call__(self, payload):
        self.payloads.append(json.loads(json.dumps(payload)))
        info = json.loads(payload["messages"][1]["content"])
        price = D(info["price"])
        long_ = info["symbol"] == "BTCUSDT"
        stop = price * (D("0.99") if long_ else D("1.01"))
        content = json.dumps({"kind": "OPEN", "side": 1 if long_ else -1, "entry_price": str(price),
                              "stop_price": str(stop), "leverage": 3, "confidence": 0.8,
                              "strategy_id": "S25", "strategy_origin": "library"})
        return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
                                       "usage": {"prompt_tokens": 2500, "completion_tokens": 60}})


# I giri di prova sono ogni 15 minuti, senza ragionamento e con 256 token (la sequenza dei minuti di questi test e'
# scritta su quel ritmo); il ritmo di oggi (ogni ora, ragionamento esteso) e' provato in fondo con ``real=True``.
LEGACY = dict(cycle_minutes=15, thinking="disabled", reasoning_effort="omit", max_tokens=256)


def _setup(symbols=("BTCUSDT", "ETHUSDT"), real=False, **cfg):
    data_dir = Path(tempfile.mkdtemp())
    base = dict(symbols=symbols, **({} if real else LEGACY))
    config = dataclasses.replace(load_default_config(), **{**base, **cfg})
    model = FakeModel()
    built = build_runner(data_dir=data_dir, run_id=RUN, config=config, get_json=_get_json_factory(),
                         inner_transport=model, view_params=VIEW)
    return built, model, data_dir, config


def _approve(built, data_dir, config):
    m = mandate_template(config.risk_policy, RUN)
    m.update(approved=True, approved_by="operator")
    (data_dir / "mandate.json").write_text(json.dumps(m), encoding="utf-8")


def _events(built, kind):
    return [r.event for r in built.journal.list_run("brain", RUN) if r.event.kind == kind]


def _beat(data_dir):
    return json.loads((data_dir / "heartbeat.json").read_text(encoding="utf-8"))


COST_PER_CALL = 822                                       # 2500 * 0.30 + 60 * 1.20 micro-dollari


def test_the_whole_loop_open_close_learn():
    built, model, data_dir, config = _setup()
    run = built.runner

    # 1. senza mandato: fermo, nessuna chiamata al modello, nessuna spesa, nessuna decisione nel journal
    t = run.tick(G + 20_000)
    assert t.state == "halted" and t.last_error == "halted:no_mandate" and t.cycle is None
    assert model.payloads == [] and built.ledger.daily_spend("deepseek") == 0
    assert _events(built, "brain_decision") == [] and _beat(data_dir)["state"] == "halted"

    # 2. mandato approvato dall'utente: nello stesso minuto il giro parte (la candela non era stata consumata)
    _approve(built, data_dir, config)
    t = run.tick(G + 25_000)
    assert t.state == "running" and t.cycle is not None and t.cycle.errors == ()
    assert {s for s, _ in t.cycle.opened} == {"BTCUSDT", "ETHUSDT"}
    assert len(model.payloads) == 2 and {p["model"] for p in model.payloads} == {"deepseek-flash"}
    assert all(p["thinking"] == {"type": "disabled"} and p["max_tokens"] == 256 for p in model.payloads)
    assert built.ledger.daily_spend("deepseek") == 2 * COST_PER_CALL
    opens = _events(built, "paper_open")
    assert {e.payload["symbol"]: e.payload["side"] for e in opens} == {"BTCUSDT": 1, "ETHUSDT": -1}
    assert all(e.payload["decision_event_id"].startswith("brain-req-") and e.portfolio_id == "brain" for e in opens)
    # ingresso a mercato sull'ultimo minuto chiuso (100) con slippage avversa di 2 bp: long 100.02, short 99.98
    fills = {e.payload["symbol"]: (D(e.payload["fill_price"]), e.payload["slippage_bps"]) for e in opens}
    assert fills == {"BTCUSDT": (D("100.02"), 2), "ETHUSDT": (D("99.98"), 2)}
    assert _beat(data_dir) == {"ts_ms": G + 25_000, "cycle": 1, "state": "running", "run_id": RUN, "last_error": None,
                               "daily_loss_level": "ok", "daily_loss_pct": "0.0", "exit_mode": "legacy"}
    first_scoreboard = json.loads(model.payloads[0]["messages"][1]["content"])["scoreboard"]

    # 3. nessuna uscita ancora; alla candela dopo i simboli con posizione aperta non chiamano il modello
    t = run.tick(G + 5 * M)
    assert t.monitor.closed == () and t.monitor.checked == 2
    t = run.tick(G + CYCLE_MS + 20_000)
    assert set(t.cycle.skipped_open) == {"BTCUSDT", "ETHUSDT"} and t.cycle.decisions == () and len(model.payloads) == 2

    # 4. il prezzo tocca il take-profit di BTC (minuto 17) e poi lo stop di ETH (minuto 21)
    t = run.tick(G + 19 * M)
    assert [r for _, r in t.monitor.closed] == ["take_profit"] and t.monitor.errors == ()
    t = run.tick(G + 23 * M)
    assert [r for _, r in t.monitor.closed] == ["stop"] and t.monitor.errors == ()
    closes = {e.payload["symbol"]: e.payload for e in _events(built, "paper_close")}
    assert closes["BTCUSDT"]["reason"] == "take_profit" and closes["ETHUSDT"]["reason"] == "stop"
    assert D(closes["BTCUSDT"]["realized_pnl"]) > 0 > D(closes["ETHUSDT"]["realized_pnl"])
    assert {c["fee_bps"] for c in closes.values()} == {"6"} and all(D(c["fees"]) > 0 for c in closes.values())

    # 5. l'esito e' legato alla decisione e alla strategia dichiarata
    outcomes = extract_outcomes(built.journal, "brain", RUN).outcomes
    assert {o.symbol: o.exit_reason for o in outcomes} == {"BTCUSDT": "take_profit", "ETHUSDT": "stop"}
    assert all(o.link_status == "linked" and o.strategy_id == "S25" and o.strategy_origin == "library"
               and o.decision_regime != "" and o.originating_ai == "deepseek" for o in outcomes)

    # 6. giro successivo: i simboli sono liberi, il modello e' richiamato e vede il tabellone con gli esiti
    t = run.tick(G + 3 * CYCLE_MS + 20_000)                                      # candela dispari: la rotazione parte da ETH
    assert {s for s, _ in t.cycle.opened} == {"BTCUSDT", "ETHUSDT"} and len(model.payloads) == 4
    assert [d[0] for d in t.cycle.decisions] == ["ETHUSDT", "BTCUSDT"]
    later = [json.loads(p["messages"][1]["content"])["scoreboard"] for p in model.payloads[2:]]
    assert first_scoreboard["n_closed_linked"] == 0 and first_scoreboard["n_labelled"] == 0
    assert [(sb["n_closed_linked"], sb["n_labelled"]) for sb in later] == [(2, 2), (2, 2)]
    assert built.ledger.daily_spend("deepseek") == 4 * COST_PER_CALL
    assert _beat(data_dir)["cycle"] == 3 and _beat(data_dir)["last_error"] is None


def test_pause_flag_stops_new_openings_and_spending_and_resuming_serves_the_same_candle():
    built, model, data_dir, config = _setup()
    _approve(built, data_dir, config)
    (data_dir / "pause.flag").write_text("")
    t = built.runner.tick(G + 20_000)
    assert t.state == "paused" and t.cycle is None and model.payloads == []
    assert _events(built, "paper_open") == [] and built.ledger.daily_spend("deepseek") == 0
    (data_dir / "pause.flag").unlink()
    t = built.runner.tick(G + 40_000)
    assert t.state == "running" and len(t.cycle.opened) == 2


def test_open_positions_keep_being_monitored_while_paused():
    built, model, data_dir, config = _setup()
    _approve(built, data_dir, config)
    built.runner.tick(G + 25_000)
    (data_dir / "pause.flag").write_text("")
    t = built.runner.tick(G + 19 * M)
    assert t.state == "paused" and [r for _, r in t.monitor.closed] == ["take_profit"] and t.cycle is None


def test_daily_cap_halts_the_next_cycle_but_not_the_monitor():
    built, model, data_dir, config = _setup(daily_cap_usd=D("0.0005"))          # 500 micro-dollari
    _approve(built, data_dir, config)
    t = built.runner.tick(G + 25_000)
    assert len(model.payloads) == 1                                              # la seconda chiamata trova il tetto
    assert [d[3] for d in t.cycle.decisions].count("ai_unavailable") == 1
    assert built.ledger.daily_spend("deepseek") == COST_PER_CALL
    t = built.runner.tick(G + CYCLE_MS + 20_000)
    assert t.state == "halted" and t.cycle is None and t.last_error == "halted:budget"
    assert len(model.payloads) == 1 and t.monitor is not None                    # nessuna spesa, uscite attive


def test_changing_the_risk_limits_voids_the_mandate():
    built, model, data_dir, config = _setup()
    _approve(built, data_dir, config)
    other = dataclasses.replace(config.risk_policy, max_loss_fraction=D("0.03"))
    built2 = build_runner(data_dir=Path(tempfile.mkdtemp()), run_id=RUN, config=dataclasses.replace(config, risk_policy=other),
                          get_json=_get_json_factory(), inner_transport=FakeModel(), view_params=VIEW)
    (built2.runner.data_dir / "mandate.json").write_bytes((data_dir / "mandate.json").read_bytes())
    t = built2.runner.tick(G + 20_000)
    assert t.state == "halted" and t.last_error == "halted:mandate_mismatch" and t.cycle is None


# ----------------------------------------------------------------------------- il mandato su file
def _mf(tmp, policy, run=RUN):
    return MandateFile(Path(tmp) / "mandate.json", policy, run)


def test_mandate_problem_codes(tmp_path):
    cfg = load_default_config()
    mf = _mf(tmp_path, cfg.risk_policy)
    assert mf.problem() == "no_mandate" and mf.read() is None
    base = mandate_template(cfg.risk_policy, RUN)
    path = tmp_path / "mandate.json"
    path.write_text("{bad", encoding="utf-8")
    assert mf.problem() == "mandate_invalid"
    path.write_text("[]", encoding="utf-8")
    assert mf.problem() == "mandate_invalid"
    path.write_text(json.dumps(base), encoding="utf-8")
    assert mf.problem() == "mandate_not_approved"
    ok = dict(base, approved=True, approved_by="operator")
    path.write_text(json.dumps(ok), encoding="utf-8")
    assert mf.problem() is None and mf.read() == ok
    for bad in (dict(ok, approved="true"), dict(ok, approved=1)):
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert mf.problem() == "mandate_not_approved"
    for bad in (dict(ok, approved_by=""), dict(ok, approved_by=5), dict(ok, version=""), dict(ok, version=1),
                dict(ok, portfolio_id="hawk"), dict(ok, run_id="altra"), dict(ok, policy_hash="0" * 16)):
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert mf.problem() == "mandate_mismatch"
    assert _mf(tmp_path, cfg.risk_policy, run="altra").problem() == "mandate_mismatch"


def test_mandate_template_is_not_approved_and_binds_run_and_policy():
    cfg = load_default_config()
    m = mandate_template(cfg.risk_policy, RUN)
    assert m["approved"] is False and m["approved_by"] == "" and m["portfolio_id"] == "brain" and m["run_id"] == RUN
    assert len(m["policy_hash"]) == 16 and m["version"] == "v1"


# ----------------------------------------------------------------------------- l'avvio da riga di comando
def test_main_refuses_unless_desk_mode_is_paper(tmp_path, capsys):
    for env in ({}, {"DESK_MODE": "live"}, {"DESK_MODE": "PAPER"}, {"DESK_MODE": ""}):
        assert main(["--data-dir", str(tmp_path / "d"), "--run-id", RUN, "--once"], env=env) == 2
    assert not (tmp_path / "d").exists()                                          # nulla creato se rifiutato
    assert "DESK_MODE" in capsys.readouterr().err


def test_main_print_mandate_needs_no_desk_mode_and_prints_an_unapproved_template(capsys, tmp_path):
    assert main(["--data-dir", str(tmp_path), "--run-id", RUN, "--print-mandate"], env={}) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["approved"] is False and out["run_id"] == RUN


def test_main_rejects_a_bad_config_file(tmp_path, capsys):
    bad = tmp_path / "c.json"
    bad.write_text("{}", encoding="utf-8")
    assert main(["--data-dir", str(tmp_path), "--run-id", RUN, "--config", str(bad), "--once"],
                env={"DESK_MODE": "paper"}) == 2
    assert main(["--data-dir", str(tmp_path), "--run-id", RUN, "--config", str(tmp_path / "nope.json"), "--once"],
                env={"DESK_MODE": "paper"}) == 2
    assert "config_invalid" in capsys.readouterr().err


def test_main_rejects_a_bad_run_id(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path / "d"), "--run-id", "bad id!", "--once"], env={"DESK_MODE": "paper"}) == 2
    assert "setup_invalid" in capsys.readouterr().err


def test_main_once_runs_a_single_tick_without_a_mandate_and_never_calls_the_model(tmp_path, capsys):
    model = FakeModel()
    rc = main(["--data-dir", str(tmp_path / "d"), "--run-id", RUN, "--once"], env={"DESK_MODE": "paper"},
              now_fn=lambda: G + 20_000, get_json=_get_json_factory(), inner_transport=model)
    assert rc == 0 and model.payloads == []
    assert json.loads(capsys.readouterr().out) == {"last_error": "halted:no_mandate", "state": "halted"}
    assert _beat(tmp_path / "d")["state"] == "halted"


def test_main_loop_runs_until_asked_to_stop_and_logs_only_what_matters(tmp_path, capsys):
    clock = iter([G + 20_000, G + 21_000, G + 22_000])
    stops = iter([False, False, False, True])
    rc = main(["--data-dir", str(tmp_path / "d"), "--run-id", RUN], env={"DESK_MODE": "paper"},
              now_fn=lambda: next(clock), sleep_fn=lambda s: None, get_json=_get_json_factory(),
              inner_transport=FakeModel(), should_stop=lambda: next(stops))
    assert rc == 0
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0]["state"] == "halted" and lines[0]["last_error"] == "halted:no_mandate"
    assert lines[0]["cycle_opened"] is None and lines[0]["closed"] == 0


def test_a_restart_catches_up_on_exits_that_happened_while_it_was_down():
    built, model, data_dir, config = _setup()
    _approve(built, data_dir, config)
    built.runner.tick(G + 25_000)                                                # apre e "muore"
    built2 = build_runner(data_dir=data_dir, run_id=RUN, config=config, get_json=_get_json_factory(),
                          inner_transport=FakeModel(), view_params=VIEW)           # riparte sullo stesso journal
    t = built2.runner.tick(G + 60 * M + 5_000)                                   # un'ora dopo: gli eventi del minuto 17 e 21 sono passati
    assert sorted(r for _, r in t.monitor.closed) == ["stop", "take_profit"] and t.monitor.errors == ()
    assert {e.payload["symbol"]: e.payload["reason"] for e in _events(built2, "paper_close")} == {
        "BTCUSDT": "take_profit", "ETHUSDT": "stop"}


def test_the_minute_cache_covers_the_longest_possible_hold():
    assert MINUTE_STORE_BARS >= load_default_policy().max_hold_ms // M


def test_verifier_rechecks_the_file_at_opening_time(tmp_path):
    cfg = load_default_config()
    mf = MandateFile(tmp_path / "mandate.json", cfg.risk_policy, RUN)
    v = make_verifier(mf, RUN)
    m = dict(mandate_template(cfg.risk_policy, RUN), approved=True, approved_by="operator")
    assert v(m, cfg.risk_policy) is False                                        # nessun file: il dizionario non basta
    (tmp_path / "mandate.json").write_text(json.dumps(m), encoding="utf-8")
    assert v(m, cfg.risk_policy) is True
    assert v(dict(m, run_id="altra"), cfg.risk_policy) is False and v(None, cfg.risk_policy) is False
    (tmp_path / "mandate.json").write_text(json.dumps(dict(m, approved=False)), encoding="utf-8")
    assert v(m, cfg.risk_policy) is False                                        # revocato nel frattempo


# ----------------------------------------------------------------------------- il ritmo di oggi: ogni ora, ragionamento esteso
def test_real_config_hourly_cycle_with_extended_reasoning_reaches_the_model_and_the_ledger():
    built, model, data_dir, config = _setup(real=True)
    assert (config.cycle_minutes, config.thinking, config.max_tokens) == (60, "enabled", 6000)
    _approve(built, data_dir, config)
    t = built.runner.tick(G + 25_000)                                            # primo giro dell'ora
    assert t.cycle is not None and t.cycle.errors == () and len(model.payloads) == 2
    for p in model.payloads:                                                     # parametri DeepSeek dalla configurazione
        assert p["model"] == "deepseek-flash" and p["max_tokens"] == 6000
        assert p["thinking"] == {"type": "enabled"} and p["reasoning_effort"] == "high"
        assert p["response_format"] == {"type": "json_object"} and p["stream"] is False
    assert built.ledger.daily_spend("deepseek") == 2 * COST_PER_CALL
    built.runner.tick(G + CYCLE_MS + 20_000)                                     # un quarto d'ora dopo: nessun nuovo giro
    t = built.runner.tick(G + 3 * CYCLE_MS + 20_000)                             # il monitor ha chiuso BTC (minuto 17) ed ETH (minuto 21)
    assert sorted(r for _, r in t.monitor.closed) == ["stop", "take_profit"] and t.cycle is None
    assert len(model.payloads) == 2 and built.runner.cycles == 1
    t = built.runner.tick(G + 4 * CYCLE_MS + 20_000)                             # un'ora dopo: nuovo giro, i simboli sono liberi
    assert built.runner.cycles == 2 and t.cycle.skipped_open == () and len(model.payloads) == 4


def test_real_config_exits_still_run_every_minute_between_hourly_cycles():
    built, model, data_dir, config = _setup(real=True)
    _approve(built, data_dir, config)
    built.runner.tick(G + 25_000)
    t = built.runner.tick(G + 19 * M)                                            # il take-profit di BTC (minuto 17) non aspetta l'ora
    assert [r for _, r in t.monitor.closed] == ["take_profit"] and t.cycle is None
    t = built.runner.tick(G + 23 * M)
    assert [r for _, r in t.monitor.closed] == ["stop"]


def test_real_config_truncated_reasoning_is_no_decision_and_the_spend_is_still_recorded():
    built, model, data_dir, config = _setup(real=True)
    _approve(built, data_dir, config)

    def truncated(payload):                                                      # il ragionamento ha finito i token: nessun JSON
        model.payloads.append(payload)
        return TransportResponse(200, {"choices": [{"finish_reason": "length", "message": {"content": ""}}],
                                       "usage": {"prompt_tokens": 2500, "completion_tokens": 6000}})
    built.metered._inner = truncated
    t = built.runner.tick(G + 25_000)
    assert t.cycle.opened == () and _events(built, "paper_open") == []
    assert {(d[0], d[3]) for d in t.cycle.decisions} == {("BTCUSDT", "ai_unavailable"), ("ETHUSDT", "ai_unavailable")}
    assert built.ledger.daily_spend("deepseek") == 2 * (2500 * 30 // 100 + 6000 * 120 // 100)   # la spesa si registra comunque
