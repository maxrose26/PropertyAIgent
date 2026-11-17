"""Executed in pinned #213 process against the same disposable candidate DB.
Actual Vault+Journal code, actual autocommit SQL; no production route is used.
"""
import copy
import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
import psycopg
from verification.ingestion_storage import owner_pilot as pinned


def main():
    value=json.load(sys.stdin)
    target=value['owner']
    assert target['host']=='127.0.0.1' and target['dbname']=='ingestion_provisioning_test'
    source=Path(value['source']).read_text()
    # Import routing only: pinned process owns the old verification package.
    anchor='from .tameside_package import PERIOD'
    assert source.count(anchor)==1
    scope={}
    exec(compile(source.replace(anchor,"PERIOD='S4_FINITE_677f555670666bcf21f45860'"),value['source'],'exec'),scope)
    class DB:
        key=hashlib.sha256(b'disposable-encryption-fixture-only').hexdigest()
        opened=0;closed=0;mutations=0;lose=False;readonly_observations=0
        @contextmanager
        def connection(self):
            self.opened+=1
            c=psycopg.connect(**target,autocommit=True,prepare_threshold=None)
            outer=self
            class Proxy:
                def execute(self,q,params=None):
                    if params and len(params)==3 and 'NULL::bytea' in q:
                        if c.execute('SHOW transaction_read_only').fetchone()==('on',):outer.readonly_observations+=1
                    result=c.execute(q,params)
                    if params and len(params)==4 and params[3] is not None:
                        outer.mutations+=1
                        if outer.lose:
                            outer.lose=False
                            raise RuntimeError('DISPOSABLE_LOST_ACK_AFTER_COMMIT')
                    return result
            try:yield Proxy()
            finally:
                c.close();assert c.closed;self.closed+=1
    db=DB()
    fresh=scope['fresh'];reconcile=scope['reconcile']
    if value.get('mode')=='save':
        journal=scope['_bound_journal'](pinned,db)
        state=journal.load()
        if state is None:
            state=dict(period=scope['PERIOD'],cleanup_reserve=dict(pinned.cleanup_reserve_policy(),cleanup_writes=0))
        state['access']=value['access']
        if value['access']['state'] in ('ACCESS_DISABLED_ACKNOWLEDGED','DATABASE_CLOSURE_ACKNOWLEDGED') or state['cleanup_reserve'].get('cleanup_writes',0):
            journal.cleanup_mode=True
        journal.save(copy.deepcopy(state))
        checked,observed=reconcile(pinned,db)
        assert observed==journal.state and observed['access']==value['access'] and checked.previous==journal.previous and db.opened==db.closed
        print(json.dumps(dict(status='ENCRYPTED_CALLBACK_READBACK',ordinal=checked.ordinal,sha256=checked.previous)))
        return

    try:reconcile(pinned,db)
    except ValueError as error:assert 'OUTCOME_UNKNOWN' in str(error)
    else:raise AssertionError('missing outcome accepted')
    journal=fresh(pinned,db)
    state=dict(period=scope['PERIOD'],status='ARMED',sequence=0,
               cleanup_reserve=dict(pinned.cleanup_reserve_policy(),cleanup_writes=0),
               private_fixture='SYNTHETIC_NOT_A_PRODUCTION_CREDENTIAL')
    db.lose=True
    try:journal.save(copy.deepcopy(state))
    except RuntimeError as error:assert 'LOST_ACK_AFTER_COMMIT' in str(error)
    else:raise AssertionError('lost ack not injected')
    assert journal.ordinal==-1 and db.mutations==1
    recovered,observed=reconcile(pinned,db)
    assert observed==state and recovered.ordinal==0 and db.mutations==1
    try:fresh(pinned,db)
    except ValueError as error:assert 'JOURNAL_USED' in str(error)
    else:raise AssertionError('duplicate operation accepted')
    # A stale writer cannot replace the acknowledged row after recovery.
    try:journal.save(dict(state,sequence=-1))
    except Exception as error:assert 'OWNER_STATE_CONCURRENT_OR_UNCERTAIN' in str(error)
    else:raise AssertionError('stale state replaced committed history')
    oversized=dict(state,padding='x'*17000)
    try:recovered.save(oversized)
    except Exception as error:assert 'OWNER_CLEANUP_RESERVE_BYTE_BOUND' in str(error)
    else:raise AssertionError('cleanup byte reserve consumed by normal state')
    # Normal writes end at47; all sixteen remaining snapshots stay available.
    for ordinal in range(1,48):
        state['sequence']=ordinal;recovered.save(copy.deepcopy(state))
    try:recovered.save(dict(state,sequence=48))
    except Exception as error:assert 'OWNER_CLEANUP_ROW_BOUND' in str(error)
    else:raise AssertionError('normal write used cleanup reserve')
    recovered.cleanup_mode=True
    for ordinal in range(48,64):
        state=copy.deepcopy(recovered.state);state['sequence']=ordinal
        recovered.save(state)
        assert recovered.ordinal==ordinal
    final=copy.deepcopy(recovered.state)
    assert final['cleanup_reserve']['cleanup_writes']==16
    try:recovered.save(copy.deepcopy(final))
    except Exception as error:assert 'OWNER_CLEANUP_ROW_BOUND' in str(error)
    else:raise AssertionError('history grew beyond bound')
    reader,readback=reconcile(pinned,db)
    assert reader.ordinal==63 and readback==final and db.opened==db.closed and db.readonly_observations>=3
    with psycopg.connect(**target,autocommit=True) as c:
        rows=c.execute('SELECT name,body,sha256 FROM ingestion_run_evidence WHERE period=%s ORDER BY name',(scope['JOURNAL'],)).fetchall()
        assert len(rows)==64 and rows[0][0]=='owner/state-000' and rows[-1][0]=='owner/state-063'
        assert all(hashlib.sha256(bytes(body)).hexdigest()==h and len(body)<=32768 and b'SYNTHETIC_NOT_A_PRODUCTION_CREDENTIAL' not in bytes(body) for _,body,h in rows)
    print(json.dumps(dict(status='VERIFIED_DISPOSABLE_JOURNAL',encrypted=True,normal_last_ordinal=47,cleanup_snapshots=16,final_ordinal=63,unknown_ack_reconciled_without_rewrite=True,connections_closed=db.opened==db.closed)))

if __name__=='__main__':main()
