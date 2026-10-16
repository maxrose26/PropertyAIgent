"""Native hosted supervisor rehearsal, real process namespace required."""

def test_supervisor_kills_and_reaps_owned_controller_on_deadline(tmp_path):
 import sys
 from verification.ingestion_storage.operational_supervisor import supervise
 result=supervise([sys.executable,'-c','import time;time.sleep(10)'],environment={},root=tmp_path/'owned',seconds=.15)
 assert result['expired'] and result['cleanup']=='CLOSED' and result['live_owned_survivors']==0



def test_supervisor_closes_orphan_after_leader_exits(tmp_path):
 import sys,json
 from verification.ingestion_storage.operational_supervisor import supervise
 code="import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])"
 result=supervise([sys.executable,'-c',code],environment={},root=tmp_path/'orphan',seconds=3)
 assert result['cleanup']=='CLOSED' and result['live_owned_survivors']==0 and result['exit_code']==0
