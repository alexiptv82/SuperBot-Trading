"""Seconda gamba in LIVE: due correzioni nate dal riesame del 20/10/2026 (commit 218aa48 -> correzioni 1 e 2).

Correzione 1 (live_sync.restore_position): se l'exchange rifiuta, si annullano gli effetti CONTABILI
(posizione, cassa, eventi nati dopo l'istantanea) ma NON cio' che il mercato ha mostrato (cursore delle barre,
minimo e massimo toccati). Niente eventi fantasma nel registro e su Telegram.

Correzione 2 (engine.on_bar(exit_first=True), solo LIVE): la seconda gamba parte sull'exchange DOPO la candela,
con un ordine a mercato. Se la stessa candela chiude comunque la posizione (liquidazione, stop o TP della prima
gamba), la gamba non e' mai esistita: non si contabilizza e non parte nessun ordine di aggiunta.
In PAPER (predefinito) il comportamento resta quello di sempre: la gamba si esegue e poi scatta l'uscita.

Il motore e' quello vero (PaperAccount), l'exchange e' finto ma usa il vero ccxt; il ciclo e' quello vero di cli.
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_bitget as fb  # noqa: E402
from fake_bitget import ccxt  # noqa: E402
from desk import cli  # noqa: E402
from desk import live_connector as lc  # noqa: E402
from desk import live_sync as ls  # noqa: E402
from desk.engine import Limits, PaperAccount  # noqa: E402

NOW = 1_800_000_000_000
BAR = 900_000
LIM = Limits(start_equity=1000, max_margin_trade=100, max_margin_total=1000, max_open=10, kill_equity=450,
             daily_stop=0.12)
SPLIT = {"retrace_pct": 0.005, "first_frac": 0.5}


# ── attrezzi ──────────────────────────────────────────────────────────────────────────────────

def world():
    fake = fb.FakeBitget()
    conn = lc.LiveConnector(data_dir=tempfile.mkdtemp(), client=fake, live=True, sleep=lambda s: None)
    return PaperAccount(LIM, "main"), conn, fake, []


def paper_acc(side=1, split=SPLIT, margin=100, price=60000.0):
    acc = PaperAccount(LIM, "main")
    sl = price * 0.97 if side == 1 else price * 1.03
    tp = price * 1.05 if side == 1 else price * 0.95
    pos, msg = acc.open("BTC", side, margin, 10, price, sl, tp, NOW, {"BTC": price}, split=split)
    assert pos, msg
    return acc, pos


def open_live(acc, conn, side=1, split=SPLIT, margin=100, price=60000.0):
    sl = price * 0.97 if side == 1 else price * 1.03
    tp = price * 1.05 if side == 1 else price * 0.95
    pos, msg = acc.open("BTC", side, margin, 10, price, sl, tp, NOW, {"BTC": price}, split=split)
    assert pos, msg
    ok, detail = ls.open_on_exchange(conn, pos, price)
    assert ok, detail
    return pos


def one_leg_reference(side, bar, price=60000.0):
    """Stesso trade con la sola prima gamba (margine 50, nessuna seconda gamba), stessa barra, comportamento di sempre."""
    acc, pos = paper_acc(side=side, split=None, margin=50, price=price)
    return acc.on_bar("BTC", NOW, *bar, BAR)


def bar_for(side, kind, pos):
    """(o, h, l, c) che tocca il livello di uscita `kind` e, nei casi long/short, anche il ritracciamento."""
    if side == 1:
        return {"stop": (60000, 60010, pos.sl - 100, pos.sl - 50),
                "tp": (60000, pos.tp + 100, 59600, pos.tp),
                "liq": (60000, 60010, pos.liq - 1000, pos.liq - 900)}[kind]
    return {"stop": (60000, pos.sl + 100, 59990, pos.sl + 50),
            "tp": (60000, 60400, pos.tp - 100, pos.tp),
            "liq": (60000, pos.liq + 1000, 59990, pos.liq + 900)}[kind]


def kinds(acc):
    return [e["ev"] for e in acc.events]


class CliRig:
    """Il ciclo vero di cli.process_closed_bars con exchange finto, registro eventi vero (in cartella temporanea) e
    notifiche intercettate."""

    def __init__(self, live=True):
        self.acc, self.conn, self.fake, self.alerts = world()
        if not live:
            self.conn = lc.LiveConnector(data_dir=tempfile.mkdtemp(), client=None, live=False, sleep=lambda s: None)
        self.d = tempfile.mkdtemp()
        self.splits, self.closes, self.calls = [], [], []
        self._saved = (cli.LIVE, cli.DATA_DIR, cli.notify_split, cli.notify_close, cli.notify_live_alert,
                       cli.record_close)
        cli.LIVE, cli.DATA_DIR = self.conn, self.d
        cli.notify_split = lambda *a, **k: self.splits.append(a)
        cli.notify_close = lambda *a, **k: self.closes.append(a)
        cli.notify_live_alert = self.alerts.append
        cli.record_close = lambda state, rec: None

    def spy_on_bar(self):
        real = self.acc.on_bar

        def spy(*a, **k):
            self.calls.append(dict(k))
            return real(*a, **k)
        self.acc.on_bar = spy

    def run(self, *bars, t0=NOW):
        rows = [[t0 + i * BAR, *b, 1.0] for i, b in enumerate(bars)]
        cli.process_closed_bars({}, self.acc, {"BTC": rows}, NOW + 99 * BAR)

    def log(self, name):
        p = os.path.join(self.d, "learning_log.jsonl")
        rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()] if os.path.exists(p) else []
        return [r for r in rows if r.get("ev") == name]

    def close(self):
        (cli.LIVE, cli.DATA_DIR, cli.notify_split, cli.notify_close, cli.notify_live_alert,
         cli.record_close) = self._saved


# ═══ CORREZIONE 1: ripristino dopo il rifiuto dell'exchange ═════════════════════════════════════

def test_snapshot_remembers_how_many_events_existed():
    acc, conn, fake, _ = world()
    open_live(acc, conn)
    acc.events.append({"ev": "split_cancel", "id": 99, "symbol": "ETH", "ts": NOW, "reason": "scaduta"})
    snap = ls.snapshot_position(acc, "BTC")
    assert snap[2] == 1 and snap[1] == acc.cash and snap[0] is not acc.positions["BTC"]


def test_rejected_second_leg_leaves_no_phantom_fill_event_and_keeps_the_earlier_ones():
    acc, conn, fake, alerts = world()
    open_live(acc, conn)
    earlier = {"ev": "split_cancel", "id": 99, "symbol": "ETH", "ts": NOW - 1, "reason": "scaduta senza ritracciamento"}
    acc.events.append(earlier)
    before = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 59600, 59650, BAR, exit_first=True)
    assert rec is None and "split_fill" in kinds(acc)                       # il motore ha eseguito la gamba
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    note = ls.after_bar(conn, acc, "BTC", before, rec, alert=alerts.append, now_ms=NOW)
    assert note and "annullata" in note
    assert "split_fill" not in kinds(acc)                                   # l'evento fantasma e' sparito
    assert acc.events[0] == earlier                                         # quello precedente allo snapshot resta
    cancels = [e for e in acc.events[1:] if e["ev"] == "split_cancel"]
    assert len(acc.events) == 2 and len(cancels) == 1                       # solo l'annullamento vero
    assert cancels[0]["reason"].startswith("rifiutata da Bitget")
    assert "DCA eseguito" not in json.dumps(acc.events)


def test_rejected_second_leg_reaches_neither_the_log_nor_telegram():
    """Con il vero flush_events: nessun 'seconda gamba eseguita' nel registro e nessuna notifica."""
    rig = CliRig()
    try:
        open_live(rig.acc, rig.conn)
        rig.fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
        rig.run((60000, 60010, 59600, 59650))
        assert rig.log("split_fill") == [] and rig.splits == []
        cancels = rig.log("split_cancel")
        assert len(cancels) == 1 and cancels[0]["reason"].startswith("rifiutata da Bitget")
        p = rig.acc.positions["BTC"]
        assert p.legs == 1 and p.pending_split is None
    finally:
        rig.close()


def test_accepted_second_leg_still_logs_and_notifies():
    rig = CliRig()
    try:
        open_live(rig.acc, rig.conn)
        rig.run((60000, 60010, 59600, 59650))
        assert len(rig.log("split_fill")) == 1 and len(rig.splits) == 1
        assert rig.log("split_cancel") == []
        assert abs(rig.fake.leg("BTC", 1)["qty"] - rig.acc.positions["BTC"].qty) <= 0.0004
    finally:
        rig.close()


def test_rejected_dca_leaves_no_phantom_split_cancel():
    """Il DCA annulla la gamba pendente ('DCA eseguito'); se Bitget rifiuta il DCA, la gamba torna in attesa e
    l'annullamento non e' mai avvenuto: non deve restare traccia."""
    acc, conn, fake, _ = world()
    pos = open_live(acc, conn)
    pos.trade_type = "medio"
    ps_before = dict(pos.pending_split)
    snap = ls.snapshot_position(acc, "BTC")
    res, msg = acc.add_dca("BTC", 58500.0, None, NOW + BAR, {"BTC": 59000.0}, "test")
    assert res, msg
    assert "split_cancel" in kinds(acc) and acc.positions["BTC"].pending_split is None
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    ok, _ = ls.dca_on_exchange(conn, acc, "BTC", snap, 59000.0)
    assert not ok
    assert acc.events == []                                                 # nessun annullamento fantasma
    assert acc.positions["BTC"].pending_split == ps_before                  # la gamba e' di nuovo in attesa
    assert acc.positions["BTC"].dca_count == 0


def test_restore_keeps_the_extremes_seen_in_the_bar():
    acc, conn, fake, alerts = world()
    open_live(acc, conn)
    p = acc.positions["BTC"]
    lo0, hi0 = p.px_lo, p.px_hi
    before = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60050, 59600, 59650, BAR, exit_first=True)
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    ls.after_bar(conn, acc, "BTC", before, rec, alert=alerts.append, now_ms=NOW)
    p = acc.positions["BTC"]
    assert p.px_lo == 59600 < lo0 and p.px_hi == 60050 > hi0                 # il mercato quei prezzi li ha toccati
    assert p.last_bar_ms == NOW                                             # e il cursore dice: barra gia' giudicata


def test_extremes_kept_after_rejection_feed_mae_in_the_final_record():
    acc, conn, fake, alerts = world()
    open_live(acc, conn)
    before = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 59600, 59650, BAR, exit_first=True)
    fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    ls.after_bar(conn, acc, "BTC", before, rec, alert=alerts.append, now_ms=NOW)
    out = acc.close("BTC", 59800.0, NOW + 2 * BAR, "test")
    entry0 = out["entry"]
    d = entry0 * out["r_dist"]
    assert out["mae_r"] > 0.2 and abs(out["mae_r"] - (entry0 - 59600) / d) < 0.01   # senza gli estremi: 0.0


def test_restore_never_turns_the_untracked_zero_into_a_false_minimum():
    """px_hi/px_lo = 0 vuol dire 'non tracciato' (stati salvati prima): il ripristino non li fa diventare un
    minimo finto a 0 e nemmeno li mescola con valori veri."""
    acc, conn, fake, _ = world()
    open_live(acc, conn)
    p = acc.positions["BTC"]
    p.px_hi = p.px_lo = 0.0                                                  # posizione vecchia, non tracciata
    snap = ls.snapshot_position(acc, "BTC")
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 59600, 59650, BAR, exit_first=True)
    assert rec is None and (acc.positions["BTC"].px_hi, acc.positions["BTC"].px_lo) == (0.0, 0.0)
    ls.restore_position(acc, "BTC", snap)
    p = acc.positions["BTC"]
    assert (p.px_hi, p.px_lo) == (0.0, 0.0) and p.last_bar_ms == NOW
    out = acc.close("BTC", 59900.0, NOW + 2 * BAR, "test")
    assert "mae_r" not in out and "mfe_r" not in out                         # niente MAE/MFE inventati


def test_restore_with_a_valid_snapshot_and_a_sentinel_current_keeps_the_snapshot_extremes():
    acc, conn, fake, _ = world()
    open_live(acc, conn)
    snap = ls.snapshot_position(acc, "BTC")
    hi, lo = snap[0].px_hi, snap[0].px_lo
    acc.positions["BTC"].px_lo = 0.0                                         # stato attuale non tracciato
    ls.restore_position(acc, "BTC", snap)
    p = acc.positions["BTC"]
    assert (p.px_hi, p.px_lo) == (hi, lo) and p.px_lo > 0


def test_restore_accepts_the_old_two_element_snapshot():
    acc, conn, fake, _ = world()
    pos = open_live(acc, conn)
    acc.events.append({"ev": "split_cancel", "id": 1, "symbol": "BTC", "ts": NOW, "reason": "x"})
    import copy
    old = (copy.deepcopy(pos), acc.cash)
    acc.cash -= 5
    ls.restore_position(acc, "BTC", old)
    assert acc.cash == old[1] and len(acc.events) == 1                       # senza lunghezza: gli eventi non si toccano


def test_restore_without_a_snapshot_changes_nothing():
    acc, conn, fake, _ = world()
    open_live(acc, conn)
    acc.events.append({"ev": "x"})
    ls.restore_position(acc, "BTC", None)
    assert len(acc.events) == 1 and "BTC" in acc.positions


# ═══ CORREZIONE 2: uscita prima della seconda gamba (solo LIVE) ═════════════════════════════════

def _check_exit_first(side, kind):
    acc, pos = paper_acc(side=side)
    bar = bar_for(side, kind, pos)
    rec = acc.on_bar("BTC", NOW, *bar, BAR, exit_first=True)
    ref = one_leg_reference(side, bar)
    why = {"stop": "stop loss", "tp": "take profit", "liq": "liquidazione"}[kind]
    assert rec and rec["why"] == why and ref and ref["why"] == why
    assert rec["legs"] == 1 and rec["margin"] == 50                          # una gamba sola
    assert "split_fill" not in kinds(acc)
    cancels = [e for e in acc.events if e["ev"] == "split_cancel"]
    assert len(cancels) == 1 and cancels[0]["reason"] == f"posizione chiusa ({why})"
    for k in ("net", "gross", "fees", "exit", "entry", "close_ms"):
        assert abs(rec[k] - ref[k]) < 1e-9, (k, rec[k], ref[k])            # esattamente il risultato della prima gamba
    assert "BTC" not in acc.positions


def test_exit_first_long_stop():
    _check_exit_first(1, "stop")


def test_exit_first_long_take_profit():
    _check_exit_first(1, "tp")


def test_exit_first_long_liquidation():
    _check_exit_first(1, "liq")


def test_exit_first_short_stop():
    _check_exit_first(-1, "stop")


def test_exit_first_short_take_profit():
    _check_exit_first(-1, "tp")


def test_exit_first_short_liquidation():
    _check_exit_first(-1, "liq")


def test_paper_default_is_unchanged_two_legs_then_exit():
    """Senza exit_first (paper) la gamba si esegue e poi scatta l'uscita: come prima di questa correzione."""
    for side in (1, -1):
        for kind in ("stop", "tp", "liq"):
            acc, pos = paper_acc(side=side)
            bar = bar_for(side, kind, pos)
            rec = acc.on_bar("BTC", NOW, *bar, BAR)
            assert rec["legs"] == 2 and rec["margin"] == 100, (side, kind)
            assert kinds(acc)[0] == "split_fill"
            assert abs(rec["net"] - one_leg_reference(side, bar)["net"]) > 1e-6
            acc2, pos2 = paper_acc(side=side)
            rec2 = acc2.on_bar("BTC", NOW, *bar, BAR, exit_first=False)       # esplicito == predefinito
            assert rec2 == rec and acc2.events == acc.events


