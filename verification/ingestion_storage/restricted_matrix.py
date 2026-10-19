"""Four-entry restricted-account connection matrix: which connection configurations work, recorded per configuration.

DIAGNOSTIC ALLOWANCE ONLY. This is not execution authority: it registers no authority, issues no grant or exception, touches no queue or ledger, calls no council and writes
no application row. It runs after the accepted credential lifecycle has installed fresh credentials, and the lifecycle's teardown disables access afterwards.

Interpretation (fixed, and exported with every result): each entry describes ONE configuration at ONE point in time after credential installation. The ordered matrix cannot
separate startup options from elapsed time, credential caching, propagation or any provider behaviour, because those vary together along the order. A result is a
configuration-specific observation, never a cause.

Each entry: exactly one connection attempt and, only if it connects, exactly one fixed identity statement; the connection is closed and positively verified closed before the
next entry begins (the logins carry CONNECTION LIMIT 1, so an unclosed connection would invalidate every later entry).
"""
import re,time
from app.ingestion.ledger import Denied
from .connection_diagnostics import safe_failure
from .operational_cleanup import Stop
from .hard_deadline import hard_deadline,abandon,DeadlineExceeded
from .operational_preparation import STARTUP_OPTIONS
from .tls_trust import owned_resources

ENTRIES=(('ingestion_worker_login','NONE'),('ingestion_worker_login','REVIEWED'),('ingestion_effect_login','NONE'),('ingestion_effect_login','REVIEWED'))
OPTIONS={'NONE':None,'REVIEWED':STARTUP_OPTIONS}
STATEMENT=("SELECT current_user,session_user,rolcanlogin,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolreplication,"
           "current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout') "
           "FROM pg_catalog.pg_roles WHERE rolname=current_user")
EXPECTED_FLAGS=(True,False,False,False,False,False)
EXPECTED_TIMEOUTS={'NONE':None,'REVIEWED':('10s','3s','20s')}
SETTING_PATTERN=re.compile(r'0|[0-9]{1,6}(?:us|ms|s|min|h|d)?')      # bounded, allow-listed rendering of a server timeout setting; anything else is recorded only as a marker


def bounded_setting(value):
    return value if isinstance(value,str) and SETTING_PATTERN.fullmatch(value) else 'NON_ALLOWLISTED_VALUE'
# A classified failure of one of these kinds does not stop the matrix. Anything else (unclassified, TLS integrity, identity, budgets, closure) is a global stop.
CONTINUABLE=frozenset({'AUTHENTICATION_REJECTED','AUTHORIZATION_REJECTED','PERMISSION_DENIED','ROUTING_IDENTITY_REJECTED','CONNECTION_CAPACITY','CONNECTION_TIMEOUT','CONNECTION_REFUSED',
                       'CONNECTION_FAILURE','SERVER_NOT_READY'})
CONNECTED_OUTCOMES=('CONNECTED_IDENTITY_VERIFIED','CONNECTED_IDENTITY_VERIFIED_OPTIONS_NOT_REFLECTED')
SECURITY_CLASS=frozenset({'TLS_HOSTNAME_MISMATCH','TLS_CA_UNAVAILABLE','TLS_CHAIN_REJECTED'})
LIMITS=dict(entries=4,connection_attempts=4,attempts_per_entry=1,identity_statements_per_entry=1,driver_statements=4,rollbacks=0,commits=0,returned_data_value_bytes=1024,
            connect_timeout_seconds=3,seconds_per_entry=13,matrix_seconds=60,
            administrative_connections=5,administrative_commands=64,administrative_commands_before_teardown=44,administrative_commands_through_teardown=58)
INTERPRETATION=dict(scope='CONFIGURATION_SPECIFIC_OBSERVATIONS_AT_ONE_POINT_IN_TIME',
                    not_established=('CAUSE_OF_ANY_FAILURE','CREDENTIAL_CACHING','PROPAGATION_DELAY','PROVIDER_DEFECT','STARTUP_OPTIONS_AS_CAUSE_OR_NON_CAUSE_WHEN_ORDER_AND_TIME_VARY_TOGETHER'),
                    execution_authority='NONE',qualification_for_execution='NOT_GRANTED_BY_THIS_DIAGNOSTIC',
                    operational_deadline_acceptance='NOT_ESTABLISHED_BY_THIS_DIAGNOSTIC',
                    deadline_note='A connected entry shows a configuration works; it does not show that a statement deadline is enforced. Each entry carries a client-side hard deadline independent of server timeout settings.')


