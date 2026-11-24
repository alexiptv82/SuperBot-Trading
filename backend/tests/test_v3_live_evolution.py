"""Brain Live Evolution (24/11/2026): strategie versionate senza reset.

Verifica: il vecchio trade aperto mantiene la propria strategia; il nuovo adotta la versione nuova; cambio senza reset
(journal, capitale e P&L invariati, catena integra); rollback solo per le nuove aperture, senza alterare il journal;
stop, presa parziale e chiusure manuali funzionanti durante l'aggiornamento; nessuna duplicazione di P&L, commissioni o
operazioni; limiti di rischio e mandato non modificabili da un comando; ricostruzione del runner al confine del giro."""
import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.tests.test_v3_brain_unico_2000 import CFG, MIN, T0, _bars
from backend.v3 import strategy_versions as sv
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.monitor import run_exit_monitor
from backend.v3.runner.strategia import main as cli
from backend.v3.unico import PartialTakeProfit

RUN = "r1"
_cfg = json.loads(CFG.read_bytes())
_cfg["brain_unico"].pop("strategy_version", None)        # questi test usano una base chiamata V1 (nome predefinito)
BASE = json.dumps(_cfg, indent=2).encode()


def _journal(tmp_path):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    return j


def _long_eth(j, *, at, strategy=None, link="brain-req-a"):
    """LONG ETH a 3.000, stop 2.970 (1R = 30), 20x."""
    d = _hand(side=1, entry="3000", stop="2970", qty="1", margin="150", lev=20, symbol="ETHUSDT", link=link)
    return execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=at, strategy=strategy).position_id


def _approve(tmp_path, j, text, now):
    reg = sv.read_registry(j, RUN)
    prop = sv.propose(text, reg, BASE, now)
    sv.save_proposal(tmp_path, prop)
    sv.approve(tmp_path, prop.id, "operatore (test)", "prova", now)
    return sv.apply_request(journal=j, data_dir=tmp_path, run_id=RUN, base_bytes=BASE, now_ms=now)


def _snapshot(j):
    return sv.effective(BASE, sv.read_registry(j, RUN)).snapshot()


def _monitor(j, bars, now, policy, partial):
    return run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=lambda s, a, b: bars,
                            policy=policy, fee_bps=6, now_ms=now, partial=partial, step_of=lambda s: D("0.001"))


# ----------------------------------------------------------------------------- 1-2. vecchio e nuovo trade
def test_old_trade_keeps_its_rules_and_new_trade_adopts_the_new_version(tmp_path):
    j = _journal(tmp_path)
    old = _long_eth(j, at=T0, link="brain-req-old")                       # nato prima: nessuna fotografia (base)
    res = _approve(tmp_path, j, "Take profit finale a 2 R e chiusura parziale del 50 % a 1 R", T0 + MIN)
    assert res["ok"] and (res["from"], res["to"]) == ("V1", "V2")
    new = _long_eth(j, at=T0 + 2 * MIN, strategy=_snapshot(j), link="brain-req-new")
    pos = {p.position_id: p for p in build_summary(j, "brain", RUN).open_positions}
    assert pos[old].strategy_version == "" and pos[old].exit_snapshot is None
    assert pos[new].strategy_version == "V2" and pos[new].exit_snapshot.take_profit_r == D("2")
    assert pos[new].partial_snapshot == PartialTakeProfit(D("0.5"), D("1"))
    base = load_runner_config(BASE)                          # il servizio delle uscite lavora con la BASE della run
    # il prezzo sale fino a +2,3 R (3.069): la nuova riduce a 1 R e poi chiude a 2 R; la vecchia riduce solo a 2 R
    bars = _bars([("3001", "3040", "3001", "3035"), ("3035", "3069", "3034", "3060"), ("3060", "3068", "3050", "3062")],
                 T0 + 3 * MIN)
    r1 = _monitor(j, bars, T0 + 7 * MIN, base.exit_policy, base.unico.partial)
    assert sorted(r1.closed) == sorted([(old, "take_profit_partial"), (new, "take_profit_partial")])
    r2 = _monitor(j, bars, T0 + 8 * MIN, base.exit_policy, base.unico.partial)
    assert r2.closed == ((new, "take_profit"),)                          # 2 R della SUA versione
    left = {p.position_id: p for p in build_summary(j, "brain", RUN).open_positions}
    assert set(left) == {old}                                            # la vecchia punta ancora a 3,5 R (base)
    reduce_new = [r.event.payload for r in j.list_run("brain", RUN)
                  if r.event.kind == "paper_reduce" and r.event.payload["position_id"] == new][0]
    assert D(reduce_new["exit_price"]) == D("3030")                       # 1 R della V2, non 2 R della base


