"""Authenticated PAPER close commands: exact-once queue, no cross-portfolio overwrite.

Synthetic portfolios only. These tests MUST NOT touch a real VPS or trade.
"""
from __future__ import annotations

import fcntl
import json
import os
import time

from fastapi.testclient import TestClient

import desk_view as dv
from desk import cli
from backend.tests.test_v3_classic_exit_only import _app, prepare, worker


def _test_feed(monkeypatch, *, price=98):
    monkeypatch.setattr(cli, "fetch_candles",
        lambda sym, bar, limit: [[int(time.time() * 1000) - 25_000,
            100, 103, 97, price, 1]] if bar == '1m' else [])


def test_double_tap_and_close_all_do_not_replace_first_single_close(tmp_path, monkeypatch):
    base, backup=prepare(tmp_path,monkeypatch)
    _test_feed(monkeypatch)
    with worker(base,backup) as service, TestClient(_app(base)) as api:
        accepted=api.post('/api/desk/close-position',json={'symbol':'BTCUSDT'})
        assert accepted.status_code==200
        old=(base/'close_position.flag').read_bytes()
        second=api.post('/api/desk/close-position',json={'symbol':'BTC'})
        assert second.status_code==409
        assert (base/'close_position.flag').read_bytes()==old
        close_all=api.post('/api/desk/close-all')
        assert close_all.status_code==409
        assert (base/'close_position.flag').read_bytes()==old
        assert not (base/'reset.flag').exists()
        # Only the first request is consumed and journaled.
        service.tick()
        assert api.get('/api/desk/status').json()['open_positions']==0
        again=api.post('/api/desk/close-position',json={'symbol':'BTC'})
        assert again.status_code==404
        service.tick()
    lines=(base/'trade_history.jsonl').read_text().splitlines()
    assert len(lines)==1
    record=json.loads(lines[0])
    assert record['symbol']=='BTC'
    assert record['closed_by']=='utente'
    assert record['manual_learning']=='profit_protection_example'


def test_close_all_rejects_any_followup_while_pending(tmp_path,monkeypatch):
    base,backup=prepare(tmp_path,monkeypatch)
    _test_feed(monkeypatch)
    with worker(base,backup) as service,TestClient(_app(base)) as api:
        result=api.post('/api/desk/close-all')
        assert result.status_code==200
        flag=(base/'reset.flag').read_bytes()
        assert api.post('/api/desk/close-all').status_code==409
        assert api.post('/api/desk/close-position',json={'symbol':'BTC'}).status_code==409
        assert (base/'reset.flag').read_bytes()==flag
        assert not (base/'close_position.flag').exists()
        service.tick()
    assert len((base/'trade_history.jsonl').read_text().splitlines())==1
    state=json.loads((base/'state_v2.json').read_text())
    assert state['main']['positions']=={}


def test_directory_lock_busy_rejects_without_writing_or_closing(tmp_path,monkeypatch):
    base,backup=prepare(tmp_path,monkeypatch)
    _test_feed(monkeypatch)
    with worker(base,backup) as service,TestClient(_app(base)) as api:
        fd=os.open(base, os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
        fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            first=api.post('/api/desk/close-position',json={'symbol':'BTC'})
            all_resp=api.post('/api/desk/close-all')
            assert first.status_code==409
            assert all_resp.status_code==409
            assert 'elaborazione' in first.json()['detail']
            assert not (base/'close_position.flag').exists()
            assert not (base/'reset.flag').exists()
            result=service.tick()
            assert result['request_writer_busy'] is True
            assert dv.exit_only_close_ready(str(base),'hawk')
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)
        assert api.post('/api/desk/close-position',json={'symbol':'BTC'}).status_code==200
        service.tick()
    assert len((base/'trade_history.jsonl').read_text().splitlines())==1


def test_wrong_portfolio_never_accepts_exit_only_request(tmp_path,monkeypatch):
    base,backup=prepare(tmp_path,monkeypatch,portfolio='hawk')
    with worker(base,backup):
        ok,code,_=dv.command_close_position(str(base),'BTC',portfolio='bull')
        assert ok is False and code==409
        result=dv.command_close_all(str(base),portfolio='bull')
        assert result['ok'] is False and result['queued'] is False
    assert not (base/'close_position.flag').exists()
    assert not (base/'reset.flag').exists()


def test_offline_requests_do_not_create_new_files(tmp_path, monkeypatch):
    base,backup=prepare(tmp_path,monkeypatch)
    files_before={p.name for p in base.iterdir()}
    ok,code,_=dv.command_close_position(str(base),'BTC',portfolio='hawk')
    all_result=dv.command_close_all(str(base),portfolio='hawk')
    assert ok is False and code==409
    assert all_result['queued'] is False
    assert {p.name for p in base.iterdir()} == files_before
