"""Standing credentials are access, never execution authority (spec032).

Only this seam is reusable. Council contracts, issuance and policy remain closed
in their existing owners. No credential lookup, mint, mapping or mutation here.
"""
from datetime import datetime,timezone
from app.ingestion.ledger import Denied
from .stable_pipeline import read_secrets
from . import restricted_route as rr
from sqlalchemy.engine import make_url

ROLES=('ingestion_worker_login','ingestion_effect_login')
# Exact maxima, including both halves; neither side may borrow from the other.
GITHUB=dict(owner_work=53,owner_closure=15,runtime_work=18,runtime_closure=14)
GITHUB['owner']=GITHUB['owner_work']+GITHUB['owner_closure']
GITHUB['runtime']=GITHUB['runtime_work']+GITHUB['runtime_closure']
GITHUB['combined']=GITHUB['owner']+GITHUB['runtime']
POLL_ATTEMPTS=3
POLL_SECONDS=60


def credentials(stream,*,disposable=False):
    token,urls=read_secrets(stream)
    if set(urls)!=set(ROLES):raise Denied('STANDING_EXACT_RUNTIME_IDENTITIES')
    for role,url in urls.items():
        u=make_url(url)
        if disposable:
            if (u.host,u.port,u.database,u.username)!=('127.0.0.1',5432,'ingestion_provisioning_test',role):raise Denied('STANDING_DISPOSABLE_DESTINATION')
        elif rr.identify(u)!=('POOLER',role):raise Denied('STANDING_EXACT_RUNTIME_IDENTITIES')
    return token,urls


def require_closure(receipts):
    if not receipts:raise Denied('STANDING_PHASE_RECEIPTS_REQUIRED')
    for receipt in receipts:
        if not isinstance(receipt,dict) or receipt.get('cleanup')!='CLOSED' or receipt.get('connections_closed') is not True:raise Denied('STANDING_PHASE_CLOSURE_UNCERTAIN')
        if any(type(receipt.get(k)) is not int or receipt[k]<0 for k in ('driver_statements','connection_attempts','returned_data_value_bytes')):raise Denied('STANDING_PHASE_ACCOUNTING_REQUIRED')
    return True


def valid_credential_lifetime(value,operation_expiry):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None or d<=operation_expiry or d<=datetime.now(timezone.utc):raise Denied('STANDING_CREDENTIAL_LIFETIME')
    return d

from .operational_publication import GitHub

OWNER_WORK_COMPONENTS=dict(preflight=6,prior_receipts=2,workflow_history=1,standing_names=2,claim=8,capture_wait=9,screen_marker=8,result_wait=6,credential_preparation=11)
RUNTIME_WORK_COMPONENTS=dict(claim_read=1,startup=2,archive_readback=1,retained_marker=8,screen_wait=6)
assert sum(OWNER_WORK_COMPONENTS.values())==GITHUB['owner_work']
assert sum(RUNTIME_WORK_COMPONENTS.values())==GITHUB['runtime_work']


class StandingGitHub(GitHub):
    def publish(self,files,*,directory,expected_head):
        # Reject BEFORE blob/tree/ref effects, leaving the separately retained
        # closure allowance untouched. Historical publisher behaviour is unchanged.
        cost=6+2*len(files)
        limit=min(self.bound,self.reserve['limit']) if self.reserve else self.bound
        if self.requests+cost>limit:raise Denied('STANDING_PUBLICATION_CAPACITY_BEFORE_EFFECTS')
        return super().publish(files,directory=directory,expected_head=expected_head)

    def put_secret(self,name,value):
        if name not in {'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}:raise Denied('STANDING_EXACT_SECRET_NAMES')
        limit=min(self.bound,self.reserve['limit']) if self.reserve else self.bound
        if self.requests+2>limit:raise Denied('STANDING_MAPPING_CAPACITY_BEFORE_EFFECTS')
        # gh secret set consumes public-key GET + encrypted PUT. Reserve both
        # BEFORE invoking it; failed acknowledgements remain an upper bound.
        self.requests+=1;self.emit('standing_secret_http_reservation',dict(name=name,http_calls=2,basis='RESERVED_UNTIL_ACK'))
        return super().put_secret(name,value)