def test_paper_stop_with_second_leg_matches_the_numbers_of_the_review():
    """Lo scenario del riesame (long 60000, 100$ x10, trigger 59700, stop 58200): due gambe in paper."""
    acc, pos = paper_acc(side=1)
    rec = acc.on_bar("BTC", NOW, 60000, 60010, 57400, 57500, BAR)
    assert abs(rec["net"] - (-29.1381)) < 0.01
    acc2, pos2 = paper_acc(side=1)
    rec2 = acc2.on_bar("BTC", NOW, 60000, 60010, 57400, 57500, BAR, exit_first=True)
    assert abs(rec2["net"] - (-15.7864)) < 0.01 and rec2["legs"] == 1


def test_exit_first_changes_nothing_unless_exit_and_trigger_are_in_the_same_bar():
    """Proprieta' su barre casuali: due conti identici, uno con exit_first e uno senza, restano identici in tutto
    (stato, record, eventi) tranne quando la barra tocca insieme ritracciamento e uscita."""
    rnd = random.Random(20261020)
    differed = same_touched = 0
    for _ in range(400):
        side = rnd.choice((1, -1))
        a, pa = paper_acc(side=side)
        b, pb = paper_acc(side=side)
        c = 60000 * (1 + rnd.uniform(-0.04, 0.04))
        hi = max(60000, c) * (1 + rnd.uniform(0, 0.03))
        lo = min(60000, c) * (1 - rnd.uniform(0, 0.03))
        bar = (60000, hi, lo, c)
        trig = pa.pending_split["trigger"]
        trig_touched = (lo <= trig) if side == 1 else (hi >= trig)
        exit_touched = PaperAccount._exit_touched(pa, hi, lo)
        ra = a.on_bar("BTC", NOW, *bar, BAR)
        rb = b.on_bar("BTC", NOW, *bar, BAR, exit_first=True)
        if trig_touched and exit_touched:
            same_touched += 1
            assert ra is not None and rb is not None and ra["legs"] == 2 and rb["legs"] == 1
            differed += 1
        else:
            assert ra == rb and a.to_dict() == b.to_dict() and a.events == b.events
    assert differed == same_touched and same_touched > 10                      # il caso raro esiste davvero nel campione


