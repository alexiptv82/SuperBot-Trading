# 2026-11-02 — Pool unhealthy: XRP paper max-hold/Donchian contradiction, isolated fix proven CI

## Grounded VPS evidence, screenshots from Termius
- Pool was `unhealthy` with 9 failed healthchecks and last successful cycle ~16,192 minutes ago (around 11 days). Falco/Hawk and Toro/Bull `healthy`; Brain Free paused `paused=True`, 0 open PAPER, AI Shadow pause proven by post-flag cycle `skip=pausa`, `called=False`; 1087/3 model call counters unchanged.
- Pool log repeats `ImmutableTradeError: trade chiuso modificato (exit_t): ('CTL_S2_top10', 1, 'paper', 'XRP/USDT:USDT', 1792461600000)`.
- Original `pool.db`, read only via SQLite mode=ro, records XRP control `entry_t 1792461600000` (2026-10-20 02:00 UTC), `closed/time` exit **2026-10-22 01:00 UTC**.
- Using **real deployed original code** `strategy_lab.py` + `replay.control_records` and 35,449 cached public 15m XRP candles, read-only `docker exec` from the user: exactly one matching control entry now calculates `closed/donchian` exit **2026-10-22 02:00 UTC**, +1h.
- Root bug identified in `strategy_lab.simulate_exit`: inside `j <= last = e+max_hold-1`, signal check `if cfg.donch_exit and j+1<n` can return `j+1`, beyond `max_hold` if new candle appears after a previously valid terminal time exit. Immutable journal correctly blocks retroactive updates.

## Isolated research correction on GitHub
- Branch `work/pool-donchian-maxhold-immutability-20261102` created from `rule-pool`.
- Single logical fix in `backend/strategy_lab.py`: `if cfg.donch_exit and j + 1 <= last and j + 1 < n:`. This preserves the terminal 48h time exit, allows earlier Donchian exit within the hold duration, and does not disable Journal immutability.
- New 6 regression tests in `backend/tests/test_pool_donchian_maxhold_regression.py`: test BOTH long/short, exact Oct 20/22 timestamps, valid earlier Donchian next-open, immutable SQLite in-memory closed trade after a new 1H candle arrives.
- Added isolated `.github/workflows/pool-donchian-immutability-ci.yml`, NO secrets/VPS/wallet/order actions.
- **GitHub Actions run 41425516433 SUCCESS: 69/69 tests PASS** (original strategy lab, rule pool, rule pool runner, 6 new cases); static gate `POOL_IMMUTABLE_MAX_HOLD_STATIC_GATE=PASS`.
- **GitHub Draft PR #28** https://github.com/alexiptv82/SuperBot-Trading/pull/28 targeting `rule-pool`, NOT merged nor deployed.

## Remaining approval gates — do NOT auto-deploy
1. Shared `strategy_lab.simulate_exit` affects all strategies using this simulator; must audit **all existing closed PAPER journal trades** against candidate corrected replay using snapshots of existing VPS cache and DB in **read-only mode**. Other old incorrectly stored late Donchian exits may need versioned correction/migration; never silently rewrite history or remove immutability guard.
2. Release only after explicit user approval and full reversible backup, restore check, no new data deletions, CI and journal read-only preflight PASS. `Pool healthy` only after genuine successful 15m cycle; do not fake last_ok timestamp.
3. Falco and Toro operational untouched; legacy Brain Free/Pilot/Shadow pauses unchanged; no orders, merge or deploy.

This note records PROVEN facts and distinguishes isolated CI from the production VPS still unhealthy.