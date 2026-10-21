"""The digit-run stall in app.scrapers.unit_filter.extract_unit_count (and so qualify, rule v1 and rule v3 screening), offline.

Before the fix a run of digits was cubic-time (800 digits ~2.6 s, 1,600 and longer never finished in 20 s) and a long word was quadratic, so unusual planning-description text could stall screening. The fix is two
textual substitutions in UNIT_COUNT_PATTERNS (see the comment in unit_filter.py). These tests (1) prove boundedness END TO END in a child process under a hard timeout, so a regression FAILS the test instead of
hanging CI; (2) prove the counting behaviour of supported wording is unchanged, by pinning the original patterns and comparing old and new on a corpus and on seeded fuzz; (3) pin the one intended change."""
import hashlib
import json
import random
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.scrapers import unit_filter as u

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=json.loads((ROOT/'specifications/035-residential-count-examples.json').read_text(encoding='utf-8'))['examples']

# sha256 of json.dumps(UNIT_COUNT_PATTERNS) on master dddb5dd, before this change (12 patterns)
ORIGINAL_PATTERNS_DIGEST='a964b0665841f38781538663429936fcdca53f607d5970d14d2522c5c9df9a6f'
ORIGINAL_SUBSTITUTIONS=((r'(?<!\d)(\d+)',r'(\d+)'),(r'(?:\w{1,40}[\s-]+){0,3}',r'(?:\w+[\s-]+){0,3}'),(r'\s*(?:(?:comprising|of|for)\s*)?',r'\s*(?:comprising|of|for)?\s*'),(r'\s*(?:\(\s*)?up',r'\s*\(?\s*up'))


def original_patterns():
    out=list(u.UNIT_COUNT_PATTERNS)
    for new,old in ORIGINAL_SUBSTITUTIONS:out=[p.replace(new,old) for p in out]
    return out


def original_extract(text):
    """extract_unit_counts exactly as it was, using the original patterns (the loop body is unchanged by the fix)."""
    normalised=u.normalise_text(text);counts=[]
    for pattern in original_patterns():
        for match in re.finditer(pattern,normalised):
            if u._is_policy_target_context(normalised,match.start(),match.end()):continue
            if u._is_reference_code(normalised,match.start()):continue
            try:value=int(match.group(1).replace(',',''))
            except (ValueError,IndexError):continue
            if value in u.YEAR_LIKE_RANGE:continue
            if 0<value<=u.MAX_PLAUSIBLE_UNITS:counts.append(value)
    for match in re.finditer(u.WORD_UNIT_COUNT_RE,normalised):
        if u._is_policy_target_context(normalised,match.start(),match.end()):continue
        counts.append(u.WORD_TO_NUMBER[match.group(1).lower()])
    return counts


# ------------------------------------------------------------------ the change is exactly the two substitutions
def test_reversing_the_two_substitutions_gives_the_original_patterns_exactly():
    assert len(u.UNIT_COUNT_PATTERNS)==12
    assert hashlib.sha256(json.dumps(original_patterns()).encode()).hexdigest()==ORIGINAL_PATTERNS_DIGEST      # nothing else in any pattern changed
    assert sum(p.count(r'(?<!\d)(\d+)') for p in u.UNIT_COUNT_PATTERNS)>=10 and sum(p.count(r'\w{1,40}') for p in u.UNIT_COUNT_PATTERNS)==1 and sum(p.count('(?:(?:comprising|of|for)') for p in u.UNIT_COUNT_PATTERNS)==1 and sum(p.count(r'(?:\(\s*)?up') for p in u.UNIT_COUNT_PATTERNS)==1      # each substitution applied exactly where intended


