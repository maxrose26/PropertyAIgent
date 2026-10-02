"""Explicit trusted-OS launch adapter. Never selected by browser input."""
from contextlib import contextmanager
from functools import wraps
import os
import secrets
import time
from app.security import access


@contextmanager
def command_scope(command):
    policy=access.load_policy()
    name=os.environ.get('PROPERTYAIGENT_COMMAND_IDENTITY')
    grant=policy['_machines'].get(name)
    if not grant or not grant['enabled'] or 'launch:'+command not in grant['actions']:
        raise access.AccessDenied('Explicit command identity and scope required.')
    now=time.time();nonce=secrets.token_urlsafe(32)
    actor=access.Actor(nonce,'machine',name,'operator',grant['workspace_id'],frozenset(grant['buyer_ids']),policy['_revision'],int(now),now+28800,nonce,True,frozenset(grant['actions']))
    registry=access.registry
    with registry.lock:
        registry._reclaim(time.time())
        if len(registry.leases) >= 10000:
            raise access.AccessUnavailable('Application access is unavailable.')
        registry.leases[nonce]=(actor,now)
    try:
        with access.actor_scope(actor): yield actor
    finally:
        with registry.lock: registry.leases.pop(nonce,None)


def authorised_cli(command):
    def decorate(function):
        @wraps(function)
        def invoke(*args,**kwargs):
            with command_scope(command): return function(*args,**kwargs)
        return invoke
    return decorate
