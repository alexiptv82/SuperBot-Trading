"""Reconcile archived PAPER positions using the existing, pinned tape audit.

No market data download, trading engine import, orders, or VPS access.
git show reads immutable inputs; --output-dir contains only derived reports.
"""
import argparse
from collections import Counter
import csv
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
from statistics import median
import subprocess
import types

DIARY_SHA='0c416e8f285e06ac423de2acadc067a014d73d42'
LAB_SHA='e9fafa2373af3c0aab935108b30f2f62805e33e5'
TAPE_AUDIT_HASH='e7a2bd43ec79db5f7d5958dd11daca57528477d1497f27b8d49fd63607866f92'
EXPORT_HASH='0d1252e15d5d07c7dc7fa61789648e0a45d9383e7efc783852439ceaf95ff281'
DATA_DIR='diario/analisi-run-2026-10-27/'
REFS={
    'a0afc63':'a0afc63fccc16b0081bc6fdd49768506b9242f89',
    '7ced3a6':'7ced3a6f4fb0db1261a3306100491a42a35ddbb4',
    '9fa667f':'9fa667ff1103f037bec06f9131996366d27370c4',
    '5818aee':'5818aee1e587f103d222510e761b30e02776ff15',
    'b4709d1':'b4709d117eee335fd33fccce8ff45f8295c67783',
    'rollback0ad':'0ad68935c1ec12e514a1652f6a43d09d4a23aa75',
}


def read_blob(repo,ref,path):
    return subprocess.check_output(['git','show',ref+':'+path],cwd=repo,timeout=20)


def summarize(rows):
    features=[json.loads(r['features_json']) for r in rows
              if r['features_json'] not in ('','{}','null')]
    components=Counter(k for r in rows for k in json.loads(r['components_json'] or '{}'))
    wins=sum(Decimal(r['net'])>0 for r in rows)
    return {
        'n':len(rows),'wins':wins,
        'net':float(sum((Decimal(r['net']) for r in rows),Decimal(0))),
        'wr':round(100*wins/len(rows),2) if rows else None,
        'feature_n':len(features),'components':dict(components),
        'median':{key:median(float(r[key]) for r in rows if r.get(key))
                  if any(r.get(key) for r in rows) else None
                  for key in ('leverage','entry_margin','entry_r_dist','duration_h')},
        'entry_code':dict(Counter(r['entry_code'] or 'unknown' for r in rows)),
        'symbols':dict(Counter(r['symbol'] for r in rows)),
    }


def reconcile(repo):
    raw=read_blob(repo,DIARY_SHA,DATA_DIR+'positions.csv')
    if sha256(raw).hexdigest()!=EXPORT_HASH:
        raise ValueError('unexpected_archived_export')
    source=read_blob(repo,LAB_SHA,'backend/rollback_lab/tape_audit.py')
    if sha256(source).hexdigest()!=TAPE_AUDIT_HASH:
        raise ValueError('unexpected_existing_tape_audit')
    # Reuse the already reviewed validator; do not fork its reconciliation.
    audit=types.ModuleType('pinned_classical_tape_audit')
    exec(compile(source,'pinned:tape_audit.py','exec'),audit.__dict__)
    rows,digest=audit.load_tape(raw)
    original=audit.analyze(raw)
    summary={'source_sha256':digest,'groups':{},'fingerprints':{}}
    for label,pairs in [('golden',[('hawk','2'),('bull','1')]),
                        ('crisis',[('hawk','3'),('bull','2')])]:
        selected=[r for r in rows if (r['bot'],r['run_no']) in pairs]
        summary['groups'][label]={side:summarize([r for r in selected if r['side']==value])
                                 for side,value in [('SHORT','-1'),('LONG','1')]}
    for label,ref in REFS.items():
        summary['fingerprints'][label]={
            filename:sha256(read_blob(repo,ref,'backend/desk/'+filename)).hexdigest()
            for filename in ('signals.py','seasonal.py')}
    fields=['bot','run_no','id','symbol','side','open_utc','entry_code',
            'entry_code_evidence','entry_log_present']
    out=io.StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n')
    writer.writeheader()
    for row in rows:
        if (row['bot'],row['run_no']) in [('hawk','2'),('bull','1')]:
            writer.writerow({key:row[key] for key in fields})
    return summary,out.getvalue(),original


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    summary,chronology,original=reconcile(args.repo)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,value in [('audit_summary.json',summary),('original_tape_audit.json',original)]:
        (args.output_dir/name).write_text(
            json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (args.output_dir/'entry_provenance.csv').write_text(chronology,encoding='utf-8')
    print('ARCHIVED_PAPER_AUDIT_NOT_REPLAY',summary['source_sha256'])
    for period,sides in summary['groups'].items():
        print(period,{side:(x['n'],x['net']) for side,x in sides.items()})


if __name__=='__main__':
    main()
