"""Fixed successor scope; historical guard bodies are not relaxed."""
import pytest
from verification.ingestion_storage import period09_successor as p, intake_policy

def test_only_registration_changes_and_finish_is_identical():
 old=intake_policy.policy_sql().split('CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(',1)[1].split('$register$;',1)[0]
 new=p.registration_sql().split('CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception(',1)[1].split('$register$;',1)[0]
 anchor="  IF session_user<>'ingestion_worker_login'"
 assert old.split(anchor,1)[1]==new.split(anchor,1)[1]
 assert p.function_inventory()['ingestion_worker_step']==p.op.Owner.daily_intake_inventory()['ingestion_worker_step']
 assert p.SUCCESSOR=='b-dbpilot-20261027-1102-09'
 assert set(p.councils())=={'manchester'}
 assert p.disposition()['before']['hard_stop_generation']==p.disposition()['after']['hard_stop_generation']==11
 assert p.disposition()['before']['last_hard_stop']==p.disposition()['after']['last_hard_stop']