def test_exit_touched_is_exactly_the_condition_under_which_on_bar_closes():
    """`_exit_touched` deve coincidere, per qualunque combinazione di livelli, con le condizioni con cui on_bar
    chiude una posizione senza seconda gamba (anche stop oltre la liquidazione o TP assente: stati rari ma possibili)."""
    import copy
    rnd = random.Random(7)
    hits = 0
    for _ in range(800):
        side = rnd.choice((1, -1))
        acc, pos = paper_acc(side=side, split=None)
        pos.liq = 60000 * (1 - side * rnd.uniform(0.02, 0.12))
        pos.sl = 60000 * (1 - side * rnd.uniform(0.01, 0.12))
        pos.tp = None if rnd.random() < 0.2 else 60000 * (1 + side * rnd.uniform(0.005, 0.1))
        lo = 60000 * (1 - rnd.uniform(0, 0.14))
        hi = 60000 * (1 + rnd.uniform(0, 0.14))
        touched = PaperAccount._exit_touched(pos, hi, lo)
        rec = copy.deepcopy(acc).on_bar("BTC", NOW, 60000, hi, lo, 60000, BAR)
        assert touched == (rec is not None), (side, pos.liq, pos.sl, pos.tp, hi, lo)
        hits += touched
    assert 100 < hits < 700                                                 # il campione contiene entrambi i casi


