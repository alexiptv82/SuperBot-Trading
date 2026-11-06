"""Fail-closed CLI plumbing for PAPER split mode; no network or VPS."""
from pathlib import Path
from types import SimpleNamespace

from backend.v3.runner import wiring


def test_split_cli_refuses_missing_directory_without_creating_it(tmp_path):
    absent = tmp_path / 'must_not_create'
    assert wiring.main(['--data-dir', str(absent), '--run-id', 'rc_trial',
                        '--exit-mode', 'sidecar', '--once'], env={'DESK_MODE': 'paper'}) == 2
    assert not absent.exists()


def test_split_cli_refuses_nonpaper_before_initializing(tmp_path):
    absent = tmp_path / 'must_not_create'
    assert wiring.main(['--data-dir', str(absent), '--run-id', 'rc_trial',
                        '--exit-mode', 'sidecar', '--once'], env={'DESK_MODE': 'live'}) == 2
    assert not absent.exists()


def test_split_cli_passes_explicit_mode_clock_and_paper_to_builder(tmp_path, monkeypatch):
    seen = {}
    now_fn = lambda: 1762000000000
    class FakeRunner:
        def tick(self, t):
            seen['tick'] = t
            return SimpleNamespace(state='halted', last_error='exit_service_unavailable')
    def stub_builder(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(runner=FakeRunner())
    monkeypatch.setattr(wiring, 'build_runner', stub_builder)
    assert wiring.main(['--data-dir', str(tmp_path), '--run-id', 'rc_trial',
                        '--exit-mode', 'sidecar', '--once'], env={'DESK_MODE': 'paper'},
                       now_fn=now_fn) == 0
    assert seen['exit_mode'] == 'sidecar'
    assert seen['desk_mode'] == 'paper'
    assert seen['clock_ms'] is now_fn
    assert seen['tick'] == 1762000000000


def test_legacy_cli_preserves_default_and_does_not_pass_split_options(tmp_path, monkeypatch):
    seen = {}
    class FakeRunner:
        def tick(self, t):
            return SimpleNamespace(state='paused', last_error=None)
    def stub_builder(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(runner=FakeRunner())
    monkeypatch.setattr(wiring, 'build_runner', stub_builder)
    d = tmp_path / 'created_legacy'
    assert wiring.main(['--data-dir', str(d), '--run-id', 'rc_trial', '--once'],
                       env={'DESK_MODE': 'paper'}) == 0
    assert d.is_dir()
    assert 'exit_mode' not in seen and 'clock_ms' not in seen
