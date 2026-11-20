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

``score`` riassume per modello: aperture eseguibili ed etichettate, EV netto medio in R, vittorie/perdite,
e per le NO_TRADE gli ingressi sfavorevoli EVITATI e le occasioni MANCATE rispetto alla proposta di riferimento
(``reference_model``) sullo stesso campione. L'accordo con il riferimento non e' mai un criterio.
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
                "barrier": None, "net_bp": None, "net_r": None, "ambiguous": None}
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


def score(records: Sequence[Mapping], labels: Sequence[Mapping], *, reference_model: str) -> dict:
    """Per modello. ``avoided_unfavorable``: NO_TRADE dove la proposta di riferimento ha perso (net_r < 0);
    ``missed_favorable``: NO_TRADE dove ha guadagnato. Campioni senza etichetta di riferimento: non giudicati."""
    if len(records) != len(labels):
        raise ValueError("labels_mismatch")
    ref = {lab["sample_id"]: lab for r, lab in zip(records, labels)
           if r.get("model_id") == reference_model and lab["status"] == "labelled"}
    per: dict = defaultdict(lambda: {"records": 0, "opens": 0, "labelled": 0, "incomplete": 0, "not_executable": 0,
                                     "wins": 0, "losses": 0, "sum_net_r": Decimal(0), "no_trade": 0,
                                     "no_trade_judged": 0, "avoided_unfavorable": 0, "missed_favorable": 0,
                                     "invalid": 0})
    for r, lab in zip(records, labels):
        if r.get("sample_id") != lab["sample_id"] or r.get("model_id") != lab["model_id"]:
            raise ValueError("labels_mismatch")
        s = per[str(r.get("model_id"))]
        s["records"] += 1
        st = lab["status"]
        if st == "invalid":
            s["invalid"] += 1
        elif st == "no_trade":
            s["no_trade"] += 1
            other = ref.get(lab["sample_id"])
            if other is not None:
                s["no_trade_judged"] += 1
                if other["net_r"] < 0:
                    s["avoided_unfavorable"] += 1
                elif other["net_r"] > 0:
                    s["missed_favorable"] += 1
        else:
            s["opens"] += 1
            if st == "labelled":
                s["labelled"] += 1
                s["sum_net_r"] += lab["net_r"]
                s["wins" if lab["net_r"] > 0 else "losses"] += 1
            else:
                s[st] += 1
    arms = {}
    for model, s in sorted(per.items()):
        s["ev_net_r"] = (s["sum_net_r"] / s["labelled"]).quantize(Decimal("0.0001")) if s["labelled"] else None
        s["sum_net_r"] = s["sum_net_r"].quantize(Decimal("0.0001"))
        arms[model] = s
    return {"arms": arms, "reference_model": reference_model, "agreement_is_correctness": False,
            "basis": "market_outcomes", "sample_size_warning": any(a["labelled"] < 30 for a in arms.values())}