class MatrixStop(Exception):
    """A global stop with a fixed code; str() is the fixed code only."""
    CODES=frozenset({'UNCLASSIFIED_FAILURE','SECURITY_CLASS_FAILURE','UNEXPECTED_IDENTITY','CLOSURE_UNCERTAIN','CONNECTION_BUDGET_EXHAUSTED','STATEMENT_BUDGET_EXHAUSTED','RETURNED_BYTES_EXHAUSTED',
                     'MATRIX_TIME_EXHAUSTED','MATRIX_ORDER_VIOLATION','RESPONSE_SHAPE','NON_CONTINUABLE_FAILURE','CAPACITY_AFTER_OWN_CONNECTION','DEADLINE_OR_BUDGET_DENIAL','ENTRY_DEADLINE_EXCEEDED'})
    def __init__(self,code):
        if code not in self.CODES:raise ValueError('MATRIX_CODE')
        self.code=code;super().__init__(code)


class Matrix:
    def __init__(self,runner,*,principal=None,connect=None,clock=time.monotonic,resources=owned_resources):
        if principal is None:
            from .operational_controller import runtime_principal as principal
        self.runner=runner;self.principal=principal;self.clock=clock;self.resources=resources
        if connect is None:
            import psycopg
            connect=psycopg.connect
        self.connect=connect
        self.entries=[dict(ordinal=i+1,role=role,startup_options=variant,outcome='NOT_REACHED') for i,(role,variant) in enumerate(ENTRIES)]
        self.attempts=0;self.statements=0;self.returned_bytes=0;self.started=None;self.stopped=None
        self.last_closed=None;self.connected_roles=set()

    # ---- accounting -------------------------------------------------------------------------------------------------------------------------------------
    def accounting(self):
        m=lambda v:dict(value=v,basis='MEASURED')
        return dict(connection_attempts=m(self.attempts),identity_statements=m(self.statements),returned_data_value_bytes=m(self.returned_bytes),rollbacks=m(0),commits=m(0),
                    entries_connected=m(sum(e['outcome'] in CONNECTED_OUTCOMES for e in self.entries)),
                    entries_options_not_reflected=m(sum(e['outcome']=='CONNECTED_IDENTITY_VERIFIED_OPTIONS_NOT_REFLECTED' for e in self.entries)),
                    entries_failed_classified=m(sum(e['outcome']=='FAILED_CLASSIFIED' for e in self.entries)),
                    entries_not_attempted=m(sum(e['outcome'] in ('NOT_REACHED','SKIPPED_GLOBAL_STOP') for e in self.entries)))

    def closed_ok(self):
        return all(e.get('connection_closure',{}).get('status')=='CLOSED' for e in self.entries if e['outcome'] not in ('NOT_REACHED','SKIPPED_GLOBAL_STOP'))

    def finalise(self):
        """Entries never reached are recorded as skipped with the reason, never silently dropped. A lifecycle stop before the matrix finished is a stop too."""
        pending=[e for e in self.entries if e['outcome']=='NOT_REACHED']
        if pending and self.stopped is None:self.stopped='LIFECYCLE_STOP_BEFORE_MATRIX_COMPLETE'
        for e in pending:e['outcome']='SKIPPED_GLOBAL_STOP'
        return self.report()

    def report(self):
        return dict(entries=[dict(e) for e in self.entries],accounting=self.accounting(),limits=dict(LIMITS),interpretation=dict(INTERPRETATION),global_stop=self.stopped,
                    lifecycle_stamps_basis='MONOTONIC_SECONDS_NON_SECRET')

    # ---- one entry --------------------------------------------------------------------------------------------------------------------------------------
    def intervals(self,role,now):
        stamps=self.runner.owner.timeline.get(role,{})
        r=lambda x:None if x is None else round(max(0.0,now-x),3)
        return dict(since_password_committed_seconds=r(stamps.get('password_committed')),since_mapping_acknowledged_seconds=r(stamps.get('mapped')),
                    since_activation_committed_seconds=r(stamps.get('activated')),since_previous_entry_closed_seconds=None if self.last_closed is None else round(max(0.0,now-self.last_closed),3))

    def run(self):
        runner=self.runner;self.started=self.clock()
        for index,(role,variant) in enumerate(ENTRIES):
            self.entry(index,role,variant)
        return self.finalise()

    def stop(self,code,entry=None):
        self.stopped=code
        raise MatrixStop(code)

    def entry(self,index,role,variant):
        runner=self.runner;record=self.entries[index]
        if record['outcome']!='NOT_REACHED':self.stop('MATRIX_ORDER_VIOLATION')
        runner.check()
        if self.clock()-self.started>=LIMITS['matrix_seconds']:self.stop('MATRIX_TIME_EXHAUSTED')
        if self.attempts>=LIMITS['connection_attempts']:self.stop('CONNECTION_BUDGET_EXHAUSTED')
        url=runner.owner.urls[role]
        u,identity=self.principal(url,runner.ssl)
        if identity!=role:self.stop('UNEXPECTED_IDENTITY')
        kwargs=dict(host=u.host,port=u.port,dbname=u.database,user=u.username,password=u.password,connect_timeout=LIMITS['connect_timeout_seconds'],prepare_threshold=None,autocommit=True)
        if OPTIONS[variant]:kwargs['options']=OPTIONS[variant]
        if u.host!='127.0.0.1':
            import ipaddress
            if not runner.hostaddr or ipaddress.ip_address(runner.hostaddr).version!=4:self.stop('UNEXPECTED_IDENTITY')
            kwargs['hostaddr']=runner.hostaddr
        kwargs.update(runner.ssl or {})
        before=self.resources()['socket_fds']
        began=self.clock();record.update(intervals_at_attempt=self.intervals(role,began),outcome='ATTEMPTING')
        self.attempts+=1
        connection=None;failure=None;verified=False;statement_count=0
        record['deadline_control']=dict(client_hard_deadline_seconds=LIMITS['seconds_per_entry'],exceeded=False)
        try:
            with hard_deadline(LIMITS['seconds_per_entry'],'ENTRY_DEADLINE_EXCEEDED'):
                runner.emit('matrix_entry_intent',dict(ordinal=record['ordinal'],role=role,startup_options=variant,**record['intervals_at_attempt']))
                connection=self.connect(**kwargs)
                record['connection_established']=True
                statement_count=1;self.statements+=1
                if self.statements>LIMITS['driver_statements']:self.stop('STATEMENT_BUDGET_EXHAUSTED')
                cursor=connection.execute(STATEMENT);rows=cursor.fetchall();result=cursor.pgresult
                if result is not None:self.returned_bytes+=sum(len(result.get_value(r,k) or b'') for r in range(result.ntuples) for k in range(result.nfields))
                if self.returned_bytes>LIMITS['returned_data_value_bytes']:self.stop('RETURNED_BYTES_EXHAUSTED')
                if len(rows)!=1 or len(rows[0])!=11:self.stop('RESPONSE_SHAPE')
                row=rows[0]
                # Two SEPARATE checks. The identity check decides whether this is the expected restricted login; the timeout check only records whether the requested startup options are
                # reflected in the session. A session that is the right login but does not carry the requested options is a configuration observation, not an identity failure.
                ident=dict(current_user_matches_login=row[0]==role,session_user_matches_login=row[1]==role,restricted_flags_match=tuple(row[2:8])==EXPECTED_FLAGS)
                identity_ok=all(ident.values());record['identity_check']=dict(ident,verified=identity_ok)
                observed=tuple(bounded_setting(x) for x in row[8:11])
                reviewed_match=observed==EXPECTED_TIMEOUTS['REVIEWED']
                record['timeout_check']=dict(requested_startup_options=variant,observed_statement_lock_idle_timeouts=list(observed),matches_reviewed_values=reviewed_match,
                                             reflected_as_requested=(reviewed_match if variant=='REVIEWED' else None))
                record['observed_server_timeouts_match_reviewed']=reviewed_match
                record['deadline_control']['server_timeouts_reflected']=reviewed_match if variant=='REVIEWED' else None
                if not identity_ok:record['outcome']='IDENTITY_UNEXPECTED'
                else:verified=True
        except MatrixStop:
            raise
        except (KeyboardInterrupt,SystemExit):
            raise
        except DeadlineExceeded:
            # a statement (or connect) outlived the CLIENT-side deadline, whatever the server timeouts are: cancel, close, record and stop everything
            record['deadline_control'].update(exceeded=True,abandon=abandon(connection) if connection is not None else dict(cancel_requested=False,client_closed=None))
            self.stopped='ENTRY_DEADLINE_EXCEEDED';record['outcome']='STOPPED_DURING_ENTRY'
            raise MatrixStop('ENTRY_DEADLINE_EXCEEDED') from None
        except (Stop,Denied):
            self.stopped='DEADLINE_OR_BUDGET_DENIAL';record['outcome']='STOPPED_DURING_ENTRY'
            raise MatrixStop('DEADLINE_OR_BUDGET_DENIAL') from None
        except BaseException as exc:
            failure=safe_failure(exc,'DRIVER_CONNECT' if connection is None else 'EXECUTION')
            exc.__context__=None;exc.__cause__=None
        finally:
            close_error=False
            if connection is not None:
                try:connection.close()
                except BaseException:close_error=True
            ended=self.clock()
            closed=(connection is None) or (not close_error and bool(getattr(connection,'closed',False)))
            leaked=len(self.resources()['socket_fds']-before)
            finished=(failure or {}).get('failed_native_connection_finished',False)
            record['connection_closure']=dict(status='CLOSED' if closed and leaked==0 else 'UNCERTAIN',connection_object_closed=closed,new_owned_sockets=leaked,
                                              failed_native_handle_finished=finished if connection is None and failure else None)
            record['elapsed_seconds']=round(ended-began,3);record['identity_statements']=statement_count
            self.last_closed=ended
            if self.stopped and record['outcome']=='ATTEMPTING':record['outcome']='STOPPED_DURING_ENTRY'
        if record['connection_closure']['status']!='CLOSED':
            record['outcome']=record['outcome'] if record['outcome']!='ATTEMPTING' else 'CLOSURE_UNCERTAIN'
            runner.emit('matrix_entry_outcome',dict(ordinal=record['ordinal'],outcome=record['outcome']));self.stop('CLOSURE_UNCERTAIN')
        if failure is not None:
            reason=failure.get('reason_code')
            record.update(outcome='FAILED_CLASSIFIED' if reason not in (None,'UNKNOWN') else 'FAILED_UNCLASSIFIED',failure=dict(phase=failure.get('phase'),exception_kind=failure.get('exception_kind'),
                          sqlstate=failure.get('sqlstate'),reason_code=reason,classification_source=failure.get('classification_source'),underlying_cause='UNDETERMINED'))
            runner.emit('matrix_entry_outcome',dict(ordinal=record['ordinal'],outcome=record['outcome'],**record['failure']))
            if reason in SECURITY_CLASS:self.stop('SECURITY_CLASS_FAILURE')
            if reason=='CONNECTION_CAPACITY' and role in self.connected_roles:self.stop('CAPACITY_AFTER_OWN_CONNECTION')      # possible residue of our own previous entry (CONNECTION LIMIT 1) or pooler retention: ambiguous, so a stop
            if record['outcome']=='FAILED_UNCLASSIFIED':self.stop('UNCLASSIFIED_FAILURE')
            if reason not in CONTINUABLE:self.stop('NON_CONTINUABLE_FAILURE')
            return
        if not verified:
            runner.emit('matrix_entry_outcome',dict(ordinal=record['ordinal'],outcome=record['outcome']));self.stop('UNEXPECTED_IDENTITY')
        reflected=record['timeout_check']['reflected_as_requested']
        record['outcome']='CONNECTED_IDENTITY_VERIFIED_OPTIONS_NOT_REFLECTED' if reflected is False else 'CONNECTED_IDENTITY_VERIFIED';self.connected_roles.add(role)
        runner.emit('matrix_entry_outcome',dict(ordinal=record['ordinal'],outcome=record['outcome'],elapsed_seconds=record['elapsed_seconds']))
