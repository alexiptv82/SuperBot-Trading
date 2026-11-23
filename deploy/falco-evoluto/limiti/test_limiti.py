"""Proposta limiti 23/11 (Brain Scalp 15/25/25 %, Falco Evoluto 6/12/12 %): configurazioni, interazioni con floor e
Guardian verificate sul codice reale, procedura di aggiornamento (prova completa in cartelle finte) e audit del freno."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import analisi_limiti as al  # noqa: E402
from backend.v3.brain_f2.engine import _policy_hash  # noqa: E402
from backend.v3.events import Event, EventJournal  # noqa: E402
from backend.v3.guardian import evaluate_guardian, session_start_ms  # noqa: E402
from backend.v3.risk import RiskRequest, quote_paper_risk  # noqa: E402
from backend.v3.runner.daily_loss import DailyLoss, DailyLossGuard  # noqa: E402
from backend.v3.runner.prepared_config_guard import verify_prepared_run_config  # noqa: E402

RUNNER = ROOT / "backend" / "v3" / "runner"
NAMES = {"scalp": "runner_config_brain_scalp_paper.json", "falco": "runner_config_falco_evoluto_paper.json"}
OLD = {k: al.load(RUNNER / v) for k, v in NAMES.items()}
NEW = {k: al.load(HERE / v) for k, v in NAMES.items()}
TOOL = HERE / "aggiorna_limiti.py"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------ configurazioni
def test_new_configs_change_exactly_the_three_requested_values():
    import aggiorna_limiti as ag
    want = {"scalp": ("0.15", "0.25", "0.25"), "falco": ("0.06", "0.12", "0.12")}
    for bot in NAMES:
        o, n = OLD[bot], NEW[bot]
        assert ag.config_fields_diff(o, n) == sorted(ag.CHANGED)
        assert (str(n.daily_loss_warn), str(n.daily_loss_halt), str(n.guardian.session_loss_fraction)) == want[bot]
        assert n.risk_policy == o.risk_policy and _policy_hash(n.risk_policy) == _policy_hash(o.risk_policy)
        assert n.exit_policy == o.exit_policy and n.initial_equity == o.initial_equity
        g, h = n.guardian, o.guardian                       # protezione dei profitti e drawdown globale invariati
        assert (g.activation_fraction, g.keep_fraction, g.global_drawdown_half, g.global_drawdown_lock) == (
            h.activation_fraction, h.keep_fraction, h.global_drawdown_half, h.global_drawdown_lock)
        assert (n.risk_policy.max_loss_fraction, n.risk_policy.max_open_risk_fraction) == (D("0.04"), D("0.10"))
        assert (n.risk_policy.min_leverage, n.risk_policy.max_leverage) == (15, 45)
        # impronte bloccate nella procedura = file del commit
        assert ag.RUNS[bot]["old_sha"] == sha(RUNNER / NAMES[bot])
        assert ag.RUNS[bot]["new_sha"] == sha(HERE / NAMES[bot])
        # testo identico salvo le tre righe
        a, b = (RUNNER / NAMES[bot]).read_text().splitlines(), (HERE / NAMES[bot]).read_text().splitlines()
        assert len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 3


# ------------------------------------------------------------------ interazioni (aritmetica)
def test_scalp_proposal_floor_and_global_drawdown_block_before_the_daily_stop():
    c = NEW["scalp"]
    first = al.primo_blocco(c, D("2000"))
    assert {s.nome for s in first} == {"floor_equity", "guardian_drawdown_globale"} and first[0].equity == D("1600")
    assert set(al.mai_raggiunti(c, D("2000"))) == {"freno_giornaliero", "guardian_sessione"}
    # dopo profitti: il drawdown globale (20 % dal massimo) scatta sempre prima dello stop giornaliero (25 %)
    for e in (D("2400"), D("3000"), D("5000")):
        assert [s.nome for s in al.primo_blocco(c, e)] == ["guardian_drawdown_globale"]
    # oggi (8 %) lo stop giornaliero e' il primo blocco
    assert {s.nome for s in al.primo_blocco(OLD["scalp"], D("2000"))} == {"freno_giornaliero", "guardian_sessione"}


def test_falco_proposal_daily_stop_is_the_real_day_stop_except_after_a_losing_day():
    c = NEW["falco"]
    first = al.primo_blocco(c, D("1000"))
    assert {s.nome for s in first} == {"freno_giornaliero", "guardian_sessione"} and first[0].equity == D("880")
    assert al.mai_raggiunti(c, D("1000")) == []
    # il rischio per trade si dimezza a -10 %, prima dello stop a -12 %
    names = [s.nome for s in al.soglie(c, D("1000"))]
    assert names.index("rischio_dimezzato") < names.index("freno_giornaliero")
    # dopo una giornata a -10 %: il floor 800 arriva prima del -12 %
    assert {s.nome for s in al.primo_blocco(c, D("900"), D("1000"))} == {"floor_equity", "guardian_drawdown_globale"}


# ------------------------------------------------------------------ stesso esito sul codice reale
def _req(**kw):
    d = dict(equity=D("2000"), available_cash=D("2000"), margin_used=D(0), existing_open_risk=D(0), entry_price=D(100),
             stop_price=D("99.5"), side=1, requested_leverage=30, exchange_leverage_limit=50, quantity_step=D("0.0001"),
             minimum_notional=D(5), maintenance_fraction=D("0.005"), market_data_fresh=True, paused=False,
             daily_loss_latched=False)
    d.update(kw)
    return RiskRequest(**d)


def test_risk_manager_floor_blocks_scalp_at_1600_whatever_the_daily_stop():
    p = NEW["scalp"].risk_policy
    assert quote_paper_risk(p, _req()).allowed
    assert quote_paper_risk(p, _req(equity=D("1600"), available_cash=D("1600"))).reason == "equity_floor_reached"
    q = quote_paper_risk(p, _req(equity=D("1700"), available_cash=D("1700"), existing_open_risk=D("100")))
    assert q.reason == "risk_budget_exhausted"                  # 1700 - 1600 - 100 = 0: niente sotto il floor
    pf = NEW["falco"].risk_policy
    assert quote_paper_risk(pf, _req(equity=D("800"), available_cash=D("800"))).reason == "equity_floor_reached"


NOW = 1_795_428_000_000                                          # 23/11/2026 12:00 UTC


def _guardian(policy, price):
    s = session_start_ms(NOW, policy)
    ev = [SimpleNamespace(kind="paper_open", occurred_at_ms=s + 60_000, payload={
        "position_id": "p", "symbol": "XRPUSDT", "side": 1, "fill_price": "100", "quantity": "20", "stop_price": "90"})]
    c = NEW["scalp"]
    return evaluate_guardian(events=ev, initial_equity=c.initial_equity, close_at=lambda sym, m: D(price), now_ms=NOW,
                             policy=policy, max_loss_fraction=D("0.04"), fee_bps=D("6"), roundtrip_cost_bp=D("16"))


def test_guardian_session_limit_and_global_drawdown_on_the_real_code():
    old, new = OLD["scalp"].guardian, NEW["scalp"].guardian
    g_old, g_new = _guardian(old, "91.8"), _guardian(new, "91.8")       # circa -8,3 % di sessione
    assert g_old.state == "LOCKED" and "session_loss" in g_old.reasons
    assert g_new.state == "NORMAL"                                       # con 25 % non blocca
    g = _guardian(new, "80")                                             # circa -20 %: drawdown globale
    assert g.state == "LOCKED" and g.reasons == ("global_drawdown",)


def _state(tmp, day, reason):
    (tmp / "daily_loss.json").write_text(json.dumps({
        "version": 2, "day_start_ms": day, "warn_sent": True, "halt_sent": reason == "loss",
        "unverified_sent": reason == "unverified", "halt_latched": True, "latch_reason": reason,
        "checked_through_ms": NOW - 120_000, "audit_from_ms": day if reason == "unverified" else 0}))


def test_a_loss_latch_survives_the_new_limits_but_an_unverified_one_would_be_lifted(tmp_path):
    day = NOW // 86_400_000 * 86_400_000
    ev = lambda now: DailyLoss("ok", D("0.082"), D("164"), day)
    c = NEW["scalp"]
    _state(tmp_path, day, "loss")
    g = DailyLossGuard(data_dir=tmp_path, evaluate=ev, warn_fraction=c.daily_loss_warn, halt_fraction=c.daily_loss_halt,
                       audit=lambda a, b: D("0.082"))
    assert g(NOW).level == "halt"                                      # il blocco di oggi resta fino a 00:00 UTC
    assert json.loads((tmp_path / "daily_loss.json").read_text())["latch_reason"] == "loss"
    _state(tmp_path, day, "unverified")
    g = DailyLossGuard(data_dir=tmp_path, evaluate=ev, warn_fraction=c.daily_loss_warn, halt_fraction=c.daily_loss_halt,
                       audit=lambda a, b: D("0.082"))
    assert g(NOW).level == "ok"            # 8,2 % < 25 %: verrebbe tolto -> la procedura rifiuta con blocco agganciato
    # domani: nessun blocco ereditato
    g = DailyLossGuard(data_dir=tmp_path, evaluate=lambda now: DailyLoss("ok", D("0"), D("0"), day + 86_400_000),
                       warn_fraction=c.daily_loss_warn, halt_fraction=c.daily_loss_halt, audit=lambda a, b: D("0"))
    assert g(NOW + 86_400_000).level == "ok"


# ------------------------------------------------------------------ procedura completa in cartelle finte
FAKE_SYSTEMCTL = """#!/bin/sh
cmd="$1"; shift
case "$cmd" in
  show) unit="$4"; cat "$FAKE_SD/$unit.pid" 2>/dev/null || echo 4242 ;;
  is-active) unit="$2"; [ ! -e "$FAKE_SD/$unit.inactive" ] ;;
  restart) unit="$1"; echo "$unit" >> "$FAKE_SD/calls"
    case "$unit" in *-runner.service)
      "$FAKE_PY" -c "import json,time,sys; s=open(sys.argv[2]).read().strip() if __import__('os').path.exists(sys.argv[2]) else 'running'; st,err=(s.split('|')+[None])[:2]; json.dump({'ts_ms':int(time.time()*1000)+5,'state':st,'last_error':err,'daily_loss_level':'ok','daily_loss_pct':'0.0'},open(sys.argv[1],'w'))" "$FAKE_RUN/heartbeat.json" "$FAKE_SD/next_state" ;;
    *) echo 9999 > "$FAKE_SD/$unit.pid" ;; esac ;;
