"""Finite qualification of the STABLE restricted credentials, performed by the restricted RUNTIME with the two restricted credentials ALONE.

No administrative credential, GitHub client, Owner, grant, exception, source request, queue row or application write exists in this module. It makes at most THREE connection attempts per
restricted login and SIX in total, in a fixed order (worker first; the effect login only after the worker qualified), reusing the same credential unchanged for every attempt.

A further attempt is made only after the EXACT recognised authentication failure (`AUTHENTICATION_REJECTED`) AND verified client closure of the previous attempt, after a fixed spacing
(SPACING_SECONDS: 20 s before the second attempt, 60 s before the third; each wait is sliced into one-second steps that honour the STOP file and the overall deadline). It stops at once on a TLS
failure, an unexpected identity/profile, uncertain closure, a circuit-breaker indication, any other failure class, or exhausted limits. There is no automatic extension and no new attempt
sequence: a new sequence is a new reviewed workflow decision.

What a restricted runtime can and cannot verify: it reads only what the two logins may read about themselves (their own role row, memberships, privileges via the privilege-inquiry functions, and -
for the worker only - the control row it holds SELECT on). It cannot see other sessions or the password state; those are OWNER verifications (listed in the result).
A failed qualification cannot disable anything (that needs the privileged revocation path): it reports the retained access and a blocked-for-use state.
A manual stop in production is cancelling the workflow run (the STOP file under the output directory exists for local rehearsals; a hosted runner is ephemeral and nobody can create it)."""
import argparse,json,os,signal,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .connection_diagnostics import safe_failure
from .operational_controller import DatabaseBudget,Denied
from .operational_journal import Journal
from .operational_preparation import Progress,resolve_addresses
from .tls_trust import verified_trust
from . import restricted_route as rr

AUTHORITY = 'AUTHORISE_INGESTION_STABLE_CREDENTIAL_QUALIFICATION_ONCE_20261020'
ROLES = ('ingestion_worker_login', 'ingestion_effect_login')
SECRET_ENV = {'ingestion_worker_login': 'INGESTION_WORKER_DATABASE_URL', 'ingestion_effect_login': 'INGESTION_EFFECT_DATABASE_URL'}
CAPABILITY = {'ingestion_worker_login': 'ingestion_worker', 'ingestion_effect_login': 'ingestion_effect_broker'}
FORBIDDEN_MEMBERSHIPS = ('ingestion_storage_owner', 'ingestion_authority_issuer', 'ingestion_barrier_releaser', 'ingestion_recovery_operator', 'ingestion_storage_operator')
SPACING_SECONDS = (20, 60)          # waited before attempt 2 and before attempt 3 of a role
MAX_PER_ROLE = 3
MAX_TOTAL = 6
OVERALL_SECONDS = 330               # 2 x (20 + 60) of spacing + 6 bounded attempts, with margin; hard stop
ATTEMPT_SECONDS = 60                # the budget of ONE attempt: no attempt may START unless it can finish inside the overall window
MIN_VALID_DAYS = 7
FORBIDDEN_ENV = ('DATABASE_URL', 'INGESTION_STORAGE_DATABASE_URL', 'GH_TOKEN', 'GITHUB_TOKEN', 'PGPASSWORD', 'PGSERVICE', 'PGSERVICEFILE')
OWNER_VERIFICATIONS = ('NO_OTHER_SESSIONS_OF_THE_TWO_LOGINS', 'PASSWORD_STATE_AND_EXACT_VALID_UNTIL_ON_THE_SERVER', 'NO_UNEXPIRED_GRANT_FOR_THE_EFFECT_VIEW', 'SERVER_SIDE_CLOSURE_OF_THE_QUALIFICATION_SESSIONS')
STOP_REASONS = frozenset({'CANCELLED', 'AUTH_REJECTED_EXHAUSTED', 'UNCERTAIN_CLOSURE', 'UNEXPECTED_PROFILE', 'OVERALL_DEADLINE', 'MANUAL_STOP', 'CIRCUIT_BREAKER_INDICATED', 'TLS_FAILURE', 'UNRECOGNISED_FAILURE', 'ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT'})