# ----------------------------------------------------------------------------- 3. cambio senza reset
def test_switch_without_reset_keeps_journal_capital_and_pnl(tmp_path):
    j = _journal(tmp_path)
    pid = _long_eth(j, at=T0)
    close_paper(portfolio_id="brain", run_id=RUN, position_id=pid, exit_price=D("3015"), reason="manual", fee_bps=6,
                journal=j, now_ms=T0 + MIN)
    before = build_summary(j, "brain", RUN)
    n_before, head_before = j.verify_chain()
    res = _approve(tmp_path, j, "Da questo momento esamina i mercati ogni 15 minuti", T0 + 2 * MIN)
    assert res["ok"] and res["to"] == "V2"
    after = build_summary(j, "brain", RUN)
    assert after.realized_pnl == before.realized_pnl and len(after.closed_trades) == len(before.closed_trades)
    n_after, _ = j.verify_chain()
    rows = j.list_run("brain", RUN)
    assert n_after == n_before + 2 and [r.event.kind for r in rows[-2:]] == ["strategy_version", "strategy_switch"]
    assert [r.event_hash for r in rows[:n_before]][-1] == head_before          # storia precedente intatta
    sw = rows[-1].event.payload
    assert (sw["from"], sw["to"], sw["approved_by"], sw["reason"]) == ("V1", "V2", "operatore (test)", "prova")
    eff = sv.effective(BASE, sv.read_registry(j, RUN))
    assert eff.config.cycle_minutes == 15 and eff.config.risk_policy == load_runner_config(BASE).risk_policy
    assert eff.config.initial_equity == load_runner_config(BASE).initial_equity
    assert not (tmp_path / sv.REQUEST_FILE).exists()
    assert json.loads((tmp_path / sv.RESULT_FILE).read_text())["ok"] is True


# ----------------------------------------------------------------------------- 4. rollback
def test_rollback_changes_only_new_opens_and_never_rewrites_the_journal(tmp_path):
    j = _journal(tmp_path)
    assert _approve(tmp_path, j, "Take profit finale a 2 R", T0)["to"] == "V2"
    v2_trade = _long_eth(j, at=T0 + MIN, strategy=_snapshot(j), link="brain-req-v2")
    rows_before = [(r.seq, r.event_hash) for r in j.list_run("brain", RUN)]
    res = _approve(tmp_path, j, "Torna alla versione precedente", T0 + 2 * MIN)
    assert res["ok"] and (res["from"], res["to"]) == ("V2", "V1")
    rows = j.list_run("brain", RUN)
    assert [(r.seq, r.event_hash) for r in rows[:len(rows_before)]] == rows_before
    assert rows[-1].event.kind == "strategy_switch" and rows[-1].event.payload["rollback"] is True
    assert sv.read_registry(j, RUN).active == "V1"
    assert _snapshot(j)["version"] == "V1" and _snapshot(j)["exit_policy"]["take_profit_r"] == "3.5"
    pos = build_summary(j, "brain", RUN).open_positions[0]
    assert pos.position_id == v2_trade and pos.strategy_version == "V2" and pos.exit_snapshot.take_profit_r == D(2)
    # di nuovo avanti: la V2 esiste gia', nessuna versione duplicata
    again = sv.propose("Per le nuove aperture usa la strategia V2; i trade vecchi completano la V1", sv.read_registry(j, RUN),
                       BASE, T0 + 3 * MIN)
    assert again.action == "activate" and again.version == "V2"
    same = sv.propose("Take profit finale a 2 R", sv.read_registry(j, RUN), BASE, T0 + 3 * MIN)
    assert same.action == "activate" and same.version == "V2"
    j.verify_chain()


# ----------------------------------------------------------------------------- 5. stop e chiusure durante l'aggiornamento
def test_stops_and_manual_closes_work_across_the_update_without_duplicates(tmp_path):
    j = _journal(tmp_path)
    a = _long_eth(j, at=T0, link="brain-req-a")
    _approve(tmp_path, j, "Stop a pareggio da 1 R", T0 + MIN)
    b = _long_eth(j, at=T0 + 2 * MIN, strategy=_snapshot(j), link="brain-req-b")
    base = load_runner_config(BASE)
    # b sale a +1,2 R (pareggio della V2 armato), poi torna sotto l'ingresso: b chiude a pareggio, a resta aperta
    bars = _bars([("3000", "3036", "2999", "3030"), ("3030", "3031", "2985", "2990")], T0 + 3 * MIN)
    r = _monitor(j, bars, T0 + 6 * MIN, base.exit_policy, base.unico.partial)
    assert r.closed == ((b, "stop"),) and r.protected == ((b, "break_even"),)
    close_paper(portfolio_id="brain", run_id=RUN, position_id=a, exit_price=D("2995"), reason="manual", fee_bps=6,
                journal=j, now_ms=T0 + 7 * MIN)                      # chiusura manuale della vecchia
    with pytest.raises(Exception):
        close_paper(portfolio_id="brain", run_id=RUN, position_id=a, exit_price=D("2995"), reason="manual",
                    fee_bps=6, journal=j, now_ms=T0 + 8 * MIN)       # mai due volte
    rows = [r.event for r in j.list_run("brain", RUN)]
    assert [e.kind for e in rows].count("paper_open") == 2 and [e.kind for e in rows].count("paper_close") == 2
    s = build_summary(j, "brain", RUN)
    assert s.open_positions == () or list(s.open_positions) == []
    assert s.realized_pnl == sum(D(e.payload["realized_pnl"]) for e in rows if e.kind == "paper_close")
    fees = sum(D(e.payload["fees"]) for e in rows if e.kind == "paper_close")
    assert fees == sum(D(e.payload["gross_pnl"]) - D(e.payload["realized_pnl"]) for e in rows if e.kind == "paper_close")