def test_exit_first_still_fills_the_second_leg_when_no_exit_is_touched():
    for side in (1, -1):
        acc, pos = paper_acc(side=side)
        bar = (60000, 60010, 59600, 59650) if side == 1 else (60000, 60400, 59990, 60350)
        assert acc.on_bar("BTC", NOW, *bar, BAR, exit_first=True) is None
        assert acc.positions["BTC"].legs == 2 and kinds(acc) == ["split_fill"]


def test_exit_first_uses_the_first_leg_liquidation_window():
    """Il minimo e' sotto la liquidazione della prima gamba ma sopra quella (piu' bassa) a due gambe. In paper la
    gamba entra, la liquidazione si abbassa e scatta lo stop; in LIVE la gamba non esiste e vale la liquidazione."""
    acc, pos = paper_acc(side=1)
    liq1 = pos.liq
    low = liq1 - 20                                                         # sotto liq1, sopra liq2
    bar = (60000, 60010, low, low + 10)
    paper, p2 = paper_acc(side=1)
    r_paper = paper.on_bar("BTC", NOW, *bar, BAR)
    assert r_paper["legs"] == 2 and r_paper["why"] == "stop loss"            # la liquidazione a due gambe e' piu' bassa
    r_live = acc.on_bar("BTC", NOW, *bar, BAR, exit_first=True)
    assert r_live["why"] == "liquidazione" and r_live["legs"] == 1
    assert abs(r_live["net"] - (-50 - 50 * 10 * LIM.fee_bp_side / 1e4)) < 1e-6   # margine della prima gamba + commissione


