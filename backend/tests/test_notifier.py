"""Test dei messaggi Telegram dei bot: ogni messaggio dice se e' LIVE o NON REALE e se viene da Hawk o Bull;
in live gli importi in dollari sono quelli REALI (importo del motore x scala). Nessuna rete: _send e' sostituita."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desk import notifier as n  # noqa: E402


def _capture(fn, *a, **kw):
    """Esegue una notifica e ritorna il testo che sarebbe partito."""
    sent = []
    keep_send, keep_ctx = n._send, dict(n._CTX)
    n._send = sent.append
    try:
        fn(*a, **kw)
    finally:
        n._send = keep_send
        n._CTX.clear()
        n._CTX.update(keep_ctx)
    assert len(sent) == 1
    return sent[0]


def _with(ctx, fn, *a, **kw):
    keep = dict(n._CTX)
    n.set_context(*ctx)
    try:
        return _capture(fn, *a, **kw)
    finally:
        n._CTX.clear()
        n._CTX.update(keep)


def _all_messages():
    return [
        (n.notify_open, ("ETH", 1, 3000.0, 15, 350.0, "medio", 80, "claude", "trend")),
        (n.notify_close, ("ETH", 40.0, "tp", "take profit")),
        (n.notify_dca, ("ETH", 1, 2900.0, 2950.0, 700.0)),
        (n.notify_split, ("ETH", 1, 2900.0, 2950.0, 700.0)),
        (n.notify_halt, ("limite giornaliero",)),
        (n.notify_daily_report, (1100.0, 800.0, 100.0, 2, 3, 80.0, 0.25)),
        (n.notify_live_alert, ("posizione estranea",)),
    ]


def test_without_context_messages_are_as_before():
    keep = dict(n._CTX)
    n._CTX.update(portfolio=None, live=False, scale=1.0)
    try:
        for fn, args in _all_messages():
            text = _capture(fn, *args)
            assert "LIVE</b> ·" not in text and "NON REALE" not in text
    finally:
        n._CTX.clear()
        n._CTX.update(keep)


def test_every_message_starts_with_the_mode_and_the_bot():
    for fn, args in _all_messages():
        paper = _with(("hawk", False, 1.0), fn, *args)
        assert paper.startswith("⚪ <b>NON REALE</b> · 🦅 Hawk\n"), (fn.__name__, paper[:60])
        live = _with(("bull", True, 1.0), fn, *args)
        assert live.startswith("🔴 <b>LIVE</b> · 🐂 Bull\n"), (fn.__name__, live[:60])
        assert "ordini al" not in live                                   # scala 1: nessuna nota


def test_paper_never_scales_amounts_even_if_a_scale_is_given():
    text = _with(("bull", False, 0.5), n.notify_open, "ETH", 1, 3000.0, 15, 350.0, "medio", 80, "claude", "trend")
    assert "Margine: 350$" in text and "ordini al" not in text


def test_live_with_half_scale_shows_real_amounts_and_says_so():
    ctx = ("bull", True, 0.5)
    assert "· ordini al 50%" in _with(ctx, n.notify_halt, "x")
    assert "Margine: 175$" in _with(ctx, n.notify_open, "ETH", 1, 3000.0, 15, 350.0, "medio", 80, "claude", "trend")
    assert "+20.00$" in _with(ctx, n.notify_close, "ETH", 40.0, "tp", "take profit")
    assert "-10.00$" in _with(ctx, n.notify_close, "ETH", -20.0, "sl", "stop loss")
    assert "Margine totale: 350$" in _with(ctx, n.notify_dca, "ETH", 1, 2900.0, 2950.0, 700.0)
    assert "Margine totale: 350$" in _with(ctx, n.notify_split, "ETH", 1, 2900.0, 2950.0, 700.0)
    rep = _with(ctx, n.notify_daily_report, 1100.0, 800.0, 100.0, 2, 3, 80.0, 0.25)
    assert "Equity: 550.00$" in rep and "Cash: 400.00$" in rep and "P&L oggi: +50.00$" in rep and "netto: +40.00$" in rep
    assert "Budget Claude usato: 0.250$" in rep                           # il costo di Claude non si scala
    assert "Posizioni aperte: 2" in rep


def test_scale_one_in_live_leaves_amounts_unchanged():
    text = _with(("hawk", True, 1.0), n.notify_close, "ETH", 40.0, "tp", "take profit")
    assert "+40.00$" in text


def test_bad_scale_falls_back_to_one_and_unknown_bot_still_gets_a_header():
    for bad in (0, -2, "x", None):
        n.set_context("hawk", True, bad)
        assert n._CTX["scale"] == 1.0
    n.set_context("zzz", False, 1.0)
    assert n._header().startswith("⚪ <b>NON REALE</b> · 🤖 Zzz")
    n.set_context("", False, 1.0)
    assert n._header() == ""
    n._CTX.update(portfolio=None, live=False, scale=1.0)
