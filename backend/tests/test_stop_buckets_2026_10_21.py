"""Collaudo di deploy/scripts/stop_buckets.py (vincite e R netto per larghezza dello stop, SOLA LETTURA).

Oracoli: la tabella costi/pareggio ricevuta da un'altra AI (ricalcolata a mano), il motore vero (PaperAccount) per i
campi del registro, e numeri calcolati a mano su registri finti."""
import importlib.util
import io
import json
import os
import re
from contextlib import redirect_stdout

import pytest

from desk.engine import Limits, PaperAccount

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.environ.get("STOP_BUCKETS_PATH") or os.path.join(ROOT, "deploy", "scripts", "stop_buckets.py")
spec = importlib.util.spec_from_file_location("stop_buckets", SCRIPT)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

spec2 = importlib.util.spec_from_file_location("pm_exec_replay", os.path.join(ROOT, "deploy", "scripts", "pm_exec_replay.py"))
R = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(R)

T0 = 1_760_000_000_000


def rec(i, stop_pct, net_r, why="stop loss", run=1, margin=100.0, lev=10.0, **extra):
    """Riga di chiusura coerente con le formule del motore: costi zero, uscita scelta per dare esattamente net_r."""
    dist = stop_pct / 100.0
    risk = margin * lev * dist
    net = net_r * risk
    entry = 100.0
    qty = margin * lev / entry
    r = {"ev": "close", "run_no": run, "id": i, "symbol": "BTCUSDT", "side": 1, "margin": margin, "leverage": lev,
         "entry": entry, "exit": entry + net / qty, "net": net, "fees": 0.0, "funding": 0.0, "why": why,
         "r_dist": dist, "risk_plan_usd": risk, "net_r": net_r, "dca_count": 0, "legs": 1}
    r.update(extra)
    return r


def write_ledger(tmp_path, rows, bot="hawk"):
    d = tmp_path / bot
    d.mkdir(parents=True, exist_ok=True)
    p = d / "learning_log.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(p)


# ------------------------------------------------------------------ pareggio = tabella ricevuta

@pytest.mark.parametrize("stop,expected", [(0.3, 54.76190476190476), (1.0, 41.42857142857142), (3.5, 37.34693877551021)])
def test_breakeven_matches_external_table(stop, expected):
    assert S.breakeven_pct(stop) == pytest.approx(expected, abs=1e-6)


def test_breakeven_with_measured_tp_and_sl():
    # TP misurato 1,72R e stop 1,02R (gia' al lordo dei costi): (1,02 + c) / 2,74
    assert S.breakeven_pct(1.0, tp=1.72, sl=1.02) == pytest.approx(43.0657, abs=1e-3)
    assert S.breakeven_pct(0.5, tp=1.72, sl=1.02) == pytest.approx(48.9051, abs=1e-3)
    assert S.breakeven_pct(3.5, tp=1.72, sl=1.02) == pytest.approx(38.8939, abs=1e-3)


def test_breakeven_grows_as_stop_gets_tighter_and_zero_cost_is_flat():
    vals = [S.breakeven_pct(s) for s in (0.3, 0.5, 1.0, 2.0, 3.5)]
    assert vals == sorted(vals, reverse=True)
    assert S.breakeven_pct(1.0, cost_bp=0.0) == pytest.approx(100 * 1.0 / 2.8)    # senza costi: 35,7% per qualunque stop
    assert S.breakeven_pct(0.3, cost_bp=0.0) == pytest.approx(S.breakeven_pct(3.5, cost_bp=0.0))


# ------------------------------------------------------------------ fasce

@pytest.mark.parametrize("stop,label", [(0.1, "<0.5%"), (0.49, "<0.5%"), (0.5, "0.5-1%"), (0.99, "0.5-1%"), (1.0, "1-2%"),
                                        (1.99, "1-2%"), (2.0, ">=2%"), (3.5, ">=2%")])
def test_bucket_label_boundaries(stop, label):
    assert S.bucket_label(stop) == label


def test_bucket_order_covers_every_label():
    assert S.bucket_order() == ["<0.5%", "0.5-1%", "1-2%", ">=2%"]
    assert {S.bucket_label(x) for x in (0.2, 0.7, 1.5, 3.0)} == set(S.bucket_order())


