"""One sequential intake run's envelope over the existing metered components.

Not authority: the SQL period/stop and source contracts are independent gates.
Unused selection allocation never consumes protected closure reserves.
"""
import time,math
from app.ingestion.ledger import Denied

LIMITS=dict(requests=90,source_bytes=23971520,source_seconds=120,supervised_seconds=150,
            driver_statements=2080,connection_attempts=80,returned_bytes=8*1024**2,
            github_calls=80,export_bytes=2*1024**2,wall_seconds=960)
RESERVE=dict(driver_statements=32,connection_attempts=4,github_calls=20,wall_seconds=180,export_bytes=768*1024)

class IntakeRun:
    def __init__(self,*,clock=time.monotonic,stop_file=None):
        self.clock=clock;self.started=clock();self.stop_file=stop_file;self.budgets=[]
        self.used=dict(requests=0,source_bytes=0,source_seconds=0,supervised_seconds=0,github_calls=0,export_bytes=0)
        self.closing=False

    def check(self):
        from pathlib import Path
        if self.stop_file and Path(self.stop_file).exists() and not self.closing:raise Denied('OWNER_STOP')
        if self.clock()-self.started>=LIMITS['wall_seconds']-(0 if self.closing else RESERVE['wall_seconds']):raise Denied('INTAKE_RUN_DEADLINE')

    def totals(self):
        cancels=sum(b.prior_cancel_attempts+sum(e.get('cancel_attempts',0) for e in b.hard_deadline_events) for b in self.budgets)
        return dict(self.used,driver_statements=sum(b.statements for b in self.budgets),
                    connection_attempts=sum(b.attempts for b in self.budgets)+cancels,cancel_requests=cancels,returned_bytes=sum(b.returned_bytes for b in self.budgets),
                    elapsed_seconds=self.clock()-self.started,
                    all_connections_closed=all(c.closed for b in self.budgets for c in b.opened))

    def database_limits(self,kw):
        self.check();totals=self.totals();out=dict(kw)
        for name,field,default in [('driver_statements','statements',120),('connection_attempts','connections',16),('returned_bytes','returned_bytes',4*1024**2)]:
            left=LIMITS[name]-totals[name]-(0 if self.closing else RESERVE.get(name,0))
            if name=='connection_attempts':left-=8-totals['cancel_requests']
            if left<(20 if field=='statements' else 1):raise Denied('INTAKE_RUN_DATABASE_RESERVE')
            out[field]=min(out.get(field,default),left)
        remaining=LIMITS['wall_seconds']-(self.clock()-self.started)-(0 if self.closing else RESERVE['wall_seconds'])
        out['seconds']=min(out.get('seconds',165),remaining)
        used=sum(b.prior_cancel_attempts+sum(e.get('cancel_attempts',0) for e in b.hard_deadline_events) for b in self.budgets)
        out['cancel_used']=max(out.get('cancel_used',0),used)
        if out['seconds']<=0:raise Denied('INTAKE_RUN_DEADLINE')
        return out

    def before_scope(self,family):
        if self.closing:raise Denied('CLOSING_NO_WORK')
        self.check();t=self.totals()
        # Reserve a whole supported scope BEFORE its claim/source intent, not
        # merely one request. Actual closed use, not a fresh budget, carries on.
        wanted=dict(requests=80 if family=='arcus' else 10,source_bytes=20971520 if family=='arcus' else 3000000,
                    source_seconds=75 if family=='arcus' else 45,supervised_seconds=90 if family=='arcus' else 60,
                    driver_statements=1040,connection_attempts=40,returned_bytes=4*1024**2,github_calls=10,export_bytes=512*1024)
        for k,v in wanted.items():
            auxiliary=8-t['cancel_requests'] if k=='connection_attempts' else 0
            if t[k]+v+RESERVE.get(k,0)+auxiliary>LIMITS[k]:raise Denied('INTAKE_RUN_SCOPE_CANNOT_FIT:'+k)
        if LIMITS['wall_seconds']-t['elapsed_seconds']<300+90+RESERVE['wall_seconds']:raise Denied('INTAKE_RUN_SCOPE_CANNOT_FIT:time')

    def source(self,metrics):
        if self.closing:raise Denied('CLOSING_NO_SOURCE')
        self.check()
        if set(metrics)!= {'requests','source_bytes','source_seconds','supervised_seconds'}:raise Denied('SOURCE_ACCOUNTING')
        for k,v in metrics.items():
            if type(v) not in (int,float) or not math.isfinite(v) or v<0 or self.used[k]+v>LIMITS[k]:raise Denied('INTAKE_RUN_SOURCE_BOUND')
        for k,v in metrics.items():self.used[k]+=v

    def publication(self,raw_bytes,calls):
        self.check()
        for k,v in dict(export_bytes=raw_bytes,github_calls=calls).items():
            if type(v) is not int or v<0 or self.used[k]+v+(0 if self.closing else RESERVE.get(k,0))>LIMITS[k]:raise Denied('INTAKE_RUN_PUBLICATION_RESERVE')
        # Reserve the entire publish before any mutation. Never refund on an
        # uncertain acknowledgement; the publisher itself refuses retries.
        self.used['export_bytes']+=raw_bytes;self.used['github_calls']+=calls