# ----------------------------------------------------------------------------- limiti e richieste non valide
@pytest.mark.parametrize("text", ["Aumenta la leva a 50", "Rischio per trade al 6 %", "Porta il capitale a 5000",
                                  "Margine massimo 600 per posizione", "Togli la perdita giornaliera massima",
                                  "Approva il mandato"])
def test_risk_limits_and_mandate_cannot_change_by_command(tmp_path, text):
    j = _journal(tmp_path)
    with pytest.raises(sv.StrategyError, match="non si cambiano"):
        sv.propose(text, sv.read_registry(j, RUN), BASE, T0)


def test_only_allowed_paths_reach_the_config_and_tampering_is_refused(tmp_path):
    with pytest.raises(sv.StrategyError):
        sv.validate_overlay({"risk_policy.max_leverage": 60})
    with pytest.raises(sv.StrategyError):
        sv.validate_overlay({"cycle_minutes": 5})                    # solo 15, 30, 45, 60
    j = _journal(tmp_path)
    prop = sv.propose("Take profit finale a 2 R", sv.read_registry(j, RUN), BASE, T0)
    sv.save_proposal(tmp_path, prop)
    sv.approve(tmp_path, prop.id, "operatore", "", T0)
    req = json.loads((tmp_path / sv.REQUEST_FILE).read_text())
    req["proposal"]["overlay"] = {"exit_policy.take_profit_r": "9"}   # alterata dopo l'approvazione
    (tmp_path / sv.REQUEST_FILE).write_text(json.dumps(req))
    res = sv.apply_request(journal=j, data_dir=tmp_path, run_id=RUN, base_bytes=BASE, now_ms=T0 + 1)
    assert res["ok"] is False and "alterata" in res["error"]
    assert sv.read_registry(j, RUN).active == "V1" and j.list_run("brain", RUN) == []


def test_a_stale_proposal_is_refused(tmp_path):
    j = _journal(tmp_path)
    p1 = sv.propose("Take profit finale a 2 R", sv.read_registry(j, RUN), BASE, T0)
    p2 = sv.propose("Ogni 15 minuti", sv.read_registry(j, RUN), BASE, T0 + 1)
    for p in (p1, p2):
        sv.save_proposal(tmp_path, p)
    sv.approve(tmp_path, p1.id, "op", "", T0)
    assert sv.apply_request(journal=j, data_dir=tmp_path, run_id=RUN, base_bytes=BASE, now_ms=T0 + 2)["ok"]
    sv.approve(tmp_path, p2.id, "op", "", T0 + 3)
    res = sv.apply_request(journal=j, data_dir=tmp_path, run_id=RUN, base_bytes=BASE, now_ms=T0 + 4)
    assert res["ok"] is False and "superata" in res["error"]