def test_quantile_interpolates():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert S.quantile(xs, 0.0) == 1.0 and S.quantile(xs, 1.0) == 4.0
    assert S.quantile(xs, 0.5) == pytest.approx(2.5)
    assert S.quantile(xs, 1 / 3) == pytest.approx(2.0)
    assert S.quantile([7.0], 0.9) == 7.0


# ------------------------------------------------------------------ statistiche a mano

def test_bucket_stats_hand_computed(tmp_path):
    rows = [rec(1, 1.0, 1.6, "take profit"), rec(2, 1.0, 1.6, "take profit"), rec(3, 1.0, -1.2), rec(4, 1.0, -1.2)]
    clean, skipped = S.load_trades(write_ledger(tmp_path, rows), "hawk")
    st = S.bucket_stats(clean)
    assert st["n"] == 4 and st["wins"] == 2 and st["win_pct"] == pytest.approx(50.0)
    assert st["mean_r"] == pytest.approx(0.2) and st["w_r"] == pytest.approx(1.6) and st["l_r"] == pytest.approx(-1.2)
    assert st["be_own"] == pytest.approx(100 * 1.2 / 2.8)                 # 42,857%
    assert st["be_theory"] == pytest.approx(41.42857142857142)            # stop mediano 1%
    assert st["stop_med"] == pytest.approx(1.0)
    assert st["exits"]["TP"] == 2 and st["exits"]["SL"] == 2 and st["exits"]["altro"] == 0
    assert st["ci"] is None                                              # meno di 5 trade: niente intervallo
    assert st["mean_net"] == pytest.approx(0.2 * 100 * 10 * 0.01)


def test_bucket_stats_only_winners_or_only_losers_has_no_own_breakeven(tmp_path):
    clean, _ = S.load_trades(write_ledger(tmp_path, [rec(1, 1.0, 1.0), rec(2, 1.0, 2.0)]), "hawk")
    assert S.bucket_stats(clean)["be_own"] is None
    clean, _ = S.load_trades(write_ledger(tmp_path, [rec(1, 1.0, -1.0), rec(2, 1.0, -2.0)], "bull"), "bull")
    st = S.bucket_stats(clean)
    assert st["be_own"] is None and st["win_pct"] == 0.0 and st["wins"] == 0


def test_zero_net_trade_counts_as_not_a_win(tmp_path):
    clean, _ = S.load_trades(write_ledger(tmp_path, [rec(1, 1.0, 0.0), rec(2, 1.0, 1.0)]), "hawk")
    st = S.bucket_stats(clean)
    assert st["wins"] == 1 and st["win_pct"] == pytest.approx(50.0)
    assert st["l_r"] == pytest.approx(0.0)                                # il pareggio secco conta tra i non vincenti


def test_bootstrap_is_deterministic_and_brackets_the_mean():
    vals = [1.6, -1.2, 1.6, -1.2, -1.2, 1.6, -1.2, -1.2]
    a, b = S.boot_ci(vals), S.boot_ci(list(vals))
    assert a == b
    mean = sum(vals) / len(vals)
    assert a[0] < mean < a[1]
    assert a[0] >= min(vals) and a[1] <= max(vals)
    assert S.boot_ci(vals[:4]) is None
    # tutti uguali: l'intervallo si riduce a un punto
    lo, hi = S.boot_ci([0.5] * 6)
    assert lo == pytest.approx(0.5) and hi == pytest.approx(0.5)


def test_bootstrap_uses_every_observation_including_the_last():
    lo, hi = S.boot_ci([0.0] * 6 + [10.0])
    assert lo == 0.0 and hi > 1.0                       # un solo valore estremo, in ultima posizione, deve poter entrare


def test_bucket_uses_median_stop_of_the_bucket(tmp_path):
    rows = [rec(1, 0.6, 1.0), rec(2, 0.8, -1.0), rec(3, 0.9, 1.0)]
    clean, _ = S.load_trades(write_ledger(tmp_path, rows), "hawk")
    st = S.bucket_stats(clean)
    assert st["stop_med"] == pytest.approx(0.8)
    assert st["be_theory"] == pytest.approx(S.breakeven_pct(0.8))


# ------------------------------------------------------------------ registro: filtri e campi (oracolo = motore)

