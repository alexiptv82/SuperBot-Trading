"""RC84 P0-A/P0-B: chiusure PAPER non protettive con commit contabile in due fasi.

Percorsi: regole/Claude, manuale singola, parziale, S25 a tempo.
Invarianti: (1) un fill nei registri esiste solo se il conto con il claim di quel fill e' su disco;
(2) mai due terminali della stessa posizione; (3) Telegram solo dopo il commit definitivo, legato
all'identita' del claim; (4) registri append-only. Sintetico, nessuna rete.
"""
import json

import pytest

import desk.cli as cli
from backend.tests.test_v3_rc82_active_paper_stops import BAR, BASE, NOW, _history, _open, _state, desk  # noqa: F401

FLAT = [[BASE - BAR, 100, 100.5, 99.5, 100, 1]]   # nessuno stop/TP/liq toccato
H13 = 13 * 3_600_000
PATHS = ("manual", "partial", "rules", "s25")
PROOF = ("symbol", "id", "open_ms", "close_ms", "why", "net")


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


def _disk(desk):
    path = desk / "state_v2.json"
    return json.loads(path.read_text()) if path.exists() else None


def _assert_coherent(desk):
    """Ogni fill nei registri e' nel conto su disco; mai due terminali; nessuna posizione fantasma."""
    disk = _disk(desk)
    closed = (disk or {}).get("main", {}).get("closed", [])
    open_ids = {p.get("id") for p in ((disk or {}).get("main", {}).get("positions") or {}).values()}
    claims = (disk or {}).get(cli.CLAIMS_KEY) or []
    for rows in (_history(desk), _learning(desk)):
        terminals = [(r["id"], r["open_ms"]) for r in rows if not r.get("partial")]
        assert len(terminals) == len(set(terminals)), "due terminali della stessa posizione"
        for r in rows:
            in_book = any(all(c.get(k) == r.get(k) for k in PROOF) for c in closed)
            assert in_book, f"fill nei registri assente dal conto salvato: {r.get('close_ms')}"
            if not r.get("partial"):
                assert r["id"] not in open_ids, "posizione fantasma: chiusa nei registri, aperta nel conto"
    for c in claims:
        assert any(all(x.get(k) == c["rec"].get(k) for k in PROOF) for x in closed)


class Rig:
    def __init__(self, desk, monkeypatch):
        self.desk, self.mp = desk, monkeypatch
        self.sent, self.at_send = [], []
        self.real_save = cli.save_state
        self.saves = 0

        def notify(*a):
            self.sent.append(a)                    # prima di tutto: un invio va sempre registrato
            self.at_send.append((_disk(desk), len(_history(desk)), len(_learning(desk))))

        monkeypatch.setattr(cli, "notify_close", notify)
        monkeypatch.setattr(cli, "notify_open", lambda *a, **k: None)
        cli.fetch_candles = lambda sym, bar="15m", limit=1000: FLAT if sym == "BTC" else []
        cli.rules_decisions = lambda *_a, **_k: []
        monkeypatch.setattr(cli, "save_state", self._save)
        self.fail_on = set()

    def _save(self, state, path):
        self.saves += 1
        if self.saves in self.fail_on:
            raise OSError("simulated_state_save_failure")
        return self.real_save(state, path)

    def fail_saves(self, *which):
        self.saves, self.fail_on = 0, set(which)

    def heal(self):
        self.fail_on = set()


@pytest.fixture
def rig(desk, monkeypatch):
    return Rig(desk, monkeypatch)


def _initial(rig, path):
    if path == "s25":
        from desk import long_s25
        rig.mp.setenv("DESK_LONG_S25", "1")
        account = _open(1, 98.0, 110.0, NOW - H13)
        account.positions["BTC"].source = long_s25.SOURCE
    else:
        account = _open(1, 98.0, 110.0, BASE - 3 * BAR)
    state = _state(account)
    rig.real_save(state, cli.STATE_FILE)           # stato iniziale su disco
    return state


