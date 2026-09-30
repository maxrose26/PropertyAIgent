"""Report accepted baseline exceptions explicitly; never call pytest fully passing."""
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MODULE = 'tests.test_pr2_final_amendment_migration_and_intelligence_processing'
EXPECTED = {f'{MODULE}.{name}' for name in (
    'test_process_intelligence_backlog_selects_only_outstanding_applications',
    'test_process_intelligence_backlog_enforces_extraction_limit_across_councils',
    'test_process_intelligence_backlog_one_failure_does_not_corrupt_remaining_work',
    'test_process_intelligence_backlog_workload_is_bounded_not_unlimited',
)}
MESSAGE = 'RuntimeError: OPENAI_API_KEY not set in .env'
REQUIRED = {
 'test_postgres_migration_and_unique_key_when_disposable_server_available',
 'test_actual_inherited_lock_and_cleanup',
 'test_actual_supervisor_death_surviving_child_holds_lock',
 'test_real_navigation_deadline_cleanup_then_subsequent_work',
 'test_real_document_recycling_then_evidence_refresh',
 'test_real_browser_descendant_cleanup_on_supervised_failure',
 'test_real_supervisor_death_with_browser_child',
 'test_real_browser_cleanup_when_persistence_blocks',
 'test_pg_transaction_bounds_rollback_replacement_and_orm',
 'test_pg_real_timeout_retry_and_subsequent_work',
 'test_pg_bound_verification_failure_invalidates_connection',
 'test_pg_exact_migration_first_repeat_and_no_data_updates',
 'test_pg_exact_migration_rolls_back_both_additions',
 'test_pg_exact_migration_rejects_unexpected_drift',
 'test_pg_exact_migration_rejects_wrong_existing_definition',
 'test_production_contract_remains_unverified',
 'test_offline_verified_scheduled_admission',
 'test_only_verified_scheduler_successor_can_recover',
}

def read_suite(folder, name):
    root = ET.parse(folder / f'{name}.xml').getroot()
    cases = list(root.iter('testcase'))
    failures, passed, skipped, errors = {}, set(), [], []
    for case in cases:
        key = case.get('classname', '') + '.' + case.get('name', '')
        if case.find('failure') is not None:
            failures[key] = case.find('failure').get('message')
        elif case.find('error') is not None: errors.append(key)
        elif case.find('skipped') is not None: skipped.append(key)
        else: passed.add(key)
    log = (folder / f'{name}.log').read_text()
    if not re.search(r'\b1 deselected\b', log):
        raise ValueError(f'{name}: expected explicit one-test deselection')
    if not cases or errors or skipped:
        raise ValueError(f'{name}: missing tests, errors={errors}, skips={skipped}')
    if set(failures) != EXPECTED or any(v != MESSAGE for v in failures.values()):
        raise ValueError(f'{name}: unexpected failures {failures}')
    return passed, failures

def assess(folder):
    candidate, failures = read_suite(folder, 'candidate')
    baseline, _ = read_suite(folder, 'baseline')
    # One intentional behaviour correction replaced the old success assertion.
    retired = 'tests.test_daily_discovery_portal_resilience.test_no_run_health_line_falls_back_to_success'
    replacement = 'tests.test_daily_discovery_portal_resilience.test_no_run_health_line_is_partial_with_process_failure'
    if replacement not in candidate or not (baseline - {retired}) <= candidate:
        raise ValueError('Baseline passing cases missing/failing in candidate')
    if len(candidate) < 351 or len(baseline) < 282:
        raise ValueError('Unexpected reduction from accepted suite coverage')
    names = {key.rsplit('.', 1)[-1] for key in candidate}
    if not REQUIRED <= names:
        raise ValueError(f'Required integration cases missing: {REQUIRED - names}')
    blocked = [key for key in candidate if '.test_independent_watchdog_bounds_blocked_persistence[' in key]
    if len(blocked) != 5:
        raise ValueError('Expected all five blocked-persistence cases to pass')
    result = {'candidate_passed': len(candidate), 'baseline_passed': len(baseline),
              'failed_each': len(failures), 'skipped_each': 0, 'deselected_each': 1,
              'accepted_failures': sorted(failures),
              'excluded_test': 'page_recycling_keeps_renderer_rss_flat_across_navigations',
              'assessment': 'No new regression against accepted exceptions; NOT a fully passing suite or release approval'}
    return result

if __name__ == '__main__':
    try:
        print(json.dumps(assess(Path(sys.argv[1])), indent=2))
    except (OSError, ValueError, ET.ParseError) as error:
        sys.exit(f'Verification assessment failed: {error}')
