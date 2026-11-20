"""Valutazione PRE-REGISTRATA dei bracci d'uscita (offline, stdlib). Regole in `preregistration.json`.

1. Solo posizioni con input e candele ATTESTATI (stessa regola del Dataset Builder): il chiamante passa solo
   quelle; qui si rifiuta qualunque record senza `attested: true`.
2. Divisione cronologica per giorno: calibrazione (prima quota dei giorni), embargo >= durata massima, test.
3. Calibrazione: per ogni famiglia si sceglie UN solo parametro (media di R netti piu' alta) SOLO sulla
   calibrazione. Il test non vede mai la scelta dei parametri.
4. Test: differenza APPAIATA (stesso trade) vincitore di famiglia - riferimento; bootstrap a blocchi per giorno
   (seme fisso), correzione di Holm sulle famiglie.
5. Superiore solo se: campione minimo raggiunto, limite inferiore dell'intervallo > 0 dopo Holm, drawdown in R
   non peggiore oltre la tolleranza, e la conclusione regge in tutti gli scenari di funding dichiarati.
   Altrimenti: "non dimostrato" (oppure "campione insufficiente"). Mai una modifica automatica.
"""
from __future__ import annotations

import random
from typing import Sequence


def split_days(days: Sequence[str], calib_frac: float, embargo_days: int) -> tuple:
    d = sorted(set(days))
    k = int(len(d) * calib_frac)
    return set(d[:k]), set(d[k + embargo_days:])


def max_drawdown(values: Sequence[float]) -> float:
    peak = cur = dd = 0.0
    for v in values:
        cur += v
        peak = max(peak, cur)
        dd = max(dd, peak - cur)
    return dd


def block_bootstrap_ci(diffs_by_day: dict, n: int, seed: int, alpha: float) -> tuple:
    days = sorted(diffs_by_day)
    if not days:
        return (None, None)
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        sample = []
        for _d in days:
            sample.extend(diffs_by_day[rng.choice(days)])
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(alpha / 2 * n)]
    hi = means[min(n - 1, int((1 - alpha / 2) * n))]
    return lo, hi


def holm_alphas(k: int, alpha: float) -> list:
    """Soglie di Holm per k confronti, nell'ordine dal piu' forte al piu' debole."""
    return [alpha / (k - i) for i in range(k)]


def evaluate(trades: Sequence[dict], spec: dict) -> dict:
    """trades: [{"id", "day", "attested": True, "results": {arm_name: net_r | None}}] per UNO scenario di funding.
    Restituisce, per famiglia: parametro scelto, n, media, differenza appaiata, intervallo e verdetto."""
    rules = spec["rules"]
    bad = [t["id"] for t in trades if t.get("attested") is not True]
    if bad:
        raise ValueError("unattested_trades:%d" % len(bad))
    base = next(a["name"] for a in spec["arms"] if a["family"] == "baseline")
    calib_days, test_days = split_days([t["day"] for t in trades], rules["calibration_fraction"],
                                       rules["embargo_days"])
    closed = [t for t in trades if all(v is not None for v in t["results"].values())]
    calib = [t for t in closed if t["day"] in calib_days]
    test = sorted((t for t in closed if t["day"] in test_days), key=lambda t: (t["day"], t["id"]))
    fams = sorted({a["family"] for a in spec["arms"]} - {"baseline"})
    chosen = {}
    for f in fams:
        names = [a["name"] for a in spec["arms"] if a["family"] == f]
        score = {n: (sum(t["results"][n] for t in calib) / len(calib)) if calib else float("-inf") for n in names}
        chosen[f] = max(names, key=lambda n: (score[n], n))          # pareggi: ordine dei nomi, deterministico
    out = {"baseline": base, "calibration_trades": len(calib), "test_trades": len(test),
           "test_days": len({t["day"] for t in test}), "families": {}}
    enough = len(test) >= rules["min_test_trades"] and out["test_days"] >= rules["min_test_days"]
    base_dd = max_drawdown([t["results"][base] for t in test])
    rows = []
    for f in fams:
        n = chosen[f]
        by_day: dict = {}
        for t in test:
            by_day.setdefault(t["day"], []).append(t["results"][n] - t["results"][base])
        diffs = [x for v in by_day.values() for x in v]
        rows.append((f, n, by_day, sum(diffs) / len(diffs) if diffs else None))
    rows.sort(key=lambda x: -(x[3] if x[3] is not None else float("-inf")))
    for (f, n, by_day, mean), a in zip(rows, holm_alphas(len(rows), rules["alpha"])):
        lo, hi = block_bootstrap_ci(by_day, rules["bootstrap_samples"], rules["seed"], a)
        dd = max_drawdown([t["results"][n] for t in test])
        dd_ok = dd <= base_dd * (1 + rules["max_drawdown_worsening"]) + 1e-12
        if not enough:
            verdict = "campione_insufficiente"
        elif lo is not None and lo > 0 and dd_ok:
            verdict = "superiore_nello_scenario"
        else:
            verdict = "non_dimostrato"
        out["families"][f] = {"arm": n, "mean_diff_r": mean, "ci_low": lo, "ci_high": hi, "holm_alpha": a,
                              "max_dd_r": dd, "baseline_max_dd_r": base_dd, "verdict": verdict}
    return out


def combine_scenarios(results: Sequence[dict]) -> dict:
    """Superiore SOLO se lo e' in TUTTI gli scenari di funding (e con lo stesso braccio scelto)."""
    fams = results[0]["families"].keys()
    final = {}
    for f in fams:
        rs = [r["families"][f] for r in results]
        same = len({x["arm"] for x in rs}) == 1
        if all(x["verdict"] == "superiore_nello_scenario" for x in rs) and same:
            final[f] = "superiore_proposta_al_proprietario"
        elif any(x["verdict"] == "campione_insufficiente" for x in rs):
            final[f] = "campione_insufficiente"
        else:
            final[f] = "non_dimostrato"
    return final
