"""Real PAPER ledger, WAL, queues and append-only memory; no external calls."""
import fcntl
import json
from pathlib import Path
import sqlite3

import pytest

from director.brain_scalp.coordinator import BrainAccount
from director.brain_scalp.operator import BrainOperator
from director.brain_scalp.operator_inbox import OperatorInbox
from director.brain_scalp.notification_outbox import NotificationOutbox
from director.brain_scalp.recovery_bundle import (
    create_bundle,verify_bundle,restore_bundle,WALLET,NOTIFICATIONS,INBOX)
from backend.tests.test_brain_resume import SPEC,NOW,markets,shortlist,plan,CONTRACTS


@pytest.fixture
def prepared(tmp_path):
    source=tmp_path/'data'
    account=BrainAccount(source,spec=SPEC,initialize=True,now_ms=NOW)
    account.accept_ai_plans('brain',{'plans':[plan()]},shortlist(),markets(),CONTRACTS,NOW)
    account.tick(markets(),CONTRACTS,NOW+1)
    operator=BrainOperator(account)
    quote=markets(NOW+1000);quote['BTC']['quote']['price']=102
    ident=account.brain.store.load()['positions']['BTC']['id']
    operator.close({'BTC':ident},quote,NOW+1000)
    operator.confirm('/insegna_si',NOW+2000)
    state=account.brain.store.load()
    events=account.brain.store.db.execute('SELECT * FROM events ORDER BY seq').fetchall()
    account.close()
    inbox_path=tmp_path/'app.sqlite3'
    inbox=OperatorInbox(inbox_path)
    for number,status in enumerate(('pending','processing','confirmed','needs_reconciliation','expired'),1):
        inbox.submit_confirmation(f'{number:032x}','a'*16,'yes',NOW)
        inbox.db.execute('UPDATE commands SET status=? WHERE id=?',(status,f'{number:032x}'))
        inbox.db.commit()
    inbox.close()
    queue=NotificationOutbox(source/NOTIFICATIONS,lambda _:pytest.fail('network forbidden'))
    for number,status in enumerate(('pending','inflight','delivered','uncertain','rejected')):
        queue.stage({'provider':'deepseek','failure_code':'balance','ts_ms':NOW+number*1800000})
        queue.db.execute('UPDATE notifications SET status=? WHERE created=?',(status,NOW+number*1800000))
        queue.db.commit()
    queue.close()
    return source,inbox_path,state,events


def test_complete_restore_keeps_ledger_memory_and_quarantines_old_queues(tmp_path,prepared):
    source,inbox,state,events=prepared
    journal={name:(source/'brain'/name).read_bytes() for name in
             ('manual_close_reviews.jsonl','learning_log.jsonl','lessons.md')}
    bundle=create_bundle(source,tmp_path/'backup',inbox_path=inbox)
    manifest=verify_bundle(bundle)
    assert manifest['identity']['version']==state['_version']
    restored=restore_bundle(bundle,tmp_path/'restored')
    assert verify_bundle(bundle)==manifest
    account=BrainAccount(restored,spec=SPEC)
    try:
        assert account.brain.store.load()==state
        assert account.brain.store.db.execute('SELECT * FROM events ORDER BY seq').fetchall()==events
        assert BrainOperator(account).sync()==0
        assert all((restored/'brain'/name).read_bytes()==body for name,body in journal.items())
    finally:account.close()
    report=json.loads((restored/'RESTORE.json').read_text())
    assert report['quarantined']=={NOTIFICATIONS:2,INBOX:2}
    assert report['ready_to_start'] is False
    queue=NotificationOutbox(restored/NOTIFICATIONS,lambda _:pytest.fail('old backup resend'))
    try:
        assert queue.step(NOW+99999999)=='idle'
        assert not queue.stage({'provider':'deepseek','failure_code':'balance','ts_ms':NOW})
        assert queue.db.execute("SELECT COUNT(*) FROM notifications WHERE status='delivered'").fetchone()[0]==1
    finally:queue.close()
    restored_inbox=OperatorInbox(restored/INBOX)
    try:
        assert restored_inbox.consume(None,NOW)==[]
        assert restored_inbox.db.execute("SELECT COUNT(*) FROM commands WHERE status='confirmed'").fetchone()[0]==1
    finally:restored_inbox.close()
    # Source queues were not quarantined or consumed by backup/restore.
    with sqlite3.connect(inbox) as db:
        assert db.execute("SELECT COUNT(*) FROM commands WHERE status='pending'").fetchone()[0]==1


