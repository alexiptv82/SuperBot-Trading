"""Offline score-only sensitivity on a hashed PAPER learning-log snapshot.
No orders, network, portfolio simulation, or inference about profitability.
Caller must verify that each allowed code version uses the bundled seasonal formula.
Threshold is an explicit analytical scenario, NOT reconstructed historical policy.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from desk.seasonal_v1 import get_seasonal   # formula in vigore nelle versioni di codice auditate (pre-V2)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def decode(raw, expected_sha):
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('snapshot_hash_mismatch')
    if not raw or not raw.endswith(b'\n'):
        raise ValueError('empty_or_truncated_snapshot')
    rows = []
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
        if not isinstance(row, dict):
            raise ValueError('non_object_event')
        rows.append(row)
    return rows


def score_without_bonus(score, bonus):
    if not finite(score) or not 0 <= score <= 100 or int(score) != score:
        raise ValueError('invalid_score')
    if score == 100 and bonus > 0:
        raise ValueError('saturated_score')
    if score < bonus:
        raise ValueError('score_below_bonus')
    return score - bonus


def selection(long, short, threshold):
    side = 1 if long > short else -1 if short > long else 0
    return side, side != 0 and max(long, short) >= threshold


def analyze(rows, threshold, versions):
    if not finite(threshold) or not 0 <= threshold <= 100 or not versions:
        raise ValueError('invalid_scenario')
    counts, excluded, seen = collections.Counter(), collections.Counter(), {}
    for row in rows:
        if row.get('ev') not in ('candidate', 'open'):
            continue
        counts['recorded_rows'] += 1
        if row.get('code_version') not in versions:
            excluded['unreviewed_code_version'] += 1
            continue
        try:
            bot, run, ts, symbol = (row[k] for k in ('portfolio', 'run_no', 'ts', 'symbol'))
            if bot not in ('hawk', 'bull') or type(run) is not int or run < 1 or type(ts) is not int or ts <= 0 or not isinstance(symbol, str) or not symbol:
                raise ValueError('invalid_identity')
            f = row['features']
            long, short = f['sig_long'], f['sig_short']
            bonus = get_seasonal(symbol, ts)
            b_long = score_without_bonus(long, bonus.long_bonus)
            b_short = score_without_bonus(short, bonus.short_bonus)
        except (KeyError, TypeError):
            excluded['missing_fields'] += 1
            continue
        except ValueError as error:
            excluded[str(error)] += 1
            continue
        key = (bot, run, ts, symbol)
        values = (long, short, row['code_version'])
        # Same reading may appear more than once; never silently merge conflicts.
        prior = seen.get(key)
        if prior is not None:
            if prior != values:
                raise ValueError('conflicting_same_cycle_readings')
            counts['duplicate_readings'] += 1
            continue
        seen[key] = values
        a, b = selection(long, short, threshold), selection(b_long, b_short, threshold)
        counts['unique_readings'] += 1
        counts['side_changed'] += a[0] != b[0]
        counts['threshold_eligibility_changed'] += a[1] != b[1]
        counts['eligible_A'] += a[1]
        counts['eligible_B'] += b[1]
    return {'scope': 'recorded_readings_only_not_trades_or_pnl',
            'threshold_scenario': threshold, 'counts': dict(counts), 'excluded': dict(excluded)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--threshold', required=True, type=float)
    p.add_argument('--reviewed-code-version', action='append', required=True)
    p.add_argument('--paper-confirmed', action='store_true', required=True)
    a = p.parse_args()
    path = Path(a.snapshot)
    if path.is_symlink() or not path.is_file():
        raise ValueError('snapshot_not_regular_file')
    raw = path.read_bytes()
    rows = decode(raw, a.sha256)
    report = analyze(rows, a.threshold, set(a.reviewed_code_version))
    if path.read_bytes() != raw:
        raise ValueError('snapshot_changed')
    report.update(input_sha256=a.sha256,
                  seasonal_sha256=hashlib.sha256((ROOT / 'backend/desk/seasonal.py').read_bytes()).hexdigest(),
                  reviewed_versions=sorted(a.reviewed_code_version),
                  paper_confirmation='operator_attestation_not_inferred_from_log')
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
