"""Bull a 10 posizioni (decisione dell'utente, 20/10/2026 13:56): il limite vero e' la cassa, non il numero di slot.
Il testo dato a Claude deve dire le stesse cifre del codice."""
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


def test_bull_has_ten_slots_and_hawk_is_unchanged():
    b, h = cli._make_bull_config(), cli._make_hawk_config()
    assert b.limits.max_open == 10 and h.limits.max_open == 10
    assert b.limits.max_margin_trade == 350.0 and h.limits.max_margin_trade == 100.0
    assert b.limits.max_margin_total == 1000.0 and h.limits.max_margin_total == 1000.0   # budget $1000 per bot (utente, 20/10 14:11)
    assert b.limits.start_equity == 1000.0 and h.limits.start_equity == 1000.0
    assert b.guardrail_min_margin == 150.0 and b.guardrail_margin_forced == 200.0        # guardrail invariato
    assert "10 posizioni" in b.description


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


def test_bull_opens_more_than_three_until_cash_runs_out():
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 150)
    opened = [s for s, p, _ in res if p is not None]
    assert len(opened) >= 6                                        # a 150$ ne stanno almeno 6
    for _, p, msg in res:
        assert "troppe posizioni" not in msg                       # il rifiuto, se c'e', e' per il margine
    first_refused = next(msg for _, p, msg in res if p is None)
    assert "margine" in first_refused or "cassa" in first_refused
    assert a.cash >= 0 and a.margin_in_use() <= limits.max_margin_total


def test_bull_slots_free_up_margin_when_positions_close():
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 150)
    n = len(a.positions)
    assert a.close("BTC", 100.0, T + 60_000, "test") is not None
    p, msg = a.open("UNI", 1, 150, 10, 100.0, 97.0, 110.0, T + 120_000, {}, trade_type="medio")
    assert p is not None, msg                                      # il margine liberato rende lo slot di nuovo disponibile
    assert len(a.positions) == n


def test_eleventh_position_is_refused_for_slots_when_margin_is_small():
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 60, 11)
    assert sum(1 for _, p, _ in res if p is not None) == 10
    assert "troppe posizioni" in res[10][2]


def test_seventh_bull_request_is_reduced_below_the_150_minimum_not_refused_DECISION_PENDING():
    """CARATTERIZZAZIONE del comportamento di oggi (segnalato da ChatGPT, riprodotto da Claude 20/10/2026):
    con budget 1000 $, leva 10 e richieste da 150 $, i primi 6 ingressi sono da 150 $, il 7mo NON e' rifiutato
    ma ridotto dal motore (room = min(350, 1000 - margine in uso, cassa*0.95)) a circa 89,9 $, SOTTO il minimo
    di 150 $ che il prompt promette e che il guardrail del cli applica alle proposte. L'8vo e' rifiutato.
    Alexander deve scegliere: (A) rifiutare se il margine rimasto e' sotto il minimo del bot, oppure (B) lasciare
    cosi'. Se sceglie A questo test va rovesciato (7mo rifiutato). Non e' una regola voluta: e' la fotografia."""
    limits = cli._make_bull_config().limits
    a, res = _open_many(limits, 150, 8)
    margins = [p.total_margin if p is not None else None for _, p, _ in res]
    assert margins[:6] == [150.0] * 6
    assert margins[6] is not None and 85.0 < margins[6] < 95.0 and margins[6] < cli._make_bull_config().guardrail_min_margin
    assert margins[7] is None and "margine" in res[7][2]
    assert a.cash < 10.0                                           # la cassa e' praticamente esaurita