PROBE_SQL = ("SELECT r.rolvaliduntil,r.rolconnlimit,r.rolcanlogin,coalesce((SELECT array_agg(m.roleid::regrole::text ORDER BY m.roleid::regrole::text) FROM pg_auth_members m WHERE m.member=r.oid),ARRAY[]::text[]),"
             "pg_has_role(current_user,CAST(:cap AS name),'USAGE'),"
             "(SELECT bool_or(pg_has_role(current_user,CAST(f AS name),'MEMBER')) FROM unnest(CAST(:forbidden AS text[])) f WHERE EXISTS(SELECT 1 FROM pg_catalog.pg_roles x WHERE x.rolname=f)),"
             "has_table_privilege(current_user,'public.ingestion_work_items','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_table_privilege(current_user,'public.ingestion_work_attempts','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),"
             "has_table_privilege(current_user,'public.ingestion_work_items','SELECT'),statement_timestamp() "
             "FROM pg_catalog.pg_roles r WHERE r.rolname=current_user")
CONTROL_SQL = ("SELECT outcome::jsonb->'global_stop' IS DISTINCT FROM 'null'::jsonb,outcome::jsonb->>'manual_stop',coalesce((outcome::jsonb->>'hard_stop_generation')::integer,0),"
               "(SELECT count(*) FROM jsonb_each(outcome::jsonb->'grants') g WHERE (g.value->>'expires_at')::double precision>extract(epoch FROM statement_timestamp())) "
               "FROM public.ingestion_work_items WHERE key=repeat('0',64)")


class Stop(Exception):
    def __init__(self, reason):
        if reason not in STOP_REASONS:raise ValueError('STOP_REASON')
        self.reason = reason
        super().__init__(reason)


class ProfileViolation(Exception):pass


class Cancelled(BaseException):
    """The run was cancelled (SIGTERM/SIGINT). A BaseException so that no generic handler can mistake it for a failure class."""


class _Cancellation:
    """Cooperative cancellation. The signal handler ONLY records the request, and raises Cancelled solely while the run is inside an explicitly interruptible region (waiting, preparation, the connection attempt itself). Everywhere else - closing the budget, building and writing records, publishing the final result - a request is deferred and acted on at the next safe point, so no catchable signal can land between recording steps."""
    interruptible = False
    requested = False


def _on_signal(signum, frame):
    _Cancellation.requested = True
    if _Cancellation.interruptible:
        _Cancellation.interruptible = False      # one-shot: the state can never be left raised by an exception unwinding through the exit
        raise Cancelled()


def install_cancellation():
    """Install the handlers (main thread); returns the previous ones. An uncatchable kill (SIGKILL, the 345 s timeout kill, runner loss) cannot be handled at all: only the per-attempt events and progress.json written so far survive, and the absence of final-result.json means UNKNOWN."""
    _Cancellation.interruptible = False;_Cancellation.requested = False
    return {sig: signal.signal(sig, _on_signal) for sig in (signal.SIGTERM, signal.SIGINT)}


class interruptible:
    def __enter__(self):
        _Cancellation.interruptible = True
        if _Cancellation.requested:
            _Cancellation.interruptible = False;raise Cancelled()
    def __exit__(self, *exc):
        _Cancellation.interruptible = False;return False


RETAINED_ACCESS = 'BOTH_LOGINS_REMAIN_ENABLED_UNTIL_THE_OWNER_RUNS_THE_PRIVILEGED_REVOCATION'
USE_BLOCKED_SEMANTICS = 'QUALIFICATION_RESULT_ONLY_NOT_A_DURABLE_DATABASE_BARRIER_THE_LOGINS_STAY_ENABLED_UNTIL_THE_OWNER_REVOKES_AND_NO_GRANT_MAY_BE_ISSUED_FROM_THIS_MILESTONE'


