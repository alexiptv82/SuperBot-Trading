# AI Arena — Incremental Bitget public delta adapter (16 November 2026)

## What is verified on the user VPS
At 17:42 Europe/Rome the user ran `python3 -m unittest -q backend.v3.arena.test_frozen_market backend.v3.arena.test_compact_market backend.v3.arena.test_incremental_cache`; stdout was `Ran 35 tests in 2.036s ... OK`. The new delta adapter below has **not** yet been run on the VPS.

## Isolated new work
Research branch `work/arena-public-delta-adapter-20261116`, based on `work/arena-incremental-research-cache-20261116`. Only new script `deploy/scripts/arena-public-delta-adapter-20261116.py` and this doc. No change to runtime Brain, Falco, Toro, UI, cron, systemd, container, wallet, keys, journal, or Actions.

- Reuses `incremental_cache.delta_plan` and `incremental_cache.merge_delta`.
- Strictly fetches missing **closed bars**; resolves Bitget V2 rounded interval overlap by discarding rows outside the requested interval and requiring every exact timestamp within it. Rejects duplicates/gaps/invalid OHLC, with all-or-nothing merge.
- `fetch_and_merge(previous, target_asof_ms=..., public_get=...)` is explicit dependency injection: does not perform any HTTP itself; caller controls GETs. Enforces maximum **100 GETs** (25 symbols × 4 timeframes), and the previous cache must be complete and at most 30 minutes old.
- `--selftest` synthesizes a 25-symbol verified snapshot and 100 delta GETs, then checks the result is identical across DeepSeek/Qwen/MiniMax; failure paths for missing candle, duplicated candle, bad OHLC and stale cache. **Zero actual network**.
- `--probe` uses the existing bounded public Bitget V2 historical candle GET helper for **BTCUSDT only**, one most recent closed candle each on 1m/15m/1h/4h (max **4 public GETs**). Validates timestamps via the same closed-bar checker. No disk files, paid AI or trading commands. A failure is a diagnostic, not an instruction to restart or deploy.
- Causal snapshot means one target time fixed before the run; eventually production will also need a time freshness gate if execution takes too long. This research module never trades.

## Critical next gate
The full 25-symbol historical dataset from the user's earlier successful 575-GET scan was built in memory and **not saved as a persistent cache**. It cannot be recovered from its SHA digest. Before production-like incremental streaming we need a first **separate authorized bootstrap-to-cache** with one verified full-history pull, then incremental data refresh and atomic persistence. We should NOT repeat 575 GETs without that specific plan, since they have already been fetched once for diagnosis.

No actual Qwen/MiniMax/DeepSeek inference or 3 × 2,000 USDT PAPER trading has begun; no new backend services are installed. Existing short strategy Falco is preserved as-is. Dynamic 23-crypto universe + gold/silver is still provisional for trading categories; AI Arena 14-day comparison has not begun.

## Public API documentation
Bitget V2 `GET /api/v2/mix/market/history-candles`; 200 rows max, provider rounds to candle boundaries and can return an extra candle. https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market