def _run(rig, path, state, now=NOW):
    """Esegue il percorso; un errore di salvataggio simulato e' atteso, altro no."""
    try:
        if path in ("rules", "partial"):
            action = ({"symbol": "BTC", "action": "close", "reason": "probe"} if path == "rules" else
                      {"symbol": "BTC", "action": "partial_close", "reason": "probe", "partial_close_fraction": 0.5})
            cli.rules_decisions = lambda *_a, **_k: [action]
            cli.run_cycle(state, now)
        elif path == "manual":
            rig.mp.setattr(cli.time, "time", lambda: now / 1000)       # richiesta e gestore sullo stesso orologio
            (rig.desk / "close_position.flag").write_text(json.dumps({"symbols": ["BTC"], "ts": now}))
            cli._check_close_position_flag(state, price_provider=lambda syms, st, n: {"BTC": 101.0})
        else:
            cli.rules_decisions = lambda *_a, **_k: []
            cli.run_cycle(state, now)
    except OSError as exc:
        assert "simulated_state_save_failure" in str(exc)
    finally:
        cli.rules_decisions = lambda *_a, **_k: []


def _restart(rig, now):
    """Riavvio del processo: solo cio' che e' su disco; un ciclo senza decisioni completa i claim."""
    state = _disk(rig.desk)
    cli.run_cycle(state, now)
    return state


def _btc_open_on_disk(rig):
    return "BTC" in (_disk(rig.desk)["main"]["positions"] or {})


# ---------------------------------------------------------------- positivo

@pytest.mark.parametrize("path", PATHS)
def test_positive_close_is_definitive_logged_once_and_notified_after_commit(rig, path):
    state = _initial(rig, path)
    _run(rig, path, state)
    assert len(rig.sent) == 1 and rig.sent[0][0] == "BTC"
    disk_at_send, hist_n, learn_n = rig.at_send[0]
    assert (hist_n, learn_n) == (1, 1)
    assert not disk_at_send.get(cli.CLAIMS_KEY)                   # definitiva prima del Telegram
    assert ("BTC" in disk_at_send["main"]["positions"]) == (path == "partial")
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    row, book = _history(rig.desk)[0], _disk(rig.desk)["main"]["closed"][-1]
    assert all(row[k] == book[k] for k in PROOF) and rig.sent[0][1] == book["net"]
    _assert_coherent(rig.desk)


# ---------------------------------------------------------------- registri non scrivibili (P0-A)

@pytest.mark.parametrize("broken", ["history", "learning"])
@pytest.mark.parametrize("path", PATHS)
def test_unwritable_register_keeps_a_durable_claim_and_recovers_exactly_once(rig, path, broken):
    real_hist, real_learn = cli.append_trade_history, cli.log_event
    if broken == "history":
        rig.mp.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    else:
        rig.mp.setattr(cli, "log_event", lambda *_a, **_k: False)
    state = _initial(rig, path)
    _run(rig, path, state)
    assert rig.sent == []
    disk = _disk(rig.desk)
    assert len(disk[cli.CLAIMS_KEY]) == 1                         # chiusura NON definitiva, ma durevole
    assert cli.HB["paper_close_claims"]["pending"] == 1
    _assert_coherent(rig.desk)
    # disco di nuovo scrivibile: il riavvio completa lo STESSO record, non ricalcola un fill
    rig.mp.setattr(cli, "append_trade_history", real_hist)
    rig.mp.setattr(cli, "log_event", real_learn)
    _restart(rig, NOW + 600_000)
    assert len(rig.sent) == 1
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    assert not _disk(rig.desk).get(cli.CLAIMS_KEY)
    assert _history(rig.desk)[0]["close_ms"] == disk[cli.CLAIMS_KEY][0]["rec"]["close_ms"]
    _assert_coherent(rig.desk)


# ---------------------------------------------------------------- salvataggi falliti / crash (P0-A, P0-B)