esac
"""


def _make_run(tmp: Path, bot: str = "scalp", *, latch: str | None = None, guardian_reasons=("floor_armed",),
              guardian_at: int | None = None) -> dict:
    import time
    import aggiorna_limiti as ag
    r = ag.RUNS[bot]
    parent, backups, sd = tmp / "runs", tmp / "backups", tmp / "sd"
    run = parent / r["dir"]
    for d in (run, backups, sd):
        d.mkdir(parents=True)
    raw = (RUNNER / NAMES[bot]).read_bytes()
    (run / "runner_config.json").write_bytes(raw)
    (run / "PREPARED_PAUSED_ONLY.json").write_text(json.dumps({
        "run_id": r["run_id"], "portfolio_id": "brain", "paper_only": True, "paused": True, "mandate_approved": False,
        "config_sha256": hashlib.sha256(raw).hexdigest(), "initial_equity": str(OLD[bot].initial_equity)}, indent=1))
    (run / "mandate.json").write_text(json.dumps({"version": "v1", "approved": True, "approved_by": "proprietario",
                                                  "portfolio_id": "brain", "run_id": r["run_id"],
                                                  "policy_hash": _policy_hash(OLD[bot].risk_policy)}))
    now = int(time.time() * 1000)
    day = now // 86_400_000 * 86_400_000
    dl = {"version": 2, "day_start_ms": day if latch else day - 86_400_000, "warn_sent": False, "halt_sent": False,
          "unverified_sent": False, "halt_latched": latch is not None, "latch_reason": latch or "",
          "checked_through_ms": now - 60_000, "audit_from_ms": 0}
    (run / "daily_loss.json").write_text(json.dumps(dl, sort_keys=True))
    (run / "heartbeat.json").write_text(json.dumps({"ts_ms": now - 30_000, "state": "running"}))
    j = EventJournal(str(run / "journal.db"))
    j.init_schema()
    j.append(Event(event_id="g1", portfolio_id="brain", run_id=r["run_id"], kind="guardian_state",
                   occurred_at_ms=guardian_at or now - 60_000, source="test",
                   payload={"state": "SELECTIVE", "reasons": list(guardian_reasons), "as_of_ms": now - 60_000}))
    for f in run.iterdir():
        os.chmod(f, 0o600)
    fake = sd / "systemctl"
    fake.write_text(FAKE_SYSTEMCTL)
    fake.chmod(0o755)
    env = dict(os.environ, LIMITI_TEST_MODE="1", LIMITI_PARENT=str(parent), LIMITI_BACKUPS=str(backups),
               LIMITI_SYSTEMCTL=str(fake), FAKE_SD=str(sd), FAKE_RUN=str(run), FAKE_PY=sys.executable,
               PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    return {"run": run, "backups": backups, "sd": sd, "env": env, "bot": bot, "r": r}


def _tool(ctx, *args):
    p = subprocess.run([sys.executable, str(TOOL), "--bot", ctx["bot"], *args, "--attesa", "10"], env=ctx["env"],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def _snap(run: Path) -> dict:
    return {f.name: f.read_bytes() for f in run.iterdir() if f.is_file()}


def test_check_only_changes_nothing(tmp_path):
    ctx = _make_run(tmp_path)
    before = _snap(ctx["run"])
    rc, out = _tool(ctx, "--controlla", "--nuova", str(HERE / NAMES["scalp"]))
    assert rc == 0 and "CONTROLLI_SUPERATI_NESSUNA_MODIFICA" in out and "VALIDO_ANCHE_DOPO" in out
    assert _snap(ctx["run"]) == before


def test_apply_changes_only_config_and_marker_hash_keeps_latch_journal_mandate_and_exits(tmp_path):
    ctx = _make_run(tmp_path)
    run = ctx["run"]
    before = _snap(run)
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["scalp"]), "--approvato-da", "proprietario")
    assert rc == 0, out
    assert "LIMITI_RESULT=LIMITI_AGGIORNATI" in out and "stesso processo 4242" in out
    assert (run / "runner_config.json").read_bytes() == (HERE / NAMES["scalp"]).read_bytes()
    m_old, m_new = json.loads(before["PREPARED_PAUSED_ONLY.json"]), json.loads((run / "PREPARED_PAUSED_ONLY.json").read_text())
    assert m_new == dict(m_old, config_sha256=ctx["r"]["new_sha"])
    verify_prepared_run_config(data_dir=run, run_id=ctx["r"]["run_id"], config=NEW["scalp"])   # i servizi ripartono
    for f in ("journal.db", "mandate.json", "daily_loss.json"):
        assert (run / f).read_bytes() == before[f], f
    assert oct((run / "runner_config.json").stat().st_mode & 0o777) == "0o600"
    calls = (ctx["sd"] / "calls").read_text().split()
    assert calls == [ctx["r"]["runner"]]                               # solo il runner, mai il servizio uscite
    amend = [json.loads(x) for x in (run / "CONFIG_AMENDMENTS.jsonl").read_text().splitlines()]
    assert amend[-1]["action"] == "amend" and amend[-1]["approved_by"] == "proprietario"
    backup = next(ctx["backups"].iterdir())
    assert (backup / "runner_config.json").read_bytes() == before["runner_config.json"]
    assert (backup / "PREPARED_PAUSED_ONLY.json").read_bytes() == before["PREPARED_PAUSED_ONLY.json"]
    # gia' applicata: rifiuto senza modifiche
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["scalp"]), "--approvato-da", "proprietario")
    assert rc == 3 and "gia_applicata" in out

    # rollback: torna la configurazione precedente; il freno su disco NON torna indietro
    (run / "daily_loss.json").write_text('{"cambiato": "dopo"}')
    rc, out = _tool(ctx, "--rollback")
    assert rc == 0 and "LIMITI_PRECEDENTI_RIPRISTINATI" in out, out
    assert (run / "runner_config.json").read_bytes() == before["runner_config.json"]
    assert (run / "PREPARED_PAUSED_ONLY.json").read_bytes() == before["PREPARED_PAUSED_ONLY.json"]
    assert (run / "daily_loss.json").read_text() == '{"cambiato": "dopo"}'
    verify_prepared_run_config(data_dir=run, run_id=ctx["r"]["run_id"], config=OLD["scalp"])


@pytest.mark.parametrize("kw,reason", [
    ({"latch": "loss"}, "freno_giornaliero_agganciato_oggi"),
    ({"latch": "unverified"}, "freno_giornaliero_agganciato_oggi"),
    ({"guardian_reasons": ("session_loss",)}, "guardian_bloccato_per_perdita_di_sessione"),
    ({"guardian_at": 1_000_000}, "nessuna_valutazione_del_guardian_nella_sessione"),
])
def test_refuses_without_changes_when_a_block_would_be_lifted(tmp_path, kw, reason):
    ctx = _make_run(tmp_path, **kw)
    before = _snap(ctx["run"])
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["scalp"]), "--approvato-da", "proprietario")
    assert rc == 3 and reason in out and "NESSUNA_MODIFICA" in out
    assert _snap(ctx["run"]) == before and not any(ctx["backups"].iterdir())


def test_refuses_unexpected_config_wrong_file_and_invalid_mandate(tmp_path):
    ctx = _make_run(tmp_path, "falco")
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["scalp"]), "--approvato-da", "x")
    assert rc == 3 and "nuova_configurazione_impronta_errata" in out
    m = json.loads((ctx["run"] / "mandate.json").read_text())
    (ctx["run"] / "mandate.json").write_text(json.dumps(dict(m, approved=False)))
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["falco"]), "--approvato-da", "x")
    assert rc == 3 and "mandato_non_valido" in out
    (ctx["run"] / "runner_config.json").write_bytes(b"{}")
    rc, out = _tool(ctx, "--controlla")
    assert rc == 3 and "configurazione_in_uso_inattesa" in out


def test_automatic_rollback_when_the_runner_is_not_healthy_after_restart(tmp_path):
    ctx = _make_run(tmp_path)
    before = _snap(ctx["run"])
    (ctx["sd"] / "next_state").write_text("halted|halted:mandate_mismatch")
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["scalp"]), "--approvato-da", "proprietario")
    assert rc == 4 and "AUTO_ROLLBACK_CONFIGURAZIONE_PRECEDENTE" in out
    for f in ("runner_config.json", "PREPARED_PAUSED_ONLY.json", "journal.db", "daily_loss.json", "mandate.json"):
        assert (ctx["run"] / f).read_bytes() == before[f], f


def test_exit_service_restart_is_detected(tmp_path):
    ctx = _make_run(tmp_path)
    exit_unit = ctx["r"]["exit"]
    fake = ctx["sd"] / "systemctl"          # un riavvio del runner che porta con se' anche le uscite
    fake.write_text(FAKE_SYSTEMCTL.replace('echo "$unit" >> "$FAKE_SD/calls"',
                                           f'echo "$unit" >> "$FAKE_SD/calls"; echo 7777 > "$FAKE_SD/{exit_unit}.pid"'))
    rc, out = _tool(ctx, "--applica", "--nuova", str(HERE / NAMES["scalp"]), "--approvato-da", "proprietario")
    assert rc == 4 and "servizio_uscite_riavviato_inatteso" in out


# ------------------------------------------------------------------ audit del freno
def test_audit_reconstructs_the_halt_minute_read_only(tmp_path, monkeypatch, capsys):
    import audit_freno
    import backend.v3.runner.feed as feed
    from backend.v3.runner.feed import Bar
    run = tmp_path / "brain-v3-brain-scalp-p1"
    run.mkdir()
    (run / "runner_config.json").write_bytes((RUNNER / NAMES["scalp"]).read_bytes())
    day = 1_795_392_000_000                                          # 23/11/2026 00:00 UTC
    j = EventJournal(str(run / "journal.db"))
    j.init_schema()
    t1, t2 = day + 16 * 3_600_000 + 52 * 60_000, day + 17 * 3_600_000 + 32 * 60_000
    for i, (t, sym, side, fill, stop, qty) in enumerate(((t1, "XRPUSDT", -1, "2", "2.04", "1900"),
                                                         (t2, "ETHUSDT", 1, "3000", "2940", "1.25"))):
        j.append(Event(event_id=f"o{i}", portfolio_id="brain", run_id="brain-scalp-paper-p1", kind="paper_open",
                       occurred_at_ms=t, source="t", payload={"position_id": f"p{i}", "symbol": sym, "side": side,
                                                              "fill_price": fill, "stop_price": stop, "quantity": qty}))
    halt_minute = day + 17 * 3_600_000 + 43 * 60_000

    def bars(sym, lo, hi, *, candle_ms, get_json):
        out = []
        for m in range(lo // 60_000 * 60_000, hi, 60_000):
            late = m + 60_000 >= halt_minute
            px = {"XRPUSDT": D("2.035") if late else D("2.0"), "ETHUSDT": D("2945") if late else D("3000")}[sym]
            out.append(Bar(open_time_ms=m, open=px, high=px, low=px, close=px, volume=D(1)))
        return out
    monkeypatch.setattr(feed, "fetch_closed_bars", bars)
    monkeypatch.setattr(audit_freno, "PARENT", tmp_path)
    before = (run / "journal.db").read_bytes()
    audit_freno.main(["--bot", "scalp", "--giorno", "2026-11-23"])
    out = capsys.readouterr().out
    # XRP: (2.035-2)*1900 = 66.5 ; ETH: (3000-2945)*1.25 = 68.75 ; totale 135.25 / 2000 = 6.76 % -> sotto l'8 %
    assert "stop (8 %): mai raggiunto" in out and "avviso (5 %): raggiunto al minuto che termina alle 17:43:00" in out
    assert "COERENTE" in out and "entro lo stop" in out
    assert (run / "journal.db").read_bytes() == before
