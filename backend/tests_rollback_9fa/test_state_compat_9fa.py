"""Il codice del 13/10 deve poter leggere lo stato scritto dal codice attuale, senza perdere nulla e senza cambiare i
parametri: i limiti vengono dal codice (make_account li riscrive), non dallo stato salvato.

Se CURRENT_BACKEND_DIR e' impostata (CI), lo stato di prova e' prodotto dal VERO codice attuale in un processo separato;
altrimenti si usa uno stato sintetico con gli stessi campi aggiunti dopo il 13/10."""
import json
import os
import subprocess
import sys

import pytest

from desk import cli
from desk.engine import Limits, PaperAccount, Position

EXTRA_LIMITS = {"min_initial_margin": 100.0, "min_initial_leverage": 10}


def _synthetic_state() -> dict:
    a = PaperAccount(Limits(max_margin_trade=250.0, max_open=10), "main")
    p, msg = a.open("BTC", -1, 100, 20, 100.0, 101.0, 98.0, 1_000, {"BTC": 100.0})
    assert p is not None, msg
    d = a.to_dict()
    d["limits"].update(EXTRA_LIMITS)
    d["positions"][str(list(d["positions"].keys())[0])]["last_bar_ms"] = 123456
    return d


def _current_code_state() -> dict:
    cur = os.environ.get("CURRENT_BACKEND_DIR")
    if not cur:
        pytest.skip("CURRENT_BACKEND_DIR non impostata: solo stato sintetico")
    code = (
        "import json\n"
        "from desk.engine import Limits, PaperAccount\n"
        "a = PaperAccount(Limits(), 'main')\n"
        "p, msg = a.open('BTC', -1, 100, 20, 100.0, 101.0, 98.0, 1000, {'BTC': 100.0})\n"
        "assert p is not None, msg\n"
        "print(json.dumps(a.to_dict(), default=str))\n"
    )
    env = dict(os.environ, PYTHONPATH=cur)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_old_loader_rejects_nothing_synthetic():
    d = _synthetic_state()
    a = PaperAccount.from_dict(d)
    assert set(a.positions) == {"BTC"}
    assert a.positions["BTC"].side == -1 and a.positions["BTC"].margin == 100
    assert a.cash == pytest.approx(PaperAccount.from_dict(d).cash)


def test_old_loader_reads_state_written_by_current_code():
    d = _current_code_state()
    a = PaperAccount.from_dict(d)
    assert set(a.positions) == {"BTC"}
    # nessuna posizione, nessun conto, nessun registro perso
    assert a.next_id == d["next_id"] and a.closed == d["closed"] and a.cash == d["cash"]


@pytest.mark.parametrize("make,margin,slots,total", [
    (cli._make_hawk_config, 100.0, 10, 1000.0),
    (cli._make_bull_config, 350.0, 3, 1050.0),
])
def test_limits_come_from_code_not_from_saved_state(monkeypatch, make, margin, slots, total):
    cfg = make()
    monkeypatch.setattr(cli, "PORTFOLIO", cfg)
    d = _synthetic_state()  # lo stato salvato porta limiti diversi (250 / 10 / campi nuovi)
    acc = cli.make_account({"main": d})
    L = acc.limits
    assert (L.max_margin_trade, L.max_open, L.max_margin_total) == (margin, slots, total)
    assert L.daily_stop == 0.12 and L.kill_equity == 450.0
    assert set(acc.positions) == {"BTC"}


def test_round_trip_does_not_drop_core_fields():
    d = _synthetic_state()
    a = PaperAccount.from_dict(d)
    out = a.to_dict()
    for k in ("cash", "closed", "next_id", "day", "day_start_equity"):
        assert out[k] == d[k]
    assert out["positions"]["BTC"]["entry"] == d["positions"]["BTC"]["entry"]
