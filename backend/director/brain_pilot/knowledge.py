"""Curated engineering/research provenance, explicitly distinct from trade evidence.

Only documented facts in reviewed source files. No unverified causal learning,
raw user prose, credentials, collector imports or recovered signal formulas.
"""
from .learning import digest

RESEARCH_REV = "bd9b04277dda8ed6a1ab310220a9b96e6234a0ed"
BRAIN_REV = "1f2edeb6182029adc96ba7218ad145a7503472a3"
GUARDIAN_REV = "63641f7059a977368f8bb8aecc517f7a7c74cbce"


def catalog(now_ms=None):
    notes = [
        {"available_after_ms":1793022958000,"topic": "counter_evidence", "kind": "documented_code_change", "scope": "Brain",
         "fact": "New exposure requires nonempty bull and bear scenarios, verdict and structured invalidation.",
         "purpose": "Make contrary evidence explicit; do not infer that directional bias or profitability is solved.",
         "effectiveness": "unverified_by_this_catalog",
         "evidence": {"repository": "alexiptv82/SuperBot-Trading", "revision": BRAIN_REV,
                      "paths": ["backend/director/brain_pilot/pilot.py", "backend/director/brain_pilot/prompt_builder.py"]}},
        {"available_after_ms":1793001132000,"topic": "profit_protection", "kind": "documented_code", "scope": "Hawk/Bull research context",
         "fact": "Profit Guardian source defines ROI/giveback review and close/partial/hold proposals; its module declares SHADOW ONLY.",
         "purpose": "Distinguish intention, code presence, runtime activation and demonstrated outcomes; none implies the others.",
         "effectiveness": "runtime_hook_and_profit_effect_not_verified_by_this_catalog",
         "evidence": {"repository": "alexiptv82/SuperBot-Trading", "revision": GUARDIAN_REV,
                      "paths": ["backend/desk/profit_guardian.py"]}},
        {"available_after_ms":1789719405000,"topic": "microstructure_research", "kind": "historical_research_not_reproduced", "scope": "Research Console BTC/ETH",
         "fact": "The 36h report rejected standalone directional alpha below its 15bps hurdle; short-horizon execution candidates remain research only.",
         "purpose": "Do not transfer millisecond/second execution effects into a 15m direction rule or size multiplier.",
         "effectiveness": "frozen_engine_not_configured_and_raw_reproduction_pending",
         "evidence": {"repository": "alexiptv82/SuperBot-Research-Console", "revision": RESEARCH_REV,
                      "paths": ["audit/cp36_x/MULTIVENUE_V2_CHECKPOINT_36H/CHECKPOINT_36H_REPORT.md",
                                "backend/frozen_engine.py", "backend/recovery/harness.py"]}},
    ]
    return [dict(n, id=digest(n)) for n in notes if now_ms is None or n["available_after_ms"] <= now_ms]
