"""Explicit in-place PAPER V1 -> V2 reframe. Never called by normal runtime.

Operator must stop the existing worker after it is paused and all positions
have closed. Migrate the SAME SQLite account, preserving complete prior event,
request and outbox history; the old run remains queryable and in the archive.
The V2 cash is the actual remaining PAPER cash (no unrequested reset/top-up).
"""
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,sqlite3,time,uuid
from pathlib import Path
from .config import Config
from .mandate import SYSTEM
from .memory import seeds
from .store import dumps
from .execution import initial


def migrate(root, backup_dir, old_sha, new_sha, now_ms=None):
    root=Path(root).absolute();backup_dir=Path(backup_dir).absolute()
    if root.is_symlink() or backup_dir.is_symlink():raise ValueError('unsafe_symlink')
    if root==backup_dir or root in backup_dir.parents:raise ValueError('backup_inside_account')
    if not (root/'pause.flag').is_file():raise ValueError('paused_flag_required')
    if (root/'brain.sqlite3').is_symlink():raise ValueError('symlink_database')
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    for sha in (old_sha,new_sha):
        if not isinstance(sha,str) or len(sha)!=40 or any(x not in '0123456789abcdef' for x in sha):
            raise ValueError('immutable_build_sha_required')
    cfg=Config();digest=cfg.digest(SYSTEM+dumps(seeds(Path(__file__).parent/'seeds')))
    # Exclusivity checked against the same writer lock used by the runtime.
    lock=(root/'writer.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:lock.close();raise ValueError('running_writer_must_stop_first') from None
    db=None
    try:
        db=sqlite3.connect(root/'brain.sqlite3',timeout=5,isolation_level=None)
        db.execute('PRAGMA busy_timeout=5000')
        ver,raw=db.execute('SELECT version,body FROM state WHERE id=1').fetchone()
        old=json.loads(raw)
        if old.get('account_id')!='brain-free-paper' or old.get('mode')!='paper':
            raise ValueError('foreign_account')
        if old.get('build_sha')!=old_sha:raise ValueError('unexpected_old_build')
        if old.get('config_hash')==digest:raise ValueError('already_reframed')
        if old.get('positions'):raise ValueError('positions_must_close_before_reframe')
        if old.get('paused') is not True:raise ValueError('pause_not_acknowledged')
        if old.get('verified_start_ms') is None:raise ValueError('old_run_not_started')
        if not 0<=now_ms-old.get('last_ms',now_ms)<7*86400000:raise ValueError('invalid_reframe_time')
        backup_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
        backup_file=backup_dir/'brain-before-v2.sqlite3'
        with sqlite3.connect(backup_file) as snapshot:
            db.backup(snapshot)
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('backup_integrity')
            for tab in ('state','events','requests','outbox'):
                # Backup proof includes exact table contents, not just row counts.
                expected=db.execute('SELECT * FROM '+tab+' ORDER BY 1').fetchall()
                actual=snapshot.execute('SELECT * FROM '+tab+' ORDER BY 1').fetchall()
                if actual!=expected:raise ValueError('backup_table_mismatch')
        # Copy immutable manifest; no deletion of original or backup ever occurs.
        (backup_dir/'sha256.txt').write_text(
            hashlib.sha256(backup_file.read_bytes()).hexdigest()+'  brain-before-v2.sqlite3\n')
        (backup_dir/'prior-run.json').write_text(dumps({
            'old_sha':old_sha,'old_run_id':old.get('experiment_id'),
            'old_verified_start_ms':old.get('verified_start_ms'),
            'old_cash':old['cash'],'old_cycles':old.get('cycles'),
            'new_sha':new_sha,'new_time_ms':now_ms}))
        state=initial(now_ms,digest)
        state['cash']=old['cash']  # no hidden equity top-up or account reset.
        state['build_sha']=new_sha
        state['verified_start_ms']=now_ms
        state['paused']=True
        state['v2_start_equity']=old['cash']
        state['previous_run_id']=old['experiment_id']
        state['previous_run_start_ms']=old['verified_start_ms']
        state['runtime_capacity']={'max_slots':cfg.max_slots,'max_margin':cfg.max_margin}
        state['last_prices']=old.get('last_prices',{})
        # Full previous state snapshot is retained as an immutable event and
        # the original database is independently backed up above.
        ident='brain-v2-reframe:'+str(uuid.uuid4())
        db.execute('BEGIN IMMEDIATE')
        try:
            updated=db.execute('UPDATE state SET version=version+1,body=? WHERE id=1 AND version=?',
                               (dumps(state),ver))
            if updated.rowcount!=1:raise ValueError('stale_version')
            db.execute('INSERT INTO events(id,kind,ts,body) VALUES(?,?,?,?)',
                       (ident,'experiment_reframed',now_ms,dumps({
                           'old_build_sha':old_sha,'new_build_sha':new_sha,
                           'old_state':old,'new_experiment_id':state['experiment_id'],
                           'old_cash':old['cash'],'new_cash':state['cash'],
                           'no_real_trading':True})))
            db.execute('INSERT OR IGNORE INTO outbox(id,body) VALUES(?,?)',
                       (ident,'[BRAIN] V2 PAPER configurata; memoria e registro V1 conservati. '
                        'Nuovi ingressi ancora in pausa fino alla verifica operatore.'))
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK');raise
        return {'status':'migrated_paused','new_run_id':state['experiment_id'],
                'cash':state['cash'],'old_events_preserved':True,'backup':str(backup_file)}
    finally:
        if db is not None:db.close()
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--backup',required=True)
    parser.add_argument('--old-sha',required=True)
    parser.add_argument('--new-sha',required=True)
    parser.add_argument('--approved',choices=('no','yes'),default='no')
    args=parser.parse_args()
    if args.approved!='yes':raise SystemExit('explicit operator approval required')
    print(json.dumps(migrate(args.root,args.backup,args.old_sha,args.new_sha)))


if __name__=='__main__':main()
