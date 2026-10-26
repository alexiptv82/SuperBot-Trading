# Brain Portfolio Dashboard — review, no deploy

User authorized adapting the requested Flask/cli.py implementation to the actual
React/FastAPI PWA. Base rule-pool `6d7fbb0cc18a546b09cfe2d3ce1f0a3000e660ee`.
Branch `work/brain-portfolio-view`. `desk/cli.py`, PAPER Dashboard, LiveDashboard,
engine, pilot, prompts, risk, Dockerfiles and operational workflows/triggers are
unchanged. Only new navigation/route/API registration alongside the existing UI.

## Data source and isolation

Source verified in `work/brain-pilot-v1:backend/director/brain_pilot/pilot.py`:
Store is defined there, not store.py. `brain.sqlite3`: `state(id,body)` and
`events(seq,kind,body)`. Account name must be brain-paper, version brain-pilot-v1.
Native trade fields: close_ms/net/why/side(+1/-1), not ts/pnl/reason.

`BRAIN_DATA_DIR` is server-controlled, default `/opt/superbot-desk-data/brain`.
No client-supplied paths. No Store/Pilot/engine import, network, subprocess or
Docker socket. GET `/api/brain/status` uses existing session authentication,
registered before the SPA fallback, synchronous handler in FastAPI worker thread,
Cache-Control no-store. No mutation endpoint. No Flask dependency added.

SQLite URI mode=ro, uri=True, check_same_thread=False, query_only=ON, explicit
read transaction, connection always closed. Busy timeout and progress handler
share a 2-second monotonic deadline; Python row processing also checks it. No
checkpoint/journal-mode pragma. Do not use immutable=1: it can hide committed WAL.
SQLite may use its existing WAL shared-memory read marks; writer DB/WAL/log bytes
remain unchanged in tests. Future integration must mount the directory read-only
with writer-created WAL/SHM present and accessible; fail unavailable otherwise.
The deadline bounds SQLite waits/scans, not an uninterruptible filesystem syscall.

trade_history.jsonl: open(path, 'r'), seek to bounded final 256KiB, last20 valid
newline-complete records in reverse append order. Torn/malformed lines skipped;
bounded tail coverage is explicit. No whole-file scan. Missing export shows no
exported trades; authoritative statistics still use SQLite events. Export can lag
committed DB snapshot; cards are observations of those separate sources.

## Metrics

- Equity follows native cash + total_margin + gross floating. P&L vs1000 PAPER.
  Prices are last closed15m-bar marks, timestamp/staleness explicit; never called
  live ticks. Per-position last_bar_ms prevents a fresh global cycle from hiding
  an older symbol mark. Missing mark gives null equity/floating, not entry price.
- Statistics cover committed full event history, group native symbol/id/open_ms.
  Partials contribute to net; only fully closed positions count in trade count,
  win rate and per-trade average. All realized events contribute realized_pnl.
  Latest20 list is explicitly realizations, including partials.
- daily_stop reads persisted brain_daily; 20% limit, drawdown including open P&L,
  quota-used percentage, stored latch. Reader never resets/rolls UTC day; old day
  shows awaiting_utc_rollover until pilot updates it.
- Cycles count committed cycle events; model_attempt timestamp is an attempt,
  not a guarantee of a successful response.

## Existing-data limits (visible, not fabricated)

1. Pilot files do not contain Docker health, installed Git SHA or process start.
   System card reports health unknown, SHA/uptime unavailable, independently
   showing heartbeat freshness. Hardcoding1f2edeb6 or mapping stale heartbeat to
   Docker down would misrepresent runtime. No Docker access added for this UI.
2. Full historical model JSON is not archived. Bull/bear/verdict come from the
   newest retained pending decision or open position features, with timestamp and
   source. Market view comes from latest cycle event. These are labelled as last
   retained thesis and last attempted call, not asserted to be the same response.
   Closed-position thesis may no longer exist. No pilot changes in this feature.

## Validation and delivery

26 offline Python tests with native synthetic SQLite, including committed WAL,
multiple readers during uncommitted writer transaction, no reset/hash changes,
timeout/lock/corruption, schema/isolation, all-history stats, tail and auth.
React tests cover six cards, values, escaped model text, empty/unavailable states,
poll non-overlap, abort/cleanup and failed refresh clearing stale data.
Dedicated brain-view-ci tests Python3.10/3.11 and production React build; no secrets
or server tasks. Existing PAPER and LIVE source files remain byte-identical.

No deployment, restart, operational trigger, server query or container changes.
Normal PWA deployment uses main, whose history differs from rule-pool: later
release preparation must port/review these app changes explicitly, not merge
entire rule-pool into main. The existing app deployment mounts only Hawk/Bull,
so a future separately approved app release also needs the Brain directory mounted
read-only. No mount/workflow is changed here; until accessible the endpoint returns
unavailable. Review this integration requirement before any release approval.
