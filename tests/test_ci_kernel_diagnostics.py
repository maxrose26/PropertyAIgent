"""The kernel memory-scope CI steps keep EXACTLY their assertions and now print what they observed (docs/design/ci/kernel-memory-failures.md). Offline: the helper runs under bash with stubbed sudo/systemctl;
no kernel, cgroup or systemd is touched."""
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'verification/ingestion_storage/ci_scope_diagnostics.sh'
WORKFLOW=ROOT/'.github/workflows/stage4-discovery-offline.yml'
UNITS=('propertyaigent-storage-memory-20261017','propertyaigent-operational-cleanup-timing-20261018','propertyaigent-operational-once')

HARNESS=r'''
source "$HELPER"
sudo(){ "$@"; }
journalctl(){ :; }; dmesg(){ :; }; sleep(){ :; }; free(){ :; }
systemctl(){
  case "$*" in
    *"-p Result --value"*) echo "$FAKE_RESULT";;
    *"-p ControlGroup --value"*) echo "$FAKE_CG";;
    reset-failed*) echo "RESET $*" >> "$LOG";;
    show*) echo "LoadState=loaded"; echo "Result=$FAKE_RESULT"; echo "ControlGroup=$FAKE_CG";;
  esac
}
assert_killed_scope propertyaigent-test "$EXIT"
'''


def run(result,cg,exit_status,tmp_path):
    log=tmp_path/'log';log.write_text('')
    env=dict(os.environ,HELPER=str(HELPER),FAKE_RESULT=result,FAKE_CG=cg,EXIT=str(exit_status),LOG=str(log))
    done=subprocess.run(['bash','-c',HARNESS],env=env,capture_output=True,text=True,timeout=30)
    return done,log.read_text()


def test_the_helper_parses_and_defines_the_diagnostic_functions():
    assert subprocess.run(['bash','-n',str(HELPER)]).returncode==0
    text=HELPER.read_text()
    for name in ('scope_report','kernel_report','expect_equal','settle_report','assert_killed_scope'):assert name+'(){' in text
    assert 'continue-on-error' not in text and '|| true' not in text.split('assert_killed_scope(){')[1]      # nothing in the assertion path is made optional


def test_the_assertions_are_unchanged_a_killed_scope_with_an_empty_control_group_passes_and_is_reset(tmp_path):
    done,log=run('oom-kill','',137,tmp_path)
    assert done.returncode==0 and "ok: systemd Result = 'oom-kill'" in done.stdout and "ok: ControlGroup after the kill = ''" in done.stdout and 'RESET reset-failed propertyaigent-test.scope' in log


@pytest.mark.parametrize('result,cg,exit_status,expect',[
    ('success','',137,"expected='oom-kill' observed='success'"),
    ('oom-kill','/system.slice/propertyaigent-test.scope',137,"observed='/system.slice/propertyaigent-test.scope'"),
    ('oom-kill','',0,'expected to fail (be killed) but exited 0')])
def test_every_unmet_assertion_still_fails_prints_the_observed_value_and_looks_again_after_two_and_five_seconds(result,cg,exit_status,expect,tmp_path):
    done,log=run(result,cg,exit_status,tmp_path)
    assert done.returncode==1 and expect in done.stdout and 'RESET' not in log      # fails, and does not reset-failed
    for phase in ('failure+0s','failure+2s','failure+5s'):assert phase in done.stdout      # the same observation again, to tell a teardown race from a wrong outcome
    assert 'scope report' in done.stdout and 'kernel messages' in done.stdout


def test_the_three_excess_steps_use_the_helper_with_their_own_unit_and_no_bare_assertion_remains():
    text=WORKFLOW.read_text()
    for unit in UNITS:
        assert 'assert_killed_scope %s "$result"'%unit in text
        assert 'test "$(sudo systemctl show %s.scope -p Result --value)" = oom-kill'%unit not in text      # replaced by the helper, which asserts the same thing and reports
    assert text.count('source verification/ingestion_storage/ci_scope_diagnostics.sh')==4      # three steps plus the failure step
    assert 'sudo systemctl reset-failed' not in text.split('Kernel scope diagnostics')[0].split('Whole-scope excessive memory')[1].split('Existing restricted SQL')[0]      # the reset now lives in the helper after the assertions pass


def test_a_failure_only_diagnostics_step_exists_observes_all_three_units_and_asserts_nothing():
    text=WORKFLOW.read_text()
    step=text.split('Kernel scope diagnostics (on failure only; observation, no assertion)')[1]
    assert 'if: failure()' in step.split('run:')[0]
    for unit in UNITS:assert unit in step
    assert 'scope_report' in step and 'kernel_report' in step and 'assert_' not in step and 'expect_' not in step and 'exit 1' not in step


def test_the_original_expected_values_are_still_in_the_assertion_itself():
    text=HELPER.read_text()
    assert 'expect_equal "systemd Result" "oom-kill"' in text and 'expect_equal "ControlGroup after the kill" ""' in text
