"""Unregistered R0 recovery executable proposal; no dispatch, credentials or writer.

Only the 28 untouched windows are admitted. Existing R0 execution is unchanged.
The executable binding and outer supervisor are proposed, not registered or
authorised for live use.
"""
import os
import math
import re
import time
from datetime import datetime, timezone
from . import finite_acceptance as f
from . import r0_proposal as original

SOURCE_RUN = 38731487848
LIMITS = dict(calls=28, requests=1120, bytes=48_000_000 + 240*1024*1024,
              seconds=1900, output_bytes=20_000_000)


def proposal():
    rows = [dict(r) for r in original.PLAN['rounds'][0]['rows']
            if r['council'] not in {'bolton', 'bury'}]
    return dict(version=1, purpose='UNATTEMPTED_R0_RECOVERY', source_run=SOURCE_RUN,
                source_manifest=original.PLAN_HASH, rows=rows, limits=LIMITS.copy(),
                unresolved_required_window='bury:2026-10-08:2026-10-14',
                bridge_start='2026-10-15', persistence=False, watermark_advance=False,
                publication_coverage='UNKNOWN', latency='UNKNOWN')


PLAN = proposal()
PLAN_HASH = f.digest(PLAN)
WORKFLOW = '.github/workflows/stage4-r0-untouched-recovery-once.yml'
AUTHORITY = 'AUTHORISE_SEVEN_COUNCIL_R0_UNTOUCHED_WINDOW_RECOVERY_ONCE'


def admit(env, sha, manifest_hash):
    """New proposed binding; old R0 authority/context never admits recovery."""
    expected = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent', GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REF='refs/heads/master', GITHUB_SHA=sha, GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF=f'maxrose26/PropertyAIgent/{WORKFLOW}@refs/heads/master',
        GITHUB_RUN_NUMBER='1', GITHUB_RUN_ATTEMPT='1', RECOVERY_AUTHORITY=AUTHORITY)
    if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha)
            or manifest_hash != PLAN_HASH or any(env.get(k) != v for k, v in expected.items())
            or any(k in env for k in ('DATABASE_URL', 'COMMITTEE_DATABASE_URL',
                                      'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'))):
        raise ValueError('RECOVERY_ADMISSION_REJECTED') from None


def resources(row, audit):
    """Certain, finite source accounting; unknown or out-of-bounds stops all."""
    arc = row['council'] in f.ARCUS
    resource = audit if arc else audit.get('resource', {})
    count = resource.get('requests', resource.get('requests_attempted'))
    if arc:
        sizes = [audit.get(k) for k in ('decoded_bytes', 'encoded_bytes', 'outbound_payload_bytes')]
        if any(type(n) is not int or n < 0 for n in sizes):
            return None
        size = max(sizes[:2]) + sizes[2]
    else:
        size = resource.get('received_bytes')
    if (type(count) is not int or type(size) is not int
            or not 0 <= count <= (80 if arc else 10)
            or not 0 <= size <= (20*1024*1024 if arc else 3_000_000)):
        return None
    return count, size


def safety(row, a):
    """Fail closed before treating any gap as local. No source errors continue."""
    arc = row['council'] in f.ARCUS
    if (a.get('persistence') is not False or a.get('failure') is not None
            or a.get('accounting_complete') is False
            or a.get('requested_interval') != [row['start'], row['end']]
            or a.get('date_semantics') != row['semantics']
            or not identities(row, a)):
        return False
    if arc:
        case = 'discovery_' + row['council'] + '_ui_window'
        config = f.dated_config(f.UI_CASES[case], row['start'], row['end'])
        return (a.get('case') == case and a.get('destination') == config.destination
                and a.get('safety_failure') is False and a.get('safety_events') == []
                and a.get('cleanup') == 'CONTEXT_BROWSER_CLOSED'
                and a.get('process_cleanup') == 'CLOSED'
                and type(a.get('live_owned_survivors')) is int and a['live_owned_survivors'] == 0
                and a.get('supervisor_limit_hit') is False
                and type(a.get('supervisor_seconds')) in (int, float)
                and 0 <= a['supervisor_seconds'] <= 45
                and a.get('measured_public_ui_posts') == a.get('public_ui_posts')
                and type(a.get('public_ui_posts')) is int
                and 1 <= a['public_ui_posts'] <= a['requests']
                and a.get('pages') == 1 and type(a.get('navigations')) is int
                and 1 <= a['navigations'] <= 2)
    resource = a.get('resource', {})
    elapsed = resource.get('elapsed_seconds')
    return (a.get('council') == row['council'] and a.get('cleanup') == 'SESSION_BOUNDARY_CLOSED'
            and resource.get('budget_exhaustion') is False
            and type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 45
            and not a.get('safety_failure') and not a.get('safety_events'))