def test_load_trades_matches_replay_loader_and_engine_net_r(tmp_path):
    rows = []
    for k, (side, px_exit, why) in enumerate([(1, 103.0, "take profit"), (-1, 101.5, "stop loss"), (1, 99.4, "stop loss")], 1):
        a = PaperAccount(Limits())
        price = 100.0
        sl = price * (1 - side * 0.01)
        pos, msg = a.open("BTCUSDT", side, 100.0, 10, price, sl, None, T0, {})
        assert pos is not None, msg
        r = a.close("BTCUSDT", px_exit, T0 + 5 * 3_600_000, why)
        r["id"] = k
        rows.append({"ev": "close", "run_no": 1, **r})
    p = write_ledger(tmp_path, rows)
    mine, sk1 = S.load_trades(p, "hawk")
    ref, sk2 = R.load_trades(p, "hawk")
    assert dict(sk1) == dict(sk2) == {}
    key = lambda t: (t["run"], t["id"])
    mine, ref = sorted(mine, key=key), sorted(ref, key=key)
    assert len(mine) == len(ref) == 3
    for m, r in zip(mine, ref):
        for f in ("symbol", "side", "margin", "lev", "entry", "exit", "net", "fees", "funding", "why", "r_dist", "recon_err"):
            assert m[f] == pytest.approx(r[f]), f
    # net_r calcolato qui = net_r registrato dal motore (additivo, una gamba)
    for m, row in zip(mine, sorted(rows, key=lambda x: x["id"])):
        assert row["net_r"] is not None
        assert m["net_r"] == pytest.approx(row["net_r"], abs=1e-3)
        assert m["stop_pct"] == pytest.approx(row["r_dist"] * 100)


def test_load_trades_filters_and_keys_by_run_and_id(tmp_path):
    rows = [rec(1, 1.0, 1.0, run=1), rec(1, 1.0, -1.0, run=2),                       # stesso id, altra run: due trade
            rec(2, 1.0, 1.0, partial=True), rec(3, 1.0, 1.0, dca_count=1), rec(4, 1.0, 1.0, legs=2),
            rec(5, 1.0, -1.0, why="liquidazione"),
            {"ev": "open", "id": 9}, {"ev": "close", "run_no": 1, "id": 6, "symbol": "X"},
            rec(7, 1.0, 1.0, side=0), rec(8, 0.0, 1.0)]
    rows[-1]["r_dist"] = 0.0
    p = tmp_path / "hawk"
    p.mkdir()
    (p / "learning_log.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnon json\n")
    clean, skipped = S.load_trades(str(p / "learning_log.jsonl"), "hawk")
    assert sorted((t["run"], t["id"]) for t in clean) == [(1, 1), (2, 1)]
    assert skipped["con parziali"] == 1 and skipped["dca o due gambe"] == 2 and skipped["liquidazione"] == 1
    assert skipped["campi mancanti"] == 1 and skipped["campi non validi"] == 2


def test_two_records_with_same_run_and_id_are_a_partial_trade_and_skipped(tmp_path):
    rows = [rec(1, 1.0, 0.5), rec(1, 1.0, 0.5), rec(2, 1.0, 1.0)]
    clean, skipped = S.load_trades(write_ledger(tmp_path, rows), "hawk")
    assert [(t["run"], t["id"]) for t in clean] == [(1, 2)] and skipped["con parziali"] == 1


def test_risk_falls_back_to_margin_lev_dist_when_not_recorded(tmp_path):
    r = rec(1, 2.0, 1.0)
    del r["risk_plan_usd"], r["net_r"]
    clean, _ = S.load_trades(write_ledger(tmp_path, [r]), "hawk")
    assert clean[0]["risk"] == pytest.approx(100 * 10 * 0.02)
    assert clean[0]["net_r"] == pytest.approx(1.0)


def test_recorded_risk_wins_over_recomputed(tmp_path):
    r = rec(1, 1.0, 1.0)
    r["risk_plan_usd"] = 20.0                    # pianificato diverso dal margine finale
    clean, _ = S.load_trades(write_ledger(tmp_path, [r]), "hawk")
    assert clean[0]["risk"] == 20.0 and clean[0]["net_r"] == pytest.approx(r["net"] / 20.0)


# ------------------------------------------------------------------ rapporto completo

