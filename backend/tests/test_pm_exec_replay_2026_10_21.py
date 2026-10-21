"""Collaudo del replay eseguibile della gestione del profitto (deploy/scripts/pm_exec_replay.py).

L'oracolo e' il motore vero (PaperAccount): lo stesso trade, con la stessa regola applicata muovendo lo stop, deve
dare lo stesso netto del replay; e una regola non puo' mai uscire dopo (o nella barra di) l'uscita vera."""
import importlib.util
import json
import os
import random
import urllib.error

import pytest

from desk.engine import Limits, PaperAccount

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("pm_exec_replay", os.path.join(ROOT, "deploy", "scripts", "pm_exec_replay.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

B = R.BAR_MS
T0 = 1_760_000_000_000 // B * B


def bars_from(closes, spread=0.0005, start=T0):
    """Barre contigue: apertura = chiusura precedente, estremi +/- spread."""
    out, prev = [], closes[0]
    for k, c in enumerate(closes):
        o = prev
        out.append([start + k * B, o, max(o, c) * (1 + spread), min(o, c) * (1 - spread), c])
        prev = c
    return out


def trade_dict(side=1, entry=100.0, margin=100.0, lev=10, r_dist=0.01, open_ms=T0 + 3 * B + 60_000, close_ms=T0 + 10 * B,
               why="chiusura decisa", mfe_r=0.0, net=0.0):
    return {"bot": "hawk", "run": 1, "id": 1, "symbol": "BTCUSDT", "side": side, "margin": margin, "lev": float(lev),
            "entry": entry, "exit": entry, "open_ms": open_ms, "close_ms": close_ms, "net": net, "fees": 0.0, "funding": 0.0,
            "why": why, "mfe_r": mfe_r, "r_dist": r_dist, "qty": margin * lev / entry, "recon_err": 0.0}


# ------------------------------------------------------------------ formule dei costi = motore

@pytest.mark.parametrize("side", [1, -1])
def test_exit_net_matches_engine_close(side):
    acc = PaperAccount(Limits())
    price = 100.0
    sl = price * (1 - side * 0.01)
    pos, msg = acc.open("BTCUSDT", side, 100.0, 10, price, sl, None, T0, {})
    assert pos is not None, msg
    rec = acc.close("BTCUSDT", 103.0, T0 + 5 * 3_600_000, "chiusura decisa")
    path = None
    # registro -> load_trades -> exit_net con lo stesso prezzo di riferimento
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "learning_log.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"ev": "close", "run_no": 3, **rec}) + "\n")
        trades, skipped = R.load_trades(path, "hawk")
    assert len(trades) == 1 and not skipped
    t = trades[0]
    assert t["recon_err"] < 0.01                                  # le formule tornano al centesimo
    assert R.exit_net(t, 103.0, rec["close_ms"]) == pytest.approx(rec["net"], abs=1e-3)


def test_load_trades_filters_and_keys_by_run_and_id(tmp_path):
    acc = PaperAccount(Limits())
    rows = []

    def one(run, tid_forced=None, partial=False, dca=0, legs=1, why="stop loss"):
        a = PaperAccount(Limits())
        p, _ = a.open("ETHUSDT", 1, 100.0, 10, 100.0, 99.0, None, T0, {})
        rec = a.close("ETHUSDT", 101.0, T0 + B, why)
        rec.update({"id": tid_forced or rec["id"], "dca_count": dca, "legs": legs})
        if partial:
            rec["partial"] = True
        rows.append({"ev": "close", "run_no": run, **rec})

    one(1, 1)                       # run 1, id 1: pulito
    one(2, 1)                       # run 2, id 1: stesso id ma altra run -> trade diverso e pulito
    one(1, 2, partial=True)         # parziale: scartato
    one(1, 3, dca=1)                # DCA: scartato
    one(1, 4, legs=2)               # due gambe: scartato
    one(1, 5, why="liquidazione")   # liquidazione: scartata
    rows.append({"ev": "open", "id": 9})
    rows.append({"ev": "close", "run_no": 1, "id": 6, "symbol": "X"})            # campi mancanti
    p = tmp_path / "l.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnon json\n")
    clean, skipped = R.load_trades(str(p), "bull")
    assert sorted((t["run"], t["id"]) for t in clean) == [(1, 1), (2, 1)]
    assert skipped["con parziali"] == 1 and skipped["dca o due gambe"] == 2 and skipped["liquidazione"] == 1
    assert skipped["campi mancanti"] == 1


# ------------------------------------------------------------------ candele

def _resp(rows):
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"code": "00000", "data": rows}).encode()
    return Resp()