def test_interpreter_examples_and_notes_for_deepseek(tmp_path):
    j = _journal(tmp_path)
    reg = sv.read_registry(j, RUN)
    p = sv.propose("Trailing da 3 R a distanza 1,5 R, massimo 2 consulti di Claude per giro", reg, BASE, T0)
    assert dict((k, b) for k, _a, b in p.changes) == {"exit_policy.trail_at_r": "3", "exit_policy.trail_dist_r": "1.5",
                                                     "brain_unico.claude_consult.max_per_cycle": 2}
    n = sv.propose("Nota strategica: privilegia i pullback sul trend a 1h; NO_TRADE se il volume e' basso", reg, BASE, T0)
    assert n.overlay[sv.NOTES_KEY].startswith("privilegia i pullback")
    with pytest.raises(sv.StrategyError, match="non compresa"):
        sv.propose("fai soldi", reg, BASE, T0)
    out = []
    cli_out = type("O", (), {"write": lambda self, s: out.append(s), "flush": lambda self: None})()
    (tmp_path / "runner_config.json").write_bytes(BASE)
    args = ["--data-dir", str(tmp_path), "--run-id", RUN, "--config", str(tmp_path / "runner_config.json")]
    assert cli(args + ["proponi", "Da questo momento esamina i mercati ogni 15 minuti"], now_fn=lambda: T0,
               out=cli_out) == 0
    text = "".join(out)
    assert "NUOVA versione V2" in text and "frequenza di analisi (minuti): 30 → 15" in text
    pid = text.split("approva ")[1].split()[0]
    assert cli(args + ["approva", pid], now_fn=lambda: T0, out=cli_out) == 0
    assert (tmp_path / sv.REQUEST_FILE).is_file() and j.list_run("brain", RUN) == []   # il CLI non scrive il journal
    assert cli(args + ["proponi", "Aumenta la leva a 50"], now_fn=lambda: T0, out=cli_out) == 3


def test_notes_reach_the_deepseek_guidance_and_risk_stays_the_base(tmp_path):
    j = _journal(tmp_path)
    _approve(tmp_path, j, "Nota strategica: evita i breakout senza volume", T0)
    eff = sv.effective(BASE, sv.read_registry(j, RUN))
    assert eff.version == "V2" and eff.notes == "evita i breakout senza volume"
    assert eff.config == load_runner_config(BASE)                    # le note non toccano la configurazione
    src = (CFG.parents[0] / "wiring.py").read_text()
    assert "Operator strategy notes" in src and "never above the risk limits" in src


# ----------------------------------------------------------------------------- 6. runner: confine del giro
def test_runner_rebuilds_with_the_new_version_between_ticks_without_repeating_the_served_cycle(tmp_path, monkeypatch):
    from backend.v3.runner import wiring
    j = _journal(tmp_path)
    builds, clock = [], {"t": T0}

    class FakeRunner:
        def __init__(self, cycle_ms):
            self._cycle_ms, self._last_slot, self.loops = cycle_ms, -1, 0

        def run(self, *, now_fn, sleep_fn, should_stop, on_tick):
            while not should_stop():
                self._last_slot = now_fn() // self._cycle_ms      # "serve" il giro corrente
                self.loops += 1
                if self.loops == 2 and len(builds) == 1:
                    prop = sv.propose("ogni 15 minuti", sv.read_registry(j, RUN), BASE, now_fn())
                    sv.save_proposal(tmp_path, prop)
                    sv.approve(tmp_path, prop.id, "operatore", "", now_fn())
                clock["t"] += 5_000

    def fake_build(**kw):
        builds.append(kw["strategy"])
        cfg = kw["strategy"].config if kw["strategy"] is not None else kw["config"]
        return SimpleNamespace(runner=FakeRunner(cfg.cycle_ms), journal=j)

    monkeypatch.setattr(wiring, "build_runner", fake_build)
    stops = {"n": 0}

    def outer_stop():
        stops["n"] += 1
        assert stops["n"] < 500, "il runner non ha cambiato versione"      # mai un ciclo infinito nei test
        return len(builds) == 2 and builds[-1] is not None and stops["n"] > 8

    a = SimpleNamespace(run_id=RUN, once=False)
    rc = wiring._run_built(a, tmp_path, load_runner_config(BASE), {}, None, None, lambda: clock["t"],
                           lambda s: None, outer_stop, {}, {}, base_raw=BASE)
    assert rc == 0 and [b.version for b in builds] == ["V1", "V2"]
    assert builds[1].config.cycle_minutes == 15 and builds[0].config.cycle_minutes == 30
    assert sv.read_registry(j, RUN).active == "V2"


def test_the_real_open_path_records_the_active_version_snapshot(tmp_path):
    """Percorso reale: runner (snapshot della versione attiva) -> commit_paper_open -> execute_paper -> payload."""
    root = CFG.parents[0]
    wiring_src, serial_src = (root / "wiring.py").read_text(), (root / "open_serial.py").read_text()
    assert "snapshot = strategy.snapshot() if strategy is not None else None" in wiring_src
    assert "strategy=snapshot)   # Brain Live Evolution" in wiring_src
    assert "legs=legs,\n                                strategy=strategy)" in serial_src
    j = _journal(tmp_path)
    pid = _long_eth(j, at=T0, strategy=_snapshot(j))
    p = [r.event.payload for r in j.list_run("brain", RUN)][0]
    assert p["position_id"] == pid and p["strategy"]["version"] == "V1"
    assert p["strategy"]["exit_policy"] == json.loads(BASE)["exit_policy"]
    assert p["strategy"]["partial_take_profit"] == json.loads(BASE)["brain_unico"]["partial_take_profit"]
