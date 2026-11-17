"""Chiusura manuale PAPER per AI dell'Arena + motivazione umana. Dati sintetici, servizio uscite vero, nessuna rete."""
from __future__ import annotations

import json
import threading
from decimal import Decimal as D

import pytest

from backend.tests.test_v3_runner_e2e import VIEW, G, _get_json_factory
from backend.v3.arena import manual_close as MC
from backend.v3.arena import runner as R
from backend.v3.arena.test_arena_runner import (
    DAY,
    ENV,
    M,
    PolicyModel,
    _approve_and_unpause,
    _kinds,
    _prepare,
)
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.exit_worker import build_exit_worker
from backend.v3.runner.manual_close import MAX_AGE_MS, REQUEST_FILE, WORK_FILE

T0 = G + 25_000
RID = "req-0000000000000001"
RID2 = "req-0000000000000002"


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "arena"
    r.mkdir()
    return r


class Prices:
    """Feed sintetico con un interruttore: ``broken`` simula un prezzo mancante per il servizio uscite."""

    def __init__(self):
        self.inner, self.broken = _get_json_factory(), False

    def __call__(self, url):
        if self.broken and "candles" in url:
            raise OSError("feed_down")
        return self.inner(url)


def _opened(root, provider="qwen"):
    plan = _prepare(root, provider)
    _approve_and_unpause(plan)
    gj = Prices()
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    exits = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=gj)
    exits.start()
    exits.tick(T0)
    built = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: T0, get_json=gj,
                                 inner_transport=PolicyModel(), view_params=VIEW)
    assert built.runner.tick(T0).cycle.opened
    pids = [o["position_id"] for o in _kinds(plan, "paper_open")]
    assert len(pids) == 2
    return plan, exits, gj, pids


def test_close_one_position_confirmed_by_journal_then_annotate_once(root):
    plan, exits, _, (pid, other) = _opened(root)
    try:
        r = MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        assert r["status"] == "pending" and r["terminal"] is False
        assert json.loads((plan.folder / REQUEST_FILE).read_text())["position_ids"] == [pid]
        # la motivazione prima della chiusura confermata e' rifiutata
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.annotate(plan, request_id=RID, reason="profit_protection", now_ms=T0 + 2)
        assert e.value.code == "close_not_confirmed"
        exits.tick(T0 + 5_000)
        s = MC.close_status(plan, request_id=RID, now_ms=T0 + 6_000)
        assert s["status"] == "closed" and s["terminal"] and s["exit_reason"] == "manual"
        assert s["close_event_id"] and s["annotation"] is None
        # una ripetizione della stessa richiesta non accoda nulla
        again = MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 7_000)
        assert again["status"] == "closed" and not (plan.folder / REQUEST_FILE).exists()
        assert len(MC.read_chain(plan.folder / MC.REQUESTS_FILE)) == 1
        # solo UNA posizione chiusa; l'altra resta aperta
        closes = _kinds(plan, "paper_close")
        assert [c["position_id"] for c in closes] == [pid]
        a = MC.annotate(plan, request_id=RID, reason="profit_protection", note=" tendenza esaurita ", now_ms=T0 + 8_000)
        assert a["note"] == "tendenza esaurita" and a["close_event_id"] == s["close_event_id"]
        assert a["source"] == "human_operator" and a["position_id"] == pid
        assert MC.annotate(plan, request_id=RID, reason="profit_protection", note="tendenza esaurita",
                           now_ms=T0 + 9_000) == a                     # ripetizione identica: idempotente
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.annotate(plan, request_id=RID, reason="loss_reduction", now_ms=T0 + 9_000)
        assert e.value.code == "already_annotated"
        assert len(MC.read_annotations(plan)) == 1
        assert MC.close_status(plan, request_id=RID, now_ms=T0 + 9_000)["annotation"]["reason"] == "profit_protection"
        assert other in {o["position_id"] for o in _kinds(plan, "paper_open")}
    finally:
        exits.stop()


def test_registers_are_hash_chained_and_tampering_fails_closed(root):
    plan, exits, _, (pid, _) = _opened(root)
    try:
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        exits.tick(T0 + 5_000)
        MC.annotate(plan, request_id=RID, reason="other", now_ms=T0 + 6_000)
    finally:
        exits.stop()
    path = plan.folder / MC.ANNOTATIONS_FILE
    rec = json.loads(path.read_text())
    assert rec["prev"] == MC.GENESIS and rec["note"] is None
    path.write_text(json.dumps(dict(rec, reason="loss_reduction")) + "\n")
    with pytest.raises(MC.ArenaCloseError) as e:
        MC.read_annotations(plan)
    assert e.value.code == "registry_corrupt"