@pytest.mark.parametrize("path", PATHS)
def test_failed_checkpoint_writes_nothing_and_a_later_retry_is_the_only_fill(rig, path):
    state = _initial(rig, path)
    rig.fail_saves(1)                                             # fase 1 fallita
    _run(rig, path, state)
    assert rig.sent == [] and _history(rig.desk) == [] and _learning(rig.desk) == []
    assert _btc_open_on_disk(rig) and not _disk(rig.desk).get(cli.CLAIMS_KEY)
    rig.heal()
    later = NOW + 60_000                                          # altro istante: nuova operazione legittima
    _run(rig, path, _disk(rig.desk), now=later)
    assert len(rig.sent) == 1
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    assert _history(rig.desk)[0]["close_ms"] == later
    _assert_coherent(rig.desk)


@pytest.mark.parametrize("path", PATHS)
def test_crash_after_registers_before_final_save_completes_the_same_close_on_restart(rig, path):
    state = _initial(rig, path)
    rig.fail_saves(2)                                             # fase 1 ok, registri scritti, fase 3 fallita
    _run(rig, path, state)
    assert rig.sent == []
    claim = _disk(rig.desk)[cli.CLAIMS_KEY][0]
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    _assert_coherent(rig.desk)
    rig.heal()
    _restart(rig, NOW + 3_600_000)                                # molto piu' tardi: nessun nuovo fill
    assert len(rig.sent) == 1
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    assert _history(rig.desk)[0]["close_ms"] == claim["rec"]["close_ms"]
    assert not _disk(rig.desk).get(cli.CLAIMS_KEY)
    _assert_coherent(rig.desk)


@pytest.mark.parametrize("path", ["manual", "rules", "s25"])
def test_retry_request_after_crash_cannot_create_a_second_terminal(rig, path):
    state = _initial(rig, path)
    rig.fail_saves(2)
    _run(rig, path, state)
    rig.heal()
    # nuova richiesta a un altro istante PRIMA che un ciclo completi il claim: la posizione e' gia' chiusa nel conto
    _run(rig, path, _disk(rig.desk), now=NOW + 60_000)
    terminals = [r for r in _history(rig.desk) if not r.get("partial")]
    assert len(terminals) == 1 and len(rig.sent) == 1
    _assert_coherent(rig.desk)


# ---------------------------------------------------------------- terminale incompatibile gia' presente (P0-B)

@pytest.mark.parametrize("path", PATHS)
def test_incompatible_terminal_already_logged_blocks_the_close_and_alters_nothing(rig, path):
    state = _initial(rig, path)
    pos = cli.make_account(state).positions["BTC"]
    foreign = {"id": pos.id, "symbol": "BTC", "side": pos.side, "open_ms": pos.open_ms,
               "close_ms": NOW - 1, "why": "altro", "net": -1.0}
    (rig.desk / "trade_history.jsonl").write_text(json.dumps(foreign) + "\n", encoding="utf-8")
    before = (rig.desk / "trade_history.jsonl").read_bytes()
    _run(rig, path, state)
    assert (rig.desk / "trade_history.jsonl").read_bytes() == before
    assert _learning(rig.desk) == [] and rig.sent == []
    assert _btc_open_on_disk(rig) and not _disk(rig.desk).get(cli.CLAIMS_KEY)
    if path == "manual":
        assert "verifica necessaria" in json.dumps(_disk(rig.desk).get("last_action"))
    elif path == "s25":
        assert "BTC" in _disk(rig.desk)["main"]["positions"]
    else:
        assert "BTC" in cli.HB.get("paper_close_blocked", [])


# ---------------------------------------------------------------- parziali legittime distinte

def test_two_legitimate_partials_keep_distinct_identities_across_a_crash(rig):
    state = _initial(rig, "partial")
    _run(rig, "partial", state)
    rig.fail_saves(1)                                             # la seconda parziale fallisce al checkpoint
    _run(rig, "partial", _disk(rig.desk), now=NOW + 60_000)
    assert len(_history(rig.desk)) == 1 and len(rig.sent) == 1
    rig.heal()
    _run(rig, "partial", _disk(rig.desk), now=NOW + 120_000)
    rows = _history(rig.desk)
    assert len(rows) == 2 and len({r["close_ms"] for r in rows}) == 2 and all(r["partial"] for r in rows)
    assert len(_learning(rig.desk)) == 2 and len(rig.sent) == 2
    _assert_coherent(rig.desk)


# ---------------------------------------------------------------- Telegram