def test_fetch_bars_windows_dedupe_429_and_open_bar_dropped():
    calls, sleeps = [], []
    n = 400
    allrows = [[str(T0 + k * B), "1", "2", "0.5", "1.5", "10", "10"] for k in range(n)]

    def opener(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else req
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 429, "slow", {}, None)
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        lo, hi = int(q["startTime"]), int(q["endTime"])
        return _resp([r for r in allrows[::-1] if lo <= int(r[0]) <= hi])

    now = T0 + 390 * B + 1000                                      # la barra 390 e' ancora aperta alle "ora"
    bars = R.fetch_bars("btc", T0, T0 + 399 * B, now_ms=now, opener=opener, sleep=sleeps.append)
    assert "BTCUSDT" in calls[0]
    assert len(calls) >= 3                                         # 429 + almeno due finestre da 190 barre
    assert sleeps[0] == 2.0
    assert [b[0] for b in bars] == [T0 + k * B for k in range(390)]   # ordinate, senza doppioni, senza barra in corso
    assert R.regular(bars)


def test_fetch_bars_rejects_error_payload():
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"code": "40001", "msg": "x"}).encode()
    with pytest.raises(ValueError):
        R.fetch_bars("BTC", T0, T0 + B, now_ms=T0 + 10 * B, opener=lambda r, timeout=0: Resp(), sleep=lambda s: None)


# ------------------------------------------------------------------ tempo: mai dopo l'uscita vera

def test_decision_limit_bar_exit_excludes_exit_bar():
    t = trade_dict(why="stop loss", close_ms=T0 + 10 * B)
    assert R.decision_limit_ms(t) == T0 + 9 * B                   # la barra d'uscita inizia a 9B
    t = trade_dict(why="chiusura decisa", close_ms=T0 + 10 * B + 5 * 60_000)
    assert R.decision_limit_ms(t) == t["close_ms"]


@pytest.mark.parametrize("why", ["stop loss", "take profit", "chiusura decisa"])
def test_rules_never_exit_after_real_exit(why):
    # prezzo che sale a +4% e poi crolla: ogni regola vorrebbe uscire, ma l'uscita vera e' alla barra 12
    closes = [100 + 0.4 * k for k in range(11)] + [96, 90, 85, 80, 80, 80, 80, 80, 80]
    bars = bars_from(closes)
    close_ms = T0 + 12 * B + (0 if why != "chiusura decisa" else 7 * 60_000)
    t = trade_dict(why=why, close_ms=close_ms, open_ms=T0 + 1 * B + 60_000, entry=100.0, r_dist=0.01)
    for arm, give in ((0.75, 0), (1.0, 0.75), (2.0, 1.5)):
        res = R.run_stop_rule(t, bars, arm, give)
        if res is not None:
            assert res[1] <= t["close_ms"]
    from desk.profit.policy_hawk import research_policy
    from desk.profit_sidecar.roi_variants import RoiPolicy
    for res in (R.run_machine(t, bars, research_policy(), None), R.run_roi(t, bars, RoiPolicy(), None, True)):
        if res is not None:
            assert res[1] <= R.decision_limit_ms(t) + 0   # uscita a un'apertura di barra, mai oltre il limite
            assert res[1] % B == 0


# ------------------------------------------------------------------ pavimenti: confronto con il motore

