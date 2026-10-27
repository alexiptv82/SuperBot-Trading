"""Durable single account, audit, usage and Telegram outbox. Never resets."""
import contextlib,fcntl,hashlib,json,os,sqlite3,time,uuid
from pathlib import Path


def dumps(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)

class Store:
    def __init__(self,root,initialize=False,digest=None,now_ms=None):
        root=Path(root).absolute()
        if root.is_symlink() or any(p.is_symlink() for p in root.parents):raise ValueError('symlink_root')
        forbidden=('/opt/superbot-desk-data','/opt/superbot-brain-adaptive','/opt/superbot/data')
        if any(root==Path(x) or Path(x) in root.parents for x in forbidden):raise ValueError('foreign_data_root')
        existed=root.exists();root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if any(p.is_symlink() for p in root.iterdir()):raise ValueError('symlink_data')
        if initialize and any(root.iterdir()):raise ValueError('initialization_requires_empty_directory')
        if not initialize and not (root/'brain.sqlite3').is_file():raise ValueError('explicit_initialization_required')
        self.root=root;self.lock=(root/'writer.lock').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:self.lock.close();raise ValueError('writer_already_active') from None
        self.db=sqlite3.connect(root/'brain.sqlite3',timeout=5,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,ts INTEGER NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,ts INTEGER NOT NULL,status TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,body TEXT NOT NULL,sent INTEGER DEFAULT 0,attempts INTEGER DEFAULT 0);''')
        if initialize:
            from .execution import initial
            state=initial(now_ms or int(time.time()*1000),digest)
            self.db.execute('INSERT INTO state VALUES(1,0,?)',(dumps(state),))
        row=self.load()
        if row['mode']!='paper' or row['account_id']!='brain-free-paper':self.close();raise ValueError('foreign_account')
        if digest is not None and row['config_hash']!=digest:self.close();raise ValueError('explicit_version_migration_required')
        # A crashed request may already have been billed. Preserve uncertainty.
        self.db.execute("UPDATE requests SET status='unknown_after_restart' WHERE status='pending'")
    def close(self):
        self.db.close();self.lock.close()
    def load(self):
        row=self.db.execute('SELECT version,body FROM state WHERE id=1').fetchone()
        if row is None:raise ValueError('missing_authoritative_account')
        state=json.loads(row[1]);state['_version']=row[0];return state
    def commit(self,state,events=(),messages=()):
        body=dict(state);version=body.pop('_version')
        with self.transaction():
            cur=self.db.execute('UPDATE state SET version=version+1,body=? WHERE id=1 AND version=?',(dumps(body),version))
            if cur.rowcount!=1:raise ValueError('stale_writer')
            for ident,kind,ts,event in events:
                self.db.execute('INSERT INTO events(id,kind,ts,body) VALUES(?,?,?,?)',(ident,kind,ts,dumps(event)))
            for ident,message in messages:self.db.execute('INSERT OR IGNORE INTO outbox(id,body) VALUES(?,?)',(ident,message))
        state['_version']=version+1
    @contextlib.contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield;self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    def record_request(self,ident,ts,body):
        self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',(ident,ts,'pending',dumps(body)))
    def finish_request(self,ident,status,body):
        self.db.execute('UPDATE requests SET status=?,body=? WHERE id=?',(status,dumps(body),ident))
    def backup(self,destination):
        destination=Path(destination)
        if destination.exists():raise ValueError('backup_exists')
        with sqlite3.connect(destination) as target:
            self.db.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('backup_integrity')
            for table in ('state','events','requests','outbox'):
                if self.db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()!=target.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall():raise ValueError('backup_mismatch')
        return destination
    def recent(self,limit=10):
        return [json.loads(x[0]) for x in self.db.execute("SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq DESC LIMIT ?",(limit,))][::-1]
    def enqueue(self,ident,text):self.db.execute('INSERT OR IGNORE INTO outbox(id,body) VALUES(?,?)',(ident,text))
