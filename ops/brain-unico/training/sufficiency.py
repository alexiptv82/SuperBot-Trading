"""Sufficienza del campione, secondo la decisione dell'utente (Issue #113, 19/11/2026). NON e' una prova di profitto.

- primo modello SHADOW esclusivamente offline: >= 300 esempi etichettati e verificati e >= 20 giorni;
- per CONSIDERARE la promozione: >= 1000 esempi, >= 45 giorni, piu' OOS cronologico con embargo, confronto con baseline,
  calibrazione, EV netto, drawdown, sufficienza delle classi e approvazione esplicita (condizioni qui solo elencate).
Se insufficiente: continuare la raccolta, senza addestrare ne' promuovere.
"""
from __future__ import annotations

from split import usable

SHADOW = {"examples": 300, "days": 20}
PROMOTION = {"examples": 1000, "days": 45}
PROMOTION_REQUIRES = ("chronological_oos_with_embargo", "baseline_comparison", "calibration", "net_ev", "drawdown",
                      "class_sufficiency", "explicit_user_approval")


def is_labeled_verified(r: dict, verified_inputs: set) -> bool:
    """Etichettato e verificato: input verificato (audit di catena / riconciliazione), feature presenti, etichetta completa,
    nessuna chiusura manuale usata come esempio da imitare."""
    o = r["outcome"]
    return (r["provenance"]["input_id"] in verified_inputs and r["features"] is not None and r["label_complete"]
            and not o.get("is_manual") and (o["status"] in ("closed", "not_executed")))


def report(rows: list, verified_inputs: set) -> dict:
    us = usable(rows)
    good = [r for r in us if is_labeled_verified(r, verified_inputs)]
    days = len({r["decision_day"] for r in good})
    n = len(good)
    status = ("promotion_considerable" if n >= PROMOTION["examples"] and days >= PROMOTION["days"] else
              "shadow_offline_ok" if n >= SHADOW["examples"] and days >= SHADOW["days"] else "insufficient")
    by_src: dict = {}
    for r in good:
        by_src[r["source_system"]] = by_src.get(r["source_system"], 0) + 1
    executed = [r for r in good if r["executed"]]
    return {"status": status, "labeled_verified_examples": n, "distinct_days": days, "by_source": dict(sorted(by_src.items())),
            "executed": len(executed), "not_executed": n - len(executed),
            "losses": sum(1 for r in executed if (r["outcome"].get("net_pnl") or 0) < 0),
            "wins": sum(1 for r in executed if (r["outcome"].get("net_pnl") or 0) > 0),
            "thresholds": {"shadow_offline": SHADOW, "promotion_considerable": PROMOTION},
            "promotion_also_requires": list(PROMOTION_REQUIRES),
            "excluded": {"duplicates": sum(1 for r in rows if r["provenance"].get("duplicate_of")),
                         "manual_closes": sum(1 for r in us if r["outcome"].get("is_manual")),
                         "unverified_input": sum(1 for r in us if r["provenance"]["input_id"] not in verified_inputs),
                         "without_features": sum(1 for r in us if r["features"] is None),
                         "labels_incomplete": sum(1 for r in us if not r["label_complete"])},
            "note": "soglie minime, non garanzie statistiche e non prova di profitto"}