def engine_run(side, bars, arm_r, give_r, open_i, lev=10, margin=100.0, sl_pct=0.012):
    """Stessa regola applicata al motore vero muovendo lo stop. Ritorna (record chiusura, floor_presente_all_uscita)."""
    acc = PaperAccount(Limits())
    o_ms = bars[open_i][0] + 60_000
    px = bars[open_i][4]
    pos, msg = acc.open("BTCUSDT", side, margin, lev, px, px * (1 - side * sl_pct), None, o_ms, {})
    assert pos is not None, msg
    entry, rd = pos.entry, pos.entry * pos.r_dist
    cost = entry * (2 * R.FEE_BP + 2 * R.SLIP_BP) / 1e4
    be = entry + side * cost
    best, floor = None, None
    for k in range(open_i, len(bars)):
        ts, o, h, l, c = bars[k]
        rec = acc.on_bar("BTCUSDT", ts, o, h, l, c, B)
        if rec is not None:
            return rec, floor is not None
        if k == open_i:
            continue                                               # barra d'ingresso: non conta per il massimo
        best = h if best is None and side == 1 else (l if best is None else (max(best, h) if side == 1 else min(best, l)))
        if side * (best - entry) / rd >= arm_r:
            cand = be
            if give_r:
                cand = max(be, best - give_r * rd) if side == 1 else min(be, best + give_r * rd)
            floor = cand if floor is None else (max(floor, cand) if side == 1 else min(floor, cand))
            pos = acc.positions["BTCUSDT"]
            pos.sl = max(pos.sl, floor) if side == 1 else min(pos.sl, floor)
    return None, floor is not None


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("side", [1, -1])
def test_stop_rule_matches_engine_with_moved_stop(seed, side):
    rnd = random.Random(seed * 7 + (3 if side == 1 else 5))
    px, closes = 100.0, [100.0]
    drift = rnd.choice([-0.0006, 0.0, 0.0008, 0.0015])
    for _ in range(80):
        px *= 1 + drift + rnd.gauss(0, 0.0035)
        closes.append(px)
    bars = bars_from(closes, spread=0.0008)
    open_i = 4
    for arm, give in ((1.0, 0), (1.5, 1.0), (0.75, 0.75)):
        rec, had_floor = engine_run(side, bars, arm, give, open_i)
        t = trade_dict(side=side, entry=bars[open_i][4] * (1 + side * R.SLIP_BP / 1e4), margin=100.0, lev=10,
                       r_dist=0.012, open_ms=bars[open_i][0] + 60_000, close_ms=T0 + 10_000 * B, why="chiusura decisa")
        t["qty"] = t["margin"] * t["lev"] / t["entry"]
        # r_dist del motore = distanza reale con lo slippage
        acc = PaperAccount(Limits())
        p, _ = acc.open("BTCUSDT", side, 100.0, 10, bars[open_i][4], bars[open_i][4] * (1 - side * 0.012), None, 0, {})
        t["r_dist"] = p.r_dist
        if rec is not None and not had_floor:
            # il motore esce sullo stop iniziale prima che la regola abbia alzato qualcosa: quella e' l'uscita VERA
            # e il replay, che la conosce (close_ms, why), non deve inventare un'uscita
            t["close_ms"], t["why"] = rec["close_ms"], rec["why"]
        res = R.run_stop_rule(t, bars, arm, give)
        if rec is None or not had_floor:
            assert res is None
        else:
            assert res is not None
            assert res[0] == pytest.approx(rec["net"], abs=1e-3)
            assert res[1] == rec["close_ms"]


# ------------------------------------------------------------------ macchina e ROI di ChatGPT con uscita alla barra dopo

def rise_then_fall():
    # lungo: sale con piccole oscillazioni fino a +6%, poi inverte con continuita'
    closes = [100.0]
    for k in range(1, 40):
        closes.append(closes[-1] * (1 + 0.0035 + (0.0006 if k % 2 else -0.0006)))
    for k in range(40, 70):
        closes.append(closes[-1] * (1 - 0.004 - (0.0005 if k % 2 else 0)))
    return bars_from(closes, spread=0.0006)


def test_machine_and_roi_exit_at_next_bar_open_with_engine_costs():
    from desk.profit.policy_hawk import research_policy
    from desk.profit_sidecar.roi_variants import RoiPolicy
    bars = rise_then_fall()
    t = trade_dict(side=1, entry=100.0, margin=100.0, lev=10, r_dist=0.01, open_ms=T0 + 2 * B + 60_000,
                   close_ms=bars[-1][0] + B, why="chiusura decisa")
    for res in (R.run_machine(t, bars, research_policy(), None), R.run_roi(t, bars, RoiPolicy(), None, False),
                R.run_roi(t, bars, RoiPolicy(), None, True)):
        assert res is not None
        net, ts, why = res
        k = [b[0] for b in bars].index(ts)
        assert why == "mercato" and k >= 1
        assert net == pytest.approx(R.exit_net(t, bars[k][1], ts))
        assert net > 0                                              # ha protetto un utile prima del crollo


