"""Etichette degli esiti per il laboratorio LLM: l'utilita' di una risposta si misura sul MERCATO, mai sull'accordo
con DeepSeek. Modulo puro (nessuna rete, nessun orologio); non decide e non apre nulla.

Regole uguali per ogni modello, fissate PRIMA di vedere i risultati (argomenti obbligatori, nessun default):
* ingresso = prezzo di mercato all'istante della decisione (``entry_of(sample_id)``), come fa il runner
  (``MarketEntryAnalyst``): l'``entry_price`` dichiarato dal modello non conta;
* stop = quello proposto dal modello; se rispetto all'ingresso di mercato e' dal lato sbagliato o nullo, la proposta
  NON e' eseguibile (``not_executable``), come la rifiuterebbe il motore;
* obiettivo = ingresso +/- ``target_r`` volte la distanza dallo stop; orizzonte massimo ``horizon_ms``; costi
  ``cost_bp`` round-trip; candela ambigua (stop e obiettivo insieme) risolta con ``ambiguous_policy``;
* etichettatura con ``backend.v3.learning.opportunity`` (gia' collaudato): solo candele che APRONO dopo la decisione,
  la candela che la contiene e' esclusa; una candela mancante => ``incomplete``, mai interpolare.

``score`` riassume per modello (vedi la sua docstring): esiti SIMULATI e controfattuali per ogni modello, esiti
OSSERVATI (trade PAPER reali del riferimento) in una sezione separata, NO_TRADE giudicate solo in RELAZIONE al
riferimento, incertezza e limiti del campione sempre dichiarati. L'accordo con il riferimento non e' mai un criterio.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Optional, Sequence

from backend.v3.learning.opportunity import Candidate, Candle, label_candidates

_BP = Decimal(10000)


def _dec(value) -> Optional[Decimal]:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def _side(record: Mapping) -> int:
    return {"LONG": 1, "SHORT": -1}.get(record.get("direction") or record.get("action"), 0)


def label_records(records: Sequence[Mapping], candles: Mapping[str, Sequence[Candle]], *,
                  entry_of: Callable[[str], Optional[Decimal]], candle_ms: int, horizon_ms: int,
                  target_r: Decimal, cost_bp: Decimal, ambiguous_policy: str) -> list[dict]:
    """Un'etichetta per ogni record (stesso ordine). ``status``: labelled / incomplete / not_executable /
    no_trade / invalid."""
    if type(target_r) is not Decimal or not target_r.is_finite() or target_r <= 0:
        raise ValueError("invalid_target_r")
    out: list[dict] = []
    todo: list[tuple[int, Candidate, Decimal]] = []
    for i, r in enumerate(records):
        base = {"sample_id": r.get("sample_id"), "model_id": r.get("model_id"), "status": None,
                "barrier": None, "net_bp": None, "net_r": None, "ambiguous": None,
                "label_kind": "simulated_counterfactual"}
        out.append(base)
        if r.get("valid") is not True:
            base["status"] = "invalid"
            continue
        if r.get("action") == "NO_TRADE":
            base["status"] = "no_trade"
            continue
        side = _side(r)
        prop = r.get("proposal") if isinstance(r.get("proposal"), Mapping) else {}
        entry = entry_of(r.get("sample_id"))
        stop = _dec(prop.get("stop_price"))
        if side == 0 or entry is None or entry <= 0 or stop is None or stop <= 0 or (stop - entry) * side >= 0:
            base["status"] = "not_executable"
            continue
        risk = abs(entry - stop)
        cand = Candidate(f"c{i}", str(r.get("symbol")), side, int(r.get("decision_ms") or 0), entry, stop,
                         entry + side * target_r * risk)
        todo.append((i, cand, risk / entry * _BP))
    if todo:
        labels = label_candidates([c for _, c, _ in todo], candles, candle_ms=candle_ms, horizons_ms=[horizon_ms],
                                  cost_bp=cost_bp, ambiguous_policy=ambiguous_policy)
        for (i, _, stop_bp), lab in zip(todo, labels):
            h = lab.horizons[0]
            row = out[i]
            if h.status != "complete":
                row["status"] = "incomplete"
                continue
            row.update(status="labelled", barrier=h.barrier, ambiguous=h.ambiguous, net_bp=h.net_bp,
                       net_r=(h.net_bp / stop_bp).quantize(Decimal("0.0001")))
    return out


DAY_MS = 86_400_000
MIN_SAMPLE = 30
LIMITS = (
    "simulated_labels_are_counterfactual",       # nessun candidato ha mai aperto: esiti simulati con regole fisse
    "bracket_exit_not_production_exit_policy",   # stop/obiettivo/orizzonte, non l'ExitService reale (trailing, ecc.)
    "no_slippage_or_gap_model",                  # uscita esattamente al livello; costi uguali per ogni barriera
    "intrabar_order_unknown",                    # candela con stop e obiettivo: risolta dalla policy dichiarata
    "no_trade_judged_relative_to_reference",     # un NO_TRADE e' giudicato contro la proposta di riferimento,
                                                 # non contro la migliore decisione possibile
    "samples_not_independent",                   # stesse ore/simboli correlati: l'intervallo e' approssimato
)


def _stats(values: list) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0, "ev_net_r": None, "sd_net_r": None, "se": None, "ci95_approx": None}
    q = Decimal("0.0001")
    mean = sum(values, Decimal(0)) / n
    if n < 2:
        return {"n": n, "ev_net_r": mean.quantize(q), "sd_net_r": None, "se": None, "ci95_approx": None}
    var = sum(((v - mean) ** 2 for v in values), Decimal(0)) / (n - 1)
    sd = var.sqrt()
    se = sd / Decimal(n).sqrt()
    half = Decimal("1.96") * se
    return {"n": n, "ev_net_r": mean.quantize(q), "sd_net_r": sd.quantize(q), "se": se.quantize(q),
            "ci95_approx": [(mean - half).quantize(q), (mean + half).quantize(q)]}


def score(records: Sequence[Mapping], labels: Sequence[Mapping], *, reference_model: str,
          observed: Optional[Mapping[str, Decimal]] = None) -> dict:
    """Per modello, su esiti SIMULATI (controfattuali, regole uguali per tutti):
    * aperture: EV netto in R con deviazione, errore standard e intervallo al 95 % APPROSSIMATO, giorni UTC distinti,
      ``sample`` = ``insufficient`` sotto 30 etichette;
    * NO_TRADE, giudicate SOLO in relazione al riferimento sullo stesso campione: ingresso sfavorevole evitato
      (riferimento in perdita), occasione mancata (in utile), entrambi astenuti (``reference_also_abstained``: non
      e' una prova di correttezza), non giudicabili;
    * ``paired_vs_reference``: differenza media di R sui soli campioni dove entrambi hanno aperto.
    ``observed`` ({sample_id: R netto del trade PAPER reale del riferimento}) resta in una sezione SEPARATA: e' un
    esito osservato con la politica d'uscita reale, non confrontabile alla pari con le simulazioni; se ne riporta
    solo la distanza media dalla simulazione dello stesso campione (quanto la simulazione rappresenta la realta').
    """
    if len(records) != len(labels):
        raise ValueError("labels_mismatch")
    for r, lab in zip(records, labels):
        if r.get("sample_id") != lab["sample_id"] or r.get("model_id") != lab["model_id"]:
            raise ValueError("labels_mismatch")
    ref_lab = {lab["sample_id"]: lab for r, lab in zip(records, labels) if r.get("model_id") == reference_model}
    per: dict = defaultdict(lambda: {"records": 0, "opens": 0, "incomplete": 0, "not_executable": 0, "invalid": 0,
                                     "values": [], "days": set(), "by_sample": {},
                                     "no_trade": {"total": 0, "avoided_unfavorable": 0, "missed_favorable": 0,
                                                  "reference_flat": 0, "reference_also_abstained": 0,
                                                  "unjudged": 0}})
    for r, lab in zip(records, labels):
        s = per[str(r.get("model_id"))]
        s["records"] += 1
        st = lab["status"]
        if st == "invalid":
            s["invalid"] += 1
        elif st == "no_trade":
            nt = s["no_trade"]
            nt["total"] += 1
            other = ref_lab.get(lab["sample_id"])
            if other is None or other["status"] in ("incomplete", "invalid", "not_executable"):
                nt["unjudged"] += 1
            elif other["status"] == "no_trade":
                nt["reference_also_abstained"] += 1
            elif other["net_r"] < 0:
                nt["avoided_unfavorable"] += 1
            elif other["net_r"] > 0:
                nt["missed_favorable"] += 1
            else:
                nt["reference_flat"] += 1
        else:
            s["opens"] += 1
            if st == "labelled":
                s["values"].append(lab["net_r"])
                s["by_sample"][lab["sample_id"]] = lab["net_r"]
                ms = r.get("decision_ms")
                if type(ms) is int:
                    s["days"].add(ms // DAY_MS)
            else:
                s[st] += 1
    arms, paired = {}, {}
    ref_values = per[reference_model]["by_sample"] if reference_model in per else {}
    for model, s in sorted(per.items()):
        st = _stats(s["values"])
        arms[model] = {"records": s["records"], "opens": s["opens"], "labelled": st["n"], "incomplete": s["incomplete"],
                       "not_executable": s["not_executable"], "invalid": s["invalid"],
                       "wins": sum(1 for v in s["values"] if v > 0), "losses": sum(1 for v in s["values"] if v <= 0),
                       **{k: st[k] for k in ("ev_net_r", "sd_net_r", "se", "ci95_approx")},
                       "distinct_days": len(s["days"]),
                       "sample": "insufficient" if st["n"] < MIN_SAMPLE else "ok",
                       "label_kind": "simulated_counterfactual", "no_trade": dict(s["no_trade"])}
        if model != reference_model:
            diffs = [v - ref_values[k] for k, v in s["by_sample"].items() if k in ref_values]
            d = _stats(diffs)
            paired[model] = {"pairs": d["n"], "mean_diff_r": d["ev_net_r"], "se": d["se"],
                             "ci95_approx": d["ci95_approx"]}
    obs = None
    if observed:
        vals = [Decimal(v) for v in observed.values()]
        gaps = [ref_values[k] - Decimal(v) for k, v in observed.items() if k in ref_values]
        o, g = _stats(vals), _stats(gaps)
        obs = {"label_kind": "observed_paper_trade", "model_id": reference_model, "n": o["n"],
               "ev_net_r": o["ev_net_r"], "se": o["se"], "ci95_approx": o["ci95_approx"],
               "simulated_minus_observed": {"n": g["n"], "mean_r": g["ev_net_r"], "se": g["se"]},
               "comparable_with_simulated_arms": False}
    return {"arms": arms, "paired_vs_reference": paired, "reference_model": reference_model,
            "reference_observed": obs, "agreement_is_correctness": False, "basis": "market_outcomes",
            "limits": list(LIMITS), "sample_size_warning": any(a["sample"] == "insufficient" for a in arms.values())}
