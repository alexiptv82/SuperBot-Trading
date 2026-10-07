"""
SuperBot V0.5 — Backtest Harness (Phase 1)
============================================

Offline, read-only research tool. It does NOT touch the live bot, the
database, the exchange order book, or any running process. It:

  1. Downloads historical 1-minute OHLCV candles from BitGet via ccxt
     (pure market-data read — no orders, no keys required beyond the
     ones already in .env for the ccxt client to authenticate reads).
  2. Resamples that 1-minute series into 15-minute and 1-hour bars
     itself, so every window handed to the strategies is internally
     consistent (no risk of misaligned timestamps between timeframes
     fetched separately).
  3. Walks forward through the series with the SAME window shape the
     live bot uses (last 100 bars per timeframe), builds a
     StrategyContext at each step, and asks all three V0.5 strategies
     for a decision.
  4. For every actionable (non-HOLD) decision, measures what actually
     happened over the next `--holding` 1-minute bars and records that
     outcome in basis points into the StrategySelector via
     record_result(). This is what "warms up" the champion/challenger
     stats before the shadow run goes live.
  5. Prints a leaderboard per regime and dumps the selector's full
     state to a JSON file.

IMPORTANT — this script produces a *standalone* state file. Loading
that state into the live bot_engine.py process (via StrategySelector.
load_state()) is a deliberate separate step, not wired yet. That keeps
this phase purely analytical: nothing it writes can affect production
until a human explicitly decides to load it.

Usage examples
--------------
    # Single pair, defaults (2000 1m candles, 15-bar forward horizon)
    python backtest_harness.py --symbols BTCUSDT

    # All configured trading pairs, into one shared selector (matches
    # how bot_engine.py runs ONE selector across every symbol)
    python backtest_harness.py

    # Longer history, slower stride (fewer, less-overlapping samples)
    python backtest_harness.py --candles 5000 --stride 10 --holding 20
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
import time
from pathlib import Path
from typing import Any

from config import config
from exchange import exchange as exchange_wrapper

try:
    from strategies import (
        TrendFollowingStrategy,
        MeanReversionStrategy,
        MomentumStrategy,
        StrategyContext,
    )
    from strategy_selector import StrategySelector
except ImportError:
    from backend.strategies import (  # type: ignore
        TrendFollowingStrategy,
        MeanReversionStrategy,
        MomentumStrategy,
        StrategyContext,
    )
    from backend.strategy_selector import StrategySelector  # type: ignore


ONE_MINUTE_MS = 60_000
WINDOW_SIZE = 100  # matches bot_engine.py's last-100-candles window per timeframe


# ─────────────────────────────────────────────────────────────────────────────
# Data fetching + resampling
# ─────────────────────────────────────────────────────────────────────────────

def fetch_1m_history(symbol: str, total_candles: int, batch_limit: int = 1000) -> list[list[float]]:
    """Page backwards-to-forwards through ccxt fetch_ohlcv to assemble a long
    1-minute series. Returns candles sorted ascending by timestamp, deduped.
    """
    client = exchange_wrapper.exchange
    now_ms = client.milliseconds()
    since = now_ms - total_candles * ONE_MINUTE_MS
    collected: dict[int, list[float]] = {}

    while True:
        attempt, batch = 0, None
        while attempt < 3:
            try:
                batch = client.fetch_ohlcv(symbol, "1m", since=since, limit=batch_limit)
                break
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                print(f"  [warn] fetch_ohlcv retry {attempt}/3 after error: {exc}", file=sys.stderr)
                time.sleep(1.0 * attempt)
        if not batch:
            break

        for c in batch:
            collected[int(c[0])] = c

        last_ts = int(batch[-1][0])
        if last_ts <= since:
            break  # no progress — stop to avoid an infinite loop
        since = last_ts + ONE_MINUTE_MS

        if len(batch) < batch_limit or len(collected) >= total_candles:
            break  # caught up to the most recent data, or have enough

        time.sleep(0.2)  # be polite to the exchange

    ordered = sorted(collected.values(), key=lambda c: c[0])
    return ordered[-total_candles:] if len(ordered) > total_candles else ordered


def resample(candles_1m: list[list[float]], minutes: int) -> list[list[float]]:
    """Aggregate 1m candles into `minutes`-sized bars. Only complete buckets
    are kept (a bucket with fewer than `minutes` 1m candles — typically the
    first or last — is dropped so every bar represents a full period)."""
    bucket_ms = minutes * ONE_MINUTE_MS
    buckets: dict[int, list[list[float]]] = {}
    for c in candles_1m:
        key = int(c[0]) - (int(c[0]) % bucket_ms)
        buckets.setdefault(key, []).append(c)

    out: list[list[float]] = []
    for key in sorted(buckets):
        group = buckets[key]
        if len(group) < minutes:
            continue
        o = group[0][1]
        h = max(c[2] for c in group)
        l = min(c[3] for c in group)
        cl = group[-1][4]
        v = sum(c[5] for c in group)
        out.append([key, o, h, l, cl, v])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Backtest loop
# ─────────────────────────────────────────────────────────────────────────────

def run_symbol(
    symbol: str,
    strategies: list,
    selector: "StrategySelector",
    *,
    total_candles: int,
    holding: int,
    stride: int,
    quiet: bool,
) -> dict[str, Any]:
    print(f"\n=== {symbol} ===")
    print(f"Fetching {total_candles} x 1m candles...")
    candles_1m = fetch_1m_history(symbol, total_candles)
    if len(candles_1m) < WINDOW_SIZE + holding + 1:
        print(f"  [skip] not enough 1m data returned ({len(candles_1m)} candles)")
        return {"symbol": symbol, "steps": 0, "signals": 0, "skipped": 0}

    candles_15m = resample(candles_1m, 15)
    candles_1h = resample(candles_1m, 60)
    end_ts_15m = [c[0] + 15 * ONE_MINUTE_MS for c in candles_15m]
    end_ts_1h = [c[0] + 60 * ONE_MINUTE_MS for c in candles_1h]

    print(f"  1m={len(candles_1m)} bars, 15m={len(candles_15m)} bars, 1h={len(candles_1h)} bars")

    steps = 0
    signals = 0
    skipped = 0
    regimes_seen: set[str] = set()
    last_report = time.time()

    i = WINDOW_SIZE - 1
    end = len(candles_1m) - holding - 1
    while i <= end:
        t = candles_1m[i][0]
        count_15m = bisect.bisect_right(end_ts_15m, t)
        count_1h = bisect.bisect_right(end_ts_1h, t)

        if count_15m < WINDOW_SIZE or count_1h < WINDOW_SIZE:
            i += stride
            continue

        window_1m = candles_1m[i - WINDOW_SIZE + 1 : i + 1]
        window_15m = candles_15m[count_15m - WINDOW_SIZE : count_15m]
        window_1h = candles_1h[count_1h - WINDOW_SIZE : count_1h]

        try:
            context = StrategyContext.from_ohlcv(
                symbol=symbol,
                ohlcv_1m=window_1m,
                ohlcv_15m=window_15m,
                ohlcv_1h=window_1h,
                regime="unknown",  # placeholder; real regime derived below
            )
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if not quiet:
                print(f"  [skip] context build failed at i={i}: {exc}")
            i += stride
            continue

        regime = str(context.indicators_15m.get("trend", "unknown")).lower()
        regimes_seen.add(regime)

        entry_price = candles_1m[i][4]
        exit_price = candles_1m[i + holding][4]

        for strat in strategies:
            try:
                decision = strat.analyze(context)
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                if not quiet:
                    print(f"  [skip] {strat.strategy_id} failed at i={i}: {exc}")
                continue

            if decision.direction.value == "hold":
                continue

            direction_sign = 1.0 if decision.direction.value == "long" else -1.0
            pnl_bps = direction_sign * (exit_price - entry_price) / entry_price * 10_000.0

            selector.record_result(
                strategy_id=decision.strategy_id,
                pnl_bps=pnl_bps,
                regime=regime,
            )
            signals += 1

        steps += 1
        if not quiet and time.time() - last_report > 5:
            print(f"  ...{steps} steps processed (i={i}/{end}), {signals} signals so far")
            last_report = time.time()

        i += stride

    print(f"  done: {steps} steps, {signals} signals recorded, {skipped} skipped, regimes={sorted(regimes_seen)}")
    return {"symbol": symbol, "steps": steps, "signals": signals, "skipped": skipped, "regimes": sorted(regimes_seen)}


def print_leaderboard(selector: "StrategySelector", regimes: list[str]) -> None:
    all_regimes = [StrategySelector.GLOBAL_REGIME] + sorted(r.upper() for r in regimes if r != "unknown")
    for regime in all_regimes:
        board = selector.leaderboard(regime)
        print(f"\n--- Leaderboard [{regime}] ---")
        print(f"{'strategy_id':<18}{'role':<12}{'samples':>9}{'expectancy_bps':>16}{'win_rate':>10}{'profit_factor':>15}{'quality':>10}")
        for row in board:
            print(
                f"{row['strategy_id']:<18}{row['role']:<12}"
                f"{row['effective_samples']:>9.1f}"
                f"{row['expectancy_bps']:>16.2f}"
                f"{row['win_rate']:>10.2%}"
                f"{row['profit_factor']:>15.2f}"
                f"{row['performance_quality']:>10.3f}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated symbols to backtest (default: all config.TRADING_PAIRS, sharing one selector)",
    )
    parser.add_argument("--candles", type=int, default=2000, help="Total 1m candles to fetch per symbol (default: 2000)")
    parser.add_argument("--holding", type=int, default=15, help="Forward horizon in 1m bars to measure pnl (default: 15)")
    parser.add_argument("--stride", type=int, default=5, help="Step size in 1m bars between backtest samples (default: 5)")
    parser.add_argument(
        "--state-out", type=str, default="v05_backtest_state.json",
        help="Output path for the warmed-up selector state JSON (default: v05_backtest_state.json)",
    )
    parser.add_argument("--state-in", type=str, default=None, help="Optional existing state file to continue warming up")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-step progress logging")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else list(config.TRADING_PAIRS)

    strategies = [TrendFollowingStrategy(), MeanReversionStrategy(), MomentumStrategy()]
    selector = StrategySelector(strategy_ids=[s.strategy_id for s in strategies])

    if args.state_in:
        state_path = Path(args.state_in)
        if state_path.exists():
            print(f"Loading existing state from {state_path} to continue warm-up...")
            selector.load_state(json.loads(state_path.read_text()))
        else:
            print(f"  [warn] --state-in path not found, starting fresh: {state_path}")

    print(f"SuperBot V0.5 Backtest Harness")
    print(f"Symbols: {symbols}")
    print(f"Candles/symbol: {args.candles} | Holding: {args.holding} bars | Stride: {args.stride}")

    all_regimes: set[str] = set()
    summary = []
    for symbol in symbols:
        result = run_symbol(
            symbol,
            strategies,
            selector,
            total_candles=args.candles,
            holding=args.holding,
            stride=args.stride,
            quiet=args.quiet,
        )
        summary.append(result)
        all_regimes.update(result.get("regimes", []))

    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)
    for row in summary:
        print(f"  {row['symbol']:<14} steps={row['steps']:<8} signals={row['signals']:<8} skipped={row['skipped']}")

    print_leaderboard(selector, sorted(all_regimes))

    out_path = Path(args.state_out)
    out_path.write_text(json.dumps(selector.export_state(), indent=2))
    print(f"\nSelector state written to: {out_path.resolve()}")
    print(
        "\nNOTE: this state file is NOT loaded by bot_engine.py. Loading it into "
        "the live shadow run is a separate, explicit step (Phase 2) — review the "
        "leaderboard above first."
    )


if __name__ == "__main__":
    main()
