"""Stable secrets in the existing encrypted owner journal, never a new store."""
import hashlib,secrets
from psycopg import sql
from . import intake_owner as op

def hashes(c):
    return dict(c.execute("SELECT rolname,encode(sha256(convert_to(rolpassword,'UTF8')),'hex') FROM pg_authid WHERE rolname=ANY(%s)",(list(op.ROLES),)).fetchall())

def prepare(c):
    op.identity(c);op.admin_capabilities(c);op.inventory(c);op.dormant(c);op.owner_absent(c)
    passwords={role:secrets.token_urlsafe(48) for role in op.ROLES}
    verifiers={role:c.pgconn.encrypt_password(value.encode(),role.encode(),algorithm=b'scram-sha-256').decode() for role,value in passwords.items()}
    return dict(version='STABLE_RESTRICTED_V1',passwords=passwords,verifiers=verifiers,
        verifier_sha256={r:hashlib.sha256(v.encode()).hexdigest() for r,v in verifiers.items()})

def configure(c,value):
    """Caller has durably sealed intent and these exact secrets before entry."""
    op.require(value.get('version')=='STABLE_RESTRICTED_V1' and set(value['passwords'])==set(op.ROLES) and
        value['verifier_sha256']=={r:hashlib.sha256(v.encode()).hexdigest() for r,v in value['verifiers'].items()},'STABLE_CONFIGURATION_PRECONDITION')
    c.execute('BEGIN')
    try:
        op.identity(c);op.admin_capabilities(c);op.inventory(c);op.dormant(c);op.owner_absent(c)
        before=op.ledger_sha(c);members=c.execute(op.MEMBERS).fetchall()
        for role,verifier in value['verifiers'].items():
            c.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD {} VALID UNTIL 'epoch'").format(sql.Identifier(role),sql.Literal(verifier)))
        op.require(hashes(c)==value['verifier_sha256'] and op.ledger_sha(c)==before and c.execute(op.MEMBERS).fetchall()==members,'STABLE_CONFIGURATION_PRESERVATION')
        op.dormant(c,stable_verifiers=value['verifier_sha256']);c.execute('COMMIT')
    except BaseException:c.execute('ROLLBACK');raise
    op.dormant(c,stable_verifiers=value['verifier_sha256']);op.owner_absent(c)
    return dict(outcome='COMMIT_ACKNOWLEDGED',logins='DISABLED',password_verifiers='RETAINED',memberships='ABSENT',secret_storage='EXISTING_ENCRYPTED_DATABASE_OWNER_STATE')
