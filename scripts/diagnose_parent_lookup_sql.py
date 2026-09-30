"""Synthetic SQLite-only trace; run with PYTHONPATH=tests:. python -m scripts.diagnose_parent_lookup_sql.

Never opens the configured application database. The imported helpers provide
only synthetic council/result objects; portal and model calls are not used.
"""
import collections, contextlib, io, json, sys, time
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db.models import Base,Council,Application
from test_p0a_bounded_discovery import run,found
engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
s=Session(engine,expire_on_commit=False)
s.add(Council(code='testcouncil',name='Test',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'));s.commit()
for n in range(192): s.add(Application(council_code='testcouncil',reference=f'CHILD/{n}',proposal=f'Reserved matters pursuant to outline planning permission OUT/{n%48}'))
s.commit()
import os
os.environ['PROPERTYAIGENT_DISCOVERY_PARENT_ITEMS']='20'
counts=collections.Counter();transactions=collections.Counter()
def before(conn,cursor,statement,params,ctx,many):
 f=sys._getframe();caller='other'
 while f:
  if f.f_code.co_filename.endswith('/parent_lookup.py'):
   caller=f.f_code.co_name;break
  f=f.f_back
 verb=statement.split()[0]
 counts[caller+' / '+verb]+=1
event.listen(engine,'before_cursor_execute',before)
event.listen(engine,'commit',lambda conn:transactions.update(['commit']))
event.listen(engine,'rollback',lambda conn:transactions.update(['rollback']))
with contextlib.redirect_stdout(io.StringIO()):
 for _ in range(3):run(s,found)
print(json.dumps({'sql_statements':sum(counts.values()),'by_function_and_verb':dict(sorted(counts.items())),'transaction_boundaries':dict(transactions)},indent=2))
