"""ROI-based research variants that mirror the user's description. Observation only.

The ROI is the LIFECYCLE net (realized partials + residual at a conservative exit) over the constant
reference margin, taken from the same Liquidation the machine uses; it is not a price percentage.
Values are the ones ChatGPT proposed on 19/10 and are NOT approved by the user: they are research
inputs, recorded with a hash in every event so any later change is visible.

Variant A  dynamic protection: once armed, floor = max(first_floor, peak - giveback_pp), monotone.
           A breach is judged against the floor that existed BEFORE this evaluation (a new level
           applies from the next evaluation, never retroactively).
Variant B  A plus a fixed target: exit signal as soon as roi >= checkpoint_roi.
Checkpoint the first evaluation at or above checkpoint_roi is recorded together with what the market
           said at that moment, so a human can see "close / partial" versus "let it run". It is
           information only: it never forces an exit by itself.

Neither variant executes anything. A decision here is the evaluation at cycle granularity (30 min):
the fill that would have followed is a separate, explicit modelling step in the replay.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math


@dataclass(frozen=True)
class RoiPolicy:
    version: str = "roi-research-1"
    arm_roi: float = 15.0
    first_floor_roi: float = 5.0
    giveback_pp: float = 5.0
    checkpoint_roi: float = 25.0

    def __post_init__(self):
        values = (self.arm_roi, self.first_floor_roi, self.giveback_pp, self.checkpoint_roi)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
            raise ValueError("non-finite roi policy")
        if not (0 < self.first_floor_roi < self.arm_roi <= self.checkpoint_roi and self.giveback_pp > 0):
            raise ValueError("invalid roi policy bounds")

    @property
    def config_hash(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RoiState:
    peak_roi: float | None = None
    armed: bool = False
    floor_roi: float | None = None
    last_eval_ms: int = -1
    a_exit_ms: int | None = None
    b_exit_ms: int | None = None
    checkpoint_ms: int | None = None


def step(state, *, roi, eval_ms, credible_reversal, features_valid, policy):
    """One evaluation. Returns (new_state, decision dict). Pure."""
    if not (isinstance(roi, (int, float)) and math.isfinite(roi)) or type(eval_ms) is not int:
        raise ValueError("invalid roi step input")
    if eval_ms <= state.last_eval_ms:
        return state, {"a": "HOLD", "b": "HOLD", "note": "evaluation already done", "checkpoint": None}
    peak = roi if state.peak_roi is None else max(state.peak_roi, roi)
    prior_floor = state.floor_roi
    breach = prior_floor is not None and roi <= prior_floor
    armed = state.armed or roi >= policy.arm_roi
    floor = prior_floor
    if armed:
        candidate = max(policy.first_floor_roi, peak - policy.giveback_pp)
        floor = candidate if floor is None else max(floor, candidate)
    a_exit, b_exit = state.a_exit_ms, state.b_exit_ms
    a = "HOLD" if a_exit is None else "DONE"
    b = "HOLD" if b_exit is None else "DONE"
    if a_exit is None and breach:
        a_exit, a = eval_ms, "EXIT_FLOOR"
    if b_exit is None and (breach or roi >= policy.checkpoint_roi):
        b_exit, b = eval_ms, ("EXIT_FLOOR" if breach else "EXIT_TARGET")
    checkpoint = None
    checkpoint_ms = state.checkpoint_ms
    if checkpoint_ms is None and roi >= policy.checkpoint_roi:
        checkpoint_ms = eval_ms
        if not features_valid:
            checkpoint = "DATI_NON_VALIDI"
        else:
            checkpoint = "CHIUDI_O_PARZIALE" if credible_reversal else "LASCIA_CORRERE"
    new = replace(state, peak_roi=peak, armed=armed, floor_roi=floor, last_eval_ms=eval_ms,
                  a_exit_ms=a_exit, b_exit_ms=b_exit, checkpoint_ms=checkpoint_ms)
    return new, {"a": a, "b": b, "roi": round(roi, 4), "peak_roi": round(peak, 4),
                 "floor_roi": None if floor is None else round(floor, 4), "armed": armed,
                 "checkpoint": checkpoint}
