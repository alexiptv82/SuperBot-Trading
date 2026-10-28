# Brain AI Libero — V2 scalp reframe (28 October 2026)

## User mandate
Keep exactly ONE independent Brain AI Libero PAPER runtime. No new parallel running Brain.
The operator wants intelligent, active intraday/scalping trading, not a fixed
time limit, mandatory 30x leverage, 350 USD position size, or trade quota.
External PDF research and a personal BTC short are OPTIONAL hypotheses,
not strategies to copy, proofs of profitability or system instructions.

## Evidence from live PAPER read-only audit
V1 SHA: `a914803a15c2d8a5fa01021f11c4def4caf82a76`.
As of 2026-10-28T05:47Z: 25 completed positions, gross -16.069 USD,
fees 48.743 USD, funding .123 USD, net -64.935 USD; 8 winners.
The AI usually REQUESTED 75-150 USD margin and 10-15x leverage.
Do not falsely attribute these values to hard forced sizing.
There were THREE open V1 positions, ARB/BTC/SOL, at the check.

**Operator-directed protected pause CONFIRMED** by GitHub Actions
`40640135126`: single V1 container remains alive with native local stop and
target enforcement; no new AI openings. A verified SQLite backup was saved
under `/opt/superbot-backups/brain-free-reframe-*`, independent backup
integrity and row counts checked. No positions were forcibly closed.

## V2 proposed actual code
- `Config`: 5 max simultaneous symbols, 1750 USD TOTAL PAPER margin;
  2000 USD original reference capital. No minimum margin or leverage,
  per-position sizing cap or count quota; exchange and stop feasibility
  remain hard safety.
- Full AI assessment each 5 minutes; position management every 2 minutes;
  physical protection continues at 5-second polling.
- Adds closed 5m market candles and transparent OHLCV-derived
  support/resistance and approximate typical-price VWAP features.
  No fabricated order-flow / depth / thousands of data points.
- Shows explicit estimated roundtrip fee and slippage in every AI prompt,
  with unquantified spread and funding explicitly marked unknown.
- Studies operator PDFs as source-labelled unverified nonbinding research
  candidates (momentum 5m, reversion 1m/5m, OI+taker flow, optional lead/lag).
- Profit metric NET of trading costs. Avoid pointless partial closes,
  micro-profit churn, and leverage for leverage's sake.
- Operator/example position size 200–350 USD is only a preference.
- Accounts, classic Hawk/Bull, prior learning, Telegram and trades
  NEVER reset merely by changing the operator mandate.

## Mandatory production preflight — NOT READY UNTIL FLAT
1. Confirm only one `superbot-brain-free` runs, PAPER, pinned old SHA.
2. Confirm `pause.flag`, state `paused=true`, live risk protections,
   and **positions={}**; never forcibly discard open V1 positions.
3. Stop the V1 writer in a controlled way only AFTER flat.
4. In a pinned V2 checkout, call `director.brain_free.reframe` with explicit
   approval and old/new full commit SHAs. It refuses if not paused,
   writer lock is held, any position open, or an unexpected SHA is found.
5. Verify SQLite backup (integrity, exact tables, restore) and preserve
   ALL existing events, model requests and Telegram outbox.
6. Migration stores V1 full state as `experiment_reframed`, begins a new
   168-hour V2 evaluation while keeping **remaining PAPER cash**.
   **No hidden top-up to 2000 USD**. V2 baseline = actual migrated equity.
7. Update and verify the read-only dashboard to display limits dynamically
   and separate new-run PnL from lifetime PnL; do not merge/deploy
   dashboard before the coordinated cutover.
8. Launch new image with EXACT same single container name/data directory;
   verify paper mode, fresh market feed, heartbeat, AI response,
   cost-report fields, margin/slot limits and local protection.
   Only AFTER postflight and verified absence of duplicate workers,
   remove `pause.flag` and verify an AI cycle.
9. On any failure, remain paused and restore verified original backup
   and V1 image; do not create a second Brain or delete account data.

## Explicit deployment status
**NO V2 DEPLOY HAS OCCURRED.** Work resides in isolated code and UI branches.
Hawk/Bull PAPER and prior Brain archives are untouched.
All coding in this branch is non-operative until a separately audited
guarded replacement (and zero open positions) is possible.

## Verification / known risks
- Offline unit tests and Docker build via branch-specific GitHub Actions.
- Read-only dashboard backend/frontend tests via separate branch.
- Changing sizing/leverage does NOT inherently improve expectancy:
  trading costs and potential loss scale with notional.
- 5-minute AI cadence can increase provider spend; track billed costs
  and reject stale decision responses.
- Paper fill simulation cannot guarantee future real execution or profits.
