"""The screening-v3 SUCCESSOR attempt (after the interrupted first attempt): which single-use identifiers were replaced and which were not, the first attempt's audit bound as a predecessor, the one-terminal progress messages and where
the owner code prints them, the safe-cancellation wording, and the absence of any automatic dispatch. Offline; no database, no network."""
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip('resource')

from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import policy_screening_v3 as p

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'docs/design/ingestion-screening-v3-activation-20261030'
RUNNER = (ROOT / 'verification/ingestion_storage/operational_runner.py').read_bytes().decode('utf-8').replace('\r\n', '\n')
SCRIPT = (DIR / 'owner-run-screening.sh').read_bytes().decode('utf-8').replace('\r\n', '\n')


def test_only_the_consumed_namespace_is_replaced_and_everything_else_is_exactly_as_approved():
    assert orr.SV3_ATTEMPT1_STATE == 'operational-bolton-screening-v3-retained-once-20261030' and orr.SV3_STATE == 'operational-bolton-screening-v3-retained-successor-once-20261030'
    assert orr.SV3_STATE != orr.SV3_ATTEMPT1_STATE and orr.SV3_STATE not in (orr.SV3_POLICY_STATE, orr.WINDOW_STATE)
    # the database allowance was never registered, so its name, the policy that admits it and the hosted/evidence identifiers are unchanged
    assert orr.SV3_NAME == p.NAME == 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN'
    assert orr.SV3_HOSTED_AUTHORITY == 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_HOSTED_ONCE_20261030'
    assert orr.SV3_EVIDENCE_DIRECTORY == 'docs/design/ingestion-operational-execution-bolton-screening-v3-retained-20261030'
    assert orr.SV3_WORKFLOW == '.github/workflows/stage4-screening-v3-retained-once.yml' and orr.SV3_MANIFEST_PATH == 'docs/design/ingestion-screening-v3-activation-20261030/MANIFEST.json'
    assert (orr.SV3_BINDING['execution_deadline_seconds'], orr.SV3_BINDING['cleanup_reserve_seconds'], orr.SV3_BINDING['grant_lifetime_seconds'], orr.SV3_BINDING['ready_wait_seconds']) == (600, 300, 900, 1800)
    assert orr.SV3_OWNER_LIMITS == dict(connections=(10, 12), commands=(96, 116, 132)) and orr.SV3_POLICY_OWNER_LIMITS == dict(connections=(4, 5), commands=(44, 52, 60))


def test_the_interrupted_first_attempts_audit_is_bound_as_a_predecessor_and_pinned_by_the_script():
    audit = orr.SV3_ATTEMPT1_AUDIT
    assert orr.SV3_PREDECESSOR['interrupted_attempt'] == audit and audit['state_directory'] == orr.SV3_ATTEMPT1_STATE
    assert re.fullmatch(r'[0-9a-f]{64}', audit['events_sha256']) and re.fullmatch(r'[0-9a-f]{64}', audit['final_result_sha256'])
    assert audit['outcome'] == 'STOPPED_IN_READY_WAIT_NO_AUTHORITY_ISSUED_NO_HOSTED_DISPATCH'
    for name, digest in (('events.jsonl', audit['events_sha256']), ('final-result.json', audit['final_result_sha256'])):
        assert digest + ' "$STATE_ROOT/' + orr.SV3_ATTEMPT1_STATE + '/' + name + '"' in SCRIPT      # the script refuses unless the preserved evidence is exactly as archived
    assert 'STATE_DIRECTORY=' + orr.SV3_STATE in SCRIPT and not re.search(r'rm', SCRIPT.replace('rm -f "$EVIDENCE_HEAD_FILE"', ''))      # the first attempt's evidence is never touched


# ---------------------------------------------------------------------------------------------- the one-terminal messages
STAGES = ['CREDENTIAL_ACCEPTED', 'RETAINED_VERIFIED', 'READY_FOR_DISPATCH', 'WAITING_FOR_HOSTED', 'AUTHORITY_REGISTERED', 'REVOCATION_AND_CLEANUP', 'FINAL_RESULT']