@pytest.mark.parametrize("path", PATHS)
def test_telegram_failure_does_not_undo_a_definitive_close(rig, path):
    def down(*_a):
        raise OSError("offline_telegram")
    rig.mp.setattr(cli, "notify_close", down)
    state = _initial(rig, path)
    _run(rig, path, state)
    assert not _disk(rig.desk).get(cli.CLAIMS_KEY)
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    _assert_coherent(rig.desk)


def test_notice_is_bound_to_the_claim_identity_not_to_symbol_and_net(rig, monkeypatch):
    base = {"id": "BTC-1", "symbol": "BTC", "side": 1, "open_ms": 1, "why": "p", "net": 1.5,
            "partial": True, "fraction": 0.5}
    a, b = dict(base, close_ms=10), dict(base, close_ms=20)          # stesso simbolo e stesso netto
    state = {"run_no": 1, "main": {}, cli.CLAIMS_KEY: []}
    cli._claim_paper_close(state, a, ("A", "partial_close"))
    cli._claim_paper_close(state, b, ("B", "partial_close"))
    real = cli.append_trade_history
    monkeypatch.setattr(cli, "append_trade_history",
                        lambda d, rec: None if rec.get("close_ms") == 20 else real(d, rec))
    cli._commit_paper_closes(state)
    assert [s[2] for s in rig.sent] == ["A"]
    assert [c["rec"]["close_ms"] for c in state[cli.CLAIMS_KEY]] == [20]


# ---------------------------------------------------------------- LIVE invariato

def test_live_close_keeps_the_original_record_close_and_creates_no_claim(rig, monkeypatch):
    order = []
    monkeypatch.setattr(cli.LIVE, "_live", True)
    monkeypatch.setattr(cli.LIVE, "close", lambda *_a, **_k: (True, "ok"))
    monkeypatch.setattr(cli, "notify_close", lambda *a: order.append("notify"))
    real = cli.record_close
    monkeypatch.setattr(cli, "record_close", lambda s, r: (order.append("record"), real(s, r))[1])
    cli.rules_decisions = lambda *_a, **_k: [{"symbol": "BTC", "action": "close", "reason": "live"}]
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    try:
        cli.run_cycle(state, NOW)
    except Exception:
        pass
    assert order[:2] == ["notify", "record"]
    assert not state.get(cli.CLAIMS_KEY)


def test_pending_partial_is_not_a_conflict_with_a_later_terminal_of_the_same_position(rig):
    real_hist = cli.append_trade_history
    rig.mp.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    state = _initial(rig, "partial")
    _run(rig, "partial", state)
    claim = _disk(rig.desk)[cli.CLAIMS_KEY][0]["rec"]
    later = {k: claim[k] for k in ("id", "symbol", "side", "open_ms")}
    later.update(close_ms=claim["close_ms"] + 60_000, why="SL", net=-2.0)
    with open(rig.desk / "trade_history.jsonl", "a", encoding="utf-8") as fh:   # terminale successivo
        fh.write(json.dumps(later) + "\n")
    rig.mp.setattr(cli, "append_trade_history", real_hist)
    cli._commit_paper_closes(_disk(rig.desk))
    assert cli.HB["paper_close_claims"] == {"pending": 0, "conflict": []}
    assert [bool(r.get("partial")) for r in _history(rig.desk)] == [False, True]
    assert len(rig.sent) == 1


def test_close_all_paper_uses_the_same_two_phase_commit_and_never_notifies(rig):
    real_hist = cli.append_trade_history
    rig.mp.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    state = _initial(rig, "rules")
    (rig.desk / "reset.flag").write_text("")
    cli._check_close_all_flag(state, price_provider=lambda syms, st, n: {"BTC": 101.0})
    assert not _btc_open_on_disk(rig) and len(_disk(rig.desk)[cli.CLAIMS_KEY]) == 1
    assert _history(rig.desk) == [] and rig.sent == []
    rig.mp.setattr(cli, "append_trade_history", real_hist)
    _restart(rig, NOW + 60_000)
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1) and rig.sent == []
    _assert_coherent(rig.desk)