def admitted(env):
    """Single-use, protected-environment admission (the same shape as the other once-workflows), and no administrative credential in the environment."""
    sha = env.get('QUALIFICATION_REVIEWED_SHA', '')
    return (len(sha) == 40 and all(ch in '0123456789abcdef' for ch in sha) and env.get('GITHUB_SHA') == sha and env.get('GITHUB_WORKFLOW_SHA') == sha and env.get('GITHUB_REF') == 'refs/heads/master'
            and env.get('GITHUB_RUN_NUMBER') == '1' and env.get('GITHUB_RUN_ATTEMPT') == '1' and env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and env.get('QUALIFICATION_AUTHORITY') == AUTHORITY and not any(env.get(k) for k in FORBIDDEN_ENV) and not any(k.startswith('PG') and env.get(k) for k in env))


class Qualification:
    def __init__(self, urls, *, emit, ssl, hostaddr, clock=time.monotonic, sleep=time.sleep, stop_file=None, budget_factory=DatabaseBudget, progress_sink=None):
        if set(urls) != set(ROLES):raise ValueError('EXACT_TWO_CREDENTIALS')
        self.urls = dict(urls);self.first_urls = dict(urls)       # compared on every attempt: the credential is never changed between attempts
        self.emit = emit;self.ssl = ssl;self.hostaddr = hostaddr;self.clock = clock;self.sleep = sleep;self.stop_file = Path(stop_file) if stop_file else None;self.budget_factory = budget_factory
        self.started = clock();self.attempts = [];self.ran = False;self.progress = progress_sink or (lambda snapshot: None)

    # ------------------------------------------------------------------ waits and limits
    def check(self, starting_attempt=False):
        if self.clock() - self.started >= OVERALL_SECONDS - (ATTEMPT_SECONDS + 10 if starting_attempt else 0):raise Stop('OVERALL_DEADLINE')
        if self.stop_file is not None and self.stop_file.exists():raise Stop('MANUAL_STOP')

    def wait(self, seconds):
        end = self.clock() + seconds
        while True:
            self.check()
            left = end - self.clock()
            if left <= 0:return
            self.sleep(min(1.0, left))

    # ------------------------------------------------------------------ one attempt
    def probe(self, connection, role, now_ok):
        from sqlalchemy import text
        row = connection.execute(text(PROBE_SQL), {'cap': CAPABILITY[role], 'forbidden': list(FORBIDDEN_MEMBERSHIPS)}).fetchone()
        if row is None:raise ProfileViolation()
        valid_until, connlimit, canlogin, memberships, has_capability, forbidden, dml, can_select, now = row
        days = None if valid_until is None else (valid_until - now).total_seconds() / 86400
        ok = (canlogin is True and connlimit == 1 and list(memberships) == [CAPABILITY[role]] and has_capability is True and not forbidden and dml is False
              and valid_until is not None and days >= MIN_VALID_DAYS and (can_select is True if role == 'ingestion_worker_login' else can_select is False))
        control = None
        if role == 'ingestion_worker_login':          # informational only: the worker holds SELECT on the ledger; a failure here is recorded, never a stop
            try:
                c = connection.execute(text(CONTROL_SQL)).fetchone()
                control = dict(global_stop_set=bool(c[0]), manual_stop=c[1] if c[1] in (None, 'STORAGE_TEST_STOP') else 'OTHER', hard_stop_generation=int(c[2]), unexpired_grants=int(c[3]))
            except Exception:control = 'UNAVAILABLE'
        if not ok:raise ProfileViolation()
        return dict(valid_days_remaining=int(days), connection_limit=connlimit, memberships=list(memberships), control_row=control)

    def attempt(self, role, ordinal, waited):
        if self.urls[role] != self.first_urls[role]:raise Stop('UNEXPECTED_PROFILE')
        from sqlalchemy.engine import make_url
        if rr.identify(make_url(self.urls[role])) != ('POOLER', role):raise Stop('ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT')
        began = self.clock();probe = None;reason = None;status = 'FAILED';cancelled = False;refused = False
        slot = len(self.attempts)
        self.attempts.append(dict(role=role, ordinal=ordinal, spacing_waited_seconds=round(waited, 3), outcome='STARTED_UNRESOLVED', reason_code=None, client_closure_verified=False, elapsed_seconds=None,
                                  credential='UNCHANGED_SINCE_FIRST_ATTEMPT', probe=None, receipt=None, receipt_basis='UNKNOWN'))      # counted as STARTED before anything can be interrupted; replaced when the attempt completes
        budget = None
        try:
          with interruptible():
            budget = self.budget_factory(connections=1, statements=24, seconds=60, emit=self.emit, stop_file=self.stop_file)
            try:
                engine = budget.engine(self.urls[role], ssl=self.ssl, hostaddr=self.hostaddr, route='POOLER')
            except Denied:
                refused = True;reason = 'ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT'
            else:
                try:
                    with engine.connect() as connection:
                        probe = self.probe(connection, role, True)
                    status = 'CONNECTED'
                except Cancelled:status, reason, cancelled = 'INTERRUPTED', 'CANCELLED', True
                except ProfileViolation:reason = 'UNEXPECTED_PROFILE'
                except Exception as exc:
                    seen = budget.connection_diagnostics[-1] if budget.connection_diagnostics else None
                    if seen is not None and seen.get('phase') == 'DRIVER_CONNECT':reason = seen.get('reason_code') or 'UNKNOWN'
                    elif isinstance(exc, Denied) and 'SERVER_TIMEOUT_OR_RESTRICTED_IDENTITY_PROFILE' in str(exc):reason = 'UNEXPECTED_PROFILE'
                    else:reason = safe_failure(exc, 'EXECUTION')['reason_code']
        except Cancelled:status, reason, cancelled = 'INTERRUPTED', 'CANCELLED', True
        finally:
            receipt = None
            try:receipt = self.sanitise(budget.close([])) if budget is not None else None
            except Exception:receipt = None      # closing failed: the measurements and the closure are UNKNOWN, never zero and never verified
        closure_ok = receipt is not None and receipt.get('cleanup') == 'CLOSED' and receipt.get('connections_closed') is True
        record = dict(role=role, ordinal=ordinal, spacing_waited_seconds=round(waited, 3), outcome=status, reason_code=reason, client_closure_verified=bool(closure_ok), elapsed_seconds=round(self.clock() - began, 3),
                      credential='UNCHANGED_SINCE_FIRST_ATTEMPT', probe=probe, receipt=receipt, receipt_basis='MEASURED' if receipt is not None else 'UNKNOWN')
        self.attempts[slot] = record
        self.emit('qualification_attempt', record)
        try:self.progress(self.accounting())
        except Exception:pass      # a failed progress write never changes the sequence; the per-attempt event above is the durable record
        if cancelled or _Cancellation.requested:raise Cancelled()      # a request received while closing or recording is acted on only now, after the record is complete
        if refused:raise Stop('ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT')
        return record

    # ------------------------------------------------------------------ the credential-free budget receipt of every attempt, and the cumulative accounting
    RECEIPT_KEYS = ('connection_attempts', 'driver_statements', 'returned_data_value_bytes', 'connection_active_seconds', 'connections_opened', 'connections_closed_count', 'connections_closed', 'cleanup',
                    'failed_native_connections_closed', 'socket_closure', 'statement_kinds', 'connection_diagnostics', 'hard_deadline_events', 'cancel_attempts', 'cancel_failures', 'cancel_seconds',
                    'cancel_allowance', 'cancel_run_allowance', 'cancel_used_before', 'errors', 'elapsed_seconds')

    @classmethod
    def sanitise(cls, receipt):
        """Whitelist of the budget receipt's own fields (allow-listed classifications, counters, durations); it never contains a URL, password, message or query text."""
        return json.loads(json.dumps({k: receipt.get(k) for k in cls.RECEIPT_KEYS if k in receipt}, default=str))

    NUMERIC_KEYS = ('connection_attempts', 'driver_statements', 'returned_data_value_bytes', 'connection_active_seconds', 'connections_opened', 'connections_closed_count', 'cancel_attempts', 'cancel_failures', 'cancel_seconds')

    @classmethod
    def complete(cls, receipt):
        return isinstance(receipt, dict) and all(isinstance(receipt.get(k), (int, float)) and not isinstance(receipt.get(k), bool) for k in cls.NUMERIC_KEYS) and isinstance(receipt.get('hard_deadline_events'), list)

    @classmethod
    def accounting_for(cls, attempts):
        started = len(attempts);measured = [a for a in attempts if cls.complete(a.get('receipt'))]
        basis = 'NOT_STARTED' if started == 0 else 'MEASURED' if len(measured) == started else 'LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN'
        def total(key, nested=None):
            return sum(a['receipt'][key] for a in measured) if nested is None else sum(len(a['receipt'][key]) for a in measured)
        metrics = {'connection_attempts': total('connection_attempts'), 'driver_commands': total('driver_statements'), 'returned_database_value_bytes': total('returned_data_value_bytes'),
                   'connection_active_seconds': round(total('connection_active_seconds'), 3), 'connections_opened': total('connections_opened'), 'connections_closed': total('connections_closed_count'),
                   'cancel_attempts': total('cancel_attempts'), 'cancel_failures': total('cancel_failures'), 'cancel_seconds': round(total('cancel_seconds'), 3), 'hard_deadline_events': total('hard_deadline_events', nested=True)}
        closed = sum(1 for a in attempts if a.get('client_closure_verified'))
        return dict(attempts_started=dict(value=started, basis='MEASURED'), attempts_with_receipt=dict(value=len(measured), basis='MEASURED'),
                    metrics={k: dict(value=v, basis=basis) for k, v in metrics.items()},
                    client_closure=dict(verified_attempts=closed, attempts_started=started,
                                        status='NOT_APPLICABLE_NO_ATTEMPT_STARTED' if started == 0 else 'VERIFIED_FOR_EVERY_ATTEMPT' if closed == started else 'NOT_VERIFIED_FOR_SOME_ATTEMPT',
                                        basis='THE_CLIENT_SIDE_BUDGET_RECEIPT_ONLY'),
                    server_session_verification='NOT_PERFORMED_BY_THE_RESTRICTED_RUNTIME_OWNER_VERIFICATION_REQUIRED')

    def accounting(self):
        return self.accounting_for(self.attempts)

    # ------------------------------------------------------------------ the finite procedure
    def run(self):
        if self.ran:raise RuntimeError('QUALIFICATION_SINGLE_USE')      # one fixed sequence; a new sequence is a new reviewed decision
        self.ran = True
        stop = None;qualified = {}
        try:
            for role in ROLES:
                for n in range(1, MAX_PER_ROLE + 1):
                    if _Cancellation.requested:raise Cancelled()
                    if len(self.attempts) >= MAX_TOTAL:raise Stop('AUTH_REJECTED_EXHAUSTED')
                    waited = 0.0
                    if n > 1:
                        waited = float(SPACING_SECONDS[n - 2])
                        with interruptible():self.wait(waited)
                    self.check(starting_attempt=True)
                    record = self.attempt(role, n, waited)
                    if not record['client_closure_verified']:raise Stop('UNCERTAIN_CLOSURE')      # verified client closure is required before ANYTHING continues, success included
                    if record['outcome'] == 'CONNECTED':
                        qualified[role] = True;break
                    reason = record['reason_code']
                    if reason == 'UNEXPECTED_PROFILE':raise Stop('UNEXPECTED_PROFILE')
                    if reason == 'CIRCUIT_BREAKER_INDICATED':raise Stop('CIRCUIT_BREAKER_INDICATED')
                    if reason and reason.startswith('TLS_'):raise Stop('TLS_FAILURE')
                    if reason != 'AUTHENTICATION_REJECTED':raise Stop('UNRECOGNISED_FAILURE')
                    if n == MAX_PER_ROLE:raise Stop('AUTH_REJECTED_EXHAUSTED')
        except Stop as stopped:stop = stopped.reason
        except Cancelled:stop = 'CANCELLED'
        except Exception:stop = 'UNRECOGNISED_FAILURE'      # attempts already made stay in the accounting
        done = len(qualified) == len(ROLES)
        return self.result(done, stop, qualified)

    def result(self, done, stop, qualified):
        return dict(status='STABLE_CREDENTIALS_QUALIFIED' if done else 'QUALIFICATION_STOPPED', stop_reason=None if done else stop,
                    roles={r: dict(qualified=qualified.get(r, False), attempts=[a for a in self.attempts if a['role'] == r]) for r in ROLES},
                    attempts_total=len(self.attempts), limits=dict(per_role=MAX_PER_ROLE, total=MAX_TOTAL, spacing_seconds=list(SPACING_SECONDS), overall_seconds=OVERALL_SECONDS),
                    elapsed_seconds=round(self.clock() - self.started, 3), use_blocked=not done, use_blocked_semantics=USE_BLOCKED_SEMANTICS, accounting=self.accounting(),
                    retained_access=None if done else RETAINED_ACCESS, owner_verifications_required=list(OWNER_VERIFICATIONS), grants_issued=0, exceptions_registered=0, source_requests=0,
                    application_writes=0, administrative_credential_present=False, grant_may_be_issued_from_this_milestone=False)


