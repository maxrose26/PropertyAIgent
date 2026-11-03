"""Pure exact-route validation. No engine construction or database capability."""
from sqlalchemy.engine import make_url
from app.db.session import _normalize_database_url

CODES=frozenset({'DRIVER_MISMATCH','HOST_MISMATCH','PORT_MISMATCH','DATABASE_MISMATCH',
                 'USERNAME_MISMATCH','QUERY_FORBIDDEN','MALFORMED_INPUT'})

class RouteRejection(ValueError):
    def __init__(self,code):
        self.code=code if code in CODES else 'MALFORMED_INPUT'
        super().__init__(self.code)


def validate_route(raw):
    """Return a private normalized URL, never an audit representation."""
    try:
        if not isinstance(raw,str) or not raw or len(raw)>8192:
            raise ValueError()
        u=make_url(_normalize_database_url(raw))
        port=5432 if u.port is None else u.port
    except Exception:
        raise RouteRejection('MALFORMED_INPUT') from None
    checks=(('DRIVER_MISMATCH',u.drivername=='postgresql+psycopg'),
        ('HOST_MISMATCH',u.host=='aws-0-eu-west-2.pooler.supabase.com'),
        ('PORT_MISMATCH',port==5432),('DATABASE_MISMATCH',u.database=='postgres'),
        ('USERNAME_MISMATCH',u.username=='postgres.zcikcfgpblzuzpanpdqd'),
        ('QUERY_FORBIDDEN',not u.query))
    for code,passed in checks:
        if not passed:raise RouteRejection(code) from None
    return u.set(port=port)


def route_audit(raw):
    """Only safe phase/result/code crosses the audit boundary."""
    try:validate_route(raw)
    except RouteRejection as exc:
        return dict(phase='REJECTED_BEFORE_ENGINE_CREATION',result='REJECTED',reason_code=exc.code,
                    driver_normalization_applied=None,default_port_applied=None)
    return dict(phase='ROUTE_VALIDATED_NO_ENGINE',result='COMPATIBLE',reason_code=None,
                driver_normalization_applied=_normalize_database_url(raw)!=raw,
                default_port_applied=make_url(raw).port is None)
