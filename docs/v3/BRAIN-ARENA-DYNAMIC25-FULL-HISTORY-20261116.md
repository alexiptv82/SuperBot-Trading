# Brain AI Arena — Three-market full history PASSED; full 25-market research gate

Date: 16 November 2026. Branch: `work/arena-dynamic25-fullhistory-20261116`.
This is an isolated public-data research experiment; no merge/deploy.

## Real VPS proof provided by user (16:26 Europe/Rome)

The script `deploy/scripts/arena-shared-three-fullhistory-20261116.py` completed:
- `ARENA_SHARED3 SELFTEST=PASS_OFFLINE`, 69 simulated pages, zero API requests in selftest.
- `shared_asof_ms=1794842754685`.
- `BTCUSDT_historical_pages=23`, `XAUUSDT_historical_pages=23`, `XAGUSDT_historical_pages=23`: 69 real PUBLIC historical Bitget GETs.
- Full Brain warmup (closed only): 1m 60, 15m 2893, 1h 733, 4h 193 per symbol.
- `combined_SHA256=ecb17713d8e6cede839296a7bbb05ffc89490482c175b47f5a58d41a24a41fdc`.
- DeepSeek/Qwen/MiniMax `snapshot_sha256` identical to the combined hash. This was the same **prepared data**, NOT three actual paid inference decisions.
- `classification=PROVISIONAL_NOT_TRADE_APPROVED`, `orders=0 paid_AI_calls=0 services_changed=0`, `RESULT=THREE_MARKET_FROZEN_HISTORY_VERIFIED_NO_DEPLOY`.

The 100/100 multi-timeframe short-window test and the new 69-history GET sample are independent checks. Both succeeded on the VPS, but neither authorizes trade execution.

## New experimental extension

Script `deploy/scripts/arena-dynamic25-fullhistory-20261116.py`:

1. Dynamically requests a fresh CoinGecko market-cap ranking and Bitget public futures contracts + tickers (three GETs) and uses the revised provisional 23-crypto preview, with stablecoin/wrapped-name heuristic exclusions and ticker/baseCoin checks.
2. Rejects an incomplete or duplicate universe, unexpected CoinGecko IDs, mismatched provisional metadata or any nonapproved status. Reserves XAUUSDT and XAGUSDT as the remaining two of exactly 25. **Native/non-native classification is not yet exhaustive; a preview PASS is NOT a trading whitelist.**
3. Freezes `asof_ms` once after the three catalog responses. Paginates every market's 1m/15m/1h/4h history using the exact Brain ATR warmup minima (60/2893/733/193), with no fill/interpolation. Invalid/missing/old bars abort the entire snapshot. Keeps **zero orders, zero AI calls, zero secrets, zero service changes**.
4. Limits the 25-market history to `25 × 23 = 575` GETs plus the 3 ranking/catalog GETs (absolute maximum 578 public HTTP GETs). Throttle 0.2 seconds for each historical GET, no retries or background jobs. Prints a short progress line for each completed symbol.
5. On full success, creates a canonical frozen snapshot in memory only, SHA-256 full digest, and checks identical bytes/hash for all 3 model lanes. Does **not** send the batch to DeepSeek/Qwen/MiniMax, start a bot, execute a trade or write operational data.
6. Modes: `--selftest` performs in-memory synthetic 25-market validation, including 575 simulated history pages; `--plan` performs just the three GETs for the provisional roster; `--full25` performs the bounded 578-public-GET full experiment. A failed stage must not silently transition into the next stage.

### Important limitations

- The code is written and statically reviewed. The new full-25 `--selftest` and `--full25` have **not** yet been executed on the VPS and should not be labeled PASS.
- The snapshot is a historical, fixed-time research artifact: if the 25-market fetch lasts across several new candles, its old `asof_ms` means it must never be passed straight into live trading after completion. The future operational runner needs freshness checks and local caching/incremental updates.
- `for_provider` returning equal bytes proves only a consistent input generator; models have NOT received them or been evaluated.
- Proposed operational architecture after verified data: cache long ATR history locally; update only closed candles and derived indicators, then provide the same compact, timestamped market view + candidate shortlist to each model. The raw 25-market historical dataset should not be sent to paid model APIs.

## Preserve operational boundaries

- Falco SHORT strategy backed up on GitHub branch `archive/falco-short-before-ai-arena-20261116`; effective VPS runtime/data backup must be confirmed before any future pause, reset or replacement. Do not alter Falco during research.
- Toro left aside; Brain DeepSeek runner unchanged, no reset, no new Qwen/MiniMax portfolio started. Do not declare the 14-day comparison underway.
- Qwen and MiniMax keys had individually 2 USD maximum, user declared 10 USD OpenRouter account recharge, **not independently rechecked** in this phase. No paid calls made by this research script.
