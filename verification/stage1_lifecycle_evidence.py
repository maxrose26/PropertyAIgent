"""Fail closed when lifecycle execution or its persisted evidence is incomplete."""
import json
from pathlib import Path
import re
import sys

EXPECTED = (['dashboard'] + [f'rerun-{i}' for i in range(18)] +
    ['navigation-' + page for page in (
        '0_Explore', '1_Scheme_Detail', '2_Review_Site_Links', '3_Local_Plan_Sites',
        '3b_Shortlist', '4_Council_Dashboard', '5_Council_Intelligence',
        '6_Council_Intelligence_Detail', '00_Dashboard')] +
    [f'independent-{i}' for i in range(18)] + ['allocation-site-matches', 'stop', 'rerun'])


def validate(evidence, log):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    require(type(evidence.get('baseline')) is int and evidence['baseline'] == 0, 'nonzero baseline')
    snapshots = evidence['snapshots']
    require([s['stage'] for s in snapshots] == EXPECTED, 'incomplete named checkpoint coverage')
    previous = 0
    sessions = 0
    for s in snapshots:
        for field in ('checkout', 'checkin', 'outstanding', 'transactions', 'new_sessions'):
            require(type(s[field]) is int and s[field] >= 0, 'invalid accounting value')
        require(s['checkout'] == s['checkin'] and s['checkout'] >= previous, 'unbalanced accounting')
        require(s['outstanding'] == s['transactions'] == 0, 'retained resource')
        require(s['errors'] == [] and s['new_sessions'] >= 1, 'failed or missing execution')
        previous = s['checkout']
        sessions += s['new_sessions']
    markers = re.findall(r"^PASS (\d+) AppTest checkpoints; (\d+) distinct sessions; \{'checkout': (\d+), 'checkin': (\d+)\}; outstanding=(\d+)$", log, re.M)
    require(markers == [(str(len(EXPECTED)), str(sessions), str(previous), str(previous), '0')], 'missing or inconsistent completion marker')
    return dict(status='PASS', checkpoints=len(snapshots), stages=EXPECTED,
                sessions=sessions, checkout=previous, checkin=previous,
                outstanding=0, transactions=0)


if __name__ == '__main__':
    print(json.dumps(validate(json.loads(Path(sys.argv[1]).read_text()),
                              Path(sys.argv[2]).read_text()), indent=2))