def preparation_failure_result(kind):
    """Preparation stopped before any database work: the measurements are NOT_STARTED (explicitly), the closure is NOT_APPLICABLE - neither is a measured zero or a verified closure."""
    return dict(status='QUALIFICATION_STOPPED', stop_reason='CANCELLED' if kind == 'Cancelled' else 'ROUTE_OR_CREDENTIAL_REJECTED_BEFORE_CONNECT', attempts_total=0, use_blocked=True, use_blocked_semantics=USE_BLOCKED_SEMANTICS, detail=kind,
                accounting=Qualification.accounting_for([]), retained_access=RETAINED_ACCESS, owner_verifications_required=list(OWNER_VERIFICATIONS), grants_issued=0, exceptions_registered=0, source_requests=0,
                application_writes=0, administrative_credential_present=False, grant_may_be_issued_from_this_milestone=False)


def main(argv=None):
    parser = argparse.ArgumentParser();parser.add_argument('--output', type=Path, required=True);args = parser.parse_args(argv)
    if not admitted(os.environ):raise SystemExit('QUALIFICATION_NOT_ADMITTED')
    urls = {role: os.environ.get(name, '') for role, name in SECRET_ENV.items()}
    if not all(urls.values()):raise SystemExit('RESTRICTED_CREDENTIALS_REQUIRED')
    journal = Journal(args.output)
    journal.emit('consumed', dict(authority=AUTHORITY))
    install_cancellation()      # a cancelled run keeps the receipts of the attempts already made and reports CANCELLED
    try:
      with interruptible():
        ca, _ = verified_trust();progress = Progress()
        hostaddr = resolve_addresses(progress)
        q = Qualification(urls, emit=journal.emit, ssl={'sslmode': 'verify-full', 'sslrootcert': str(ca)}, hostaddr=hostaddr, stop_file=journal.root / 'STOP', progress_sink=lambda snap: journal.save('progress.json', snap))
    except (Exception, Cancelled) as exc:
        result = preparation_failure_result(type(exc).__name__)
    else:result = q.run()      # run() keeps every attempt already made, whatever happens
    journal.emit('final', result);journal.save('final-result.json', result)      # not interruptible: a signal only records a request
    print(json.dumps({k: result.get(k) for k in ('status', 'stop_reason', 'attempts_total', 'use_blocked')}, sort_keys=True))
    raise SystemExit(0 if result['status'] == 'STABLE_CREDENTIALS_QUALIFIED' else 1)


if __name__ == '__main__':main()
