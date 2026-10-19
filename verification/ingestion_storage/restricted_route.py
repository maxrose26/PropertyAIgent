"""The two reviewed routes for the RESTRICTED logins. Exact, registration-bound, no fallback.

POOLER: the shared session-mode pooler, routing username `<role>.<project-ref>` (the original route).
DIRECT: the project's direct Postgres endpoint, plain role name. Needs an IPv4 address for the host (the project's IPv4 add-on) because every reviewed runtime is IPv4-only.
A run uses exactly ONE route, chosen by its registration; nothing here ever selects another one after a failure. The administrative route is separate and unchanged."""
from urllib.parse import quote

REF = 'zcikcfgpblzuzpanpdqd'
POOLER = 'POOLER'
DIRECT = 'DIRECT'
ROUTES = {
    POOLER: dict(host='aws-0-eu-west-2.pooler.supabase.com', port=5432, database='postgres', username_suffix='.' + REF),
    DIRECT: dict(host='db.' + REF + '.supabase.co', port=5432, database='postgres', username_suffix=''),
}
RESTRICTED_ROLES = ('ingestion_worker_login', 'ingestion_effect_login', 'ingestion_application_login')


def username(route, role):
    if route not in ROUTES or role not in RESTRICTED_ROLES:
        raise ValueError('EXACT_RESTRICTED_ROUTE_AND_ROLE')
    return role + ROUTES[route]['username_suffix']


def url(route, role, password):
    """Same in-memory value goes to protected mapping and the native URL parser."""
    spec = ROUTES[route]
    return 'postgresql://' + quote(username(route, role), safe='') + ':' + quote(password, safe='') + '@' + spec['host'] + ':' + str(spec['port']) + '/' + spec['database']


def identify(parsed):
    """(route name, SQL role) of a parsed URL, or None. The match is exact on host, port, database and username."""
    for name, spec in ROUTES.items():
        if (parsed.host, parsed.port, parsed.database) == (spec['host'], spec['port'], spec['database']):
            for role in RESTRICTED_ROLES:
                if parsed.username == role + spec['username_suffix']:
                    return name, role
    return None
