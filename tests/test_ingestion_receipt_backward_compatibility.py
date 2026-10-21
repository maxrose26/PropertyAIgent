"""Backward compatibility of the partial-observation change (PR 162) for HISTORICAL receipts and audits: nothing is rewritten, recomputed or reinterpreted.
A pre-change source audit has no page_size on its pages; a stored historical receipt has no window key (the coordinator pops it) and carries durable_archive. Offline."""
import copy
import json

import pytest

from app.ingestion import observation_history as oh
from app.ingestion.ledger import Denied,digest
from tests.test_ingestion_listing_observation import LIMITS,contract,multi_page_audit,single_page_audit,outer,stored,T1,T2,observe

# Golden digest of the `records` of the RECONSTRUCTED 12-reference two-page window (tests/test_ingestion_listing_observation.py::multi_page_audit). PROVENANCE: it was reproduced with the pre-change adapter and window runner
# (master 368e1a6, before PR 162 added `page_size`; no page_size anywhere in the audit) by running that fixture through IdoxListingContract.project; PR 162's adapter gives the same digest for the same audit with page_size
# removed AND with it present. The fixture itself is a reconstruction (see that file), not Bolton's original bytes.
GOLD="17552ee4dc64b29daa3c5f06558862dda7002bcbf4ffcb32c64c13acc432d590"


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


def _stored_receipt(audit):
    receipt=stored(contract(False).project(audit,outer(),LIMITS))
    receipt.pop("window",None);receipt["durable_archive"]=dict(sha256="b"*64,bytes=1,commit="a"*40,path="docs/design/x/capture/source.json",readback_verified=True)
    return receipt


def _per_application(history):
    return {k:[(o["record_digest"],o["source_record_id"],o["observed_at"],o["evidence_kind"]) for o in a["observations"]] for k,a in history["applications"].items()}


def test_history_built_from_a_historical_receipt_and_from_a_current_one_describes_the_applications_identically():
    old=_stored_receipt(historical_audit(multi_page_audit()));new=_stored_receipt(multi_page_audit())
    assert old!=new      # the two receipts differ only by the new page_size evidence, so their whole-receipt digests differ ...
    h_old=oh.append(oh.empty_history(),old,observed_at=T2);h_new=oh.append(oh.empty_history(),new,observed_at=T2)
    assert _per_application(h_old)==_per_application(h_new) and len(_per_application(h_old))==12      # ... but every application's identity, record digest, source id and timestamp are identical
    assert h_old["conflicts"]==h_new["conflicts"]==[] and {k:v["first_observed_at"] for k,v in h_old["applications"].items()}=={k:v["first_observed_at"] for k,v in h_new["applications"].items()}


def test_a_stored_identity_that_differs_from_any_recomputation_is_kept_verbatim_not_replaced():
    receipt=_stored_receipt(historical_audit(multi_page_audit()))
    assert "source_sha256" in receipt
    tampered=copy.deepcopy(receipt);tampered["source_sha256"]="f"*64      # a stored identity that today's code would not produce
    h_a=oh.append(oh.empty_history(),receipt,observed_at=T2);h_b=oh.append(oh.empty_history(),tampered,observed_at=T2)
    ids_a={o["evidence_digest"] for a in h_a["applications"].values() for o in a["observations"]};ids_b={o["evidence_digest"] for a in h_b["applications"].values() for o in a["observations"]}
    assert ids_a=={digest(receipt)} and ids_b=={digest(tampered)} and ids_a!=ids_b      # the history follows the stored value exactly; it never normalises it back to a recomputed one
    assert tampered["source_sha256"]=="f"*64 and _per_application(h_a)==_per_application(h_b)      # and nothing about the applications changes because the stored identity is unusual


def test_linking_a_historical_complete_capture_to_an_observation_does_not_alter_either_and_is_idempotent():
    receipt=_stored_receipt(historical_audit(multi_page_audit()));observation=observe(single_page_audit(4),observed_at=T1)
    base=oh.append(oh.empty_history(),observation);before=(copy.deepcopy(receipt),copy.deepcopy(observation),copy.deepcopy(base))
    once=oh.link_complete_capture(base,receipt,observed_at=T2);twice=oh.link_complete_capture(once,receipt,observed_at=T2)
    assert (receipt,observation,base)==before      # inputs untouched
    assert once==twice and len(once["links"])==4 and all(l["complete_receipt_digest"]==digest(receipt) and l["observation_evidence_digest"]==digest(observation) for l in once["links"])
    assert once["applications"]==base["applications"]      # linking adds links only; the observation history itself is unchanged
