"""One cumulative runtime allocation; no new entitlement and no replay allocation."""
import time
from app.ingestion.ledger import Denied
from .chain_caller import ChainCaller
CAPS=dict(commands=1040,connections=40,returned_bytes=4*1024**2,seconds=300)
RESERVE=dict(commands=32,connections=2,returned_bytes=64*1024,seconds=10)

def capacity(records,nominees):
    """Conservative closed-caller reservation incl. per-record readbacks. Not a promise of completion.

    80 statements/two connections per batch,120/four per nominee,8/one per
    screening readback plus fixed capture/preflight/readback and closure reserve.
    Source ceilings remain45seconds per nominee; total deadline is independent.
    """
    if type(records) is not int or type(nominees) is not int or not 0<=nominees<=records<=60:raise Denied('OLDHAM_CAPACITY_INPUT')
    batches=(records+4)//5
    need=dict(commands=50+80*batches+120*nominees+8*records,connections=3+2*batches+4*nominees+records,returned_bytes=0,seconds=45*nominees)
    if any(need[k]+RESERVE[k]>CAPS[k] for k in CAPS):raise Denied('OLDHAM_PACKAGE_CAPACITY')
    return need

class Allocation:
    def __init__(self):self.started=time.monotonic();self.budgets=[];self.failed=False
    def totals(self):
        return dict(commands=sum(b.statements-b.previous.get('driver_statements',0) for b in self.budgets),connections=sum(b.attempts-b.previous.get('connection_attempts',0) for b in self.budgets),returned_bytes=sum(b.returned_bytes-b.previous.get('returned_data_value_bytes',0) for b in self.budgets),seconds=time.monotonic()-self.started)
    def check(self):
        if self.failed:raise Denied('OLDHAM_ALLOCATION_RECONCILE')
        if any(v>=CAPS[k]-RESERVE[k] for k,v in self.totals().items()):
            self.failed=True;raise Denied('OLDHAM_AGGREGATE_EXHAUSTED')

class FiniteCaller(ChainCaller):
    def __init__(self,*args,allocation,**kw):
        super().__init__(*args,**kw)
        if self.sb.council!='oldham' or not isinstance(allocation,Allocation):raise Denied('OLDHAM_ALLOCATION_BINDING')
        self.allocation=allocation
    def _budget(self,**kw):
        self.allocation.check()
        totals=self.allocation.totals();prior=kw.get('previous') or {}
        kw['returned_bytes']=min(4*1024**2,CAPS['returned_bytes']-RESERVE['returned_bytes']-totals['returned_bytes']+prior.get('returned_data_value_bytes',0))
        kw['cancel_used']=sum(sum(e.get('cancel_attempts',0) for e in x.hard_deadline_events) for x in self.allocation.budgets)
        b=super()._budget(**kw);self.allocation.budgets.append(b)
        b.hard_stop_at=self.allocation.started+CAPS['seconds']-RESERVE['seconds']
        original_close=b.close
        def close(*a,**k):
            try:
                receipt=original_close(*a,**k)
                if receipt.get('cleanup')!='CLOSED' or receipt.get('connections_closed') is not True:self.allocation.failed=True
                return receipt
            except BaseException:
                self.allocation.failed=True;raise
        b.close=close
        original=b.check
        def check():self.allocation.check();original()
        b.check=check
        return b