def test_exit_first_boundary_levels_count_as_touched():
    """Uguaglianza: il motore considera toccato un livello quando low <= sl (high >= sl per gli short)."""
    acc, pos = paper_acc(side=1)
    r = acc.on_bar("BTC", NOW, 60000, 60010, pos.sl, pos.sl + 10, BAR, exit_first=True)
    assert r and r["why"] == "stop loss" and r["legs"] == 1
    acc, pos = paper_acc(side=1)
    r = acc.on_bar("BTC", NOW, 60000, pos.tp, 59600, 59900, BAR, exit_first=True)
    assert r and r["why"] == "take profit" and r["legs"] == 1
    acc, pos = paper_acc(side=-1)
    r = acc.on_bar("BTC", NOW, 60000, pos.sl, 59990, 60100, BAR, exit_first=True)
    assert r and r["why"] == "stop loss" and r["legs"] == 1
    acc, pos = paper_acc(side=-1)
    r = acc.on_bar("BTC", NOW, 60000, 60400, pos.tp, 60100, BAR, exit_first=True)
    assert r and r["why"] == "take profit" and r["legs"] == 1
    acc, pos = paper_acc(side=1)                        # un tick sopra lo stop: non e' toccato, la gamba entra
    r = acc.on_bar("BTC", NOW, 60000, 60010, pos.sl + 0.01, 59900, BAR, exit_first=True)
    assert r is None and acc.positions["BTC"].legs == 2


