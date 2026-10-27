#!/usr/bin/env python3
"""Offline PAPER method migration; workers must be stopped, new entries paused.

Compute via the actual runtime.configure/method_digest in a dedicated process.
Never initialize accounts, change financial history, reset budgets or deploy.
Use the same image/dependencies and policy environment as the target worker.
A complete rollout still requires image promotion, backups of all profile
files/shared ledger, protected restart and postflight; this is only DB migration.
"""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = Path('/opt/superbot-brain-adaptive')
HELPER = '''import sys,io,contextlib
sys.path.insert(0,sys.argv[1])
with contextlib.redirect_stdout(io.StringIO()):
    from director.classical_adaptive.runtime import configure,method_digest
    cli=configure(sys.argv[2],sys.argv[3])
    result=method_digest(cli)
print(result)
'''


def valid_digest(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ValueError('INVALID_METHOD_DIGEST')
    return value


def compute_method_digest_subprocess(profile, parent):
    env=os.environ.copy()
    env['DESK_MODE']='paper'
    env['PYTHONDONTWRITEBYTECODE']='1'
    # configure enforces the isolated PAPER profile and disables alternate keys.
    result=subprocess.run([sys.executable,'-I','-c',HELPER,str(REPO_ROOT/'backend'),str(parent),profile],
                          env=env,capture_output=True,text=True,timeout=60)
    if result.returncode:raise ValueError('DIGEST_SUBPROCESS_FAILED')
    return valid_digest(result.stdout.strip())


def backup_db(source,path):
    backup=path.with_name('brain.sqlite3.before-method-'+uuid.uuid4().hex)
    fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    try:
        with sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('BACKUP_INTEGRITY_FAILED')
            # Reopen comparison checks full authoritative state and events.
        with sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True) as restored:
            for table,columns in [('state','id,body'),('events','seq,kind,body')]:
                query='SELECT '+columns+' FROM '+table+' ORDER BY 1'
                if source.execute(query).fetchall()!=restored.execute(query).fetchall():
                    raise ValueError('BACKUP_RESTORE_COMPARISON_FAILED')
        return backup
    except Exception:
        # Retain any partial backup for investigation; never overwrite it.
        raise


def migrate(profile,expected_old_method,*,dry_run=False,data_root=DEFAULT_ROOT,source_sha=None):
    if profile not in ('hawk','bull'):raise ValueError('UNKNOWN_PROFILE')
    valid_digest(expected_old_method)
    if os.getenv('DESK_MODE','paper')!='paper':raise ValueError('PAPER_REQUIRED')
    if not isinstance(source_sha,str) or not re.fullmatch('[a-f0-9]{40}',source_sha):
        raise ValueError('FULL_SOURCE_SHA_REQUIRED')
    parent=Path(data_root).absolute();folder=parent/('brain-'+profile)
    path=folder/'brain.sqlite3';lock=folder/'writer.lock'
    if any(p.is_symlink() for p in (path,lock,folder,*folder.parents)):
        raise ValueError('SYMLINK_DATA_PATH')
    if not path.is_file() or not lock.is_file():raise ValueError('EXISTING_PROFILE_REQUIRED')
    # Require an existing operator pause before any actual migration.
    if not dry_run and not (folder/'pause.flag').is_file():raise ValueError('PAUSE_REQUIRED')
    with lock.open('rb') as writer:
        try:fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('WRITER_STILL_ACTIVE') from None
        mode='ro' if dry_run else 'rw'
        db=sqlite3.connect(path.resolve().as_uri()+'?mode='+mode,uri=True,isolation_level=None,timeout=2)
        try:
            row=db.execute('SELECT body FROM state WHERE id=1').fetchone()
            if row is None:raise ValueError('MISSING_STATE')
            original=json.loads(row[0]);old=valid_digest(original.get('method'))
            if (original.get('version'),original.get('profile'),original.get('desk',{}).get('main',{}).get('name'))!=('classical-adaptive-v1',profile,'brain-'+profile):
                raise ValueError('PROFILE_STATE_MISMATCH')
            if old!=expected_old_method:raise ValueError('UNEXPECTED_OLD_METHOD')
            new=compute_method_digest_subprocess(profile,parent)
            report={'profile':profile,'mode':'paper','dry_run':dry_run,'source_sha':source_sha,
                    'from_method':old,'to_method':new,'changed':new!=old}
            if dry_run or new==old:return report
            before_count=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            backup=backup_db(db,path)
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT body FROM state WHERE id=1').fetchone()[0]!=row[0] or db.execute('SELECT COUNT(*) FROM events').fetchone()[0]!=before_count:
                raise ValueError('STATE_CHANGED_DURING_BACKUP')
            updated=copy.deepcopy(original);updated['method']=new
            event={'kind':'method_migration','profile':profile,'mode':'paper','ts_ms':int(time.time()*1000),
                   'from_method':old,'to_method':new,'source_sha':source_sha}
            db.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(updated,allow_nan=False),))
            db.execute("INSERT INTO events(kind,body) VALUES('journal',?)",(json.dumps(event,allow_nan=False),))
            verified=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            verified['method']=old
            if verified!=original:raise ValueError('STATE_PRESERVATION_FAILED')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('DATABASE_INTEGRITY_FAILED')
            db.commit();report['backup']=str(backup)
            return report
        except Exception:
            if db.in_transaction:db.rollback()
            raise
        finally:db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['hawk','bull'],required=True)
    parser.add_argument('--expected-old-method',required=True)
    parser.add_argument('--source-sha',required=True,help='Reviewed target image/source SHA, recorded as provenance; verify image label externally.')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(migrate(args.profile,args.expected_old_method,dry_run=args.dry_run,source_sha=args.source_sha),sort_keys=True))
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z_]+',str(exc)) else type(exc).__name__
        print('METHOD_MIGRATION_FAILED='+code);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
