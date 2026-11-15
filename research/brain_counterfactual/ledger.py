"""Offline, read-only Brain PAPER counterfactual ledger; never used by a runner.

Hypothetical LONG/SHORT at each journal snapshot, using 1m OHLC, fixed stop and
2R. Observed model direction is never inferred from risk rejection. Quotes
are illustrative and DO NOT model real latency, margin limits or concurrency.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3

M1 = 60_000
HOLD = 1_440  # 24 hours, in 1m candles
STOP = Decimal('0.0074')
FEE = Decimal('0.0006')  # per side
SLIP = Decimal('0.0002')
SYMBOL_RE = re.compile(r'[A-Z0-9]{3,24}\Z')


def d(raw: str) -> Decimal:
    if type(raw) is not str:
        raise ValueError('invalid_decimal')
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError('invalid_decimal') from exc
    if not value.is_finite():
        raise ValueError('nonfinite_decimal')
    return value


def minute_bars(path: Path) -> list[tuple]:
    """Parse 1-minute CSV with exact schema; reject gaps and bad OHLC."""
    import csv
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['open_time_ms', 'open', 'high', 'low', 'close', 'volume']:
            raise ValueError('candle_header_invalid')
        bars = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('candle_row_incomplete')
            t = int(row['open_time_ms'])
            o, hi, lo, cl, volume = (d(row[k]) for k in ('open', 'high', 'low', 'close', 'volume'))
            if (t < 0 or t % M1 or min(o, hi, lo, cl) <= 0 or volume < 0
                    or lo > min(o, cl) or hi < max(o, cl) or lo > hi):
                raise ValueError('invalid_candle_ohlc')
            if bars and t != bars[-1][0] + M1:
                raise ValueError('candle_gap_or_duplicate')
            bars.append((t, o, hi, lo, cl))
    return bars


def snapshot(db_path: Path, run_id: str) -> tuple[list[dict], dict, list[dict]]:
    """Snapshot in transaction, SQLite mode=ro/query_only; no schema changes."""
    if not db_path.is_file() or not run_id or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', run_id):
        raise ValueError('journal_or_run_invalid')
    con = sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        events = con.execute(
            "SELECT event_id,kind,occurred_at_ms,payload_json FROM v3_events "
            "WHERE portfolio_id='brain' AND run_id=? "
            "AND kind IN ('brain_decision','paper_open','paper_close') ORDER BY seq",
            (run_id,),
        ).fetchall()
        con.rollback()
    finally:
        con.close()
    decisions, by_id, opens, closes = [], {}, [], {}
    for eid, kind, ts, raw in events:
        payload = json.loads(raw)
        if type(payload) is not dict or type(ts) is not int or ts <= 0:
            raise ValueError('journal_event_invalid')
        if kind == 'brain_decision':
            sym = payload.get('symbol')
            if type(sym) is not str or not SYMBOL_RE.fullmatch(sym) or eid in by_id:
                raise ValueError('decision_invalid')
            obj = {
                'event_id': eid, 'ts_ms': ts, 'symbol': sym,
                'kind': payload.get('kind'), 'status': payload.get('status'),
                'regime': payload.get('regime'), 'rationale': payload.get('rationale'),
                'opening': None, 'observed_side': None, 'side_origin': 'unavailable',
            }
            decisions.append(obj)
            by_id[eid] = obj
        elif kind == 'paper_open':
            opens.append((eid, ts, payload))
        else:
            pid = payload.get('position_id')
            if type(pid) is not str or pid in closes:
                raise ValueError('close_link_invalid')
            closes[pid] = (ts, payload)
    orphan = []
    for eid, ts, p in opens:
        did, pid = p.get('decision_event_id'), p.get('position_id')
        decision = by_id.get(did) if type(did) is str else None
        side = p.get('side')
        valid = (decision is not None and decision['symbol'] == p.get('symbol')
                 and decision['kind'] == 'OPEN' and decision['status'] == 'APPROVED'
                 and decision['ts_ms'] <= ts and decision['opening'] is None
                 and type(side) is int and side in (-1, 1) and type(pid) is str)
        if not valid:
            orphan.append({'event_id': eid, 'code': 'unlinked_or_inconsistent_open'})
            continue
        close = closes.get(pid)
        realized = None
        if close is not None:
            end, cp = close
            if end < ts or cp.get('symbol') != p.get('symbol') or cp.get('side') != side:
                raise ValueError('close_inconsistent')
            realized = d(cp['realized_pnl'])
        decision['opening'] = {
            'position_id': pid, 'ts_ms': ts, 'side': side,
            'realized_pnl_usdt': str(realized) if realized is not None else None,
        }
        decision['observed_side'] = side
        decision['side_origin'] = 'verified_paper_open'
    return decisions, by_id, orphan


def observer_map(path: Path | None, decisions: list[dict]) -> dict:
    """Timestamp+symbol observer is OPTIONAL; duplicates are always ambiguous."""
    if path is None:
        return {}
    keys = Counter((r['ts_ms'], r['symbol']) for r in decisions)
    seen: dict[tuple, dict | None] = {}
    with path.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            p = json.loads(line)
            if type(p) is not dict or type(p.get('ts_ms')) is not int or type(p.get('symbol')) is not str:
                raise ValueError('observer_row_invalid')
            key = (p['ts_ms'], p['symbol'])
            if key in seen:
                seen[key] = None
            else:
                seen[key] = p
    return {key: row for key, row in seen.items() if row is not None and keys[key] == 1}


def annotate(dcs: list[dict], observer: dict) -> None:
    for decision in dcs:
        row = observer.get((decision['ts_ms'], decision['symbol']))
        if row is None:
            continue
        if decision['kind'] == 'NO_TRADE' and decision['status'] == 'DRAFT':
            # A model NO_TRADE is not a model-selected side.
            continue
        if row.get('kind') != 'OPEN' or type(row.get('side')) is not int or row['side'] not in (-1, 1):
            continue
        side = row['side']
        if decision['observed_side'] is not None and decision['observed_side'] != side:
            decision['side_conflict'] = True
            decision['observed_side'] = None
            decision['side_origin'] = 'conflicting_evidence'
        elif decision['observed_side'] is None:
            decision['observed_side'] = side
            decision['side_origin'] = 'unique_observer_ts_symbol'


def simulate(bars: list[tuple], ts: int, side: int, lag_minutes: int) -> dict:
    """Idealized future 1m bar entry; no pretend position opened by a bot.

    Entry at next 1m open on/after snapshot + assumed lag. Stops and targets
    checked in that same future minute, stop prioritized if both touched.
    Missing observations are CENSORED or UNAVAILABLE (never a win/loss).
    """
    if type(side) is not int or side not in (-1, 1) or lag_minutes < 0:
        raise ValueError('simulate_args_invalid')
    t = ts + lag_minutes * M1
    times = [b[0] for b in bars]
    k = bisect_left(times, t)
    if k >= len(bars) or bars[k][0] - t >= M1:
        return {'status': 'UNAVAILABLE'}
    opened = bars[k][1] * (Decimal(1) + side * SLIP)
    stop = opened * (Decimal(1) - side * STOP)
    target = opened * (Decimal(1) + side * 2 * STOP)
    for j in range(k, min(k + HOLD, len(bars))):
        _, o, hi, lo, cl = bars[j]
        bad = lo <= stop if side == 1 else hi >= stop
        good = hi >= target if side == 1 else lo <= target
        if bad:
            base = min(o, stop) if side == 1 else max(o, stop)
            exit_px = base * (Decimal(1) - side * SLIP)
            why = 'stop'
        elif good:
            exit_px = target
            why = 'take_profit'
        elif j == k + HOLD - 1:
            exit_px = cl
            why = 'timeout'
        else:
            continue
        pnl_fraction = side * (exit_px / opened - 1) - FEE * (1 + exit_px / opened)
        return {
            'status': 'RESOLVED', 'reason': why, 'net_r': str((pnl_fraction / STOP).quantize(Decimal('0.0001'))),
            'minutes': j - k + 1, 'entry_time_ms': bars[k][0],
        }
    return {'status': 'CENSORED'}


def build(db: Path, run_id: str, candles: Path, observer: Path | None = None,
          lag_minutes: tuple[int, ...] = (0, 1, 3)) -> tuple[list[dict], dict]:
    decisions, _, orphan = snapshot(db, run_id)
    annotate(decisions, observer_map(observer, decisions))
    cache: dict[str, list[tuple] | None] = {}
    for row in decisions:
        sym = row['symbol']
        if sym not in cache:
            try:
                cache[sym] = minute_bars(candles / sym / '1m.csv')
            except (OSError, ValueError):
                cache[sym] = None
        bars = cache[sym]
        hypothetical = {}
        for lag in lag_minutes:
            if bars is None:
                up = down = {'status': 'UNAVAILABLE'}
            else:
                up = simulate(bars, row['ts_ms'], 1, lag)
                down = simulate(bars, row['ts_ms'], -1, lag)
            hypothetical[str(lag)] = {'LONG': up, 'SHORT': down}
        row['hypothetical_only'] = hypothetical
        row['opening_state'] = (
            'EXECUTED' if row['opening'] is not None else
            'APPROVED_NOT_OPENED_CAUSE_UNKNOWN'
            if row['kind'] == 'OPEN' and row['status'] == 'APPROVED' else
            'NOT_APPROVED'
        )
    counts = Counter((x['kind'], x['status']) for x in decisions)
    executed = sum(x['opening'] is not None for x in decisions)
    summary = {
        'schema': 'brain_counterfactual_offline_v1',
        'mode': 'PAPER_RESEARCH_ONLY', 'run_id': run_id,
        'decision_count': len(decisions), 'executed_decision_count': executed,
        'approved_without_open_unknown_cause': sum(
            x['opening_state'] == 'APPROVED_NOT_OPENED_CAUSE_UNKNOWN' for x in decisions),
        'unknown_side_count': sum(x['observed_side'] is None for x in decisions),
        'orphan_open_count': len(orphan), 'orphan_open_details': orphan,
        'decision_counts': {f'{k}/{st}': n for (k, st), n in sorted(counts.items())},
        'hypothesis': 'fixed_0.74pct_stop_2R_fee6bp_each_side_slippage2bp_on_entry_and_stop',
        'assumed_lag_minutes': list(lag_minutes),
        'caution': ('Journal decision timestamp may precede DeepSeek response; lag is hypothetical. '
                    'Scenarios overlap, ignore margin/concurrency, and are NOT PnL. '
                    'Reasons for non-executed approvals are unavailable from journal alone.'),
        'journal_modified': False, 'orders_sent': 0,
    }
    return decisions, summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description='Read-only Brain PAPER hypothetical LONG/SHORT ledger')
    ap.add_argument('--journal', required=True, type=Path)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--candles-dir', required=True, type=Path)
    ap.add_argument('--observer', type=Path, default=None)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args(argv)
    db, candles, target = args.journal.resolve(strict=True), args.candles_dir.resolve(strict=True), args.out.resolve()
    if (target == db or db.parent in target.parents
            or target == candles or candles in target.parents
            or (args.observer is not None and target == args.observer.resolve(strict=True))):
        ap.error('output_must_be_outside_input_directories')
    rows, summary = build(db, args.run_id, candles, args.observer)
    with target.open('x', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n')
    print(json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
