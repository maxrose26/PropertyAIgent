"""The kernel memory-scope CI steps keep EXACTLY their assertions and now print what they observed (docs/design/ci/kernel-memory-failures.md). Offline: the helper runs under the SAME shell options as a
GitHub `run:` step (bash --noprofile --norc -eo pipefail) against fake sudo/systemctl/journalctl/dmesg/free executables on PATH, so the real `timeout` and the real error behaviour are exercised.
No kernel, cgroup or systemd is touched."""
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'verification/ingestion_storage/ci_scope_diagnostics.sh'
WORKFLOW=ROOT/'.github/workflows/stage4-discovery-offline.yml'
UNITS=('propertyaigent-storage-memory-20261017','propertyaigent-operational-cleanup-timing-20261018','propertyaigent-operational-once')
CI_SHELL=['bash','--noprofile','--norc','-eo','pipefail','-c']      # what GitHub runs for `run:` with the default bash shell

FAKES={
 'sudo':'exec "$@"',
 'sleep':'exit 0',      # the helper's settle waits; the hang fakes below call /bin/sleep directly
 'free':'[ -n "$FAKE_HANG_FREE" ] && exec /bin/sleep 30; echo "fake free"; exit "${FAKE_FREE_STATUS:-0}"',
 'dmesg':'[ -n "$FAKE_HANG_DMESG" ] && exec /bin/sleep 30; echo "fake dmesg"; exit "${FAKE_DMESG_STATUS:-0}"',
 'journalctl':'[ -n "$FAKE_HANG_JOURNAL" ] && exec /bin/sleep 30; echo "fake oom line"; exit "${FAKE_JOURNAL_STATUS:-0}"',
 'systemctl':r'''
case "$1" in
  reset-failed) echo "RESET $*" >> "$LOG"; exit 0;;
  show)
    prop=""; for a in "$@"; do case "$a" in Result|ControlGroup) prop=$a;; esac; done
    if [ -n "$FAKE_HANG_SHOW" ] && { [ -z "$FAKE_HANG_PROP" ] || [ "$FAKE_HANG_PROP" = "$prop" ]; }; then exec /bin/sleep 30; fi
    case " $FAKE_FAIL_PROPS " in *" $prop "*) [ -n "$prop" ] && exit "${FAKE_SHOW_STATUS:-1}";; esac
    if [ -n "$FAKE_FAIL_ALL_SHOW" ]; then exit "${FAKE_SHOW_STATUS:-1}"; fi
    case "$prop" in
      Result) echo "$FAKE_RESULT";;
      ControlGroup) echo "$FAKE_CG";;
      *) echo "LoadState=loaded"; echo "Result=$FAKE_RESULT"; echo "ControlGroup=$FAKE_CG";;
    esac;;
esac''',
}


@pytest.fixture
def fakes(tmp_path):
    bindir=tmp_path/'bin';bindir.mkdir()
    for name,body in FAKES.items():
        f=bindir/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(f.stat().st_mode|stat.S_IXUSR)
    return bindir


def run(fakes,harness,tmp_path,**env):
    log=tmp_path/'log';log.write_text('')
    full=dict(os.environ,PATH=str(fakes)+os.pathsep+os.environ['PATH'],HELPER=str(HELPER),LOG=str(log),DIAG_TIMEOUT_SECONDS='1')
    for k in [k for k in full if k.startswith('FAKE_')]:del full[k]
    full.update({k:str(v) for k,v in env.items()})
    start=time.monotonic()
    done=subprocess.run(CI_SHELL+['source "$HELPER"; '+harness],env=full,capture_output=True,text=True,timeout=120)
    return done,log.read_text(),time.monotonic()-start


def test_the_helper_parses_and_defines_the_diagnostic_functions():
    assert subprocess.run(['bash','-n',str(HELPER)]).returncode==0
    text=HELPER.read_text()
    for name in ('bounded','observe','scope_report','kernel_report','expect_equal','settle_report','read_scope_property','assert_killed_scope'):assert name+'(){' in text
    assert 'continue-on-error' not in text      # nothing in the assertion path is made optional
    assert text.split('assert_killed_scope(){')[1].count('|| true')==0


def test_the_assertions_are_unchanged_a_killed_scope_with_an_empty_control_group_passes_and_is_reset(fakes,tmp_path):
    done,log,_=run(fakes,'assert_killed_scope propertyaigent-test 137',tmp_path,FAKE_RESULT='oom-kill',FAKE_CG='')
    assert done.returncode==0 and "ok: systemd Result = 'oom-kill'" in done.stdout and "ok: ControlGroup after the kill = ''" in done.stdout and 'RESET reset-failed propertyaigent-test.scope' in log