def test_the_seven_numbered_messages_exist_in_order_and_are_secret_free():
    texts = orr.SV3_OPERATOR_TEXT
    assert [texts[s][:5] for s in STAGES] == ['[1/7]', '[2/7]', '[3/7]', '[4/7]', '[5/7]', '[6/7]', '[7/7]']
    for stage, text in texts.items():
        for forbidden in ('postgres', 'password', 'secret', 'token', 'DATABASE_URL', 'sslmode'):
            assert forbidden.lower() not in text.lower(), (stage, forbidden)
    ready = texts['READY_FOR_DISPATCH']
    assert 'READY FOR HOSTED DISPATCH' in ready and 'Paste this whole message into the Claude chat' in ready and 'Claude will dispatch the hosted job ONCE' in ready
    assert 'Ctrl-C ends this attempt safely' in ready and 'Waiting is expected' in ready and 'OUTSIDE the grant lifetime' in ready and 'Do not dispatch the workflow yourself unless Claude hands that to you' in ready


def test_announce_records_the_event_then_prints_and_formats_only_reviewed_fields():
    events, lines = [], []
    orr.announce(lambda name, payload: events.append((name, payload)), lines.append, 'RETAINED_VERIFIED', orr.SV3_OPERATOR_TEXT['RETAINED_VERIFIED'])
    assert events == [('operator_progress', {'stage': 'RETAINED_VERIFIED'})] and lines == [orr.SV3_OPERATOR_TEXT['RETAINED_VERIFIED']]
    moment = datetime(2026, 10, 22, 10, 30, tzinfo=timezone.utc)
    assert orr.clock_text(moment) == '10:30:00 UTC / 11:30:00 BST'      # UTC and UK-local
    sample = orr.SV3_OPERATOR_TEXT['READY_FOR_DISPATCH'].format(workflow='stage4-screening-v3-retained-once.yml', sha='a' * 40, head='b' * 40, hosted_authority=orr.SV3_HOSTED_AUTHORITY, deadline=orr.clock_text(moment), minutes=30)
    assert 'reviewed_sha=' + 'a' * 40 in sample and 'evidence_head=' + 'b' * 40 in sample and 'at most 30 minutes' in sample
    final = orr.final_result_text(dict(status='X', cleanup='CLOSED', authority_invalidation='NOT_REQUIRED_NO_AUTHORITY'))
    assert 'status=X' in final and 'cleanup=CLOSED' in final and orr.SV3_STATE in final and 'screening=not started' in final


def test_the_messages_are_printed_at_the_real_stages_and_the_dispatch_message_only_after_every_check():
    pipeline = RUNNER[RUNNER.index('Owner side of the screening-only v3 pipeline'):RUNNER.index('    def form_probe')]
    order = ["self.owner.pipeline_readback(expected,label='BEFORE_ANY_GRANT')", 'verify_world(rows,receipt);verify_no_v3_rows(rows,receipt,rule)', "self.emit('sv3_retained_world_verified'", "self.announce('RETAINED_VERIFIED')",
             'self.require_evidence_anchor(head)', "raise Uncertain('EVIDENCE_DIRECTORY_NOT_FRESH')", "self.operation_phase='SV3_AWAIT_HOSTED_READY'", "self.announce('READY_FOR_DISPATCH'", "self.announce('WAITING_FOR_HOSTED'",
             "self.await_any(('hosted-ready/ready.json',)", "'HOSTED_READY_BINDING'", 'self.owner.register(batches3', "self.github.publish({'registered.json'", "self.announce('AUTHORITY_REGISTERED'", "self.operation_phase='SV3_AWAIT_SCREENING'",
             'self.announce_revocation()', "self.operation_phase='SV3_INVALIDATION'", 'self.owner.invalidate_authorities()']
    positions = [pipeline.index(x) for x in order]
    assert positions == sorted(positions) and pipeline.count("self.announce('READY_FOR_DISPATCH'") == 1 and pipeline.count("self.announce('RETAINED_VERIFIED')") == 1
    failed = RUNNER[RUNNER.index('    def failed(self,exc):'):RUNNER.index('    def failed(self,exc):') + 3000]
    assert "if getattr(self,'sv3_mode',False) and self.owner.authorities:self.announce_revocation()" in failed and failed.index('announce_revocation') < failed.index('invalidate_authorities()')      # a failure that finds an authority announces its revocation too
    main = RUNNER[RUNNER.index('def main():'):]
    assert main.index("journal.emit('hidden_input_prechecked'") < main.index("announce(journal.emit,operator_print,'CREDENTIAL_ACCEPTED'") < main.index('result=session(') < main.index('operator_print(final_result_text(result))') < main.index('raise SystemExit(exit_status(result))')


