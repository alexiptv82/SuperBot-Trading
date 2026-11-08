"""RC84 P1: l'avviso Telegram di chiusura PAPER non protettiva parte solo dopo storico, learning e stato salvati.

Percorsi: (1) regole/Claude, (2) manuale singola, (3) parziale, (4) S25 a tempo.
Sintetico, nessuna rete: notify_close e' sostituito da un registratore.
"""
import json
import time

import pytest

import desk.cli as cli
from backend.tests.test_v3_rc82_active_paper_stops import BAR, BASE, NOW, _history, _open, _state, desk  # noqa: F401

FLAT = [[BASE - BAR, 100, 100.5, 99.5, 100, 1]]   # nessuno stop/TP/liq toccato
H13 = 13 * 3_600_000


def _learning(desk):
    path = desk / "learning_log.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("ev") == "close":
            rows.append(row)
    return rows


class Rig:
    def __init__(self, desk, monkeypatch):
        self.desk, self.mp = desk, monkeypatch
        self.sent, self.events = [], []
        self.real_save = cli.save_state

        def notify(*a):
            self.sent.append(a)                    # prima di tutto: un invio va sempre registrato
            # Al momento dell'invio la chiusura deve essere gia' su disco in tutti e tre i posti.
            state_file = desk / "state_v2.json"
            saved = (json.loads(state_file.read_text())["main"]["positions"]
                     if state_file.exists() else None)
            self.events.append(("notify", len(_history(desk)), len(_learning(desk)), saved))

        monkeypatch.setattr(cli, "notify_close", notify)
        monkeypatch.setattr(cli, "notify_open", lambda *a, **k: None)
        cli.fetch_candles = lambda sym, bar="15m", limit=1000: FLAT if sym == "BTC" else []

    def fail_save(self):
        def boom(*_a):
            raise OSError("simulated_state_save_failure")
        self.mp.setattr(cli, "save_state", boom)

    def restore_save(self):
        self.mp.setattr(cli, "save_state", self.real_save)


@pytest.fixture
def rig(desk, monkeypatch):
    return Rig(desk, monkeypatch)


# ---- percorsi: ciascuno come funzione (fresh_state) -> esegue il percorso, restituisce nulla

def _rules_close(rig, kind):
    action = {"close": {"symbol": "BTC", "action": "close", "reason": "probe"},
              "partial": {"symbol": "BTC", "action": "partial_close", "reason": "probe",
                          "partial_close_fraction": 0.5}}[kind]
    cli.rules_decisions = lambda *_a, **_k: [action]
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    cli.run_cycle(state, NOW)
    return state


def _manual_close(rig):
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    (rig.desk / "close_position.flag").write_text(json.dumps({"symbols": ["BTC"], "ts": int(time.time() * 1000)}))
    cli._check_close_position_flag(state, price_provider=lambda syms, st, now: {"BTC": 101.0})
    return state


def _s25_close(rig):
    from desk import long_s25
    rig.mp.setenv("DESK_LONG_S25", "1")
    account = _open(1, 98.0, 110.0, NOW - H13)
    account.positions["BTC"].source = long_s25.SOURCE
    cli.rules_decisions = lambda *_a, **_k: []
    state = _state(account)
    cli.run_cycle(state, NOW)
    return state


PATHS = {
    "rules": lambda rig: _rules_close(rig, "close"),
    "partial": lambda rig: _rules_close(rig, "partial"),
    "manual": _manual_close,
    "s25": _s25_close,
}


def _swallow(fn, rig):
    try:
        return fn(rig)
    except OSError as exc:
        assert "simulated_state_save_failure" in str(exc)


@pytest.mark.parametrize("path", sorted(PATHS))
def test_positive_notice_only_after_history_learning_and_state_are_on_disk(rig, path):
    PATHS[path](rig)
    assert len(rig.sent) == 1 and rig.sent[0][0] == "BTC"
    _, hist_n, learn_n, saved_positions = rig.events[0]
    assert hist_n >= 1 and learn_n >= 1 and saved_positions is not None
    if path == "partial":
        assert "BTC" in saved_positions            # resta il 50%
    else:
        assert "BTC" not in saved_positions        # lo stato su disco ha gia' la chiusura
    assert len(_history(rig.desk)) == 1 and len(_learning(rig.desk)) == 1