def test_exit_first_without_take_profit_only_looks_at_stop_and_liquidation():
    acc, pos = paper_acc(side=1)
    acc.positions["BTC"].tp = None
    assert acc.on_bar("BTC", NOW, 60000, 90000, 59600, 80000, BAR, exit_first=True) is None
    assert acc.positions["BTC"].legs == 2


def test_exit_first_does_not_hide_a_legitimate_expiry_or_missing_margin():
    # scadenza: l'evento legittimo resta, nessuna gamba, nessuna uscita
    acc, pos = paper_acc(side=1)
    t = pos.pending_split["expire_ms"]
    assert acc.on_bar("BTC", t, 60000, 60010, 59600, 59650, BAR, exit_first=True) is None
    assert [e["reason"] for e in acc.events] == ["scaduta senza ritracciamento"] and acc.positions["BTC"].legs == 1
    # margine non disponibile: l'evento legittimo resta
    acc, pos = paper_acc(side=1)
    acc.cash = 1.0
    assert acc.on_bar("BTC", NOW, 60000, 60010, 59600, 59650, BAR, exit_first=True) is None
    assert [e["reason"] for e in acc.events] == ["margine non disponibile"] and acc.positions["BTC"].legs == 1


def test_expiry_and_missing_margin_events_survive_the_live_cycle():
    rig = CliRig()
    try:
        pos = open_live(rig.acc, rig.conn)
        rig.run((60000, 60010, 59600, 59650), t0=pos.pending_split["expire_ms"])      # barra oltre la scadenza
        reasons = [e["reason"] for e in rig.log("split_cancel")]
        assert reasons == ["scaduta senza ritracciamento"] and rig.splits == [] and rig.log("split_fill") == []
        assert rig.fake.count("create_order") == 1                                    # solo l'apertura
    finally:
        rig.close()
    rig = CliRig()
    try:
        open_live(rig.acc, rig.conn)
        rig.acc.cash = 1.0
        n = rig.fake.count("create_order")
        rig.run((60000, 60010, 59600, 59650))
        assert [e["reason"] for e in rig.log("split_cancel")] == ["margine non disponibile"]
        assert rig.log("split_fill") == [] and rig.fake.count("create_order") == n    # niente ordine di aggiunta
    finally:
        rig.close()


