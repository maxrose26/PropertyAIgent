import json
from pathlib import Path
import sys
from .shape_audit import validate as base_validate
from .manchester_shape import CASE as INITIAL_CASE
from .manchester_search_shape import CASE, GETTERS, HOST


def validate(a):
    if a.get('case')!=CASE or type(a.get('bootstrap_reads')) is not int or not 1<=a['bootstrap_reads']<=3:
        raise ValueError('bootstrap accounting')
    base_validate(dict(a,case=INITIAL_CASE))
    later=[m for m in a['blocked_action_metadata'] if m.get('descriptor')!=HOST
           and (m.get('classname'),m.get('method')) not in GETTERS]
    if not later: raise ValueError('no later RPC observed')
    return {'outcome':'LATER_RPC_SHAPE_OBSERVED_ONLY','completeness':'UNKNOWN','production_admission':False}


if __name__=='__main__':
    p=Path(sys.argv[1])
    if p.stat().st_size>=65536: raise ValueError('audit bound')
    print(json.dumps(validate(json.loads(p.read_bytes()))))