def run_main(tmp_path, bots="hawk,bull"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        S.main(["--data-root", str(tmp_path), "--bots", bots])
    return buf.getvalue()


def test_report_end_to_end(tmp_path):
    rows, i = [], 0
    # fascia <0.5%: 6 trade, 2 vincenti a +1.0R e 4 perdenti a -1.5R  -> media -0.667R, vinc 33.3%
    for r in (1.0, 1.0, -1.5, -1.5, -1.5, -1.5):
        i += 1
        rows.append(rec(i, 0.4, r, "take profit" if r > 0 else "stop loss"))
    # fascia >=2%: 5 trade, 3 vincenti a +1.7R e 2 perdenti a -1.0R   -> media +0.62R, vinc 60%
    for r in (1.7, 1.7, 1.7, -1.0, -1.0):
        i += 1
        rows.append(rec(i, 3.0, r, "take profit" if r > 0 else "stop loss"))
    rows.append(rec(99, 1.0, 1.0, why="chiusura decisa", fees=5.0, net=1.0))      # net non torna con le formule: escluso
    write_ledger(tmp_path, rows)
    out = run_main(tmp_path, "hawk")
    assert "=== HAWK: trade puliti 12" in out
    assert "11 su 12 tornano al centesimo, 1 esclusi" in out
    assert "stop iniziale in % del prezzo: min 0.40" in out and "max 3.00" in out
    assert "costo di un giro (16 bp) in R: mediana 0.40 | stop piu' stretto 0.40 | stop piu' largo 0.05" in out
    assert "| p25 0.40 | mediana 0.40 | p75 3.00 | p90 3.00 |" in out
    low = [l for l in out.splitlines() if l.startswith("<0.5%")][0]
    assert "n=  6" in low and "vinc  33.3%" in low and "R netto medio -0.67" in low
    assert "R vinc +1.00" in low and "R perd -1.50" in low and "uscite TP 2 SL 4 altro 0" in low
    # pareggio proprio = 1.5 / 2.5 = 60%; teorico a stop 0.4%: (1 + 0.4) / 2.8 = 50%
    assert "pareggio proprio 60.0%" in low and "teorico a stop 0.40%: 50.0%" in low
    high = [l for l in out.splitlines() if l.startswith(">=2%")][0]
    assert "n=  5" in high and "vinc  60.0%" in high and "R netto medio +0.62" in high
    assert not [l for l in out.splitlines() if l.startswith("0.5-1%") or l.startswith("1-2%")]   # fasce vuote non stampate
    allr = [l for l in out.splitlines() if l.startswith("TUTTI")][0]
    assert "n= 11" in allr


def test_report_handles_missing_and_empty_ledgers(tmp_path):
    write_ledger(tmp_path, [{"ev": "open", "id": 1}], "bull")
    out = run_main(tmp_path, "hawk,bull")
    assert "=== HAWK: registro non trovato" in out
    assert "=== BULL: trade puliti 0" in out and "nessun trade utilizzabile" in out


def test_ci_shown_only_with_five_or_more_trades(tmp_path):
    write_ledger(tmp_path, [rec(k, 1.0, r) for k, r in enumerate((1.0, -1.0, 1.0, -1.0), 1)])
    assert "IC95 n<5" in run_main(tmp_path, "hawk")
    write_ledger(tmp_path, [rec(k, 1.0, r) for k, r in enumerate((1.0, -1.0, 1.0, -1.0, 1.0), 1)])
    assert "IC95 n<5" not in run_main(tmp_path, "hawk")


# ------------------------------------------------------------------ sola lettura

def test_script_is_read_only_and_offline():
    src = open(SCRIPT, encoding="utf-8").read()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for banned in ("urllib", "socket", "subprocess", "requests", "http.client", "os.remove", "os.rename", "shutil",
                   "unlink", "rmtree", "write(", "os.system"):
        assert banned not in code, banned
    for m in re.finditer(r"open\(([^)]*)\)", code):
        assert not re.search(r"""['"][^'"]*[wax+][^'"]*['"]""", m.group(1).split("encoding")[0]), m.group(0)
    assert code.count("open(") == 1


def test_ledger_file_is_not_modified_by_a_run(tmp_path):
    p = write_ledger(tmp_path, [rec(k, 1.0, 1.0 if k % 2 else -1.0) for k in range(1, 8)])
    before = open(p, "rb").read()
    mtime = os.stat(p).st_mtime_ns
    run_main(tmp_path, "hawk")
    assert open(p, "rb").read() == before and os.stat(p).st_mtime_ns == mtime
    assert sorted(os.listdir(tmp_path / "hawk")) == ["learning_log.jsonl"]
