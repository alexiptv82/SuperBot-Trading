"""Offline, coordinated PAPER recovery. Never stops or starts a service.

Owner locks must be available. SQLite writers (including the app inbox) are
excluded for the complete snapshot. Restore only creates a new directory and
quarantines queued side effects: an older backup cannot know later deliveries.
"""
from contextlib import ExitStack, closing
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

WALLET='brain/brain_scalp.sqlite3'
NOTIFICATIONS='brain.notifications.sqlite3'
INBOX='control/operator.sqlite3'
FILES={WALLET,NOTIFICATIONS,INBOX,
       'brain/manual_close_reviews.jsonl','brain/learning_log.jsonl',
       'brain/lessons.md','brain/brain_operator_updates.jsonl'}
LOCKS=('brain/writer.lock','brain/.manual_teaching.lock',
       'brain/.brain_operator_updates.lock',NOTIFICATIONS+'.owner')


def _safe(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('unsafe_recovery_path')
    return path


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else _stream_sha(stream)


def _stream_sha(stream):
    digest=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def _connect(path):
    return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.1)


def _identity(path):
    with closing(_connect(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('recovery_integrity')
        version,body=db.execute('SELECT version,body FROM state WHERE id=1').fetchone()
        state=json.loads(body)
        if state.get('mode')!='paper' or state.get('account_id')!='brain-scalp-single-paper':
            raise ValueError('recovery_paper_single_only')
        if not state.get('experiment_id') or not state.get('config_hash'):
            raise ValueError('recovery_missing_identity')
        return {k:state[k] for k in ('account_id','experiment_id','config_hash')}|{'version':version}


def _write_json(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,sort_keys=True,ensure_ascii=False,allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    path.chmod(0o600)


def _sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _inventory(root):
    result={}
    for path in root.rglob('*'):
        _safe(path)
        if path.is_dir():continue
        if not path.is_file():raise ValueError('unsupported_recovery_file')
        result[path.relative_to(root).as_posix()]=path
    return result


def _locked(stack,path):
    _safe(path)
    lock=stack.enter_context(path.open('a'))
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:raise ValueError('recovery_owner_active') from None


def create_bundle(data_dir,destination,*,inbox_path=None):
    """Requires stopped owners; no permission to stop them is implied.

    An enabled inbox must be passed explicitly, including if outside data_dir.
    Refuse unrecognized files rather than silently omit durable new components.
    """
    source=_safe(data_dir);target=_safe(destination)
    if not source.is_dir() or not (source/WALLET).is_file():
        raise ValueError('recovery_wallet_missing')
    if target.exists() or source==target or source in target.parents:
        raise ValueError('recovery_destination_must_be_new_external')
    if not target.parent.is_dir():raise ValueError('recovery_parent_missing')
    inbox=_safe(inbox_path) if inbox_path is not None else None
    if inbox is not None and (not inbox.is_file() or inbox in (source/WALLET,source/NOTIFICATIONS)):
        raise ValueError('invalid_recovery_inbox')
    with ExitStack() as stack:
        for name in LOCKS:_locked(stack,source/name)
        inventory=_inventory(source)
        skip=set(LOCKS)|{name+suffix for name in (WALLET,NOTIFICATIONS)
                        for suffix in ('-wal','-shm','-journal')}
        if inbox is not None and source in inbox.parents:
            relative=inbox.relative_to(source).as_posix()
            skip|={relative,relative+'-wal',relative+'-shm',relative+'-journal'}
        if set(inventory)-FILES-skip:raise ValueError('unmapped_recovery_data')
        sources={name:path for name,path in inventory.items() if name in FILES and name!=INBOX}
        if inbox is not None:sources[INBOX]=inbox
        elif INBOX in inventory:raise ValueError('explicit_recovery_inbox_required')
        # BEGIN IMMEDIATE on *all* databases first establishes one quiet cut.
        # Separate read connections use SQLite backup so WAL pages are included.
        for name,path in sorted(sources.items()):
            if not name.endswith('.sqlite3'):continue
            db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=.1)
            stack.callback(db.close)
            try:db.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError:raise ValueError('recovery_database_busy') from None
            stack.callback(db.rollback)
        identity=_identity(source/WALLET)
        part=Path(tempfile.mkdtemp(prefix='.'+target.name+'-',dir=target.parent))
        try:
            records=[]
            for name,path in sorted(sources.items()):
                out=part/name;out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                if name.endswith('.sqlite3'):
                    with closing(_connect(path)) as src,closing(sqlite3.connect(out)) as dst:
                        src.backup(dst)
                        dst.execute('PRAGMA journal_mode=DELETE')
                        if dst.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                            raise ValueError('recovery_integrity')
                else:shutil.copyfile(path,out)
                out.chmod(0o600)
                with out.open('rb') as stream:os.fsync(stream.fileno())
                records.append({'path':name,'sha256':_sha(out),'size':out.stat().st_size})
            manifest={'schema':1,'paper':True,'created_ms':int(time.time()*1000),
                      'identity':identity,'inbox_configured':inbox is not None,
                      'notification_present':NOTIFICATIONS in sources,'files':records,
                      'restore_policy':'quarantine_all_queued_side_effects'}
            _write_json(part/'MANIFEST.json',manifest)
            verify_bundle(part)
            for folder in sorted((p for p in part.rglob('*') if p.is_dir()),reverse=True):_sync_dir(folder)
            _sync_dir(part)
            # A concurrent creator must not be overwritten, even if empty.
            target.mkdir(mode=0o700)
            for child in sorted(part.iterdir(),key=lambda p:p.name=='MANIFEST.json'):
                os.rename(child,target/child.name)
            part.rmdir();_sync_dir(target);_sync_dir(target.parent)
            return target
        except BaseException:
            shutil.rmtree(part,ignore_errors=True)
            # Never delete an existing target: failed publication stays visibly
            # incomplete and verify_bundle will reject it if no manifest.
            raise


def verify_bundle(bundle):
    root=_safe(bundle)
    inventory=_inventory(root)
    manifest=json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))
    if (manifest.get('schema')!=1 or manifest.get('paper') is not True or
            manifest.get('restore_policy')!='quarantine_all_queued_side_effects'):
        raise ValueError('invalid_recovery_manifest')
    entries=manifest.get('files')
    if not isinstance(entries,list):raise ValueError('invalid_recovery_manifest')
    names=[]
    for item in entries:
        name=item.get('path')
        if name not in FILES or name in names:raise ValueError('invalid_recovery_entry')
        names.append(name)
        path=inventory.get(name)
        if path is None or path.stat().st_size!=item.get('size') or _sha(path)!=item.get('sha256'):
            raise ValueError('recovery_hash_mismatch')
        if name.endswith('.sqlite3'):
            with closing(_connect(path)) as db:
                if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                    raise ValueError('recovery_integrity')
    if (set(inventory)!=set(names)|{'MANIFEST.json'} or WALLET not in names or
            manifest.get('inbox_configured') is not (INBOX in names) or
            manifest.get('notification_present') is not (NOTIFICATIONS in names)):
        raise ValueError('incomplete_recovery_bundle')
    if _identity(root/WALLET)!=manifest.get('identity'):raise ValueError('recovery_identity_mismatch')
    return manifest


