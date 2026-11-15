"""Prove del modulo ombra su un universo SINTETICO: coerenza col laboratorio, niente informazione futura, ripetibilita'."""
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shadow  # noqa: E402

DAY = 86_400_000
T0 = 1_700_000_000_000 - 1_700_000_000_000 % DAY


def _universe(path, days, n_sym=36, seed=7):
    rng = np.random.default_rng(seed)
    market = np.cumsum(rng.normal(0.004, 0.02, days))                # mercato in salita: filtro acceso
    for k in range(n_sym):
        name = ("BTCUSDT", "ETHUSDT")[k] if k < 2 else f"A{k:02d}USDT"
        r = (1.0 if k < 2 else rng.uniform(0.8, 1.8)) * np.diff(np.r_[0, market]) + rng.normal(0.0005 * (k % 5 - 1), 0.03, days)
        c = 100 * np.exp(np.cumsum(r))
        o = np.r_[100.0, c[:-1]]
        h, l = np.maximum(o, c) * (1 + rng.uniform(0, 0.02, days)), np.minimum(o, c) * (1 - rng.uniform(0, 0.02, days))
        with open(os.path.join(path, f"{name}_1Dutc.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ts", "open", "high", "low", "close", "base_vol", "quote_vol"])
            for i in range(days):
                w.writerow([T0 + i * DAY, o[i], h[i], l[i], c[i], 1000, 1e6 * (n_sym - k)])


def _date(i):
    return str(np.datetime64(T0 + i * DAY, "ms").astype("datetime64[D]"))


def test_shadow_is_repeatable_and_matches_the_lab_engine(tmp_path):
    _universe(str(tmp_path), 420)
    rows1, state1 = shadow.run(str(tmp_path), _date(200))
    rows2, state2 = shadow.run(str(tmp_path), _date(200))
    assert rows1 == rows2 and state1 == state2
    done = [r for r in rows1 if r.get("stato") == "chiusa"]
    assert len(done) >= 10 and state1["riepilogo"]["chiuse"] == len(done)          # l'assert interno confronta col laboratorio
    assert all(r["data_segnale"] >= _date(200) for r in rows1)
    assert sum(r["esito"] == "eseguito_virtuale" for r in rows1) >= len(done)
    assert all(r["distanza_stop_pct"] > 0 and r["stop_iniziale"] < r["ingresso"] for r in done)
    assert len(state1["posizioni_virtuali_aperte"]) <= shadow.SLOTS


def test_past_observations_do_not_change_when_new_days_arrive(tmp_path):
    full, cut = tmp_path / "full", tmp_path / "cut"
    full.mkdir(), cut.mkdir()
    _universe(str(full), 420)
    for name in os.listdir(full):                                                   # stessa storia, 40 giorni in meno
        lines = open(full / name).read().splitlines()
        (cut / name).write_text("\n".join(lines[:-40]) + "\n")
    rows_full, _ = shadow.run(str(full), _date(200))
    rows_cut, state_cut = shadow.run(str(cut), _date(200))
    last = state_cut["ultimo_giorno_chiuso"]
    key = lambda r: (r["data_segnale"], r["simbolo"])  # noqa: E731
    closed_then = {key(r): r for r in rows_cut if r.get("stato") == "chiusa"}
    later = {key(r): r for r in rows_full}
    assert len(closed_then) >= 5
    for k, r in closed_then.items():
        assert later[k] == r, k                                                     # riga chiusa = riga definitiva
    assert all(r["data_segnale"] <= last for r in rows_cut)
    # i segnali fino all'ultimo giorno comune sono gli stessi, nello stesso ordine e con lo stesso esito
    common = [(key(r), r["esito"]) for r in rows_full if r["data_segnale"] <= last]
    assert common == [(key(r), r["esito"]) for r in rows_cut]
