"""Bounded nonsecret timestamp evidence; never accepts arbitrary row text."""
import math,sys
from datetime import datetime,timezone
from decimal import Decimal

def value(v):
    if v is None:return {'type':'NoneType','value':None}
    if type(v) not in (int,float,Decimal):return {'type':'UNSUPPORTED','value':None}
    if type(v) is float:return {'type':'float','value':repr(v),'hex':v.hex(),'ratio':list(v.as_integer_ratio()) if math.isfinite(v) else None}
    s=str(v)
    return {'type':type(v).__name__,'value':s if len(s)<=64 else 'OUT_OF_BOUND'}

def deadline_evidence(deadline,observed,numeric=None):
    expected=datetime.fromtimestamp(deadline,timezone.utc).timestamp()
    result=dict(version='DEADLINE_OBSERVATION_V1',python=sys.version.split()[0],input=value(deadline),write_iso=datetime.fromtimestamp(deadline,timezone.utc).isoformat(),expected=value(expected),observed=value(observed),database_numeric_epoch=value(numeric),strict_equal=observed==expected)
    if type(observed) in (int,float,Decimal) and (type(observed) is not float or math.isfinite(observed)):
        result['difference_seconds_exact']=str(Decimal(observed)-Decimal(expected))
    return result
