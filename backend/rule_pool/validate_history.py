"""Validazione su DATI REALI (sola lettura, candele pubbliche BitGet, nessuna chiave).

Tre domande:
1. Il pool riproduce i numeri gia' pubblicati dal laboratorio (n e lordo medio per periodo)?
2. Il runner in avanti, alimentato giro per giro con candele reali, produce gli stessi trade
   del calcolo su tutta la storia?
3. L'API reale di BitGet restituisce quello che il runner presume (la candela in formazione e'
   l'ultima riga, i valori sono numerici, le righe sono ordinate)?

Il giudizio sulle regole (stati del pool) sullo storico e' solo informativo: le regole sono
state scelte guardando quello stesso storico.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time

import numpy as np

import strategy_lab as sl
from rule_pool import evidence as ev
from rule_pool import pool, replay, runner
from rule_pool.journal import Journal
from rule_pool.rules import MAJORS, Rule

# Numeri pubblicati nel Project (laboratorio-strategie-risultati-2026-10-09.md), BTC+ETH insieme
EXPECT = {
    "S1_donchian_4h": {"dev": (257, 19.5), "val": (94, 35.7), "test": (76, 50.0)},
    "S2_donchian_1h": {"dev": (861, 23.5), "val": (364, 1.1), "test": (255, 28.9)},
}
LINES: list = []


def say(text: str) -> None:
    print(text, flush=True)
    LINES.append(text[:230])


def check_lab_numbers(frames: dict) -> bool:
    ok_all = True
    for strat in EXPECT:
        rule = Rule("V_" + strat, strat, MAJORS)
        closed = []
        for sym in MAJORS:
            closed += [r for r in replay.compute_trades(rule, sym, frames[sym]) if r["status"] == "closed"]
        for p, (n_exp, g_exp) in EXPECT[strat].items():
            lo, hi = sl.PERIODS[p]
            sel = [r for r in closed if lo <= r["entry_t"] < hi]
            g = float(np.mean([r["gross_bp"] for r in sel])) if sel else float("nan")
            ok = len(sel) == n_exp and abs(g - g_exp) < 0.06
            ok_all &= ok
            say(f"{'OK ' if ok else 'DIVERSO'} {strat} {p}: n={len(sel)} (lab {n_exp}) lordo={g:+.2f} (lab {g_exp:+.1f})")
    return ok_all


def informative_pool(frames: dict) -> None:
    base = [Rule("R_S1_majors", "S1_donchian_4h", MAJORS), Rule("R_S2_majors", "S2_donchian_1h", MAJORS)]
    ctl = [Rule("CTL_" + r.rule_id[2:], r.strategy, r.symbols, kind="control", base_rule=r.rule_id) for r in base]
    j = Journal()
    for r in base + ctl:
        for sym in MAJORS:
            replay.sync_journal(j, r, sym, frames[sym], venue="replay")
    res = pool.evaluate_pool(j, base + ctl, venue="replay")
    say("[storico, solo informativo] " + ("ALLARME controlli" if res["alarm"] else "controlli ok") + f", K={res['k']}")
    for line in runner.render_report(j, base + ctl, res, venue="replay").splitlines()[1:]:
        say("  " + line)


class Feed:
    """Serve candele reali giro per giro, come farebbe l'exchange (inclusa la candela in formazione)."""

    def __init__(self, arrays: dict):
        self.arrays, self.now_ms = arrays, 0

    def fetch(self, symbol, since_ms):
        a = self.arrays[symbol]
        i = np.searchsorted(a[:, 0], since_ms, side="left")
        j = np.searchsorted(a[:, 0], self.now_ms, side="right")
        return a[i:min(j, i + 200)].tolist()