def restore_bundle(bundle,destination):
    """Copy into a new offline staging tree; never install over any wallet.

    Keep deduplication history and financial state exactly. Pending/inflight
    notifications and pending/processing confirmations require reconciliation,
    since they may already have completed after this backup was taken.
    """
    root=_safe(bundle);target=_safe(destination)
    manifest=verify_bundle(root)
    if target.exists() or root==target or root in target.parents:
        raise ValueError('restore_destination_must_be_new_external')
    target.mkdir(mode=0o700)
    try:
        for entry in manifest['files']:
            out=target/entry['path'];out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            shutil.copyfile(root/entry['path'],out);out.chmod(0o600)
            if _sha(out)!=entry['sha256']:raise ValueError('restore_hash_mismatch')
        changed={}
        for name,query in (
                (NOTIFICATIONS,"UPDATE notifications SET status='uncertain' WHERE status IN ('pending','inflight')"),
                (INBOX,"UPDATE commands SET status='needs_reconciliation',result=\'{\"status\":\"needs_reconciliation\"}\' WHERE status IN ('pending','processing')")):
            if not (target/name).exists():continue
            with sqlite3.connect(target/name) as db:
                changed[name]=db.execute(query).rowcount
        # Deliberately not a bundle manifest: derived queue states differ.
        _write_json(target/'RESTORE.json',{'schema':1,'paper':True,
            'identity':manifest['identity'],'quarantined':changed,
            'source_manifest_sha256':_sha(root/'MANIFEST.json'),
            'ready_to_start':False,'requires':'review_config_and_reconcile_side_effects'})
        if _identity(target/WALLET)!=manifest['identity']:raise ValueError('restore_identity_mismatch')
        for path in target.rglob('*'):
            if path.is_file():
                with path.open('rb') as stream:os.fsync(stream.fileno())
        for folder in sorted((p for p in target.rglob('*') if p.is_dir()),reverse=True):_sync_dir(folder)
        _sync_dir(target);_sync_dir(target.parent)
        return target
    except BaseException:
        shutil.rmtree(target)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description='Offline PAPER recovery; no service control')
    commands=parser.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('backup');backup.add_argument('--data-dir',required=True)
    backup.add_argument('--destination',required=True);backup.add_argument('--inbox')
    verify=commands.add_parser('verify');verify.add_argument('--bundle',required=True)
    restore=commands.add_parser('restore');restore.add_argument('--bundle',required=True)
    restore.add_argument('--destination',required=True)
    args=parser.parse_args(argv)
    if args.command=='backup':create_bundle(args.data_dir,args.destination,inbox_path=args.inbox)
    elif args.command=='verify':verify_bundle(args.bundle)
    else:restore_bundle(args.bundle,args.destination)
    print('PAPER recovery '+args.command+': OK (offline only)')


if __name__=='__main__':main()
