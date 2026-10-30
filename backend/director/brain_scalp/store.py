"""Strict, separate SQLite state per PAPER wallet. No existing Brain migration."""
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from director.brain_free.execution import initial
from .config import SPECS,validate_spec


def encode(v): return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)


def wallet_spec_digest(spec):
    """Fingerprint parameters affecting risk, exposure and plan lifetime.

    Changes require an explicit reviewed migration with verified backup:
    never reset or silently alter a persisted PAPER experiment.
    """
    keys=('slots','min_margin','max_margin_trade','start_cash',
          'max_margin_total','risk_trade_usd','risk_portfolio_usd',
          'daily_stop_pct','kill_equity','max_plan_age_ms',
          'max_plan_lifetime_ms')
    return hashlib.sha256(encode({k:getattr(spec,k) for k in keys}).encode()).hexdigest()[:16]


class WalletStore:
    def __init__(self,root,name,initialize=False,now_ms=None,*,spec=None):
        self.spec=validate_spec(SPECS.get(name) if spec is None else spec)
        if self.spec.name!=name: raise ValueError('wrong_wallet_name')
        root=Path(root).absolute()
        forbidden=('superbot-desk-data','superbot-brain-free','superbot-brain-adaptive')
        if (root.name!=name or root.is_symlink() or
            any(p.is_symlink() for p in root.parents) or
            any(x in root.parts for x in forbidden)):
            raise ValueError('invalid_isolated_wallet_root')
        if initialize and root.exists() and any(root.iterdir()):
            raise ValueError('wallet_root_not_empty')
        if not initialize and not (root/'brain_scalp.sqlite3').is_file():
            raise ValueError('explicit_initialization_required')
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if any(p.is_symlink() for p in root.iterdir()): raise ValueError('symlink_data')
        self.root=root
        self.lock=(root/'writer.lock').open('a')
        try: fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise ValueError('wallet_writer_already_active') from None
        self.db=None
        try:
            self.db=sqlite3.connect(root/'brain_scalp.sqlite3',timeout=5,isolation_level=None)
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.executescript('''CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,ts INTEGER NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL);''')
            if initialize:
                now=int(now_ms) if now_ms is not None else 0
                if now<=0: raise ValueError('initial_timestamp_required')
                state=initial(now,wallet_spec_digest(self.spec))
                state.update(account_id=self.spec.account_id,cash=self.spec.start_cash,
                             verified_start_ms=now,plans={},plan_ids=[],
                             daily={'utc':now//86400000,'start_equity':self.spec.start_cash},
                             daily_stop_triggered=False,daily_stop_day=now//86400000,
                             experiment_id=str(uuid4()),runtime_capacity={'max_slots':self.spec.slots,
                             'max_margin':self.spec.max_margin_total})
                self.db.execute('INSERT INTO state VALUES(1,0,?)',(encode(state),))
            self.load()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db=None
        self.lock.close()

    def load(self):
        row=self.db.execute('SELECT version,body FROM state WHERE id=1').fetchone()
        if row is None: raise ValueError('missing_wallet_state')
        state=json.loads(row[1]);state['_version']=row[0]
        if state.get('mode')!='paper' or state.get('account_id')!=self.spec.account_id:
            raise ValueError('wrong_wallet_identity')
        current=wallet_spec_digest(self.spec)
        if state.get('config_hash')!=current:
            raise ValueError('explicit_config_migration_required')
        # Old offline wallets must be backed up and explicitly migrated.
        if 'daily_stop_triggered' not in state or 'daily_stop_day' not in state:
            raise ValueError('explicit_daily_stop_migration_required')
        return state

    def commit(self,state,now,events=()):
        body=dict(state);version=body.pop('_version')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            cur=self.db.execute('UPDATE state SET version=version+1,body=? WHERE id=1 AND version=?',
                                (encode(body),version))
            if cur.rowcount!=1: raise ValueError('stale_writer')
            for ev in events:
                self.db.execute('INSERT INTO events(id,ts,kind,body) VALUES(?,?,?,?)',
                    (str(uuid4()),now,ev['kind'],encode(ev)))
            self.db.execute('COMMIT')
            state['_version']=version+1
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def backup(self,destination):
        destination=Path(destination)
        if destination.exists(): raise ValueError('backup_exists')
        with sqlite3.connect(destination) as target:
            self.db.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('backup_integrity')
            for table in ('state','events'):
                if (self.db.execute('SELECT * FROM '+table).fetchall() !=
                    target.execute('SELECT * FROM '+table).fetchall()):
                    raise ValueError('backup_mismatch')
        return destination
