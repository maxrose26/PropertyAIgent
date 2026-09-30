"""Strict catalogue-expression comparison; native catalogue test remains required."""
import pytest
from app.revisit.migration import STAGE_EXPRESSION, validate_stage_check


def row(**changes):
    return dict(dict(name='ck_revisit_stage',expression='('+STAGE_EXPRESSION+')',validated=True,no_inherit=False),**changes)


def test_only_outer_expression_parentheses_ignored():
    validate_stage_check([row()])
    validate_stage_check([row(expression=STAGE_EXPRESSION)])


@pytest.mark.parametrize('changes', [
    {'expression':STAGE_EXPRESSION.replace("'relationships'", "'anything'")},
    {'expression':STAGE_EXPRESSION+' OR true'},
    {'validated':False}, {'no_inherit':True}, {'name':'other_constraint'},
])
def test_altered_or_unvalidated_definition_rejected(changes):
    with pytest.raises(RuntimeError,match='stage check drift'):
        validate_stage_check([row(**changes)])


def test_missing_or_extra_checks_rejected():
    for rows in ([],[row(),row()]):
        with pytest.raises(RuntimeError,match='stage check drift'):validate_stage_check(rows)