@pytest.mark.parametrize("path", sorted(PATHS))
def test_negative_state_save_fails_means_no_notice(rig, path):
    rig.fail_save()
    _swallow(PATHS[path], rig)
    assert rig.sent == []


@pytest.mark.parametrize("path", sorted(PATHS))
def test_negative_history_not_written_means_no_notice(rig, path):
    rig.mp.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    PATHS[path](rig)
    assert rig.sent == []
    assert _history(rig.desk) == []


@pytest.mark.parametrize("path", sorted(PATHS))
def test_negative_learning_not_written_means_no_notice(rig, path):
    rig.mp.setattr(cli, "log_event", lambda *_a, **_k: False)
    PATHS[path](rig)
    assert rig.sent == []
    assert len(_history(rig.desk)) == 1


@pytest.mark.parametrize("path", sorted(PATHS))
def test_telegram_failure_does_not_undo_a_saved_paper_close(rig, path):
    def down(*_a):
        raise OSError("offline_telegram")
    rig.mp.setattr(cli, "notify_close", down)
    PATHS[path](rig)
    saved = json.loads((rig.desk / "state_v2.json").read_text())["main"]["positions"]
    assert ("BTC" in saved) == (path == "partial")
    assert len(_history(rig.desk)) == 1 and len(_learning(rig.desk)) == 1


@pytest.mark.parametrize("path", sorted(PATHS))
def test_crash_after_logs_then_retry_notifies_once_without_duplicate_rows(rig, path, monkeypatch):
    if path == "manual":                           # il gestore usa l'orologio reale: ripresa a istante identico
        monkeypatch.setattr(cli.time, "time", lambda: NOW / 1000)
    rig.fail_save()
    _swallow(PATHS[path], rig)
    assert rig.sent == []
    rows_after_crash = (len(_history(rig.desk)), len(_learning(rig.desk)))
    assert rows_after_crash == (1, 1)              # il registro e' scritto, il conto no: nulla annunciato
    rig.restore_save()
    PATHS[path](rig)                               # riavvio: stessa posizione ancora aperta su disco
    assert len(rig.sent) == 1
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)


def test_a_failed_cycle_never_leaks_its_notice_into_the_next_commit(rig):
    rig.fail_save()
    _swallow(PATHS["rules"], rig)
    rig.restore_save()
    cli.rules_decisions = lambda *_a, **_k: []
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    state["run_no"] = 1
    cli.run_cycle(state, NOW)                      # nessuna chiusura: nessun avviso vecchio
    assert rig.sent == []


def test_live_mode_keeps_the_original_notify_before_record_order(rig, monkeypatch):
    order = []
    monkeypatch.setattr(cli.LIVE, "_live", True)
    monkeypatch.setattr(cli.LIVE, "close", lambda *_a, **_k: (True, "ok"))
    monkeypatch.setattr(cli, "notify_close", lambda *a: order.append("notify"))
    real = cli.record_close
    monkeypatch.setattr(cli, "record_close", lambda s, r: (order.append("record"), real(s, r))[1])
    cli.rules_decisions = lambda *_a, **_k: [{"symbol": "BTC", "action": "close", "reason": "live"}]
    try:
        cli.run_cycle(_state(_open(1, 98.0, 110.0, BASE - 3 * BAR)), NOW)
    except Exception:
        pass
    assert order[:2] == ["notify", "record"]


def test_manual_retry_at_another_instant_is_a_new_fill_and_never_rewrites_history(rig, monkeypatch):
    clock = {"t": NOW / 1000}
    monkeypatch.setattr(cli.time, "time", lambda: clock["t"])
    rig.fail_save()
    _swallow(PATHS["manual"], rig)
    assert rig.sent == [] and len(_history(rig.desk)) == 1
    rig.restore_save()
    clock["t"] += 60
    PATHS["manual"](rig)
    assert len(rig.sent) == 1                      # un solo avviso, dopo il commit vero
    assert len(_history(rig.desk)) == 2            # riga orfana del tentativo fallito conservata (append-only)
