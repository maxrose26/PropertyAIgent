"""Single-use isolated observation; no database/provider/intake API."""
import json,os,sys
from pathlib import Path
from verification.discovery.manchester_navigation_diagnostic import MODE,ROW
from verification.ingestion_storage.operational_supervisor import supervise

ROOT=Path('/tmp/pai-mnav-20261105')
def main():
 # Exclusive directory is the local submission receipt. Never reuse on uncertainty.
 ROOT.mkdir(mode=0o700,exist_ok=False)
 plan=ROOT/'plan.json';output=ROOT/'observation.json'
 plan.write_text(json.dumps(dict(row=ROW,fixture=None,diagnostic_mode=MODE)))
 result=supervise([sys.executable,'-B','-m','verification.ingestion_storage.daily_intake_runtime','--source-worker','--plan',str(plan),'--output',str(output)],
   environment=dict(INGESTION_SOURCE_PRIVATE='ONCE',PLAYWRIGHT_BROWSERS_PATH='/tmp/propertyaigent-manchester-diagnostic-browser'),
   root=ROOT/'owned',source=True,seconds=45,diagnostic_mode=MODE)
 observation=json.loads(output.read_bytes()) if output.is_file() and output.stat().st_size<8192 else dict(status='NO_COMPLETE_OBSERVATION',physical_requests='UNKNOWN')
 observation['supervisor']=result
 raw=json.dumps(observation,sort_keys=True).encode()
 if len(raw)>16384:raise ValueError('DIAGNOSTIC_OUTPUT_BOUND')
 with (ROOT/'result.json').open('xb') as f:f.write(raw)
 print(raw.decode())
 return 0 if result['cleanup']=='CLOSED' and result['exit_code']==0 else 2
if __name__=='__main__':raise SystemExit(main())