# ── il ciclo vero: nessun ordine di seconda gamba, chiusura rifiutata, flag passato correttamente ──

def _cycle_stop_with_trigger(side, kind, fail_close=False):
    rig = CliRig()
    pos = open_live(rig.acc, rig.conn, side=side)
    n0 = rig.fake.count("create_order")
    q1 = rig.fake.leg("BTC", side)["qty"]
    bar = bar_for(side, kind, pos)
    if fail_close:
        rig.fake.errors["create_order"] = [ccxt.ExchangeError("rifiutato")]
    rig.run(bar)
    return rig, n0, q1


def test_live_cycle_stop_in_the_trigger_candle_sends_no_second_leg_order():
    for side in (1, -1):
        for kind in ("stop", "tp"):
            rig, n0, q1 = _cycle_stop_with_trigger(side, kind)
            try:
                assert rig.fake.count("create_order") == n0 + 1                        # una sola chiamata: la chiusura
                last = rig.fake.orders[-1]
                assert str(last.get("reduceOnly")).lower() in ("true", "yes", "1")     # ed e' di sola chiusura
                assert rig.fake.legs == {} and "BTC" not in rig.acc.positions
                assert rig.log("split_fill") == [] and rig.splits == []
                assert rig.log("split_cancel")[0]["reason"].startswith("posizione chiusa")
                assert rig.acc.closed == [] or rig.acc.closed[-1]["legs"] == 1
            finally:
                rig.close()


def test_live_cycle_rejected_close_stays_in_pending_close_with_a_single_leg():
    for side in (1, -1):
        rig, n0, q1 = _cycle_stop_with_trigger(side, "stop", fail_close=True)
        try:
            assert rig.conn.pending_close == {"BTC": side}                          # da ritentare al giro dopo
            assert rig.fake.leg("BTC", side)["qty"] == q1                           # sull'exchange c'e' ancora la prima gamba
            assert rig.fake.count("create_order") == n0 + 1                         # mai un ordine di aggiunta
            assert rig.acc.closed[-1]["legs"] == 1 and rig.alerts
            res = ls.sync(rig.conn, rig.acc, {"BTC": 57600.0}, NOW + 3 * BAR, alert=rig.alerts.append)
            assert rig.fake.legs == {} and rig.conn.pending_close == {} and res["interlock"] is None
        finally:
            rig.close()


def test_live_cycle_passes_exit_first_only_when_live():
    rig = CliRig(live=True)
    try:
        open_live(rig.acc, rig.conn)
        rig.spy_on_bar()
        rig.run((60000, 60010, 59900, 59950))
        assert rig.calls and all(c.get("exit_first") is True for c in rig.calls)
    finally:
        rig.close()
    rig = CliRig(live=False)
    try:
        acc, pos = paper_acc(side=1)
        rig.acc = acc
        rig.spy_on_bar()
        rig.run((60000, 60010, 59900, 59950))
        assert rig.calls and all(c.get("exit_first") is False for c in rig.calls)
    finally:
        rig.close()


def test_paper_cycle_still_books_both_legs_when_the_candle_has_stop_and_trigger():
    rig = CliRig(live=False)
    try:
        acc, pos = paper_acc(side=1)
        rig.acc = acc
        rig.run(bar_for(1, "stop", pos))
        assert rig.acc.closed[-1]["legs"] == 2 and len(rig.log("split_fill")) == 1
        assert rig.fake.count("create_order") == 0
    finally:
        rig.close()
