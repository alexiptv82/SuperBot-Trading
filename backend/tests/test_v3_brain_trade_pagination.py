"""Brain history is run-isolated, pageable and never fabricates winning trades."""
import asyncio

from backend.v3_api import _overview, _trades
from backend.tests.test_v3_dashboard_unified import _paths, _journal_sample, RUN, T0


def test_brain_history_has_true_total_and_exact_winning_losing_counts(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=True)
    result = asyncio.run(_trades(paths, 100, None, offset=0))
    assert result['total_closed'] == 1
    assert result['win_count'] == 1
    assert result['loss_count'] == 0
    assert result['break_even_count'] == 0
    assert result['offset'] == 0
    assert result['has_more'] is False
    assert len(result['closed_trades']) == 1


def test_brain_history_next_page_is_empty_not_from_different_runs(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=True)
    second = asyncio.run(_trades(paths, 100, None, offset=1))
    assert second['closed_trades'] == []
    assert second['total_closed'] == 1
    assert second['win_count'] == 1
    assert second['offset'] == 1
    assert second['has_more'] is False


def test_brain_cutover_readonly_is_reported_to_all_three_wallets(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    _journal_sample(paths,close=False)
    monkeypatch.setenv('V3_CUTOVER_READONLY','1')
    data = _overview(paths, T0+1000)
    assert [p['id'] for p in data['portfolios']] == ['falco','toro','brain']
    assert data['cutover_readonly'] is True
    monkeypatch.setenv('V3_CUTOVER_READONLY','0')
    assert _overview(paths,T0+1000)['cutover_readonly'] is False