def test_invalid_inputs_and_no_guessing_of_the_reason(root):
    plan, exits, _, (pid, _) = _opened(root)
    try:
        for bad in ("short", "x" * 65, "req id with spaces!", 7, None):
            with pytest.raises(MC.ArenaCloseError) as e:
                MC.request_close(plan, position_id=pid, request_id=bad, now_ms=T0 + 1)
            assert e.value.code == "invalid_request_id"
        for bad in ("", "../x", 5, "a" * 65):
            with pytest.raises(MC.ArenaCloseError):
                MC.request_close(plan, position_id=bad, request_id=RID, now_ms=T0 + 1)
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.request_close(plan, position_id="nope", request_id=RID, now_ms=T0 + 1)
        assert e.value.status == 404 and e.value.code == "position_not_open"
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        exits.tick(T0 + 5_000)
        for reason in ("guess_from_pnl", "", None, "PROFIT_PROTECTION"):
            with pytest.raises(MC.ArenaCloseError) as e:
                MC.annotate(plan, request_id=RID, reason=reason, now_ms=T0 + 6_000)
            assert e.value.code == "invalid_reason"
        for note in ("", "   ", "x" * 281, "riga\nnuova", 3):
            with pytest.raises(MC.ArenaCloseError) as e:
                MC.annotate(plan, request_id=RID, reason="other", note=note, now_ms=T0 + 6_000)
            assert e.value.code == "invalid_note"
        assert MC.read_annotations(plan) == []
        # "unspecified" e' una scelta esplicita dell'operatore, non una deduzione
        assert MC.annotate(plan, request_id=RID, reason="unspecified", now_ms=T0 + 6_000)["reason"] == "unspecified"
    finally:
        exits.stop()


def test_exit_service_down_refuses_without_writing_a_request(root):
    plan, exits, _, (pid, _) = _opened(root)
    exits.stop()                                            # lease rilasciato: nessun proprietario delle uscite
    with pytest.raises(MC.ArenaCloseError) as e:
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
    assert e.value.code == "exit_service_not_ready"
    assert not (plan.folder / REQUEST_FILE).exists() and MC.read_chain(plan.folder / MC.REQUESTS_FILE) == []
    assert MC.manual_close_ready(plan, T0 + 1) is False


def test_one_request_in_flight_reused_id_and_already_closed(root):
    plan, exits, _, (pid, other) = _opened(root)
    try:
        assert MC.manual_close_ready(plan, T0 + 1) is True
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.request_close(plan, position_id=other, request_id=RID2, now_ms=T0 + 2)
        assert e.value.code == "request_in_progress"
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.request_close(plan, position_id=other, request_id=RID, now_ms=T0 + 3)
        assert e.value.code == "request_id_reused"
        exits.tick(T0 + 5_000)
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.request_close(plan, position_id=pid, request_id=RID2, now_ms=T0 + 6_000)
        assert e.value.code == "position_already_closed"
        assert MC.request_close(plan, position_id=other, request_id=RID2, now_ms=T0 + 7_000)["status"] == "pending"
    finally:
        exits.stop()


def test_concurrent_duplicate_clicks_produce_one_request_and_one_close(root):
    plan, exits, _, (pid, _) = _opened(root)
    results, errors = [], []

    def click():
        try:
            results.append(MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1))
        except MC.ArenaCloseError as exc:
            errors.append(exc.code)
    try:
        threads = [threading.Thread(target=click) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [] and len(results) == 8
        assert len(MC.read_chain(plan.folder / MC.REQUESTS_FILE)) == 1
        exits.tick(T0 + 5_000)
        exits.tick(T0 + 10_000)
    finally:
        exits.stop()
    assert [c["position_id"] for c in _kinds(plan, "paper_close")] == [pid]


def test_missing_price_is_a_terminal_failure_and_blocks_the_annotation(root):
    plan, exits, prices, (pid, _) = _opened(root)
    try:
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        prices.broken = True
        exits.tick(T0 + 5_000)
        s = MC.close_status(plan, request_id=RID, now_ms=T0 + 6_000)
        assert s["status"] == "failed" and s["terminal"] and s["code"] == "price_unavailable"
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.annotate(plan, request_id=RID, reason="loss_reduction", now_ms=T0 + 7_000)
        assert e.value.code == "close_not_confirmed"
        assert _kinds(plan, "paper_close") == []
    finally:
        exits.stop()


def test_worker_never_picks_up_the_request_becomes_unconfirmed(root):
    plan, exits, _, (pid, _) = _opened(root)
    try:
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
    finally:
        exits.stop()                                        # il servizio muore prima di prendere in carico
    assert MC.close_status(plan, request_id=RID, now_ms=T0 + 60_000)["status"] == "pending"
    late = T0 + MAX_AGE_MS + MC.GRACE_MS + 10
    s = MC.close_status(plan, request_id=RID, now_ms=late)
    assert s["status"] == "unconfirmed" and s["terminal"] and s["code"] == "exit_service_did_not_confirm"
    assert _kinds(plan, "paper_close") == []


def test_crash_after_claim_resumes_and_confirms_on_restart(root):
    plan, exits, prices, (pid, _) = _opened(root)
    MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
    exits.stop()
    (plan.folder / REQUEST_FILE).replace(plan.folder / WORK_FILE)   # preso in carico, poi crash
    assert MC.close_status(plan, request_id=RID, now_ms=T0 + 2_000)["status"] == "pending"
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    again = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=prices)
    with again:
        again.tick(T0 + 30_000)
    assert MC.close_status(plan, request_id=RID, now_ms=T0 + 31_000)["status"] == "closed"
    assert len(_kinds(plan, "paper_close")) == 1


