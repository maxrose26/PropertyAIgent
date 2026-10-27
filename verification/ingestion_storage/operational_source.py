"""Credential-free Idox child binding existing qualified listing/detail workers.

Only a trusted controller calls read after its exact SQL source intent commits.
No workflow, dispatch, database client, retry or historical authority issuance.
"""
import argparse,json,os,sys,tempfile
from pathlib import Path
from dataclasses import asdict
from datetime import date
from verification.ingestion_storage.operational_supervisor import supervise


def read(kind,configuration,*,root,stop_file=None,memory_group=None,observe=None,closed_target=False):
 if kind not in {'listing','detail','form_probe'}:raise ValueError('SOURCE_KIND')
 if type(closed_target) is not bool or (closed_target and kind!='detail'):raise ValueError('CLOSED_IDOX_SELECTION')
 if kind=='detail':
  from .idox_target import validate
  if closed_target or configuration.get('case','').startswith('chain_idox_') or 'target_sha256' in configuration:validate(configuration)
 root=Path(root)
 # Configuration contains only literal source identity/date scope, never secrets.
 raw=json.dumps(configuration,sort_keys=True,allow_nan=False).encode()
 if len(raw)>16384:raise ValueError('SOURCE_CONFIGURATION_BOUND')
 with tempfile.TemporaryDirectory(prefix='ingestion-source-plan-') as home:
  plan=Path(home)/'plan.json';plan.write_bytes(raw)
  output=root/'worker-result.json'
  outer=supervise([sys.executable,'-m','verification.ingestion_storage.operational_source','--worker',kind,'--plan',str(plan),'--output',str(output)]+(['--closed-idox-target'] if closed_target else []),environment={'INGESTION_SOURCE_PRIVATE':'ONCE'},root=root,source=True,seconds=45,stop_file=stop_file,memory_group=memory_group)
  if observe is not None:observe('source_supervisor_observed',outer)
  if output.is_file() and output.stat().st_size<=512*1024 and observe is not None:
   try:observe('source_worker_resource_observed',json.loads(output.read_bytes()).get('resource'))
   except (ValueError,TypeError):observe('source_worker_resource_observed',None)
  if outer['exit_code']!=0 or outer['cleanup']!='CLOSED' or outer['limit_hit'] is not None or not output.is_file() or output.stat().st_size>512*1024:raise ValueError('SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY')
  audit=json.loads(output.read_bytes())
  if kind=='detail':audit.update(process_cleanup='CLOSED',live_owned_survivors=0,peak_owned_rss=outer['peak_owned_rss'],owned_processes_seen=outer['processes_seen'],supervisor_seconds=outer['elapsed_seconds'],supervisor_limit_hit=False)
  return audit,outer


def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',choices=['listing','detail','form_probe'],required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--closed-idox-target',action='store_true');a=p.parse_args()
 if os.environ.get('INGESTION_SOURCE_PRIVATE')!='ONCE' or any('DATABASE' in k or k.endswith('_KEY') or k.endswith('_TOKEN') or k.endswith('_PASSWORD') for k in os.environ) or a.output.exists():raise ValueError('PRIVATE_CREDENTIAL_FREE_SOURCE')
 cfg=json.loads(a.plan.read_bytes())
 if a.closed_idox_target and a.worker!='detail':raise ValueError('CLOSED_IDOX_SELECTION')
 if a.worker=='detail':
  from .idox_target import validate
  if a.closed_idox_target or cfg.get('case','').startswith('chain_idox_') or 'target_sha256' in cfg:validate(cfg)
 import resource
 resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CPU,(45,45));resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024,512*1024))
 if a.worker in ('listing','form_probe'):
  from verification.discovery.idox_window import WindowConfig,live,form_probe
  contract=WindowConfig(cfg['council'],cfg['semantics'],date.fromisoformat(cfg['start']),date.fromisoformat(cfg['end']),0)
  audit=form_probe(contract) if a.worker=='form_probe' else live(contract)
 else:
  from verification.discovery.material_qualification import idox_worker
  audit=idox_worker(cfg)
 raw=json.dumps(audit,sort_keys=True,allow_nan=False).encode()
 if len(raw)>512*1024:raise ValueError('SOURCE_AUDIT_BOUND')
 with a.output.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

if __name__=='__main__':main()
