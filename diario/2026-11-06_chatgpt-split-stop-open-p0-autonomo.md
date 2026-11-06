# SuperBot V3 — Integrazione autonoma del runner PAPER: uscite indipendenti, OPEN serializzato, perdita giornaliera persistente

**Checkpoint:** 6 novembre 2026 | Autore/revisore: ChatGPT GPT-6 (Claude temporaneamente non disponibile) | **Modalità:** PAPER, sandbox locale isolata. NESSUN merge, deploy, VPS, riavvio, push del codice, cambio storico o capitali.

## Provenienza e confini
- Runner baseline PR #57 al commit `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421`; PR #61 dashboard al commit `a9044b6759da327b44da04f9e7f51e211d44e03f`. Entrambe ancora draft e separate alla verifica.
- ZIP `superbot-trading-e25c8dd.zip`: **385 file originali**, di cui **381 byte-identici e 4 modificati soltanto nella sandbox**: `backend/v3/runner/cycle.py`, `runner.py`, `wiring.py`, `daily_loss.py`.
- Seven new source modules packaged including exit_service/exit_worker/post_ai_guard/open_serial/legacy_exit_fence/cutover_preflight/paper_close_fence; proposed opt-in patch is NOT applied to GitHub; CLI legacy default unchanged.

## Integrazione PAPER sviluppata e verificata
- `cycle.py`: opt-in `require_open_commit=True` requires a real persisted `paper_open` event receipt matching run, symbol and decision. NO fallback to direct `execute_paper` when sidecar split mode is requested; sanitizes bad callback errors.
- `runner.py`: explicit legacy (default) versus sidecar; sidecar mode must not run old `_monitor` or manual commands and must confirm worker health before/after DeepSeek. Fresh current clock after model call updates heartbeat accurately. If exit worker becomes unhealthy during AI, no OPEN and status halt.
- `wiring.py`: `build_runner(exit_mode='sidecar', desk_mode='paper')` strict opt-in, existing journal/budget/run checks, live pause, mandate, AI budget, data freshness, current quote and exit lease; CLI not enabled for split while runtime gate remains unmet.
- `daily_loss.py`: fresh post-AI evaluation invalidates one-minute cached snapshot, latch at daily-loss halt 50% persisted and re-read; if storage fails, OPEN veto. 35% warn/50% halt unchanged.
- **`paper_close_fence.py` NEW**: exit service and OPEN serial writer use the same exclusive POSIX flock `.brain-paper-open.lock` while mutating PnL or authorizing/opening. Exit worker marks degraded when cannot acquire; no fake healthy heartbeat. Cross-process tests with mock data passed. Security checks for symlink, hard link and insecure permissions.
- Cooperating readers/writers only: existing VPS legacy process may ignore the shared locks. This work does NOT make the runtime globally atomic yet.

## Test and packaging evidence
- `PYTHONPATH=.:backend python -m pytest backend/tests/test_v3_*.py -q -p no:cacheprovider --disable-warnings` -> **4469 passed in 155.06s**, exit 0, log `superbot_split_LOCKED_full.log`.
- Targeted regression runner/risk/journal/close/exits -> **306 passed in 11.56s**, exit 0.
- Two new test modules from `/tmp` -> **39 passed in 1.75s**, exit 0. Includes real multiprocess lock, worker stop while AI blocked, risk/budget/pause/mandate mid-AI, fresh clocks, persistent loss latch and journal receipt cross-check.
- `git apply --check` + `patch --dry-run -p1` against fresh PR57 source -> PASS; patch roundtrip exact bytes of all four modified sources. All work isolated; no full CRA/Jest, systemd or VPS performed.

## Artifacts saved in ChatGPT Library `/SuperBot-Trading`
- `SuperBot-V3-Integrazione-Autonoma-Split-Stop-Open-P0-2026-11-06.zip`: SHA256 `39388a989afea0dbaf9805fef14695a70d5b9a390b9e5c5de2b9ee5eb36b32ee`, libfile `libfile_a341d340765c819188942c3a4711adab`.
- `RAPPORTO_SUPERBOT_V3_INTEGRAZIONE_AUTONOMA_SPLIT_P0_2026-11-06.md`: SHA256 `c278ad094227a3e366752dc02f58d477174b0976db348732ef8208aa1711c7dd`, libfile `libfile_e495b3c7544081919149d93159a631c3`.
- Included patch `patches/P0-SPLIT-PAPER-CYCLE-RUNNER-WIRING-DAILY-LOSS-OPTIN.patch` SHA256 `131b727b20f65323b2c400d9c59ff587da69db195c8c3796237d13b307059f04`.

## Release decision: NO-GO
- Legacy runner actually operating on VPS does NOT yet cooperate in OPEN/CLOSE exclusive locks, no controlled cutover tested, sidecar not supervised/installed, no verified service failover and alerting, no dashboard PR61 Jest/CRA unification, S0/S1/S2 remain isolated/reconstructed modules.
- No new code branch push/merge or VPS touch occurred. This can be reviewed/combined on a separate PR only after controlled rollout test, legacy exit owner handover, complete CI and explicit user OK.
- Immutable PAPER risk policy: 2% trade risk, 5% open risk, daily warning 35%, halt 50%, absolute equity floor 450 USDT; no forced midnight exits, no memory overwrite.

**Next:** integrate reviewed patch into an isolated branch, test cutover while portfolio flat, verify live stop/close processes under simulated 30s model delay and real process crash, audit systemd watchdog, finalize UI and full CI, then request explicit authorization before any VPS action.