def test_the_wait_loop_reports_the_remaining_time_every_poll_on_a_simulated_clock(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(orr.time, 'monotonic', lambda: clock[0])

    class Github:
        calls = 0

        def call(self, method, path, *args, **kwargs):
            self.calls += 1
            return {'object': {'sha': 'a' * 40}}

        def probe(self, path):
            return None
    runner = orr.Runner.__new__(orr.Runner)
    runner.github = Github()
    runner.r = {'evidence_directory': 'd'}
    runner.check = lambda: None
    runner.stop_requested = lambda: None
    runner.pipeline_sleep = lambda s: clock.__setitem__(0, clock[0] + s)
    remaining = []
    runner.wait_tick = remaining.append
    with pytest.raises(orr.Denied, match='HOSTED_PUBLICATION_WAIT_EXPIRED'):
        runner.await_any(('x.json',), 1800)
    assert remaining == sorted(remaining, reverse=True) and remaining[0] == 1800 - 0 and len(remaining) == 60 and remaining[-1] == 30      # 60 reports; the last poll raises the expiry before reporting
    runner.wait_tick = None      # no heartbeat registered: the loop is unchanged
    clock[0] = 1000.0
    with pytest.raises(orr.Denied):
        runner.await_any(('x.json',), 60)


# ---------------------------------------------------------------------------------------------- cancellation and dispatch responsibility
def test_cancellation_is_explained_as_ending_the_attempt_never_as_forbidden():
    assert 'Ctrl-C ENDS THE ATTEMPT' in SCRIPT and 'Ctrl-C ENDS THIS ATTEMPT' in SCRIPT and 'the owner revokes the allowance before it exits' in SCRIPT
    assert 'Ctrl-C now ends the attempt: the owner revokes the allowance before it exits' in orr.SV3_OPERATOR_TEXT['AUTHORITY_REGISTERED']
    for text in (SCRIPT, *orr.SV3_OPERATOR_TEXT.values()):
        assert not re.search(r'do not (press )?ctrl-?c|must not (press )?ctrl-?c|cannot (stop|cancel)', text, re.I)


def test_a_terminal_that_cannot_be_written_to_never_disrupts_the_run(monkeypatch):
    class Broken:
        def write(self, *a):
            raise BrokenPipeError

        def flush(self):
            raise BrokenPipeError
    monkeypatch.setattr(orr.sys, 'stderr', Broken())
    orr.operator_print('anything')      # swallowed: the message is lost, the revocation and the result are not
    assert 'instant of registration' in SCRIPT and 'in the middle of being registered' in SCRIPT      # the one uncertain window is stated


def test_nothing_in_the_owner_path_dispatches_the_workflow():
    for forbidden in ('workflow run', 'actions/workflows', '/dispatches', 'workflow_dispatch'):
        assert forbidden not in SCRIPT and forbidden not in RUNNER.replace('SV3_WORKFLOW', ''), forbidden
    assert 'Nothing here dispatches the hosted workflow' in SCRIPT and 'Claude dispatches the hosted workflow ONCE' in SCRIPT
    assert not re.search(r' -f \w+=', SCRIPT) and ' --ref ' not in SCRIPT      # no dispatch command line, no fallback in the owner script
    banner = SCRIPT[SCRIPT.index("printf '%s\\n' \\\n  'SCREENING-V3"):]
    assert 'second terminal' not in SCRIPT.lower() and 'ONE terminal' in banner      # the one-terminal handoff
