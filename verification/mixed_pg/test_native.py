"""Finite real admitted-child walkthrough. PostgreSQL/OS isolation required."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import pytest
from sqlalchemy import select,update,func
from app.db.models import Council,Application
from app.revisit.migration import migrate
from app.revisit.schema import work,versions,observations,attempts
from app.revisit.storage import Store
from verification.revisit_pg.test_native import engine
from verification.mixed_pg.pause_control import PauseControl


def encoded(body,status=200):
    return dict(status=status,chunks_hex=[body.encode().hex()])


def recordings(council,revision='statement-v1'):
    result={}
    refs=['dc/085997','dc/093884','dc/094889','dc/098428','zz/crash']
    for ref in refs:
        html='<table></table>'
        if ref in ['dc/093884','zz/crash']:
            html='<table><tr><th>Description</th><th>Document Type</th></tr><tr><td><a href="/'+ref.replace('/','-')+'.pdf">Affordable Housing Statement</a></td><td>Statement</td></tr></table>'
            result['https://recorded.invalid/'+ref.replace('/','-')+'.pdf']=encoded(revision+'; 72 retirement apartments and ten private houses')
        if ref in ['dc/094889','dc/098428']:
            # Failed/inaccessible stage; not an empty successful register.
            result[council+'/'+ref+'/register']=encoded('inaccessible final notice',403)
        else:result[council+'/'+ref+'/register']=encoded(html)
        edges=[]
        if ref=='dc/085997':edges=[dict(council=council,reference='DC/093884',type='variation',confidence='verified_reference',citation='synthetic DC/085997')]
        if ref=='dc/093884':edges=[dict(council=council,reference='DC/094889',type='discharge',confidence='verified_reference',citation='synthetic DC/093884')]
        result[council+'/'+ref+'/relationships/start']=encoded(json.dumps(dict(next=None,edges=edges)))
    return result


def launch(engine,tmp_path,out,index,council='stockport',revision='statement-v1',kill=False,reject=False):
    responses=recordings(council,revision)
    urls=[]
    for i in range(3):
        url='fixture://new/'+str(index)+'/'+str(i);urls.append(url)
        responses[url]=encoded('<table><tr><th>Reference</th><td>SYN/'+str(index)+'/'+str(i)+'</td></tr><tr><th>Proposal</th><td>Erection of 82 dwellings</td></tr></table>')
    spec=dict(proof=str(engine._ah_test_manifest),council=council,new_urls=urls,responses=responses,
              pause_reference='zz/crash' if kill else None,reject_ticket=reject)
    path=tmp_path/('slice-'+str(index)+'.json');path.write_text(json.dumps(spec))
    process=subprocess.Popen([sys.executable,'-u','-m','verification.mixed_pg.supervisor',str(path)],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
    lines=queue.Queue()
    def read():
        for line in process.stdout:lines.put(line)
        lines.put(None)
    reader=threading.Thread(target=read,daemon=True);reader.start()
    transcript=[];control=PauseControl(council,kill,os.kill);deadline=time.monotonic()+100
    try:
        while time.monotonic()<deadline:
            try:line=lines.get(timeout=1)
            except queue.Empty:continue
            if line is None:break
            transcript.append(line)
            control.observe(line)
        else:raise AssertionError('supervisor exceeded finite walkthrough timeout')
        assert process.wait(timeout=5)==0,''.join(transcript)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
        (out/('mixed-slice-'+str(index)+'.log')).write_text(''.join(transcript))
    killed=control.killed_pid
    report=json.loads((tmp_path/(path.stem+'-run.json')).read_text())
    report['killed_child_pid']=killed
    with engine.connect() as c:
        snapshot={
            'work':[dict(r) for r in c.execute(select(work).order_by(work.c.id)).mappings()],
            'versions':[dict(r) for r in c.execute(select(versions.c.id,versions.c.council,versions.c.reference,versions.c.url,versions.c.digest).order_by(versions.c.id)).mappings()],
            'observations':[dict(r) for r in c.execute(select(observations).order_by(observations.c.id)).mappings()],
            'attempts':[dict(r) for r in c.execute(select(attempts).order_by(attempts.c.id)).mappings()]}
    (out/('mixed-state-'+str(index)+'.json')).write_text(json.dumps(snapshot,indent=2))

    with (out/'mixed-ledger.jsonl').open('a') as f:f.write(json.dumps(dict(slice=index,**report))+'\n')
    assert (killed is not None)==kill
    discovery=report['progress']['mixed_discovery']
    assert discovery['attempted']==discovery['completed']==2 and len(discovery['deferred'])==1
    assert discovery['requests']==2 and discovery['bytes']<=8192
    with engine.connect() as conn:
        for i in range(2):assert conn.execute(select(Application.id).where(Application.council_code==council,Application.reference=='SYN/'+str(index)+'/'+str(i))).scalar_one()
        assert conn.execute(select(Application.id).where(Application.reference=='SYN/'+str(index)+'/2')).first() is None
    if not kill:
        revisit=report['progress']['mixed_revisit']
        assert revisit['attempted']<=2 and revisit['requests']<=8 and revisit['received_bytes']<=16385
        assert revisit['elapsed_seconds']<15
    return report


def n(engine,table):
    with engine.connect() as c:return c.execute(select(func.count()).select_from(table)).scalar_one()


def test_mixed_real_child_interruption_and_successor(engine,tmp_path):
    out=Path(os.environ['MIXED_EVIDENCE'])
    with engine.begin() as c:
        migrate(c)
        for council in ['stockport','bury']:
            c.execute(Council.__table__.insert().values(code=council,name='Synthetic',base_url='https://recorded.invalid',date_field_mode='received',doc_system='idox'))
        for ref in ['DC/085997','DC/093884']:
            c.execute(Application.__table__.insert().values(council_code='stockport',reference=ref,
                proposal='Unchanged synthetic summary: 82 homes',estimated_unit_count=82))
        Store.seed_in(c,'stockport','DC/085997');Store.seed_in(c,'stockport','DC/098428')
    reports=[launch(engine,tmp_path,out,i) for i in range(4)]
    with engine.connect() as c:
        refs=set(c.execute(select(work.c.reference)).scalars())
        assert {'dc/085997','dc/093884','dc/094889','dc/098428'}<=refs
        assert c.execute(select(work.c.outcome).where(work.c.reference=='dc/094889',work.c.stage=='documents')).scalar_one()=='partial'
    assert n(engine,versions)==n(engine,observations)==1
    with engine.connect() as c:
        assert c.execute(select(Application.proposal).where(Application.council_code=='stockport',Application.reference=='DC/093884')).scalar_one()=='Unchanged synthetic summary: 82 homes'
    # Explicit next observation cycles in the finite fixture, not a scheduler.
    def due_again():
        with engine.begin() as c:c.execute(update(work).where(work.c.reference=='dc/093884',work.c.stage=='documents').values(outcome='pending',cursor='start',due=0,last_attempt=None))
    due_again();launch(engine,tmp_path,out,4)
    assert n(engine,versions)==1 and n(engine,observations)==2
    due_again();launch(engine,tmp_path,out,5,revision='statement-v2')
    assert n(engine,versions)==2 and n(engine,observations)==3
    with engine.begin() as c:Store.seed_in(c,'stockport','ZZ/CRASH')
    failed=launch(engine,tmp_path,out,6,kill=True)
    assert failed['status']=='failed'
    assert n(engine,versions)==2 and n(engine,observations)==3
    with engine.connect() as c:
        assert c.execute(select(work.c.outcome).where(work.c.reference=='zz/crash',work.c.stage=='documents')).scalar_one()=='in_flight'
    recovered=launch(engine,tmp_path,out,7,reject=True)
    assert recovered['progress']['stale_ticket_rejected'] is True
    with engine.connect() as c:assert c.execute(select(func.count()).select_from(attempts).where(attempts.c.outcome=='interrupted')).scalar_one()==1
    assert n(engine,observations)==4
    # A later council completes its slice while Stockport retains partial work.
    with engine.begin() as c:Store.seed_in(c,'bury','ZZ/CRASH')
    later=launch(engine,tmp_path,out,8,council='bury')
    assert later['progress']['mixed_revisit']['pending']==0
    with engine.connect() as c:
        assert c.execute(select(work.c.outcome).where(work.c.council=='stockport',work.c.reference=='dc/094889',work.c.stage=='documents')).scalar_one()=='partial'
    assert n(engine,observations)==5
