"""Backward compatibility of the partial-observation change (PR 162) for HISTORICAL receipts and audits: nothing is rewritten, recomputed or reinterpreted.
A pre-change source audit has no page_size on its pages; a stored historical receipt has no window key (the coordinator pops it) and carries durable_archive. Offline."""
import copy
import json

import pytest

from app.ingestion import observation_history as oh
from app.ingestion.ledger import Denied,digest
from tests.test_ingestion_listing_observation import LIMITS,contract,multi_page_audit,single_page_audit,outer,stored,T1,T2,observe

GOLD="17552ee4dc64b29daa3c5f06558862dda7002bcbf4ffcb32c64c13acc432d590"      # records the ORIGINAL adapter produced for the reconstructed 12-reference window


def historical_audit(audit):
    old=json.loads(json.dumps(audit))
    for p in old["pages"]:p.pop("page_size",None)      # exactly the shape every audit had before page_size existed
    return old


def test_a_pre_change_audit_without_page_size_still_projects_to_identical_records_and_receipt_identities():
    current=multi_page_audit();old=historical_audit(current)
    assert "page_size" not in old["pages"][0] and "page_size" in current["pages"][0]
    r_old=contract(False).project(old,outer(),LIMITS);r_new=contract(False).project(current,outer(),LIMITS)
    assert digest(stored(r_old)["records"])==GOLD==digest(stored(r_new)["records"])      # record identities (and so queue item identities) are unaffected
    assert r_old["records"]==r_new["records"] and [p["terminal"] for p in r_old["segments"]]==[p["terminal"] for p in r_new["segments"]]
    assert "page_size" not in r_old["segments"][0]      # the historical receipt is carried as it was: nothing adds a key after the fact


def test_a_historical_audit_cannot_become_an_observation_and_is_not_reinterpreted():
    old=historical_audit(single_page_audit(4))      # an unknown-total audit from before page_size existed
    with pytest.raises(Denied,match="IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE"):contract().observe(old,outer(),LIMITS,observed_at=T1)      # fails closed; the old audit is never "upgraded"
    with pytest.raises(Denied,match="IDOX_WINDOW_BINDING_OR_COMPLETENESS"):contract(False).project(old,outer(),LIMITS)      # and still stops exactly as it did


def test_a_stored_historical_receipt_is_accepted_by_the_history_without_being_changed_or_re_identified():
    receipt=stored(contract(False).project(historical_audit(multi_page_audit()),outer(),LIMITS))
    receipt.pop("window",None);receipt["durable_archive"]=dict(sha256="b"*64,bytes=1,commit="a"*40,path="docs/design/x/capture/source.json",readback_verified=True)      # the stored checkpoint shape
    before=copy.deepcopy(receipt);identity=digest(receipt)
    h=oh.append(oh.empty_history(),receipt,observed_at=T2)
    assert receipt==before and digest(receipt)==identity      # the input was not mutated
    assert {o["evidence_digest"] for a in h["applications"].values() for o in a["observations"]}=={identity}      # the history records the receipt under ITS OWN stored identity
    assert digest(oh.stored(receipt))==identity      # normalising an already-stored receipt is the identity function
    linked=oh.link_complete_capture(oh.append(oh.empty_history(),observe(single_page_audit(4),observed_at=T1)),receipt,observed_at=T2)      # a receipt with no window key links (received semantics assumed only because it is a LISTING_RECEIPT_V1 of a RECEIVED contract)
    assert linked["links"] and all(l["complete_receipt_digest"]==identity for l in linked["links"])


def test_the_new_code_never_recomputes_a_stored_identity():
    import inspect
    from app.ingestion import observation_history as module
    source=inspect.getsource(module)
    assert "source_sha256" not in source and "capture_sha256" not in source      # the history never touches the identities the ledger already holds
