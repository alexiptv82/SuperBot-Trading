"""Bull a 6 posizioni e budget 1050 $ (decisione dell'utente, 21/10/2026: "tornare come all'inizio" nella gestione di
leve e puntate; il 20/10 erano 10 posizioni e 1000 $, all'inizio 3 posizioni e 1050 $ = 3 x 350 $).
Hawk non cambia: 10 posizioni, 1000 $. Il testo dato a Claude deve dire le stesse cifre del codice."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from dataclasses import replace  # noqa: E402

from desk import brain, cli  # noqa: E402
from desk.engine import PaperAccount  # noqa: E402

T = 1_800_000_000_000
SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX", "DOT", "LINK", "UNI", "ATOM"]


def _open_many(limits, margin, n=len(SYMS)):
    a = PaperAccount(limits)
    results = []
    for s in SYMS[:n]:
        p, msg = a.open(s, 1, margin, 10, 100.0, 97.0, 110.0, T, {}, trade_type="medio")
        results.append((s, p, msg))
    return a, results


def test_bull_has_six_slots_1050_budget_and_hawk_is_unchanged():
    b, h = cli._make_bull_config(), cli._make_hawk_config()
    assert b.limits.max_open == 6 and h.limits.max_open == 10
    assert b.limits.max_margin_trade == 350.0 and h.limits.max_margin_trade == 100.0
    assert b.limits.max_margin_total == 1050.0 and h.limits.max_margin_total == 1000.0   # Bull 1050 (utente, 21/10); Hawk invariato
    assert b.limits.start_equity == 1000.0 and h.limits.start_equity == 1000.0
    assert b.guardrail_min_margin == 150.0 and b.guardrail_margin_forced == 200.0        # guardrail invariato
    assert b.refuse_below_min_margin is True                                             # opzione A invariata
    assert "6 posizioni" in b.description and "1050" in b.description


def test_bull_prompt_states_the_same_slots_and_sizes_as_the_code():
    cfg = cli._make_bull_config()
    n, lo, hi = cfg.limits.max_open, int(cfg.guardrail_min_margin), int(cfg.limits.max_margin_trade)
    p = brain.SYSTEM_BULL
    assert f"fino a {n} posizioni contemporanee, margine da ${lo} a ${hi} per trade" in p
    assert f"margine {lo}-{hi}$" in p
    assert f"Posizioni max {n}." in p and f"FINO A {n} POSIZIONI" in p
    for old in ("MAX 3 POSIZIONI", "SOLO 3", "Posizioni max 3", "max 3 trade", "gia' 3 posizioni", "selettivissimo"):
        assert old not in p, old
    assert "Non e' obbligatorio riempire gli slot" in p


def test_old_cap_would_have_refused_the_fourth_trade_control():
    """Controllo: con il vecchio tetto di 3 il quarto trade veniva rifiutato per il numero di posizioni."""
    old = replace(cli._make_bull_config().limits, max_open=3)
    _, res = _open_many(old, 100, 4)
    assert [p is not None for _, p, _ in res] == [True, True, True, False]
    assert "troppe posizioni" in res[3][2]


def test_bull_opens_up_to_six_then_the_slots_are_full():
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 150)
    opened = [s for s, p, _ in res if p is not None]
    assert len(opened) == 6                                        # sei da 150 $ = 900 $ entrano, la settima no
    first_refused = next(msg for _, p, msg in res if p is None)
    assert "troppe posizioni" in first_refused                     # il rifiuto e' per gli slot: 6 su 6
    assert a.cash >= 0 and a.margin_in_use() <= limits.max_margin_total


def test_bull_slots_free_up_margin_when_positions_close():
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 150)
    n = len(a.positions)
    assert a.close("BTC", 100.0, T + 60_000, "test") is not None
    p, msg = a.open("UNI", 1, 150, 10, 100.0, 97.0, 110.0, T + 120_000, {}, trade_type="medio")
    assert p is not None, msg                                      # il margine liberato rende lo slot di nuovo disponibile
    assert len(a.positions) == n


def test_seventh_position_is_refused_for_slots_when_margin_is_small():
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 60, 7)
    assert sum(1 for _, p, _ in res if p is not None) == 6
    assert "troppe posizioni" in res[6][2]


def test_hawk_still_has_ten_slots():
    limits = cli._make_hawk_config().limits
    a, res = _open_many(limits, 60, 11)
    assert sum(1 for _, p, _ in res if p is not None) == 10
    assert "troppe posizioni" in res[10][2]


def test_direct_engine_call_still_reduces_below_the_minimum_by_design_the_cli_gate_is_the_policy():
    """CHIAMATA DIRETTA AL MOTORE (PaperAccount.open), non il ciclo del bot. Il motore NON e' cambiato: con budget
    1050 $, leva 10, cinque ingressi da 190 $ (950 $) lasciano ~50 $ di cassa e il sesto, richiesto da 150 $, viene
    ridotto dal motore a ~42 $. Resta cosi' per progetto, perche' Hawk e Turbo usano lo stesso motore e non cambiano.
    La DECISIONE di Alexander (opzione A, 20/10/2026 16:30, ancora attiva) e' applicata dal ciclo del bot:
    cli.margin_gate rifiuta l'apertura di Bull quando il margine disponibile e' sotto 150 $ (vedi
    test_bull_margin_gate_2026_10_20.py)."""
    cfg = cli._make_bull_config()
    a = PaperAccount(cfg.limits)
    for s in SYMS[:5]:
        p, msg = a.open(s, 1, 190, 10, 100.0, 97.0, 110.0, T, {}, trade_type="medio")
        assert p is not None and p.total_margin == 190.0, msg
    p, msg = a.open(SYMS[5], 1, 150, 10, 100.0, 97.0, 110.0, T, {}, trade_type="medio")
    assert p is not None and 35.0 < p.total_margin < 50.0 and p.total_margin < cfg.guardrail_min_margin
    # la politica di Bull e' invece quella del ciclo: prima del sesto ingresso il cancello dice di no
    b = PaperAccount(cfg.limits)
    for s in SYMS[:5]:
        assert cli.margin_gate(b, cfg) is None
        b.open(s, 1, 190, 10, 100.0, 97.0, 110.0, T, {}, trade_type="medio")
    assert cli.margin_gate(b, cfg) is not None
