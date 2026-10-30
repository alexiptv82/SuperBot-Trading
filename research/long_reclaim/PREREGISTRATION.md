# Reclaim v1 — research only, 30 October 2026

Frozen before any historical economic result. This is a new experiment, not a
continuation that relaxes Claude's failed regime-v2 acceptance criteria.

Observation: 20 preceding closed candles define support/resistance and median
volume. The reaction candle breaches a level and closes back inside. Its volume
must reach 1.5 times the preceding median. The next candle must close beyond the
reaction high (LONG), or low (SHORT). Event time is that confirming close, never
the earlier reaction. Same arithmetic mirrored for both directions. No pivots
requiring future candles. Primary timeframe 5m; 1m/15m supported for separate
registered experiments, not simultaneous optimization. This is an OHLCV proxy,
not evidence of CVD, passive liquidity, or institutional absorption.

Current output is diagnostic only, with execution_permission=false. No import
from runtime, no AI input and no classic scorer patch. Stable event IDs allow a
future collector to deduplicate; the pure function does not persist dedup state.

Economic protocol before promotion: verify dataset coverage/venue/instrument,
freeze execution rules and costs, and compare against baseline and matched-time
controls. Use next available executable quote after confirmation, stop beyond
reaction extreme plus a fixed instrument tick, target 2 initial price-risk units,
maximum holding time 12 primary candles. Compare conservative intrabar ordering
(stop first when ambiguous), fees, slippage and funding when known. These exit
rules are experimental labels only, not new production exits. Reject events
with unavailable prices/costs rather than manufacturing measured net results.
Report uncosted labels separately if necessary; they cannot pass promotion.

Report independent events and clustered uncertainty by time/symbol, gross and
net R, drawdown, coverage and comparison against unchanged baseline, including
SHORT opportunity cost under shared portfolio capacity. Positive mean R alone
is insufficient. Use a new chronological holdout, register its exact dates and
hashes before reading outcomes; the already inspected 18 months are development
data, not untouched validation. No historical run or profitability claimed in
this commit. Missing true aggressor-side trades means CVD experiment unavailable.