@pytest.mark.parametrize('result,cg,exit_status,expect',[
    ('success','',137,"expected='oom-kill' observed='success'"),
    ('oom-kill','/system.slice/propertyaigent-test.scope',137,"observed='/system.slice/propertyaigent-test.scope'"),
    ('oom-kill','',0,'expected to fail (be killed) but exited 0')])
def test_every_unmet_assertion_still_fails_with_status_1_prints_the_observed_value_and_looks_again_after_two_and_five_seconds(fakes,result,cg,exit_status,expect,tmp_path):
    done,log,_=run(fakes,'assert_killed_scope propertyaigent-test %d; echo NOT_REACHED'%exit_status,tmp_path,FAKE_RESULT=result,FAKE_CG=cg)
    assert done.returncode==1 and 'NOT_REACHED' not in done.stdout and expect in done.stdout and 'RESET' not in log      # the original `test` status, and no reset-failed
    for phase in ('failure+0s','failure+2s','failure+5s'):assert phase in done.stdout
    assert 'scope report' in done.stdout and 'kernel messages' in done.stdout


def test_a_failing_systemctl_show_for_Result_is_reported_not_fatal_and_the_assertion_fails_with_status_1_after_the_full_report(fakes,tmp_path):
    done,log,_=run(fakes,'assert_killed_scope propertyaigent-test 137; echo NOT_REACHED',tmp_path,FAKE_RESULT='oom-kill',FAKE_CG='',FAKE_FAIL_PROPS='Result',FAKE_SHOW_STATUS=3)
    assert done.returncode==1 and 'NOT_REACHED' not in done.stdout      # exactly the original: an empty observation is not oom-kill
    assert "ended with status 3" in done.stdout and "expected='oom-kill' observed=''" in done.stdout
    for phase in ('failure+0s','failure+2s','failure+5s'):assert phase in done.stdout      # the report was NOT cut short by -e
    assert 'RESET' not in log


def test_a_failing_systemctl_show_for_ControlGroup_is_judged_on_its_output_exactly_as_the_original_test_was(fakes,tmp_path):
    done,log,_=run(fakes,'assert_killed_scope propertyaigent-test 137',tmp_path,FAKE_RESULT='oom-kill',FAKE_CG='/not/read',FAKE_FAIL_PROPS='ControlGroup',FAKE_SHOW_STATUS=1)
    assert done.returncode==0 and "ended with status 1" in done.stdout and "ok: ControlGroup after the kill = ''" in done.stdout and 'RESET' in log      # test -z "$(failing)" passed before as well


def test_every_diagnostic_survives_failure_and_the_reports_never_abort_under_errexit_and_pipefail(fakes,tmp_path):
    done,_,_=run(fakes,'scope_report propertyaigent-test; kernel_report; settle_report propertyaigent-test; echo REACHED_END',tmp_path,
                 FAKE_RESULT='x',FAKE_CG='',FAKE_FAIL_ALL_SHOW=1,FAKE_SHOW_STATUS=7,FAKE_JOURNAL_STATUS=5,FAKE_DMESG_STATUS=6,FAKE_FREE_STATUS=8)
    assert done.returncode==0 and 'REACHED_END' in done.stdout
    for status in ('status 7','status 5','status 6','status 8'):assert status in done.stdout


def test_every_diagnostic_command_is_bounded_a_hanging_one_is_cut_off_and_reported(fakes,tmp_path):
    done,_,elapsed=run(fakes,'kernel_report; echo REACHED_END',tmp_path,FAKE_HANG_JOURNAL=1,FAKE_HANG_DMESG=1,FAKE_HANG_FREE=1,DIAG_TIMEOUT_SECONDS=1)
    assert done.returncode==0 and 'REACHED_END' in done.stdout and elapsed<30      # three 30 s hangs would otherwise take 90 s
    assert done.stdout.count('124')>=3


def test_a_hanging_systemctl_show_in_the_assertion_is_bounded_and_the_assertion_still_fails_with_status_1(fakes,tmp_path):
    done,log,elapsed=run(fakes,'assert_killed_scope propertyaigent-test 137; echo NOT_REACHED',tmp_path,FAKE_RESULT='oom-kill',FAKE_CG='',FAKE_HANG_SHOW=1,FAKE_HANG_PROP='Result',DIAG_TIMEOUT_SECONDS=1)
    assert done.returncode==1 and 'NOT_REACHED' not in done.stdout and 'status 124' in done.stdout and elapsed<60 and 'RESET' not in log


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
