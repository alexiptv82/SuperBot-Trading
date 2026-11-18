"""Cancello economico dell'avvio: la gara parte solo con costi coerenti, equi e approvati.

Blocca (codici fissi) se:
* tetto giornaliero, cadenza o max_tokens differiscono fra le tre AI (stesse opportunita');
* il prezzo in config di un modello e' SOTTO il listino (spesa sottostimata) o oltre 1,5x il listino di picco
  (quel modello verrebbe fermato dal tetto prima degli altri: confronto falsato);
* il budget dei 3 giorni di un modello OpenRouter supera il limite massimo di chiave accettato dal trasporto
  (la gara si fermerebbe da sola dopo pochi giorni);
* manca un budget totale approvato dall'utente, o il massimo teorico (3 x tetto x 3) lo supera.
Non cambia mai prezzi, tetti o cadenza: segnala soltanto. Nessuna rete.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional

from backend.v3.runner.config import RunnerConfig

TRIAL_DAYS = 3
MAX_PRICE_RATIO = Decimal("1.5")
PRICING_EVIDENCE = Path(__file__).resolve().parents[3] / "docs" / "v3" / "arena_model_pricing_20261117.json"
# Modello del listino usato come riferimento per ciascuna AI (DeepSeek diretto = stesso modello su OpenRouter).
LISTING = {"deepseek": "deepseek/deepseek-v4.1-flash", "qwen": "qwen/qwen3.7-plus",
           "minimax": "minimax/minimax-m3.1-flash"}
OPENROUTER = ("qwen", "minimax")


def listing_peak(pricing: Mapping) -> tuple[Decimal, Decimal]:
    """Prezzo di picco per milione (input, output): base e fasce orarie; esclusi i rincari per prompt > 256k token,
    che il trasporto non puo' raggiungere (messaggi <= 25.000 caratteri)."""
    rows = [pricing] + [o for o in pricing.get("overrides", []) if "min_prompt_tokens" not in o]
    million = Decimal(1_000_000)
    return (max(Decimal(str(r["prompt"])) for r in rows) * million,
            max(Decimal(str(r["completion"])) for r in rows) * million)


def load_evidence(path: Path = PRICING_EVIDENCE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def budget_gate(configs: Mapping[str, RunnerConfig], *, evidence: Mapping, approved_total_usd: Optional[Decimal],
                key_limit_usd: Decimal) -> dict:
    blockers: list[str] = []
    caps = {p: c.daily_cap_usd for p, c in configs.items()}
    if len(set(caps.values())) != 1:
        blockers.append("DAILY_CAP_DIFFERS_BETWEEN_AIS")
    if len({c.cycle_minutes for c in configs.values()}) != 1:
        blockers.append("CADENCE_DIFFERS_BETWEEN_AIS")
    if len({c.max_tokens for c in configs.values()}) != 1:
        blockers.append("MAX_TOKENS_DIFFERS_BETWEEN_AIS")
    prices = {}
    for p, c in configs.items():
        model = (evidence.get("models") or {}).get(LISTING[p])
        if not model:
            blockers.append(f"PRICE_EVIDENCE_MISSING:{p}")
            continue
        pin, pout = listing_peak(model["pricing_usd_per_token"])
        prices[p] = {"config_in": str(c.input_usd_per_million), "config_out": str(c.output_usd_per_million),
                     "listing_peak_in": str(pin), "listing_peak_out": str(pout)}
        if c.input_usd_per_million < pin or c.output_usd_per_million < pout:
            blockers.append(f"PRICE_BELOW_LISTING:{p}")
        elif c.input_usd_per_million > pin * MAX_PRICE_RATIO or c.output_usd_per_million > pout * MAX_PRICE_RATIO:
            blockers.append(f"PRICE_ESTIMATE_DISTORTS_COMPARISON:{p}")
    for p in OPENROUTER:
        if p in configs and configs[p].daily_cap_usd * TRIAL_DAYS > key_limit_usd:
            blockers.append(f"KEY_LIMIT_BELOW_TRIAL_BUDGET:{p}")
    worst = sum(caps.values(), Decimal(0)) * TRIAL_DAYS
    if approved_total_usd is None:
        blockers.append("TOTAL_BUDGET_NOT_APPROVED")
    elif worst > approved_total_usd:
        blockers.append("WORST_CASE_EXCEEDS_APPROVED_BUDGET")
    return {"blockers": blockers, "daily_caps_usd": {p: str(v) for p, v in caps.items()},
            "worst_case_trial_usd": str(worst), "approved_total_usd": None if approved_total_usd is None
            else str(approved_total_usd), "key_limit_usd": str(key_limit_usd), "prices_per_million": prices}
