"""Stage 2.5B V8-B: buyer fit for an R1 derived residual subject (specifications/025).

A WRAPPER around the unchanged ``assess_buyer_fit`` (the v8 matcher is not modified for residuals): the residual is evaluated as an ordinary planning-delivery
subject whose scale is the derived residual count, and the result is then capped, explicitly and visibly, at POSSIBLE_FIT. The cap is never achieved through
fake unknown facts: a would-be STRONG_FIT is reported as POSSIBLE_FIT with a stated reason. Only an R1 qualification can be evaluated; R2/R3 have no fit.
"""
from __future__ import annotations

from dataclasses import replace

from app.policy.buyer_matching import (
    AFFORDABLE_STATE_UNKNOWN, POSSIBLE_FIT, STRONG_FIT, BuyerFitAssessment, assess_buyer_fit,
)
from app.reporting.residual_opportunity import LEVEL_R1, R1_CAVEAT

CAP_NOTE = ("Fit is capped at Possible Fit: this is a derived (apparent) residual planning capacity, not a consented, separately evidenced scheme.")


class NotAResidualSubject(ValueError):
    """Only an R1 qualification has a buyer fit."""


def residual_matching_facts(parent_facts, qualification):
    """The parent site's trusted facts with the residual scale substituted. A residual never inherits whole-site affordable evidence (as a phase does not)."""
    if qualification.level != LEVEL_R1 or qualification.residual_assessment is None:
        raise NotAResidualSubject(f"qualification level {qualification.level} has no residual subject")
    return replace(parent_facts, unit_count=qualification.residual_value, count_assessment=qualification.residual_assessment, affordable_unit_count=None,
                   affordable_percentage=None, affordable_percentage_trusted=False, whole_site_affordable_state=AFFORDABLE_STATE_UNKNOWN)


def assess_residual_fit(profile, parent_facts, qualification, context=None) -> BuyerFitAssessment:
    facts = residual_matching_facts(parent_facts, qualification)
    assessment = assess_buyer_fit(profile, facts, context=context)
    matches, investigate = list(assessment.matches), list(assessment.investigate)
    classification = assessment.classification
    if classification == STRONG_FIT:
        classification = POSSIBLE_FIT
        matches.append(CAP_NOTE)
    investigate.append(R1_CAVEAT)
    return replace(assessment, classification=classification, matches=matches, investigate=investigate)
