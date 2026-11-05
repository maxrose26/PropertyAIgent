"""Actual normal Manchester worker inside its outer supervisor, loopback only."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
import pytest

@pytest.mark.skipif(os.environ.get('MANCHESTER_REAL_BROWSER')!='1',reason='hosted isolated Chromium only')
def test_worker_browser_inside_reviewed_supervisor(tmp_path):
 from verification.ingestion_storage.operational_supervisor import supervise
 from verification.ingestion_storage.owner_pilot import source_profile
 from verification.direct_reference.prepared_font_cache import headless_shell_executable
 browser=os.environ['PLAYWRIGHT_BROWSERS_PATH'];sha=hashlib.sha256(Path(headless_shell_executable(browser)).read_bytes()).hexdigest()
 revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
 profile=source_profile(dict(browser_path=browser,browser_sha256=sha,execution_binding=dict(revision=revision),browser_canary="LAUNCHED_AND_CLOSED"),revision)
 receipt=tmp_path/'browser-receipt.json'
 # No real provider/source transport: the existing representative fixture starts
 # a loopback TLS server, routes Chromium exclusively to it, then invokes the real
 # source_worker with its exact normal 2 MiB per-file profile.
 env=dict(MANCHESTER_REAL_BROWSER='1',MEASURE_FILE_LIMIT='2097152',MEASURE_ACTUAL_WORKER='1',P09_BOUNDARY_RECEIPT=str(receipt))
 command=[sys.executable,'-c','import os,pytest;os.environ.update('+repr(env)+');raise SystemExit(pytest.main(["tests/test_manchester_file_measurement.py","-q","-s","--tb=short"]))']
 outer=supervise(command,environment=dict(INGESTION_SOURCE_PRIVATE='ONCE',PLAYWRIGHT_BROWSERS_PATH=browser,INGESTION_RENDER_PROFILE=json.dumps(profile)),root=tmp_path/'owned',source=True,seconds=75,execution_budget='BROWSER_SOURCE_V2',render_profile=profile)
 print('P09_BROWSER_BOUNDARY '+json.dumps(outer,sort_keys=True))
 assert outer['cleanup']=='CLOSED' and outer['live_owned_survivors']==0,outer
 assert outer['exit_code']==0 and outer['limit_hit'] is None,outer
 report=json.loads(receipt.read_text());assert report['actual_worker'] and report['records']==60 and report['enumeration']=='COUNT_RECONCILED'
 assert report['physical_requests']==1 and report['cleanup']=='CONTEXT_BROWSER_CLOSED'
