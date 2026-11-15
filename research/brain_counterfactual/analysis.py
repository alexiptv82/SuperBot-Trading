"""Descriptive paired diagnostics for ledger output, never trading signals."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import hashlib


def analyze(rows: list[dict], lag: str = '1') -> dict:
    eligible, unknown = [], 0
    counters = Counter()
    group_scenarios = defaultdict(list)
    for row in rows:
        counters[row['opening_state']] += 1
        sim = row['hypothetical_only'].get(lag)
        if sim is None or any(sim[k]['status'] != 'RESOLVED' for k in ('LONG', 'SHORT')):
            continue
        group_scenarios[f"{row['kind']}/{row['status']}"].append(
            (Decimal(sim['LONG']['net_r']), Decimal(sim['SHORT']['net_r']))
        )
        side = row['observed_side']
        if type(side) is not int or side not in (-1, 1):
            unknown += 1
            continue
        selection = 'LONG' if side == 1 else 'SHORT'
        selected = Decimal(sim[selection]['net_r'])
        bearish = Decimal(sim['SHORT']['net_r'])
        # A fair coin is an illustrative baseline, not an independent trade.
        rand = hashlib.sha256((row['event_id'] + ':baseline-v1').encode()).digest()[0] & 1
        coin = Decimal(sim['LONG' if rand else 'SHORT']['net_r'])
        eligible.append((selected, bearish, coin, row['regime']))
    n = len(eligible)
    def avg(index):
        return str((sum((r[index] for r in eligible), Decimal(0)) / n).quantize(Decimal('0.0001'))) if n else None
    delta = str((sum((r[0]-r[1] for r in eligible), Decimal(0)) / n).quantize(Decimal('0.0001'))) if n else None
    return {
        'lag_minutes': int(lag), 'paired_n': n, 'unknown_side_with_resolved_scenarios': unknown,
        'model_side_mean_hypothetical_r': avg(0),
        'same_timestamp_always_short_mean_r': avg(1),
        'same_timestamp_hash_coin_mean_r': avg(2),
        'model_minus_always_short_r': delta,
        'opening_state_counts': dict(sorted(counters.items())),
        'scenario_by_decision_group': {
            key: {
                'resolved_n': len(v),
                'hypothetical_long_mean_r': str((sum((x[0] for x in v), Decimal(0)) / len(v)).quantize(Decimal('0.0001'))),
                'hypothetical_short_mean_r': str((sum((x[1] for x in v), Decimal(0)) / len(v)).quantize(Decimal('0.0001'))),
            } for key, v in sorted(group_scenarios.items())
        },
        'not_statistically_independent': True,
        'no_real_pnl_mixed_in': True,
        'warning': ('Multiple overlapping trades and shared market moves make naive confidence intervals invalid; '
                    'proposals may be reconstructed only with unique observer evidence. '
                    'This is descriptive and cannot establish AI alpha.'),
    }
