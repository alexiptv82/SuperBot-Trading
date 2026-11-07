#!/usr/bin/env python3
"""Independently verify the completed RC69 local PAPER snapshot: read-only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

DATA_ROOT = Path('/opt/superbot-desk-data')
BACKUP_ROOT = Path('/opt/superbot-backups')
ESSENTIAL = {'state_v2.json','trade_history.jsonl','learning_log.jsonl','lessons.md'}
EXPECTED_OPEN = {'hawk':6,'bull':2}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()

def verify_one(snapshot):
    if snapshot.is_symlink() or not snapshot.is_dir():
        return None
    manifest_path = snapshot/'MANIFEST.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return None
    try:
        m=json.loads(manifest_path.read_text('utf-8'))
        if (m.get('schema') != 'rc69-paper-local-snapshot-v1'
                or m.get('restore_rehearsal') != 'PASS'
                or m.get('source_data_unchanged') is not True
                or set(m.get('portfolios',{})) != set(EXPECTED_OPEN)):
            return None
        counts = {}
        for name,n_expected in EXPECTED_OPEN.items():
            portfolio=m['portfolios'][name]
            if type(portfolio.get('open_positions')) is not int or portfolio['open_positions'] != n_expected:
                return None
            hashes=portfolio.get('hashes')
            if type(hashes) is not dict or not ESSENTIAL.issubset(hashes):
                return None
            if len(hashes) != portfolio.get('files') or len(hashes)>100000:
                return None
            actual=DATA_ROOT/name
            archive=snapshot/name
            if archive.is_symlink() or not archive.is_dir() or not actual.is_dir():
                return None
            for rel,digest_expected in hashes.items():
                if type(rel) is not str or len(rel)>400 or type(digest_expected) is not str:
                    return None
                relpath=Path(rel)
                if relpath.is_absolute() or '..' in relpath.parts or not relpath.parts:
                    return None
                a=actual/relpath
                b=archive/relpath
                if any(f.is_symlink() for f in (a,b)) or not a.is_file() or not b.is_file():
                    return None
                if digest(a)!=digest_expected or digest(b)!=digest_expected:
                    return None
            positions=json.loads((archive/'state_v2.json').read_text('utf-8'))['main']['positions']
            if not isinstance(positions,dict) or len(positions)!=n_expected:
                return None
            counts[name]=len(hashes)
        return counts
    except (OSError,TypeError,ValueError,KeyError):
        return None

def main():
    if BACKUP_ROOT.is_symlink() or not BACKUP_ROOT.is_dir():
        print('RC69_VERIFICATION=REFUSED_NO_BACKUP_ROOT')
        return 2
    matches=[]
    for directory in BACKUP_ROOT.glob('rc69-paper-legacy-*'):
        verified=verify_one(directory)
        if verified:
            matches.append((directory.name,verified))
    if not matches:
        print('RC69_VERIFICATION=NO_VALID_CURRENT_SNAPSHOT')
        return 2
    latest,counts=max(matches,key=lambda x:x[0])
    print('RC69_VERIFICATION=PASS')
    print('RC69_USABLE_SNAPSHOTS='+str(len(matches)))
    print('RC69_PREFERRED_SNAPSHOT_BASENAME='+latest)
    print('RC69_HAWK_FULL_FILE_MATCHES='+str(counts['hawk']))
    print('RC69_BULL_FULL_FILE_MATCHES='+str(counts['bull']))
    print('RC69_RESTORE_TEST_EVIDENCE=MANIFEST_RECORDED_PASS')
    print('RC69_REMOTE_READ_ONLY=True')
    return 0

if __name__=='__main__':
    sys.exit(main())