def test_owner_active_refuses_backup_without_wallet_write(tmp_path,prepared):
    source,inbox,state,_=prepared
    account=BrainAccount(source,spec=SPEC)
    try:
        with pytest.raises(ValueError,match='owner_active'):
            create_bundle(source,tmp_path/'backup',inbox_path=inbox)
        assert account.brain.store.load()==state
        assert not (tmp_path/'backup').exists()
    finally:account.close()


@pytest.mark.parametrize('lock_name',['brain.notifications.sqlite3.owner',
    'brain/.manual_teaching.lock','brain/.brain_operator_updates.lock'])
def test_other_owner_locks_are_required(tmp_path,prepared,lock_name):
    source,inbox,_,_=prepared
    with (source/lock_name).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError,match='owner_active'):
            create_bundle(source,tmp_path/'backup',inbox_path=inbox)


def test_inbox_writer_lock_blocks_cut_and_wal_rows_are_included(tmp_path,prepared):
    source,inbox,_,_=prepared
    db=sqlite3.connect(inbox)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO commands VALUES (?,?,?,?,?)",('b'*32,NOW,'{}','pending',None))
        with pytest.raises(ValueError,match='database_busy'):
            create_bundle(source,tmp_path/'backup',inbox_path=inbox)
        db.commit()
        # The source writer stays open, with committed content in the WAL.
        assert Path(str(inbox)+'-wal').is_file()
        bundle=create_bundle(source,tmp_path/'backup',inbox_path=inbox)
        with sqlite3.connect(bundle/INBOX) as copy:
            assert copy.execute('SELECT COUNT(*) FROM commands').fetchone()[0]==6
    finally:db.close()


@pytest.mark.parametrize('attack',['hash','missing','extra','traversal','identity','duplicate','symlink'])
def test_invalid_bundle_never_creates_restore(tmp_path,prepared,attack):
    source,inbox,_,_=prepared
    bundle=create_bundle(source,tmp_path/'backup',inbox_path=inbox)
    if attack=='hash':(bundle/'brain/lessons.md').write_text('modified')
    elif attack=='missing':(bundle/NOTIFICATIONS).unlink()
    elif attack=='extra':(bundle/'untracked').write_text('extra')
    elif attack=='symlink':
        (bundle/'brain/lessons.md').unlink();(bundle/'brain/lessons.md').symlink_to(source/'brain/lessons.md')
    else:
        manifest=json.loads((bundle/'MANIFEST.json').read_text())
        if attack=='traversal':manifest['files'][0]['path']='../outside'
        elif attack=='identity':manifest['identity']['experiment_id']='wrong'
        else:manifest['files'].append(manifest['files'][0])
        (bundle/'MANIFEST.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):restore_bundle(bundle,tmp_path/'restored')
    assert not (tmp_path/'restored').exists()


def test_never_overwrites_existing_destination_or_omits_new_data(tmp_path,prepared):
    source,inbox,_,_=prepared
    existing=tmp_path/'existing';existing.mkdir();(existing/'sentinel').write_text('keep')
    with pytest.raises(ValueError):create_bundle(source,existing,inbox_path=inbox)
    assert (existing/'sentinel').read_text()=='keep'
    with pytest.raises(ValueError):create_bundle(source,source/'nested',inbox_path=inbox)
    (source/'unmapped-memory.json').write_text('{}')
    with pytest.raises(ValueError,match='unmapped'):
        create_bundle(source,tmp_path/'backup',inbox_path=inbox)
    (source/'unmapped-memory.json').unlink()
    bundle=create_bundle(source,tmp_path/'backup',inbox_path=inbox)
    with pytest.raises(ValueError):restore_bundle(bundle,existing)
    assert (existing/'sentinel').read_text()=='keep'


def test_notifications_disabled_and_explicit_inbox_inside_tree(tmp_path,prepared):
    source,inbox,_,_=prepared
    (source/NOTIFICATIONS).unlink()
    internal=source/'brain'/'operator.sqlite3'
    inbox.rename(internal)
    with pytest.raises(ValueError,match='unmapped'):
        create_bundle(source,tmp_path/'backup')
    bundle=create_bundle(source,tmp_path/'backup',inbox_path=internal)
    assert verify_bundle(bundle)['notification_present'] is False
    assert (restore_bundle(bundle,tmp_path/'restored')/INBOX).is_file()
