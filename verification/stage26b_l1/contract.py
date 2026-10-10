"""Pure offline outcome/budget contract. Not a live verifier or persistence writer."""
from urllib.parse import urlsplit
from verification.stage26b_l0.dependencies import material_fields_changed
from app.pipeline.lapse_tracking import parse_portal_date
import datetime as dt
OUTCOMES=frozenset(('VERIFIED_UNCHANGED','VERIFIED_MATERIAL_CHANGE','VERIFIED_NON_MATERIAL_CHANGE','SOURCE_UNAVAILABLE','REFERENCE_NOT_FOUND','AMBIGUOUS_SOURCE_RESULT','PARTIAL_RETRIEVAL','PARSER_FAILURE','RATE_LIMITED','TIMEOUT','UNSUPPORTED_COUNCIL'))
FAILURES=OUTCOMES-{o for o in OUTCOMES if o.startswith('VERIFIED_')}
def assess(before, candidate, *, reference, base_url, signal=None):
 """signal is an explicit transport observation, never guessed from None/exception prose."""
 if signal:
  if signal not in FAILURES:raise ValueError('Unknown failure signal')
  return dict(outcome=signal,acceptance_candidate=None,advance_verification=False)
 if candidate is None:return dict(outcome='PARTIAL_RETRIEVAL',acceptance_candidate=None,advance_verification=False)
 fields=getattr(candidate,'fields',None)
 if not isinstance(fields,dict) or any(v is not None and not isinstance(v,str) for v in fields.values()):return assess(before,None,reference=reference,base_url=base_url,signal='PARSER_FAILURE')
 u=urlsplit(candidate.summary_url);b=urlsplit(base_url)
 if candidate.reference!=reference or fields.get('Reference')!=reference or u.scheme!='https' or u.hostname!=b.hostname or u.username or u.password:return assess(before,None,reference=reference,base_url=base_url,signal='AMBIGUOUS_SOURCE_RESULT')
 if not (fields.get('Status') or fields.get('Decision')):return assess(before,None,reference=reference,base_url=base_url,signal='PARTIAL_RETRIEVAL')
 status=fields.get('Status');decision=fields.get('Decision'); date=fields.get('Decision Issued Date') or None
 # Reuse production date interpretation; absent remains absent.
 if date:
  parsed=parse_portal_date(date)
  if parsed==dt.date.min:return assess(before,None,reference=reference,base_url=base_url,signal='PARSER_FAILURE')
  date=parsed.isoformat()
 before=dict(before)
 if before.get('decision_issued_date'):
  parsed=parse_portal_date(before['decision_issued_date'])
  if parsed==dt.date.min:return assess(before,None,reference=reference,base_url=base_url,signal='PARSER_FAILURE')
  before['decision_issued_date']=parsed.isoformat()
 combined=f'{status or ""} {decision or ""}'.lower()
 if any(w in combined for w in ('committee','resolution','recommend')) and decision and any(w in decision.lower() for w in ('grant','approv','refus')):return assess(before,None,reference=reference,base_url=base_url,signal='AMBIGUOUS_SOURCE_RESULT')
 if not decision and not any(w in combined for w in ('await','pending','recommend','committee','resolution','decided','decision made','withdraw','appeal')):return assess(before,None,reference=reference,base_url=base_url,signal='PARSER_FAILURE')
 if 'grant' in combined and 'refus' in combined:return assess(before,None,reference=reference,base_url=base_url,signal='AMBIGUOUS_SOURCE_RESULT')
 after=dict(status=status,decision=decision,decision_issued_date=date)
 changed=material_fields_changed(before,after)
 outcome='VERIFIED_MATERIAL_CHANGE' if changed else 'VERIFIED_UNCHANGED' if all(before.get(k)==v for k,v in after.items()) else 'VERIFIED_NON_MATERIAL_CHANGE'
 return dict(outcome=outcome,acceptance_candidate=after,advance_verification=True,material_fields=list(changed),persistence_authorized=False)
class CanaryBudget:
 """Offline arithmetic checks. Does not intercept browser or network traffic."""
 def __init__(self,allowlist,requests=20,bytes_limit=10000000,seconds=180):
  if len(allowlist)>2 or not allowlist or requests>40 or bytes_limit>20000000 or seconds>240:raise ValueError('Invalid canary limits')
  self.allowlist=frozenset(allowlist);self.requests=requests;self.bytes_limit=bytes_limit;self.seconds=seconds;self.used_requests=0;self.used_bytes=0;self.failed=False
 def charge(self,reference,*,response_bytes,elapsed):
  if self.failed:raise ValueError('Circuit open')
  self.used_requests+=1;self.used_bytes+=response_bytes
  if reference not in self.allowlist or response_bytes<0 or elapsed<0 or self.used_requests>self.requests or self.used_bytes>self.bytes_limit or elapsed>self.seconds:
   self.failed=True;raise ValueError('Canary budget/allowlist exceeded')
