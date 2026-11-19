"""Modelli fissi del laboratorio. Nessuna scelta automatica."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Prezzi letti da backend/v3/runner/runner_config.json. Sono la tabella del
# repository, non una fattura misurata sul conto.
_DEEPSEEK_IN = Decimal("0.30")
_DEEPSEEK_OUT = Decimal("1.20")
_FREE = Decimal("0")

# Fonte degli id gratuiti: documentazione REST di FreeLLMAPI, esempi espliciti
# (non le strategie auto:*). Il nome nudo gemini-2.5-flash può essere rimappato
# dal router su auto; qui si usa l'id di catalogo provider/modello.
_FREE_DOC = "https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md"
_CONFIG = "backend/v3/runner/runner_config.json"


@dataclass(frozen=True)
class ModelSpec:
    arm: str
    model_id: str
    provider: str
    version: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    price_basis: str
    source: str

    def public(self) -> dict:
        return {
            "arm": self.arm,
            "model_id": self.model_id,
            "provider": self.provider,
            "version": self.version,
            "input_usd_per_million": format(self.input_usd_per_million, "f"),
            "output_usd_per_million": format(self.output_usd_per_million, "f"),
            "price_basis": self.price_basis,
            "source": self.source,
        }


BASELINE = ModelSpec(
    arm="A",
    model_id="deepseek-flash",
    provider="deepseek",
    version="deepseek-flash",
    input_usd_per_million=_DEEPSEEK_IN,
    output_usd_per_million=_DEEPSEEK_OUT,
    price_basis="repository_config_not_invoice",
    source=_CONFIG,
)
CANDIDATE_B = ModelSpec(
    arm="B",
    model_id="google/gemini-2.5-flash",
    provider="google",
    version="gemini-2.5-flash",
    input_usd_per_million=_FREE,
    output_usd_per_million=_FREE,
    price_basis="documented_free_tier_not_measured",
    source=_FREE_DOC,
)
CANDIDATE_C = ModelSpec(
    arm="C",
    model_id="groq/llama-3.3-70b",
    provider="groq",
    version="llama-3.3-70b",
    input_usd_per_million=_FREE,
    output_usd_per_million=_FREE,
    price_basis="documented_free_tier_not_measured",
    source=_FREE_DOC,
)
CANDIDATES = (BASELINE, CANDIDATE_B, CANDIDATE_C)
_BY_ID = {item.model_id: item for item in CANDIDATES}


def forbid_auto_model(model_id: str) -> ModelSpec:
    """Rifiuta auto, fusion e qualunque id non presente nel catalogo fisso."""
    if type(model_id) is not str:
        raise ValueError("unpinned_model")
    folded = model_id.strip().lower()
    if folded.startswith("auto") or folded in {"fusion", ""} or ":" in model_id:
        raise ValueError("unpinned_model")
    found = _BY_ID.get(model_id)
    if found is None:
        raise ValueError("unpinned_model")
    return found