def test_roi_target_exits_before_floor_and_phase_filters_decisions():
    from desk.profit_sidecar.roi_variants import RoiPolicy
    bars = rise_then_fall()
    t = trade_dict(side=1, entry=100.0, margin=100.0, lev=10, r_dist=0.01, open_ms=T0 + 2 * B + 60_000,
                   close_ms=bars[-1][0] + B)
    b_ = R.run_roi(t, bars, RoiPolicy(), None, True)
    a_ = R.run_roi(t, bars, RoiPolicy(), None, False)
    assert b_[1] <= a_[1]                                           # B ha in piu' il bersaglio: non esce dopo A
    for ph in (0, 1):
        res = R.run_roi(t, bars, RoiPolicy(), ph, True)
        assert res is not None
        # l'uscita avviene all'apertura della barra successiva a una barra di decisione della fase scelta
        assert (res[1] // B) % 2 == ph


def test_no_trigger_when_trade_never_in_profit():
    from desk.profit.policy_hawk import research_policy
    from desk.profit_sidecar.roi_variants import RoiPolicy
    closes = [100.0 - 0.15 * k for k in range(30)]
    bars = bars_from(closes)
    t = trade_dict(side=1, close_ms=bars[-1][0] + B, open_ms=T0 + 2 * B + 60_000)
    assert R.run_machine(t, bars, research_policy(), None) is None
    assert R.run_roi(t, bars, RoiPolicy(), None, True) is None
    assert R.run_stop_rule(t, bars, 1.0, 0) is None


def test_summary_counts_and_tolerates_runner_errors():
    t1 = trade_dict(net=-20.0, mfe_r=1.5)
    t2 = trade_dict(net=30.0)
    bars = {id(t1): [1], id(t2): [1]}

    def runner(t, b):
        if t is t1:
            return (5.0, 1, "mercato")                             # perdita girata in utile
        return (12.0, 1, "mercato")                                # vincente tagliato
    rows, errs = R.evaluate_policy([t1, t2], bars, runner)
    s = R.summarize(rows, errs)
    assert "n=2" in s and "meglio 1 (+25$)" in s and "peggio 1 (-18$; di cui 1 erano vincenti)" in s
    assert "persi dopo +1R: 1, girati in utile 1" in s

    def boom(t, b):
        raise ValueError("barra non valida")
    rows, errs = R.evaluate_policy([t1, t2], bars, boom)
    assert rows == [] and errs == 2 and "errori 2" in R.summarize(rows, errs)


# ------------------------------------------------------------------ casi limite dei pavimenti

def _flat_bars(n, price=100.0, start=T0):
    return [[start + k * B, price, price * 1.0004, price * 0.9996, price] for k in range(n)]


def test_entry_bar_pre_entry_high_does_not_arm_floor():
    bars = _flat_bars(30)
    k = 3
    bars[k][2] = 105.0                                            # massimo +5% nella barra d'ingresso, prima dell'ingresso
    t = trade_dict(side=1, entry=100.0, r_dist=0.01, open_ms=bars[k][0] + 14 * 60_000, close_ms=bars[-1][0] + B,
                   why="chiusura decisa")
    assert R.run_stop_rule(t, bars, 1.0, 0) is None               # nessun pavimento: il prezzo non si e' mai mosso dopo


def test_floor_fill_gaps_to_open_when_bar_opens_beyond_level():
    bars = _flat_bars(12)
    bars[4] = [bars[4][0], 100.0, 102.0, 100.0, 102.0]            # sale a +2% (2R): arma il pavimento al pareggio
    bars[5] = [bars[5][0], 102.0, 102.5, 101.5, 102.0]            # resta sopra il pavimento
    bars[6] = [bars[6][0], 98.0, 98.5, 97.5, 98.0]                # gap in apertura sotto il pavimento
    for k in range(7, 12):
        bars[k] = [bars[k][0], 98.0, 98.2, 97.8, 98.0]
    t = trade_dict(side=1, entry=100.0, r_dist=0.01, open_ms=bars[2][0] + 60_000, close_ms=bars[-1][0] + B,
                   why="chiusura decisa")
    net, ts, why = R.run_stop_rule(t, bars, 1.0, 0)
    assert why == "pavimento" and ts == bars[6][0] + B
    assert net == pytest.approx(R.exit_net(t, 98.0, ts))          # all'apertura (98), non al livello del pavimento (~100.1)
    short = trade_dict(side=-1, entry=100.0, r_dist=0.01, open_ms=bars[2][0] + 60_000, close_ms=bars[-1][0] + B,
                       why="chiusura decisa")
    mirror = [[b[0], 10000 / b[1], 10000 / b[3], 10000 / b[2], 10000 / b[4]] for b in bars]
    res = R.run_stop_rule(short, mirror, 1.0, 0)
    assert res is not None and res[2] == "pavimento"


def test_real_stop_loss_exit_bar_is_included_for_floor_rules():
    bars = _flat_bars(14)
    bars[4] = [bars[4][0], 100.0, 102.0, 100.0, 102.0]            # arma il pavimento (pareggio)
    for k in (5, 6, 7):                                           # resta sopra il pavimento fino al crollo
        bars[k] = [bars[k][0], 102.0, 102.5, 101.5, 102.0]
    j = 8
    bars[j] = [bars[j][0], 101.0, 101.0, 97.0, 97.5]              # crolla attraverso il pavimento e lo stop iniziale (99)
    t = trade_dict(side=1, entry=100.0, r_dist=0.01, open_ms=bars[2][0] + 60_000, close_ms=bars[j][0] + B,
                   why="stop loss")
    res = R.run_stop_rule(t, bars, 1.0, 0)
    assert res is not None and res[1] == bars[j][0] + B           # il pavimento, piu' vicino dello stop, scatta nella stessa barra
    assert res[0] > R.exit_net(t, 99.0, t["close_ms"])            # e salva piu' dello stop iniziale


# ------------------------------------------------------------------ parziale a +N R: confronto con il motore

def _path(seed, side):
    rnd = random.Random(seed * 11 + (1 if side == 1 else 2))
    px, closes = 100.0, [100.0]
    drift = rnd.choice([0.0, 0.0008, 0.0015, -0.0004])
    for _ in range(60):
        px *= 1 + drift + rnd.gauss(0, 0.0035)
        closes.append(px)
    closes += [closes[-1] * (1 - side * 0.03)] * 3             # chiude con un crollo: l'uscita "vera" c'e' sempre
    return bars_from(closes, spread=0.0008)


def _engine_unmanaged(side, bars, open_i):
    acc = PaperAccount(Limits())
    px = bars[open_i][4]
    pos, _ = acc.open("BTCUSDT", side, 100.0, 10, px, px * (1 - side * 0.012), None, bars[open_i][0] + 60_000, {})
    for k in range(open_i, len(bars)):
        rec = acc.on_bar("BTCUSDT", *bars[k], B)
        if rec:
            return rec
    return None


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("be_rest", [False, True])
def test_partial_matches_engine_partial_close(seed, side, be_rest):
    bars, open_i, level_r, frac = _path(seed, side), 4, 1.0, 0.5
    rec0 = _engine_unmanaged(side, bars, open_i)
    if rec0 is None:
        pytest.skip("nessuna uscita")
    # il trade "vero" e' quello senza gestione
    t = trade_dict(side=side, entry=rec0["entry"], margin=rec0["margin"], lev=rec0["leverage"], r_dist=rec0["r_dist"],
                   open_ms=rec0["open_ms"], close_ms=rec0["close_ms"], why=rec0["why"], net=rec0["net"])
    t["qty"] = t["margin"] * t["lev"] / t["entry"]
    limit = R.decision_limit_ms(t)
    # stesso trade gestito nel motore: parziale a +level_r R poi (opzionale) stop a pareggio+costi sul resto
    acc = PaperAccount(Limits())
    px = bars[open_i][4]
    pos, _ = acc.open("BTCUSDT", side, 100.0, 10, px, px * (1 - side * 0.012), None, bars[open_i][0] + 60_000, {})
    level = pos.entry + side * level_r * pos.entry * pos.r_dist
    be = pos.entry + side * pos.entry * (2 * R.FEE_BP + 2 * R.SLIP_BP) / 1e4
    part = None
    total = None
    for k in range(open_i, len(bars)):
        ts, o, h, l, c = bars[k]
        end = ts + B
        rec = acc.on_bar("BTCUSDT", ts, o, h, l, c, B)
        if rec is not None:
            total = rec["net"] + (part["net"] if part else 0.0)
            break
        if part is None and k > open_i and end <= limit and ((h >= level) if side == 1 else (l <= level)):
            part = acc.partial_close("BTCUSDT", level, end, frac)
            if be_rest:
                p = acc.positions["BTCUSDT"]
                p.sl = max(p.sl, be) if side == 1 else min(p.sl, be)
    res = R.run_partial(t, bars, level_r, frac, be_rest)
    if part is None:
        assert res is None
    else:
        assert res is not None
        assert res[0] == pytest.approx(total, abs=2e-3)
        assert res[1] == part["close_ms"]


def test_partial_never_triggers_in_or_after_real_exit_bar_and_skips_entry_bar():
    bars = _flat_bars(14)
    bars[3][2] = 105.0                                            # barra d'ingresso con massimo +5% precedente
    j = 9
    bars[j] = [bars[j][0], 100.0, 103.0, 99.0, 99.0]              # la barra d'uscita (stop) tocca anche +1R
    t = trade_dict(side=1, entry=100.0, r_dist=0.01, open_ms=bars[3][0] + 14 * 60_000, close_ms=bars[j][0] + B,
                   why="stop loss", net=-12.0)
    assert R.run_partial(t, bars, 1.0, 0.5, True) is None


def test_partial_breakeven_floor_applies_from_the_next_bar_only():
    bars = _flat_bars(16)
    m = 5
    bars[m] = [bars[m][0], 100.0, 101.5, 99.8, 101.0]             # tocca +1R (101) e scende sotto il pareggio nella STESSA barra
    for k in range(6, 12):
        bars[k] = [bars[k][0], 101.0, 101.3, 100.8, 101.0]        # poi resta sopra il pareggio
    j = 12
    bars[j] = [bars[j][0], 101.0, 101.0, 98.0, 98.5]              # l'uscita vera (stop) crolla
    t = trade_dict(side=1, entry=100.0, r_dist=0.01, open_ms=bars[2][0] + 60_000, close_ms=bars[j][0] + B,
                   why="stop loss", net=-15.0)
    net, ts, why = R.run_partial(t, bars, 1.0, 0.5, True)
    assert ts == bars[m][0] + B                                   # il parziale e' nella barra m
    assert why == "parziale+pareggio"
    assert bars[j][0] + B == ts + (j - m) * B                     # il pareggio colpisce solo alla barra del crollo (j), non in m
    # con pareggio sul resto: il resto esce alla barra j al pareggio+costi, non nella barra m
    part = R._scaled(t, 0.5)
    rest = R._scaled(t, 0.5)
    be = 100.0 + 100.0 * (2 * R.FEE_BP + 2 * R.SLIP_BP) / 1e4
    assert net == pytest.approx(R.exit_net(part, 101.0, ts) + R.stop_net(rest, be, bars[j][1], bars[j][0] + B))


def test_take_profit_exit_bar_convention_engine_vs_favourable():
    bars = _flat_bars(14)
    bars[4] = [bars[4][0], 100.0, 102.0, 100.0, 102.0]            # arma il pavimento (pareggio ~100.16)
    for k in (5, 6, 7):
        bars[k] = [bars[k][0], 102.0, 102.5, 101.5, 102.0]
    j = 8
    bars[j] = [bars[j][0], 102.0, 104.0, 100.0, 103.5]            # barra del take profit: il minimo tocca anche il pavimento
    t = trade_dict(side=1, entry=100.0, r_dist=0.01, open_ms=bars[2][0] + 60_000, close_ms=bars[j][0] + B,
                   why="take profit", net=30.0)
    eng = R.run_stop_rule(t, bars, 1.0, 0)                        # convenzione dell'engine: lo stop prevale sul TP
    fav = R.run_stop_rule(t, bars, 1.0, 0, tp_bar=False)          # ipotesi favorevole alla regola: barra esclusa
    assert eng is not None and eng[1] == bars[j][0] + B and eng[0] < t["net"]
    assert fav is None
