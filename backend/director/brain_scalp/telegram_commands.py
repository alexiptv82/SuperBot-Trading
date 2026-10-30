"""Authenticated, idempotent Telegram update handler (no Telegram networking).

The operator's PAPER wallet remains the only financial writer. The eventual
Telegram poller must run once per token and hand in verified getUpdates data on
the owner thread; this module never starts that poller automatically.
"""
import fcntl
import json
import os
from pathlib import Path


class PaperTelegramCommands:
    def __init__(self,operator,*,allowed_chat_id,allowed_user_id):
        if (type(allowed_chat_id)!=int or type(allowed_user_id)!=int or
                allowed_chat_id==0 or allowed_user_id<=0):
            raise ValueError('explicit_telegram_owner_required')
        self.operator=operator
        self.chat_id=allowed_chat_id
        self.user_id=allowed_user_id
        root=operator.wallet.store.root
        self.journal=Path(root)/'brain_operator_updates.jsonl'
        self.lock=Path(root)/'.brain_operator_updates.lock'

    def _seen(self,update_id):
        if not self.journal.exists():return False
        if self.journal.is_symlink():raise ValueError('unsafe_telegram_journal')
        with self.journal.open(encoding='utf-8') as f:
            for line in f:
                try:r=json.loads(line)
                except ValueError:raise ValueError('corrupt_telegram_journal')
                if r.get('update_id')==update_id:return True
        return False

    def handle(self,update,markets,now):
        """Consumes one Telegram getUpdates item; never retries a close after a crash.

        Only allowlisted chat+user may execute commands. An unrecognized or
        stale request is not stored, executed or reflected to the model.
        """
        if not isinstance(update,dict) or type(update.get('update_id'))!=int or (
            update['update_id']<0):
            raise ValueError('invalid_telegram_update')
        msg=update.get('message')
        if not isinstance(msg,dict) or type(msg.get('chat',{}).get('id'))!=int or (
            type(msg.get('from',{}).get('id'))!=int) or (
            msg['chat']['id']!=self.chat_id or msg['from']['id']!=self.user_id):
            return {'status':'ignored_unauthorized'}
        content=msg.get('text')
        if not isinstance(content,str) or len(content)>160:
            return {'status':'invalid_command'}
        parts=content.strip().split()
        is_teach=(parts[:1] in (['/insegna_si'],['/insegna_no']))
        is_close=(parts[:2]==['/chiudi','brain'] and len(parts)==4 and
                  parts[3]=='motivo=profitto_ok')
        if not is_teach and not is_close:
            return {'status':'unsupported_or_ambiguous_command'}
        if self.journal.is_symlink() or self.lock.is_symlink():
            raise ValueError('unsafe_telegram_journal')
        with self.lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                if self._seen(update['update_id']):
                    return {'status':'duplicate_ignored'}
                # Record the command BEFORE modifying any wallet state. A
                # process crash after this write cannot replay '/chiudi all'
                # onto new positions that appeared after the first request.
                fd=os.open(str(self.journal),os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o600)
                with os.fdopen(fd,'a',encoding='utf-8') as f:
                    f.write(json.dumps({'update_id':update['update_id'],
                                        'ts_ms':now,'event':'accepted'})+'\n')
                    f.flush();os.fsync(f.fileno())
                if is_teach:
                    return {'status':'teaching_recorded',
                            'count':self.operator.confirm(content,now)}
                symbol=parts[2].upper()
                state=self.operator.wallet.store.load()
                positions=state['positions']
                if symbol=='ALL':
                    ids={s:p['id'] for s,p in positions.items()}
                else:
                    if symbol.endswith('USDT') and len(symbol)>4:
                        symbol=symbol[:-4]
                    if not symbol.isascii() or not symbol.isalnum() or len(symbol)>20:
                        raise ValueError('invalid_symbol')
                    ids=({symbol:positions[symbol]['id']}
                         if symbol in positions else {})
                if not ids:
                    return {'status':'no_open_paper_positions'}
                result=self.operator.close(ids,markets,now,reason='profit_ok_free_slot')
                return {'status':'closed_paper_verified','result':result}
            finally:
                fcntl.flock(lock,fcntl.LOCK_UN)
