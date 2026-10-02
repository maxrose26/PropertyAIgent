"""Server-owned admission and revocable single-process execution leases.

OIDC verification belongs to Streamlit/Authlib. No client-supplied roles or
headers establish authority here. Infrastructure administrators remain trusted.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import math
import os
import re
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit


class AccessDenied(RuntimeError):
    pass


class AccessUnavailable(AccessDenied):
    pass


@dataclass(frozen=True)
class Actor:
    lease_id: str
    issuer: str
    subject: str
    role: str
    workspace_id: int
    buyer_ids: frozenset[int]
    revision: str
    issued_at: int
    expires_at: float
    cookie_key: str
    machine: bool = False
    actions: frozenset[str] = frozenset()


_current: ContextVar[Actor | None] = ContextVar('propertyaigent_actor', default=None)
_log = logging.getLogger(__name__)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def load_policy():
    try:
        path = Path(os.environ['PROPERTYAIGENT_ACCESS_POLICY'])
        raw = path.read_bytes()
        data = json.loads(raw)
        if not _integer(data['version']) or data['version'] != 1 or data['enabled'] is not True:
            raise ValueError()
        if data['environment'] not in ('local', 'production'):
            raise ValueError()
        issuer = data['issuer']
        url = urlsplit(issuer)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError()
        if url.scheme != 'https' and not (data['environment'] == 'local' and url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')):
            raise ValueError()
        if not isinstance(data['client_id'], str) or not data['client_id']:
            raise ValueError()
        if any(not _integer(data[key]) or data[key] != 1 for key in ('web_processes','web_replicas')):
            raise ValueError()
        principals = {}
        for grant in data['principals']:
            if grant['issuer'] != issuer or not isinstance(grant['subject'], str) or not grant['subject']:
                raise ValueError()
            key = (issuer, grant['subject'])
            if key in principals or grant['role'] not in ('reader', 'operator') or not isinstance(grant['enabled'], bool):
                raise ValueError()
            if not _integer(grant['workspace_id']) or grant['workspace_id'] <= 0:
                raise ValueError()
            if not isinstance(grant['buyer_ids'], list) or any(not _integer(x) or x <= 0 for x in grant['buyer_ids']):
                raise ValueError()
            if len(set(grant['buyer_ids'])) != len(grant['buyer_ids']):
                raise ValueError()
            if not _integer(grant.get('not_before', 0)):
                raise ValueError()
            principals[key] = grant
        owner = principals[(issuer, data['owner_subject'])]
        if owner['role'] != 'operator' or not owner['enabled']:
            raise ValueError()
        paid = data.get('paid_actions', {})
        if not isinstance(paid, dict) or any(not isinstance(k, str) or not isinstance(v, bool) for k, v in paid.items()):
            raise ValueError()
        from app.security.commands import PAID_LIMITS
        if set(paid)-set(PAID_LIMITS):raise ValueError()
        data['_grants'] = principals
        machines = {}
        if not isinstance(data.get('machines', {}), dict):raise ValueError()
        for name, grant in data.get('machines', {}).items():
            if not isinstance(name,str) or not name or not isinstance(grant['enabled'],bool): raise ValueError()
            if not _integer(grant['workspace_id']) or grant['workspace_id'] <= 0: raise ValueError()
            if not isinstance(grant['buyer_ids'],list) or any(not _integer(x) or x <= 0 for x in grant['buyer_ids']): raise ValueError()
            if not isinstance(grant['actions'],list) or any(not isinstance(x,str) or not x or '*' in x for x in grant['actions']): raise ValueError()
            machines[name] = grant
        data['_machines'] = machines
        data['_revision'] = hashlib.sha256(raw).hexdigest()
        return data
    except (OSError, KeyError, TypeError, ValueError):
        raise AccessUnavailable('Application access is unavailable.') from None


class LeaseRegistry:
    def __init__(self):
        self.boot = math.ceil(time.time())
        self.key = secrets.token_bytes(32)
        self.lock = threading.RLock()
        self.leases = {}
        self.issuance_revisions = {}  # same bounded keyset as issuances
        self.issuances = {}  # validated principal/issuance => last activity
        self.revoked_issuances = set()
        self.middleware_ready = False
        self.last_clock = self.boot - 1
        self.new_issuance_floor = 0  # boot validation is independent

    def fingerprint(self, cookies):
        # Mirror the pinned native cookie's consumed chunks, not arbitrary
        # prefix matches. The signed base may contain only a chunks-N manifest.
        # These framework helpers verify cookie signatures; OIDC identity
        # validation remains entirely in native Streamlit/Authlib.
        from streamlit.web.server.server_util import get_cookie_secret
        from streamlit.web.server.starlette.starlette_app_utils import decode_signed_value
        base=cookies.get('_streamlit_user','')
        if not isinstance(base,str) or not base or len(base)>131072:
            raise AccessDenied('Authentication required.')
        secret=get_cookie_secret()
        decoded=decode_signed_value(secret,'_streamlit_user',base)
        if decoded is None:raise AccessDenied('Authentication required.')
        selected=[('_streamlit_user',base)]
        match=re.match(rb'chunks-(\d+)',decoded)
        if match:
            count=int(match.group(1))
            if count<1 or count>32:raise AccessDenied('Authentication required.')
            for index in range(1,count+1):
                name=f'_streamlit_user_{index}';value=cookies.get(name)
                if not isinstance(value,str) or decode_signed_value(secret,name,value) is None:
                    raise AccessDenied('Authentication required.')
                selected.append((name,value))
        if sum(len(k)+len(v) for k,v in selected)>131072:
            raise AccessDenied('Authentication required.')
        payload = json.dumps(selected, separators=(',', ':')).encode()
        return hmac.new(self.key, payload, hashlib.sha256).hexdigest()

    def _reclaim(self, now):
        # Called under the RLock. Retain every issuance until its maximum
        # possible validity, not the exp of one token with that issuance.
        if now < self.last_clock:
            raise AccessUnavailable('Authentication clock moved backwards.')
        self.last_clock = now
        for key, activity in list(self.issuances.items()):
            if now >= key[2] + 28800:
                del self.issuances[key]
                self.issuance_revisions.pop(key, None)
                self.revoked_issuances.discard(key)
            elif now - activity >= 1800:
                self.revoked_issuances.add(key)
        for key, (actor, _) in list(self.leases.items()):
            issuance = (actor.issuer, actor.subject, actor.issued_at)
            if now >= actor.expires_at and not actor.machine and issuance in self.issuances:
                self.revoked_issuances.add(issuance)
            if now >= actor.expires_at or (not actor.machine and issuance in self.revoked_issuances):
                del self.leases[key]

    def issue(self, claims, cookie_key, prior=None):
        if not self.middleware_ready:
            raise AccessUnavailable('Application access is unavailable.')
        policy = load_policy()
        issuer = claims.get('iss')
        if policy['issuer'] == 'https://accounts.google.com' and issuer == 'accounts.google.com':
            issuer = policy['issuer']
        subject = claims.get('sub')
        issued, expiry = claims.get('iat'), claims.get('exp')
        now = time.time()
        aud = claims.get('aud')
        audiences = [aud] if isinstance(aud, str) else aud
        if not isinstance(audiences, list) or policy['client_id'] not in audiences:
            raise AccessDenied('Access denied.')
        if (len(audiences) > 1 and claims.get('azp') != policy['client_id']) or claims.get('azp', policy['client_id']) != policy['client_id']:
            raise AccessDenied('Access denied.')
        if issuer != policy['issuer'] or not isinstance(subject, str) or claims.get('email_verified') is not True:
            raise AccessDenied('Access denied.')
        if not _integer(issued) or not _integer(expiry) or issued < self.boot or issued > now or expiry <= now or expiry <= issued or issued + 28800 <= now:
            raise AccessDenied('Sign in again.')
        grant = policy['_grants'].get((issuer, subject))
        if not grant or not grant['enabled'] or issued < grant.get('not_before', 0):
            raise AccessDenied('Access denied.')
        with self.lock:
            now = time.time()
            if issued > now or expiry <= now or issued + 28800 <= now:
                raise AccessDenied('Sign in again.')
            self._reclaim(now)
            issuance = (issuer, subject, issued)
            if issuance in self.revoked_issuances:
                raise AccessDenied('Sign in again.')
            if issuance in self.issuance_revisions and self.issuance_revisions[issuance] != policy['_revision']:
                self.revoked_issuances.add(issuance)
                raise AccessDenied('Access changed. Sign in again.')
            if prior is not None:
                self.check(prior)
                if (prior.issuer, prior.subject, prior.cookie_key, prior.issued_at) != (issuer, subject, cookie_key, issued):
                    raise AccessDenied('Sign in again.')
                self.leases[prior.lease_id] = (prior, now)
                self.issuances[issuance] = now
                return prior
            if issuance not in self.issuances and issued < self.new_issuance_floor:
                raise AccessDenied('Sign in again.')
            if len(self.leases) >= 10000 or (issuance not in self.issuances and len(self.issuances) >= 10000):
                raise AccessUnavailable('Application access is unavailable.')
            actor = Actor(secrets.token_urlsafe(32), issuer, subject, grant['role'], grant['workspace_id'], frozenset(grant['buyer_ids']), policy['_revision'], issued, min(expiry, issued + 28800), cookie_key)
            self.leases[actor.lease_id] = (actor, now)
            self.issuances[issuance] = now
            self.issuance_revisions[issuance] = policy['_revision']
            return actor

    def check(self, actor):
        policy = load_policy()
        with self.lock:
            now = time.time()
            self._reclaim(now)
            stored = self.leases.get(actor.lease_id) if isinstance(actor, Actor) else None
            if not stored or stored[0] is not actor:
                raise AccessDenied('Authentication required.')
            grant = policy['_machines'].get(actor.subject) if actor.machine else policy['_grants'].get((actor.issuer, actor.subject))
            issuance = (actor.issuer, actor.subject, actor.issued_at)
            if not grant or not grant['enabled'] or actor.revision != policy['_revision'] or actor.issued_at < grant.get('not_before', 0):
                if not actor.machine: self.revoked_issuances.add(issuance)
                raise AccessDenied('Access changed. Sign in again.')
            if not actor.machine and issuance in self.revoked_issuances:
                raise AccessDenied('Sign in again.')
        return actor

    def revoke_native(self, cookies):
        # Native logout can happen before the first application execution.
        # Reuse the exact pinned signed/chunk decoder after bounded validation.
        self.fingerprint(cookies)
        from streamlit.auth_util import get_cookie_with_chunks
        from streamlit.web.server.server_util import get_cookie_secret
        from streamlit.web.server.starlette.starlette_app_utils import decode_signed_value
        secret=get_cookie_secret()
        try:
            claims=json.loads(get_cookie_with_chunks(
                lambda name:decode_signed_value(secret,name,cookies.get(name,'')), '_streamlit_user'))
            issuer,subject,issued=claims['iss'],claims['sub'],claims['iat']
            if issuer=='accounts.google.com':issuer='https://accounts.google.com'
            if not isinstance(issuer,str) or not isinstance(subject,str) or not _integer(issued):raise ValueError()
        except (ValueError,TypeError,KeyError):
            raise AccessDenied('Invalid native identity cookie.') from None
        with self.lock:
            now=time.time();self._reclaim(now)
            if issued<self.boot or issued>now or issued+28800<=now:return
            issuance=(issuer,subject,issued)
            if issuance not in self.issuances:
                if len(self.issuances)>=10000:
                    # No required tombstone is evicted. One scalar rejects this
                    # and older *new* issuances; existing active leases survive.
                    self.new_issuance_floor=max(self.new_issuance_floor,issued+1)
                    return
                self.issuances[issuance]=now
                self.issuance_revisions[issuance]='logged-out-before-admission'
            self.revoked_issuances.add(issuance)
            for key,(actor,_) in list(self.leases.items()):
                if (actor.issuer,actor.subject,actor.issued_at)==issuance:del self.leases[key]

    def revoke(self, cookie_key):
        with self.lock:
            self._reclaim(time.time())
            # Issuance tombstones cover all aliases/tabs without an unbounded
            # second collection of cookie digests. Unknown cookies had no lease.
            targets = {(a.issuer, a.subject, a.issued_at) for a, _ in self.leases.values()
                       if a.cookie_key == cookie_key and not a.machine}
            self.revoked_issuances.update(targets)
            for key, (actor, _) in list(self.leases.items()):
                if (actor.issuer, actor.subject, actor.issued_at) in targets:
                    del self.leases[key]



registry = LeaseRegistry()


def current_actor():
    return registry.check(_current.get())


@contextmanager
def actor_scope(actor):
    registry.check(actor)
    token = _current.set(actor)
    try:
        yield actor
    finally:
        _current.reset(token)


def require_admitted():
    return current_actor()


def require_operator(action='shared.write', *, paid=False):
    actor = current_actor()
    if actor.role != 'operator':
        raise AccessDenied('Operator permission required.')
    if actor.machine and action not in actor.actions:
        raise AccessDenied('Command scope denied.')
    if paid and load_policy().get('paid_actions', {}).get(action) is not True:
        raise AccessDenied('This paid action is disabled.')
    return actor


def require_buyer(workspace_id, buyer_id):
    actor = current_actor()
    if workspace_id != actor.workspace_id or buyer_id not in actor.buyer_ids:
        raise AccessDenied('Access denied.')
    return actor


def is_operator():
    return current_actor().role == 'operator'


def actor_label():
    actor=current_actor()
    return 'principal:'+hashlib.sha256((actor.issuer+'\0'+actor.subject).encode()).hexdigest()[:24]