# ------------------------------------------------------------------ boundedness, end to end, under a hard timeout
CHILD=textwrap.dedent('''
    import sys,time,json
    sys.path.insert(0,sys.argv[1])
    from app.scrapers import unit_filter as u
    from app.ingestion import listing_screening as ls, count_assessment as ca
    text=json.loads(sys.stdin.read())      # via stdin: a long argument list is refused by Windows
    def row(t):return dict(reference="T/1",fields={"proposal":dict(state="PRESENT_VALUE",value=t,locator="x",truncated=False),"address":dict(state="PRESENT_VALUE",value="1 Test Street",locator="x",truncated=False),"application_type":dict(state="UNKNOWN",value=None,locator="x",truncated=False)})
    steps=[("extract_unit_count",lambda:u.extract_unit_count(text)),("qualify",lambda:u.qualify(text)),("screen_row_v1",lambda:ls.screen_row(row(text))),
           ("screen_row_v3",lambda:ls.screen_row(row(text),rule_version=ls.RULE_V3,unit_threshold=10)),("assess_proposal",lambda:ca.assess_proposal(text))]
    out={}
    for name,fn in steps:
        s=time.monotonic();fn();out[name]=round(time.monotonic()-s,3)
    print(json.dumps(out))
''')
N=8192
ADVERSARIAL={
    'digits_800':'1'*800,'digits_1600':'1'*1600,'digits_8192':'1'*N,'digits_then_flats':'1'*8000+' flats','erection_then_digits':'erection of '+'1'*8000,'build_to_rent_digits':'build to rent '+'9'*8000,
    'number_of_digits':'number of dwellings '+'1'*8000,'units_proposed_digits':'units proposed '+'1'*8000,'up_to_digits':'flats (up to '+'1'*8000+')',
    'comma_digits':'1,'*4096,'dot_digits':'1.'*4096,'newline_digits':'1\n'*4096,'dash_digits':'1-'*4096,'space_digits':'1 '*4096,
    'runs_of_32_then_a':('1'*32+'a')*248,'runs_of_32_then_dash':('1'*32+'-')*248,'runs_of_200_then_x1':('1'*200+'x1')*40,'alnum_token':'a1'*4096,'word_then_alnum':'twelve '+'a1'*4000,
    'number_words_run':'one'*2730,'flats_then_spaces':'flats'+' '*8187,'flats_spaces_digit':'flats'+' '*8186+'1','units_then_spaces':'units'+' '*8187,'ideographic_spaces':'flats'+'\u3000'*8187,'number_of_units_spaces':'number of units'+' '*8177,
    'flats_up_to_spaces':'flats (up to'+' '*8180,'hyphen_run':'12'+'-'*8190,'hyphen_run_flats':'12'+'-'*8187+'flats','btr_many':'btr '*2048,'tab_newline_runs':('1\t\n')*2730,'long_word_then_flats':'12 '+'a'*8000+' flats','hyphenated_words':'12 '+'a-'*4000+'flats'}
PER_STEP_SECONDS=1.5      # CI headroom over a measured worst case of about 0.3 s after the fix; the old code takes 2.6 s at 800 digits and never finishes at 1,600
CHILD_TIMEOUT=15


