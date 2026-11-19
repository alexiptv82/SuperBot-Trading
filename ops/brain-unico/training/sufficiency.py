"""Sufficienza del campione, secondo la decisione dell'utente (Issue #113, 19/11/2026). NON e' una prova di profitto.

- primo modello SHADOW esclusivamente offline: >= 300 esempi AMMESSI (`eligible_for_training`) e >= 20 giorni;
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


def report(rows: list, verified_inputs=None) -> dict:
    """`verified_inputs` e' IGNORATO (compatibilita'): conta solo `eligible_for_training`, calcolato una volta dal builder."""
    el = usable(rows)
    days = len({r["decision_day"] for r in el})
    n = len(el)
    status = ("promotion_considerable" if n >= PROMOTION["examples"] and days >= PROMOTION["days"] else
              "shadow_offline_ok" if n >= SHADOW["examples"] and days >= SHADOW["days"] else "insufficient")
    by_src: dict = {}
    for r in el:
        by_src[r["source_system"]] = by_src.get(r["source_system"], 0) + 1
    executed = [r for r in el if r["executed"]]
    reasons: dict = {}
    for r in rows:
        for x in r["ineligible_reasons"]:
            reasons[x] = reasons.get(x, 0) + 1
    return {"status": status, "eligible_examples": n, "distinct_days": days, "by_source": dict(sorted(by_src.items())),
            "realized_outcomes": len(executed), "counterfactual_simulations": n - len(executed),
            "losses": sum(1 for r in executed if (r["outcome"].get("net_pnl") or 0) < 0),
            "wins": sum(1 for r in executed if (r["outcome"].get("net_pnl") or 0) > 0),
            "thresholds": {"shadow_offline": SHADOW, "promotion_considerable": PROMOTION},
            "promotion_also_requires": list(PROMOTION_REQUIRES),
            "excluded_by_reason": dict(sorted(reasons.items())),
            "note": "soglie minime, non garanzie statistiche e non prova di profitto; le simulazioni controfattuali non sono profitto realizzato"}
