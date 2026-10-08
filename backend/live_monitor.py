"""SuperBot V0.5 -- Live Shadow Monitor.

Polls BitGet's public 1m/15m/1h OHLCV every POLL_SECONDS in real time,
runs the three V0.5 strategies + StrategySelector on the current market,
and resolves each decision's realized pnl once --holding-minutes have
elapsed since it was made. Logs every cycle to stdout and periodically
checkpoints selector state to JSON.

Purely read-only / no order placement. Never touches the live bot's
trade-execution path. Stops after --max-hours (safety cap) or when killed.
"""
import argparse
import json
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from config import config
from exchange import exchange as exchange_wrapper

try:
    from strategies import (
        TrendFollowingStrategy, MeanReversionStrategy, MomentumStrategy, StrategyContext,
    )
    from strategy_selector import StrategySelector
except ImportError:
    from backend.strategies import (
        TrendFollowingStrategy, MeanReversionStrategy, MomentumStrategy, StrategyContext,
    )
    from backend.strategy_selector import StrategySelector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holding-minutes", type=int, default=15)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--max-hours", type=float, default=5.5)
    parser.add_argument("--state-out", type=str, default="v05_live_state.json")
    parser.add_argument(
        "--state-in", type=str, default=None,
        help="Stato selettore da un run precedente (opzionale): se presente, "
             "il test riparte dalle statistiche già accumulate invece che da zero.",
    )
    parser.add_argument("--symbols", type=str, default=None)
    parser.add_argument(
        "--decision-log", type=str, default="decisions.jsonl",
        help="File JSONL con una riga per ogni ciclo di selezione (anche i NO_SIGNAL), "
             "con il motivo per cui ogni strategia e' stata scelta o scartata -- "
             "una sorta di 'kill ledger' leggero per rivedere la qualita' dei NO TRADE "
             "senza dover rileggere tutto il log testuale.",
    )
    args = parser.parse_args()

    symbols = (
        [s.strip() for s in args.symbols.split(",")]
        if args.symbols
        else list(config.TRADING_PAIRS)
    )
    strategies = [TrendFollowingStrategy(), MeanReversionStrategy(), MomentumStrategy()]
    selector = StrategySelector(strategy_ids=[s.strategy_id for s in strategies])

    if args.state_in and Path(args.state_in).exists():
        try:
            previous_state = json.loads(Path(args.state_in).read_text())
            selector.load_state(previous_state)
            print(f"Stato precedente caricato da {args.state_in} (le statistiche si accumulano).", flush=True)
        except Exception as e:
            print(f"[warn] impossibile caricare lo stato precedente da {args.state_in}: {e} -- si riparte da zero.", flush=True)

    client = exchange_wrapper.exchange

    decision_log_path = Path(args.decision_log) if args.decision_log else None
    decision_log_file = decision_log_path.open("a", encoding="utf-8") if decision_log_path else None

    def log_decision(ts, symbol, regime, price, result) -> None:
        if decision_log_file is None:
            return
        row = {
            "ts": ts,
            "symbol": symbol,
            "regime": regime,
            "price": price,
            "champion_strategy_id": result.champion_strategy_id,
            "selected_strategy_id": result.selected_strategy_id,
            "selected_role": result.selected_role,
            "promotion": result.promotion,
            # Motivo per cui ogni strategia e' stata presa o scartata in questo
            # ciclo: actionable=False spiega gia' se era hold o sotto la soglia
            # di forza minima; selection_score/performance_quality dicono se
            # avrebbe comunque perso il confronto con le altre.
            "candidates": [
                {
                    "strategy_id": r["strategy_id"],
                    "role": r["role"],
                    "actionable": r["actionable"],
                    "direction": r["direction"],
                    "strength": r["strength"],
                    "confidence": r["confidence"],
                    "selection_score": round(r["selection_score"], 4),
                    "performance_quality": round(r["performance_quality"], 4),
                    "effective_samples": round(r["effective_samples"], 2),
                }
                for r in result.rankings
            ],
        }
        decision_log_file.write(json.dumps(row) + "\n")
        decision_log_file.flush()

    # (due_ts, symbol, strategy_id, sign, entry_price, entry_regime)
    pending = deque()
    start = time.time()
    end_time = start + args.max_hours * 3600
    iteration = 0

    def fetch(symbol, tf, limit=100):
        for attempt in range(3):
            try:
                return client.fetch_ohlcv(symbol, tf, limit=limit)
            except Exception as e:
                print(f"[warn] fetch {symbol} {tf} failed (try {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2)
        return None

    print(
        f"Live shadow monitor starting. symbols={symbols} "
        f"holding={args.holding_minutes}min poll={args.poll_seconds}s "
        f"max_hours={args.max_hours}",
        flush=True,
    )

    while time.time() < end_time:
        iteration += 1
        now = time.time()

        # Resolve any pending decisions whose holding horizon has elapsed,
        # bucketing the realized pnl into the regime that was active when
        # the signal actually fired (entry-time regime, not resolution time).
        still_pending = deque()
        resolved = 0
        for due_ts, symbol, sid, sign, entry_price, entry_regime in pending:
            if now >= due_ts:
                bars = fetch(symbol, "1m", 2)
                if bars:
                    exit_price = bars[-1][4]
                    pnl_bps = sign * (exit_price - entry_price) / entry_price * 10000.0
                    selector.record_result(strategy_id=sid, pnl_bps=pnl_bps, regime=entry_regime)
                    resolved += 1
                else:
                    still_pending.append((due_ts, symbol, sid, sign, entry_price, entry_regime))
            else:
                still_pending.append((due_ts, symbol, sid, sign, entry_price, entry_regime))
        pending = still_pending

        for symbol in symbols:
            ohlcv_1m = fetch(symbol, "1m", 100)
            ohlcv_15m = fetch(symbol, "15m", 100)
            ohlcv_1h = fetch(symbol, "1h", 100)
            if not ohlcv_1m or not ohlcv_15m or not ohlcv_1h:
                continue
            try:
                context = StrategyContext.from_ohlcv(
                    symbol=symbol,
                    ohlcv_1m=ohlcv_1m,
                    ohlcv_15m=ohlcv_15m,
                    ohlcv_1h=ohlcv_1h,
                    regime="unknown",
                )
            except Exception as e:
                print(f"[warn] context build failed {symbol}: {e}", file=sys.stderr)
                continue

            # Derive the real regime from the 15m trend indicator, same
            # convention used by backtest_harness.py -- the "unknown"
            # passed into from_ohlcv above is just a required placeholder.
            regime = str(context.indicators_15m.get("trend", "unknown")).lower()

            decisions = [s.analyze(context) for s in strategies]
            result = selector.select(decisions, regime=regime)
            price_now = ohlcv_1m[-1][4]
            ts_now = datetime.now(timezone.utc).isoformat()
            log_decision(ts_now, symbol, regime, price_now, result)

            for d in decisions:
                if d.direction.value != "hold":
                    sign = 1.0 if d.direction.value == "long" else -1.0
                    pending.append(
                        (now + args.holding_minutes * 60, symbol, d.strategy_id, sign, price_now, regime)
                    )

            selected_txt = (
                f"{result.selected_role}:{result.selected_strategy_id}"
                if result.selected
                else "NO_SIGNAL"
            )
            print(
                f"[{ts_now}] {symbol} regime={regime} selected={selected_txt} "
                f"price={price_now} resolved_this_cycle={resolved}",
                flush=True,
            )

        if iteration % 5 == 0:
            Path(args.state_out).write_text(json.dumps(selector.export_state(), indent=2))
            print(f"  [checkpoint] state saved -> {args.state_out}, pending={len(pending)}", flush=True)

        time.sleep(args.poll_seconds)

    Path(args.state_out).write_text(json.dumps(selector.export_state(), indent=2))
    if decision_log_file is not None:
        decision_log_file.close()
    print("Live shadow monitor finished (max-hours elapsed).", flush=True)


if __name__ == "__main__":
    main()