def test_stop_hit_first_is_reported_as_other_exit_and_cannot_be_annotated(root):
    plan, exits, _, pids = _opened(root)
    try:
        for minute in range(1, 26):                         # target BTC al 17, stop ETH al 21
            exits.tick(T0 + minute * M)
        closes = {c["position_id"]: c for c in _kinds(plan, "paper_close")}
        assert set(closes) == set(pids)
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.request_close(plan, position_id=pids[0], request_id=RID, now_ms=T0 + 26 * M)
        assert e.value.code == "position_already_closed"
    finally:
        exits.stop()


def test_race_with_automatic_exit_after_request(root):
    plan, exits, _, (pid, _) = _opened(root)
    try:
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        # lo stop/target arriva prima che il comando sia eseguito: simulato chiudendo dal journal con altro motivo
        from backend.v3.events import EventJournal
        from backend.v3.executor.paper_close import close_paper
        close_paper(portfolio_id="brain", run_id=plan.run_id, position_id=pid, exit_price=D("1"),
                    reason="stop", fee_bps=0, journal=EventJournal(plan.journal), now_ms=T0 + 2)
        exits.tick(T0 + 5_000)
        s = MC.close_status(plan, request_id=RID, now_ms=T0 + 6_000)
        assert s["status"] == "closed_by_other_exit" and s["exit_reason"] == "stop"
        with pytest.raises(MC.ArenaCloseError) as e:
            MC.annotate(plan, request_id=RID, reason="loss_reduction", now_ms=T0 + 7_000)
        assert e.value.code == "close_not_confirmed"
    finally:
        exits.stop()


def test_dispatch_codes_and_strict_bodies(root):
    plan, exits, _, (pid, _) = _opened(root)
    plans = {"qwen": plan}
    try:
        assert MC.dispatch(plans, "close", "minimax", {"position_id": pid, "request_id": RID}, T0) == \
            (422, {"ok": False, "code": "invalid_provider"})
        assert MC.dispatch(plans, "close", "qwen", {"position_id": pid, "request_id": RID, "x": 1}, T0)[0] == 422
        assert MC.dispatch(plans, "status", "qwen", {"request_id": RID}, T0) == \
            (404, {"ok": False, "code": "request_not_found"})
        code, body = MC.dispatch(plans, "close", "qwen", {"position_id": pid, "request_id": RID}, T0 + 1)
        assert code == 200 and body["ok"] and body["status"] == "pending"
        exits.tick(T0 + 5_000)
        code, body = MC.dispatch(plans, "annotate", "qwen", {"request_id": RID, "reason": "trend_change"}, T0 + 6_000)
        assert code == 200 and body["annotation"]["reason"] == "trend_change"
    finally:
        exits.stop()


def test_backup_copy_restores_journal_and_human_registers_verifiably(root, tmp_path):
    import shutil

    from backend.v3.arena.prepare import plan_for
    from backend.v3.events import EventJournal
    plan, exits, _, (pid, _) = _opened(root)
    try:
        MC.request_close(plan, position_id=pid, request_id=RID, now_ms=T0 + 1)
        exits.tick(T0 + 5_000)
        MC.annotate(plan, request_id=RID, reason="trend_change", now_ms=T0 + 6_000)
    finally:
        exits.stop()
    restored_root = tmp_path / "restored"
    shutil.copytree(root, restored_root, ignore=shutil.ignore_patterns(".exit_service.lock"))
    copy = plan_for("qwen", DAY, restored_root)
    EventJournal(copy.journal).verify_chain()
    assert MC.read_chain(copy.folder / MC.REQUESTS_FILE) == MC.read_chain(plan.folder / MC.REQUESTS_FILE)
    assert MC.read_annotations(copy) == MC.read_annotations(plan)
    assert MC.close_status(copy, request_id=RID, now_ms=T0 + 7_000)["annotation"]["reason"] == "trend_change"
    # la sola cronologia degli eventi resta: nessun file dell'Arena tocca altre run
    assert sorted(p.name for p in root.iterdir()) == ["qwen"]
