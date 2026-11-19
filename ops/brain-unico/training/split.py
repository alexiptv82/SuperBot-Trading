"""Split cronologici con embargo e purging (nessun mescolamento casuale, nessun look-ahead sulle etichette).

Una riga di training e' ammessa solo se la SUA etichetta (che guarda avanti fino a `label_end_ms`) finisce PRIMA che inizi
il test, meno l'embargo. Le righe sovrapposte vengono "purgate" (escluse dal train, non cancellate dal dataset).
"""
from __future__ import annotations

from typing import Iterable

DEFAULT_LABEL_SPAN_MS = 86_400_000


def label_end_ms(row: dict, span_ms: int = DEFAULT_LABEL_SPAN_MS) -> int:
    """Fine dell'informazione futura usata dall'etichetta della riga: il piu' tardi tra orizzonte forward e chiusura reale."""
    end = row["decision_ts_ms"] + span_ms
    closed = (row.get("outcome") or {}).get("closed_ms")
    return max(end, closed) if isinstance(closed, int) else end


def usable(rows: Iterable[dict]) -> list:
    """Righe ammesse al training: SOLO `eligible_for_training` (criteri uniformi in eligibility.py: attestate, con feature,
    etichetta completa, non duplicate/sintetiche/manuali/censurate...). Le altre restano nel dataset, fuori dagli split."""
    return [r for r in rows if r["eligible_for_training"] is True]


def chronological_split(rows: list, fractions=(0.6, 0.2, 0.2), embargo_ms: int = 0, span_ms: int = DEFAULT_LABEL_SPAN_MS) -> dict:
    if len(fractions) != 3 or abs(sum(fractions) - 1) > 1e-9 or any(f <= 0 for f in fractions):
        raise ValueError("invalid_fractions")
    rs = sorted(usable(rows), key=lambda r: (r["decision_ts_ms"], r["example_id"]))
    n = len(rs)
    if n < 3:
        return {"train": [], "valid": [], "test": [], "purged": rs, "boundaries": None}
    i1, i2 = int(n * fractions[0]), int(n * (fractions[0] + fractions[1]))
    valid_start, test_start = rs[i1]["decision_ts_ms"], rs[i2]["decision_ts_ms"]
    train = [r for r in rs[:i1] if label_end_ms(r, span_ms) + embargo_ms <= valid_start]
    valid = [r for r in rs[i1:i2] if r["decision_ts_ms"] >= valid_start and label_end_ms(r, span_ms) + embargo_ms <= test_start]
    test = [r for r in rs[i2:]]
    kept = {r["example_id"] for r in train + valid + test}
    return {"train": train, "valid": valid, "test": test, "purged": [r for r in rs if r["example_id"] not in kept],
            "boundaries": {"valid_start_ms": valid_start, "test_start_ms": test_start}}


def walk_forward(rows: list, train_ms: int, test_ms: int, step_ms: int, embargo_ms: int = 0,
                 span_ms: int = DEFAULT_LABEL_SPAN_MS) -> list:
    rs = sorted(usable(rows), key=lambda r: (r["decision_ts_ms"], r["example_id"]))
    if not rs or min(train_ms, test_ms, step_ms) <= 0:
        return []
    t0, t_end, folds, start = rs[0]["decision_ts_ms"], rs[-1]["decision_ts_ms"], [], rs[0]["decision_ts_ms"]
    while start + train_ms + test_ms <= t_end + 1:
        test_start = start + train_ms
        train = [r for r in rs if start <= r["decision_ts_ms"] < test_start and label_end_ms(r, span_ms) + embargo_ms <= test_start]
        test = [r for r in rs if test_start <= r["decision_ts_ms"] < test_start + test_ms]
        folds.append({"train": train, "test": test, "test_start_ms": test_start})
        start += step_ms
    return folds


def assert_no_leakage(train: list, test: list, embargo_ms: int = 0, span_ms: int = DEFAULT_LABEL_SPAN_MS) -> None:
    """Solleva AssertionError se una riga di train ha l'etichetta che invade il test o se i due insiemi si sovrappongono."""
    if not train or not test:
        return
    ids = {r["example_id"] for r in train}
    assert not (ids & {r["example_id"] for r in test}), "train_test_overlap"
    t_start = min(r["decision_ts_ms"] for r in test)
    for r in train:
        assert r["decision_ts_ms"] < t_start, "train_after_test_start"
        assert label_end_ms(r, span_ms) + embargo_ms <= t_start, "train_label_leaks_into_test"
