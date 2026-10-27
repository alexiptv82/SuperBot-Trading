"""The future deployment path is tested with temporary data, never a VPS."""
import importlib.util,json,os,sqlite3,subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('free_rollout',ROOT/'deploy/scripts/brain_free_rollout.py')
rollout=importlib.util.module_from_spec(spec);spec.loader.exec_module(rollout)


def test_plan_is_side_effect_free_and_never_calls_docker(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['rollout'])
    monkeypatch.setattr(rollout,'run',lambda *a,**k:pytest.fail('must not call a command'))
    rollout.main();assert 'PLAN_ONLY' in capsys.readouterr().out

@pytest.mark.parametrize('approved,sha,app',[('no','a'*40,'b'*40),('yes','main','b'*40),('yes','a'*40,'main')])
def test_apply_requires_separate_approval_and_immutable_shas(monkeypatch,approved,sha,app):
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic')
    with pytest.raises(ValueError):rollout.check_inputs(approved,sha,app)


def test_live_is_always_rejected(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic');monkeypatch.setenv('DESK_MODE','live')
    with pytest.raises(ValueError,match='paper_required'):rollout.check_inputs('yes','a'*40,'b'*40)


def test_backup_restores_sqlite_and_keeps_source_bytes(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'notes.json').write_text('{"synthetic":true}')
    with sqlite3.connect(source/'brain.sqlite3') as db:
        db.execute('CREATE TABLE events(id INTEGER,body TEXT)');db.execute('INSERT INTO events VALUES(1,?)',('{"synthetic":true}',))
    before=(source/'brain.sqlite3').read_bytes()
    rollout.snapshot_tree(source,tmp_path/'backup')
    assert (source/'brain.sqlite3').read_bytes()==before
    with sqlite3.connect(tmp_path/'backup/brain.sqlite3') as db:assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
    assert json.loads((tmp_path/'backup/BACKUP_MANIFEST.json').read_text())


def test_backup_missing_or_symlink_source_blocks(tmp_path):
    with pytest.raises(ValueError):rollout.snapshot_tree(tmp_path/'missing',tmp_path/'backup')
    source=tmp_path/'source';source.mkdir();(source/'unsafe').symlink_to(tmp_path/'outside')
    with pytest.raises(ValueError,match='symlink'):rollout.snapshot_tree(source,tmp_path/'backup')


def test_no_classic_restarts_or_account_reset_paths_in_rollout():
    source=(ROOT/'deploy/scripts/brain_free_rollout.py').read_text()
    assert "for name in OLD:run(['docker','stop'" in source
    assert "docker','rm" not in source and 'shutil.rmtree' not in source
    assert 'new_account_directory_not_empty_no_reset' in source
    trigger=(ROOT/'deploy/brain-free.trigger').read_text()
    assert trigger=='action=none\napproved=no\n'
