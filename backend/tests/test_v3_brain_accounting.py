"""Dashboard Brain BOOK accounting: independently audited closed PAPER results only."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from backend.tests.test_v3_dashboard_unified import _paths, _journal_sample, RUN, T0
from backend.v3_api import _overview, V3Paths

PROFILE = Path(__file__).parents[1] / 'v3' / 'runner' / 'runner_config_brain2000_paper.json'


def test_verified_brain_closed_trade_yields_book_equity_and_utc_daily_profit(tmp_path):
    p = replace(_paths(tmp_path), brain_config_path=str(PROFILE))
    _journal_sample(p, close=True)
    out = _overview(p, T0 + 65_000)
    brain = out['portfolios'][2]
    assert brain['start_equity'] == '2000'
    assert Decimal(brain['equity']) == Decimal('2003.75760000')
    assert brain['equity'] == brain['settled_equity']
    assert brain['equity_basis'] == 'settled'
    assert Decimal(brain['day_pnl']) == Decimal('3.75760000')
    assert brain['pnl_day_timezone'] == 'UTC'


def test_day_pnl_resets_on_utc_day_without_erasing_lifetime_book_equity(tmp_path):
    p = replace(_paths(tmp_path), brain_config_path=str(PROFILE))
    _journal_sample(p)
    out = _overview(p, T0 + 2 * 86_400_000)
    brain = out['portfolios'][2]
    assert Decimal(brain['equity']) == Decimal('2003.75760000')
    assert brain['day_pnl'] == '0'


def test_open_positions_have_settled_balance_but_no_invented_total_equity(tmp_path):
    p = replace(_paths(tmp_path), brain_config_path=str(PROFILE))
    _journal_sample(p, close=False)
    brain = _overview(p, T0 + 65_000)['portfolios'][2]
    assert brain['settled_equity'] == '2000'
    assert brain['equity'] is None
    assert brain['equity_basis'] == 'open_unmarked'
    assert brain['day_pnl'] == '0'


def test_missing_wrong_or_invalid_run_profile_fails_closed(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=True)
    brain = _overview(paths, T0 + 65_000)['portfolios'][2]
    assert brain['equity'] is None and brain['day_pnl'] is None
    wrong = replace(paths, run_id='another-run', brain_config_path=str(PROFILE))
    brain = _overview(wrong, T0 + 65_000)['portfolios'][2]
    assert brain['equity'] is None and brain['day_pnl'] is None
    invalid_profile = tmp_path / 'bad-config.json'
    invalid_profile.write_text('{"initial_equity":"999999"}', encoding='utf-8')
    brain = _overview(replace(paths, brain_config_path=str(invalid_profile)), T0 + 65_000)['portfolios'][2]
    assert brain['equity'] is None and brain['day_pnl'] is None


def test_peer_observations_are_only_read_only_classic_status_and_not_ai_input(tmp_path):
    paths = _paths(tmp_path)
    _journal_sample(paths, close=False)
    entries = _overview(paths, T0 + 65_000)['portfolios']
    brain = entries[2]
    assert brain['peer_observations_mode'] == 'display_only_not_ai_input'
    assert [x['portfolio_id'] for x in brain['peer_observations']] == ['falco', 'toro']
    assert [x['open_positions'] for x in brain['peer_observations']] == [
        entries[0]['open_positions'], entries[1]['open_positions']
    ]
    assert all(set(peer) == {'portfolio_id', 'state', 'open_positions', 'day_pnl',
                            'last_event_ms'} for peer in brain['peer_observations'])


def test_profile_source_must_be_explicit_environment_not_a_guess(monkeypatch):
    monkeypatch.delenv('V3_RUNNER_CONFIG_PATH', raising=False)
    assert V3Paths.from_env('hawk', 'bull').brain_config_path is None
    monkeypatch.setenv('V3_RUNNER_CONFIG_PATH', '/opt/paper/run-specific-config.json')
    assert V3Paths.from_env('hawk', 'bull').brain_config_path == '/opt/paper/run-specific-config.json'