def identities(row, a):
    """Identity safety applies to every child, including count-COMPLETE ones."""
    arc = row['council'] in f.ARCUS
    records = a.get('listing_records' if arc else 'records')
    if not isinstance(records, list):
        return False
    refs, keys = [], []
    for record in records:
        if not isinstance(record, dict):
            return False
        ref = record.get('reference'); key = record.get('source_record_id' if arc else 'source_key')
        if (not isinstance(ref, str) or not ref.strip() or ref != ref.strip()
                or len(ref) > 100 or any(ord(c) < 32 for c in ref)
                or not isinstance(key, str) or not key
                or (not arc and record.get('identity_state') != 'PRESENT_VALUE')):
            return False
        refs.append(ref); keys.append(key)
    if len(set(refs)) != len(refs) or len(set(keys)) != len(keys):
        return False
    return True


def local_gap(row, a):
    """Only missing count/terminal or an ordinary page cap can continue.

    Identity conflicts, source exceptions and unclassified failures remain hard
    stops. Complete child contracts continue to use the original classifier.
    """
    arc = row['council'] in f.ARCUS
    if not identities(row, a):
        return False
    if a.get('applied_interval') != [row['start'], row['end']]:
        return False
    fingerprint = a.get('applied_evidence_sha256')
    if not arc and (not isinstance(fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', fingerprint)
                    or a.get('applied_evidence') not in {'STRICT_REFINE_FORM_ECHO', 'STRICT_ZERO_RESULT_FORM_ECHO'}):
        return False
    # Do not silently reinterpret an arbitrary listing_failure or exception.
    if a.get('listing_failure') is not None:
        return False
    pages = a.get('listing_segments' if arc else 'pages')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 6:
        return False
    return (a.get('enumeration_evidence') in {'TOTAL_UNKNOWN', 'PAGE_CAP'}
            or a.get('capped') is True)


def execute(plan, expected_hash, *, reader, clock=time.monotonic):
    """Fixed-plan execution API; source use requires separate registered authority."""
    if plan != PLAN or expected_hash != PLAN_HASH:
        raise ValueError('RECOVERY_MANIFEST_REJECTED')
    if any(k in os.environ for k in ('DATABASE_URL', 'COMMITTEE_DATABASE_URL',
                                    'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')):
        raise ValueError('CREDENTIAL_CONTEXT_REJECTED')
    started = clock(); results = []; requests = size = 0; stop = None; certain = True
    for row in plan['rows']:
        arc = row['council'] in f.ARCUS
        if (requests + (80 if arc else 10) > LIMITS['requests']
                or size + (20*1024*1024 if arc else 3_000_000) > LIMITS['bytes']
                or clock() - started + 55 > LIMITS['seconds']):
            stop = 'ROUND_BUDGET'; break
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            a = dict(reader(row))
            a['primary_observation'] = dict(started_at=stamp, ended_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            certain = False
            results.append(dict(window=row, enumeration_completeness='FAILED', completeness='FAILED', reason='SOURCE_EXCEPTION'))
            stop = 'SOURCE_EXCEPTION'; break
        cost = resources(row, a)
        if cost is None:
            certain = False
            results.append(dict(window=row, enumeration_completeness='UNKNOWN', completeness='UNKNOWN', reason='RESOURCE_ACCOUNTING'))
            stop = 'RESOURCE_ACCOUNTING'; break
        requests += cost[0]; size += cost[1]
        if a.get('accounting_complete') is False:
            certain = False
        state = f.classify(row, a)
        safe = safety(row, a)
        # Safety dominates even an apparently COMPLETE child.
        if not safe:
            state = 'FAILED'
        local = safe and state != 'COMPLETE' and local_gap(row, a)
        results.append(dict(window=row, source=a, enumeration_completeness=state,
                            completeness='UNKNOWN' if state == 'COMPLETE' else state,
                            safe_local_gap=local))
        if not safe or (state != 'COMPLETE' and not local):
            stop = 'SAFETY_OR_UNCLASSIFIED_FAILURE'; break
    if stop is None and clock() - started > LIMITS['seconds']:
        stop = 'ROUND_DEADLINE'
    result = dict(manifest_sha256=PLAN_HASH, results=results,
                  not_attempted=plan['rows'][len(results):], stop_reason=stop,
                  enumeration_completeness='COMPLETE' if stop is None and all(
                      x['enumeration_completeness'] == 'COMPLETE' for x in results) else 'INCOMPLETE',
                  # Prior Bury gap alone prevents parent R0 coverage COMPLETE.
                  completeness='INCOMPLETE', source_contract_qualified=False,
                  accounting_complete=certain, requests=requests, bytes=size,
                  persistence=False, completed_through_advanced=False)
    import json
    if len(json.dumps(result).encode()) > LIMITS['output_bytes']:
        raise ValueError('OUTPUT_LIMIT')
    return result


def supervise(plan, output, *, runner=None):
    """Use existing hard supervisor, selecting only the new fixed worker."""
    if plan != PLAN:
        raise ValueError('RECOVERY_MANIFEST_REJECTED')
    kwargs = {} if runner is None else dict(runner=runner)
    return original.supervise_round(plan, output,
        worker_module='verification.discovery.r0_recovery_proposal', **kwargs)


def main():
    import argparse, hashlib, json, resource, subprocess
    from pathlib import Path
    p = argparse.ArgumentParser()
    p.add_argument('--worker', type=Path); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reviewed-sha'); p.add_argument('--manifest-sha')
    args = p.parse_args()
    if args.worker:
        if args.worker.stat().st_size > 20_000 or args.output.exists():
            raise ValueError('WORKER_FILE_BOUNDARY')
        resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['output_bytes'], LIMITS['output_bytes']))
        plan = json.loads(args.worker.read_bytes())
        result = execute(plan, PLAN_HASH, reader=f.read)
        args.output.write_text(json.dumps(result, sort_keys=True))
        return
    admit(os.environ, args.reviewed_sha, args.manifest_sha)
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() != args.reviewed_sha
            or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()):
        raise ValueError('CHECKOUT_MISMATCH')
    args.output.mkdir(exist_ok=False)
    metadata = dict(sha=args.reviewed_sha, manifest_sha256=PLAN_HASH,
        run_id=os.environ['GITHUB_RUN_ID'], run_number=1, attempt=1,
        started_at=datetime.now(timezone.utc).isoformat(), persistence=False,
        publication_coverage='UNKNOWN', latency='UNKNOWN',
        code_hashes={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            Path(__file__), Path(original.__file__), Path(f.__file__),
            Path(__file__).with_name('arcus_ui_config.py'), Path(__file__).with_name('idox_window.py'))})
    (args.output/'execution.json').write_text(json.dumps(metadata, sort_keys=True))
    supervise(PLAN, args.output/'round.json')
    metadata['ended_at'] = datetime.now(timezone.utc).isoformat()
    (args.output/'execution.json').write_text(json.dumps(metadata, sort_keys=True))


if __name__ == '__main__':
    main()