@pytest.mark.parametrize('name',sorted(ADVERSARIAL))
def test_screening_is_bounded_end_to_end_and_a_regression_fails_rather_than_hangs(name):
    text=ADVERSARIAL[name][:N]
    try:
        done=subprocess.run([sys.executable,'-I','-c',CHILD,str(ROOT)],input=json.dumps(text),capture_output=True,text=True,timeout=CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail('HUNG: %s did not finish within %d s (the digit-run stall has regressed)'%(name,CHILD_TIMEOUT))
    assert done.returncode==0,done.stderr[-400:]
    timings=json.loads(done.stdout.strip().splitlines()[-1])
    slow={k:v for k,v in timings.items() if v>PER_STEP_SECONDS}
    assert not slow,(name,timings)


# ------------------------------------------------------------------ supported wording is unchanged
WORDING=['ERECTION OF 12 DWELLINGS','Erection of 49 self contained apartments','2no. semi-detached 3 bedroom dwellinghouses','48no. affordable dwellings','1 four bed dwelling','1 detached house with garage',
         'Total proposed residential units 102','Number of dwellings: 24','Total units proposed | 24','erection of 5 houses and 5 flats','Conversion of 12 flats into 24 flats','build to rent scheme comprising 150 homes',
         'BTR development of 200 apartments','supported living for 3 adults','residential development (up to 150 dwellings)','flats comprising 30','Erection of 3 blocks comprising 24 apartments','twelve dwellings',
         'PP-14236922 unit sq. metres','21383-thp-u8-xx-dr-a-1021_p03 unit 8 roof plan','a minimum requirement of 26,500 dwellings over the plan period 2022-2039','Erection of 90 dwellings and a hundred-space car park',
         '12 no. 2 storey dwellings','2 x 3 bed houses','4 no. apartment blocks comprising of no. 49 self contained apartments (class c3)']


def test_supported_wording_gives_identical_counts_old_and_new():
    texts=WORDING+[e['proposal'] for e in EXAMPLES]
    assert len(texts)>=85
    for t in texts:assert u.extract_unit_counts(t)==original_extract(t),t
    assert u.extract_unit_count('ERECTION OF 12 DWELLINGS')==12 and u.extract_unit_count('Number of dwellings: 24')==24 and u.extract_unit_count('Erection of 5 houses and 5 flats')==5


def test_digit_runs_near_valid_count_wording_do_not_change_the_valid_count():
    for run in ('1'*13,'1'*30,'9'*60,'12345678901234567890'):
        for t in ('Erection of 12 dwellings, ref '+run,run+' erection of 12 dwellings','Erection of 12 dwellings '+run+' and a car park','erection of '+run+' x 12 dwellings','12 dwellings '+run+' flats'):
            assert u.extract_unit_counts(t)==original_extract(t),(run,t)
    assert 12 in u.extract_unit_counts('Erection of 12 dwellings, ref '+'1'*8000) and 12 in u.extract_unit_counts('1'*8000+' Erection of 12 dwellings')
    assert u.extract_unit_count('1'*8000)is None      # a huge number is still not a unit count


def test_old_and_new_agree_on_seeded_fuzz_with_digit_runs_and_words_up_to_forty_characters():
    rnd=random.Random(20261026)
    atoms=['1','12','7','49','150','1'*14,'1'*30,'9'*38,'x','abc','a1b2','dwellings','flats','house','units','apartment','erection','of','and','no.','2no.','up to','(up to','  ','\n','\t','(',')',',','.','-','/','self contained','residential','number of','total','proposed','adults','comprising','new homes','build to rent','btr','plots','twelve','one','pursuant to','2022-2039','per year','a'*30,'b2'*20]
    compared=skipped=0
    for _ in range(3000):
        t=' '.join(rnd.choice(atoms) for _ in range(rnd.randint(1,24)))
        if rnd.random()<0.3:t=t.replace(' ','',rnd.randint(1,3))
        if re.search(r'\w{41,}',u.normalise_text(t)):skipped+=1;continue      # gluing atoms can build an over-long word: that is the one intended change, pinned below
        compared+=1
        assert u.extract_unit_counts(t)==original_extract(t),t
    assert compared>2000 and skipped<1000      # the comparison really ran on the great majority of cases


def test_the_one_intended_behaviour_change_a_word_longer_than_forty_characters_between_a_count_and_its_noun():
    t='12 '+'a'*41+' flats'
    assert original_extract(t)==[12] and u.extract_unit_counts(t)==[]      # no real planning wording does this; stated, pinned, not silent
    t='12 '+'9'*45+' new homes'      # the same change when the over-long "word" is a digit run
    assert original_extract(t)==[12] and 12 not in u.extract_unit_counts(t)
    t='12 '+'a'*40+' flats'
    assert u.extract_unit_counts(t)==original_extract(t)==[12]      # up to forty characters is unchanged


# ------------------------------------------------------------------ screening results are unchanged
def test_rule_v1_and_the_62_examples_are_unchanged_by_the_fix():
    from app.ingestion import listing_screening as ls
    from tests.test_ingestion_count_assessment import V1_GOLDEN,TEXTS,VARIANTS,row
    from app.ingestion.ledger import digest
    assert digest([ls.screen_row(row(t,**v)) for t in TEXTS for v in VARIANTS])==V1_GOLDEN      # byte-identical to master over 192 results