def check_forward_runner(arrays: dict, days: int, step_h: int) -> bool:
    end = int(max(a[-1, 0] for a in arrays.values())) + sl.M15
    t0 = end - days * 86_400_000
    seed = {s: a[a[:, 0] < t0] for s, a in arrays.items()}
    rules_ = [Rule("R_S1_majors", "S1_donchian_4h", MAJORS), Rule("R_S2_majors", "S2_donchian_1h", MAJORS)]
    rules_ += [Rule("CTL_" + r.rule_id[2:], r.strategy, r.symbols, kind="control", base_rule=r.rule_id)
               for r in rules_[:2]]
    feed, j = Feed(arrays), Journal()
    j.set_meta("backfill_from_ms", str(sl.DATA_START))
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        for s, a in seed.items():
            store._save(s, a)
        now = t0 + 60_000
        steps = 0
        while now <= end + 60_000:
            feed.now_ms = now
            runner.run_once(j, rules_, store, feed.fetch, now)
            steps += 1
            now += step_h * 3_600_000
        last_now = now - step_h * 3_600_000
    fwd = int(j.get_meta("forward_from_ms"))
    frames = {s: replay.frames_for(sl.bars_from_array(a)) for s, a in arrays.items()}
    ok_all = True
    for r in rules_:
        batch, rows = {}, {}
        for sym in MAJORS:
            fn = replay.control_records if r.kind == "control" else replay.compute_trades
            for x in fn(r, sym, frames[sym]):
                if x["status"] == "closed" and x["entry_t"] >= fwd and x["exit_t"] + r.tf_ms <= last_now:
                    batch[(sym, x["entry_t"])] = x
        for x in j.all_trades(r.rule_id, r.version, "paper"):
            if x["status"] == "closed":
                rows[(x["symbol"], x["entry_t"])] = x
        same = all(k in rows and rows[k]["side"] == x["side"] and abs(rows[k]["net_bp"] - x["net_bp"]) < 1e-9
                   for k, x in batch.items())
        extra = [k for k in rows if k not in batch]
        ok = same and not extra
        ok_all &= ok
        say(f"{'OK ' if ok else 'DIVERSO'} runner in avanti {r.rule_id}: {len(rows)} trade nel giornale, "
            f"{len(batch)} attesi dal calcolo completo, extra={len(extra)} ({steps} giri, passo {step_h}h)")
    return ok_all


def check_live_api() -> bool:
    now = int(time.time() * 1000)
    rows = runner.fetch_bitget("BTC/USDT:USDT", now - 4 * 3_600_000)
    if not rows:
        say("DIVERSO API reale: nessuna riga")
        return False
    ts = [int(r[0]) for r in rows]
    numeric = all(all(isinstance(x, (int, float)) for x in r[:6]) for r in rows)
    sorted_ok = ts == sorted(ts) and len(set(ts)) == len(ts) and all(b - a == sl.M15 for a, b in zip(ts, ts[1:]))
    limit = runner.last_closed_open(now)
    forming = ts[-1] > limit
    say(f"API reale BTC: {len(rows)} righe, ordinate/contigue={sorted_ok}, numeriche={numeric}, "
        f"ultima riga {'IN FORMAZIONE (verra scartata)' if forming else 'gia chiusa'} "
        f"(ultima={(now - ts[-1]) // 1000}s fa, limite chiuso={(now - limit) // 1000}s fa)")
    return sorted_ok and numeric and ts[-1] <= now


def annotate() -> None:
    for i in range(0, len(LINES), 12):
        msg = "%0A".join(x.replace("%", "%25") for x in LINES[i:i + 12])
        print(f"::notice title=Validazione pool ({i // 12 + 1})::{msg}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="lab_cache")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--step-h", type=int, default=8)
    args = ap.parse_args()
    ok = True
    try:
        ok &= check_live_api()
    except Exception as exc:  # noqa: BLE001
        say(f"DIVERSO API reale: errore {type(exc).__name__} {str(exc)[:80]}")
        ok = False
    arrays = {s: sl.fetch_15m(s, sl.DATA_START, sl.DATA_END, args.cache_dir) for s in MAJORS}
    frames = {s: replay.frames_for(sl.bars_from_array(a)) for s, a in arrays.items()}
    ok &= check_lab_numbers(frames)
    informative_pool(frames)
    ok &= check_forward_runner(arrays, args.days, args.step_h)
    say("ESITO: " + ("tutto coincide" if ok else "CI SONO DIFFERENZE"))
    annotate()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
