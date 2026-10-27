"""Incremental projection for the faster paired runtime, same SQLite authority.

Reconcile the complete append-only projection once on startup or external file
change. Ordinary minute checkpoints export only new event sequences, avoiding
repeated full-history scans. Crash recovery and torn-line policy stay intact.
"""
import json
from director.ai_shadow import journal
from director.brain_pilot.pilot import Store


class CachedStore(Store):
    def __init__(self,*args,**kwargs):
        self._projection_cursors={}
        super().__init__(*args,**kwargs)

    @staticmethod
    def signature(path):
        if not path.exists():return None
        s=path.stat()
        return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

    def export_kind(self,kind,filename):
        path=self.root/filename;signature=self.signature(path)
        cached=self._projection_cursors.get(kind)
        if cached is not None and cached['signature']==signature:
            last=cached['seq'];seen=None
        else:
            last=0;seen=set()
            if path.exists():
                with path.open('rb') as stream:
                    for line in stream:
                        if not line.endswith(b'\n'):raise ValueError('torn_export_requires_recovery')
                        row=json.loads(line);ident=row.pop('brain_event_id')
                        if not isinstance(ident,str) or not ident.startswith('brain-') or not ident[6:].isdigit() or ident in seen:
                            raise ValueError('invalid_or_duplicate_projection_event')
                        source=self.db.execute('SELECT kind,body FROM events WHERE seq=?',(int(ident[6:]),)).fetchone()
                        if source is None or source[0]!=kind or json.loads(source[1])!=row:
                            raise ValueError('projection_source_mismatch')
                        seen.add(ident)
        high=last
        for seq,body in self.db.execute('SELECT seq,body FROM events WHERE kind=? AND seq>? ORDER BY seq',(kind,last)):
            ident='brain-'+str(seq)
            if seen is None or ident not in seen:
                journal.append_jsonl(str(path),dict(json.loads(body),brain_event_id=ident))
            high=seq
        self._projection_cursors[kind]={'signature':self.signature(path),'seq':high}
