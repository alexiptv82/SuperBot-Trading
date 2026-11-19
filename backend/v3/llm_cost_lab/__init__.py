"""Laboratorio SHADOW per il costo dei modelli. Non è il Brain e non apre posizioni."""

from backend.v3.llm_cost_lab.models import CANDIDATES, BASELINE, forbid_auto_model
from backend.v3.llm_cost_lab.shadow import ShadowSession

__all__ = ["BASELINE", "CANDIDATES", "ShadowSession", "forbid_auto_model"]
