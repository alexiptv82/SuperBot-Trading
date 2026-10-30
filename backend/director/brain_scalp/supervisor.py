"""Offline-ready single-account supervisor; external host supplies fresh data.

No HTTP, daemon launch or credentials. Only analysis runs in the worker; all
SQLite/protect/admission/snapshot work stays on the owner's thread. The host
must invoke step frequently, even while AI is pending, and enforce transport
network timeouts and a conservative per-analysis cost ceiling (both providers).
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from .ai_analysis import evaluate
from .ai_context import decode
from .scanner import scan
from .snapshot import atomic_write,build_account_snapshot


class PaperSupervisor:
    def __init__(self,account,*,primary_call,reviewer_call,clock_ms,
                 daily_budget_micro_usd,reservation_micro_usd,
                 analysis_interval_ms=300000,deadline_ms=30000,snapshot_path=None):
        if set(account.wallets)!={'brain'}:raise ValueError('single_account_required')
        if not callable(primary_call) or not callable(clock_ms):
            raise ValueError('explicit_callbacks_required')
        if reviewer_call is not None and not callable(reviewer_call):
            raise ValueError('invalid_reviewer')
        if (any(type(v)!=int or v<=0 for v in (daily_budget_micro_usd,
                reservation_micro_usd,analysis_interval_ms,deadline_ms)) or
                reservation_micro_usd>daily_budget_micro_usd or
                deadline_ms>account.brain.spec.max_plan_age_ms):
            raise ValueError('invalid_supervisor_limits')
        previous=getattr(account,'_analysis_supervisor',None)
        if previous is not None and (not previous.closed or
                (previous.future is not None and not previous.future.done())):
            raise ValueError('supervisor_already_active')
        self.account=account;self.primary=primary_call;self.reviewer=reviewer_call
        self.clock=clock_ms;self.budget=daily_budget_micro_usd
        self.reservation=reservation_micro_usd;self.interval=analysis_interval_ms
        self.deadline=deadline_ms;self.snapshot_path=snapshot_path
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='brain-analysis')
        self.future=None;self.request=None;self.last_snapshot=None
        self.cancel=Event();self.closed=False
        account._analysis_supervisor=self

    def close(self):
        self.closed=True;self.cancel.set()
        self.pool.shutdown(wait=False,cancel_futures=True)
        # Cannot kill an in-flight network call: host transports need timeouts.
        # Worker never owns SQLite and will never admit a late response.

    def _guarded(self,call,request):
        if call is None:return None
        def invoke(system,user):
            now=self.clock()
            if (self.cancel.is_set() or type(now)!=int or
                    not request.created_ms<=now<=request.deadline_ms):
                raise ValueError('analysis_expired_before_provider')
            return call(system,user)
        return invoke

    def _reserve(self,now):
        store=self.account.brain.store;state=store.load()
        previous=state.get('ai_budget_reservation',{})
        day=now//86400000
        old_day=previous.get('day',day)
        if day<old_day:raise ValueError('budget_clock_backwards')
        last=previous.get('last_started_ms')
        if last is not None and now-last<self.interval:return 'cooldown'
        used=previous.get('reserved_micro_usd',0) if old_day==day else 0
        if used+self.reservation>self.budget:return 'budget_exhausted'
        # Charge before submitting, never refund unknown/failed requests.
        # Survives restart; conservative bound, NOT measured API expenditure.
        state['ai_budget_reservation']={'day':day,'last_started_ms':now,
            'reserved_micro_usd':used+self.reservation}
        store.commit(state,now,[{'kind':'ai_budget_reserved','day':day,
            'reserved_micro_usd':self.reservation}])
        return 'reserved'

    def step(self,markets,contracts,*,references=None):
        if self.closed:raise ValueError('supervisor_closed')
        now=self.clock()
        if type(now)!=int or now<=0:raise ValueError('invalid_clock')
        # Always protect first, independent of a slow, broken or unavailable AI.
        tick=self.account.tick(markets,contracts,now)
        output={'tick':tick,'analysis_status':'idle'}
        scan_result=scan(markets,now,limit=10,diagnostics=True)
        output['scanner_diagnostics']=scan_result['diagnostics']
        healthy=tick['brain'].get('status')!='error'
        if healthy:
            store=self.account.brain.store;state=store.load()
            if state.get('scanner_audit_minute')!=now//60000:
                diag=scan_result['diagnostics']
                state['scanner_audit_minute']=now//60000
                store.commit(state,now,[{'kind':'scanner_observed','as_of_ms':now,
                    'counts':diag['counts'],'scope':diag['scope'],
                    'rows':diag['rows'][:200],'omitted_rows':max(0,len(diag['rows'])-200)}])
        if self.future is not None:
            if self.future.done():
                try:
                    analysis=self.future.result()
                    output['analysis']=self.account.accept_ai_analysis(
                        'brain',self.request,analysis,markets,contracts,now) if healthy else {'status':'wallet_error'}
                except Exception:
                    output['analysis']={'status':'analysis_failed'}
                self.future=None;self.request=None
                output['analysis_status']='completed'
            else:
                output['analysis_status']=('expired_waiting_for_transport' if
                    now>self.request.deadline_ms else 'pending')
        elif healthy and scan_result['candidates']:
            state=self.account.brain.store.load()
            if state.get('paused') or state.get('daily_stop_triggered') or state.get('coverage_gaps'):
                output['analysis_status']='wallet_guarded'
            else:
                request=self.account.prepare_ai_request('brain',scan_result,markets,
                    contracts,references or {},now,now+self.deadline)
                if not decode(request.payload_json)['candidates']:
                    output['analysis_status']='no_fresh_candidates'
                else:
                    status=self._reserve(now);output['analysis_status']=status
                    if status=='reserved':
                        self.request=request
                        self.future=self.pool.submit(evaluate,request,
                            self._guarded(self.primary,request),self._guarded(self.reviewer,request))
                        output['analysis_status']='started'
        if self.snapshot_path is not None and (self.last_snapshot is None or now-self.last_snapshot>=5000):
            atomic_write(self.snapshot_path,build_account_snapshot(self.account,now))
            self.last_snapshot=now
        return output
