"""One-off import of Stockport data already gathered in the earlier prototype
project ("Property Acquistion Search AI"), reused because the live Idox
scraper for Stockport has been confirmed to fail at the portal level (30
months in a row timed out during the 2-year backfill - see project history),
independent of the request-delay fix already applied for its earlier
rate-limiting problem.

Two source files, both under the old project's folder:
- stockport_schemes_enriched_classified.csv: ~125 candidate applications with
  portal metadata (address/proposal/decision/dates), spanning roughly
  2020-2026 decisions.
- stockport_planning_document_text.csv: real extracted document text for a
  subset of those references (168 rows, 70 distinct references extracted
  cleanly via pymupdf - the rest are corrupted RTF-mislabelled PDF binary and
  are skipped).

Re-qualifies every row through the CURRENT app.scrapers.unit_filter.qualify()
rather than trusting the old prototype's own ad-hoc AI classification columns
(deliberately - this codebase's qualification logic has been fixed several
times since that prototype was last touched), then reuses the live pipeline's
own stages (stage_link_sites / stage_extraction / stage_geocode_sites /
stage_check_build_status) so this data ends up looking exactly like a normal
scrape would have produced, not a special-cased import path.

Idempotent: Application has a (council_code, reference) unique constraint, so
re-running this - or a future working Stockport scraper re-discovering the
same references - upserts rather than duplicates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select

load_dotenv()

from app.config import load_councils
from app.db.models import Application, Document
from app.db.session import get_session
from app.extraction.pdf_text import standardise_document_type
from app.pipeline.run_weekly import (
    ensure_council_row,
    stage_check_build_status,
    stage_extraction,
    stage_geocode_sites,
    stage_link_sites,
)
from app.scrapers.unit_filter import classify_application_category, qualify

OLD_PROJECT = Path(r"C:\Users\m4xee\Documents\Property\Property Acquistion Search AI")
APPLICATIONS_CSV = OLD_PROJECT / "stockport_schemes_enriched_classified.csv"
DOCUMENT_TEXT_CSV = OLD_PROJECT / "stockport_planning_document_text.csv"

COUNCIL_CODE = "stockport"


def import_applications(session, council) -> list[Application]:
    df = pd.read_csv(APPLICATIONS_CSV)
    df = df[df["Reference"].notna()].copy()
    df["Reference"] = df["Reference"].astype(str)

    imported: list[Application] = []
    skipped_not_qualifying = 0
    skipped_existing = 0

    for _, row in df.iterrows():
        reference = row["Reference"].strip()
        proposal = row.get("Proposal")
        proposal = None if pd.isna(proposal) else str(proposal)

        result = qualify(proposal, unit_threshold=council.unit_threshold)
        if not result.qualifies:
            skipped_not_qualifying += 1
            continue

        existing = session.execute(
            select(Application).where(Application.council_code == COUNCIL_CODE, Application.reference == reference)
        ).scalar_one_or_none()
        if existing is not None:
            skipped_existing += 1
            imported.append(existing)
            continue

        def clean(value):
            return None if pd.isna(value) else str(value)

        app = Application(
            council_code=COUNCIL_CODE,
            reference=reference,
            alternative_reference=clean(row.get("Alternative Reference")),
            address=clean(row.get("Address")),
            proposal=proposal,
            status=clean(row.get("Status")),
            decision=clean(row.get("Decision")),
            decision_issued_date=clean(row.get("Decision Issued Date")),
            application_received=clean(row.get("Application Received")),
            application_validated=clean(row.get("Application Validated")),
            summary_url=clean(row.get("Summary URL")),
            estimated_unit_count=result.unit_count,
            application_category=classify_application_category(proposal),
            opportunity_classification=clean(row.get("Opportunity Classification")),
            # Matches _upsert_scraped_application's own rule: a confident
            # portal-text unit count skips the confirm-units gate; a
            # keyword-only "review" qualification is left None, same as a
            # live scrape would leave it (UNIT_GATE_PASSED treats None as
            # "not yet excluded", so it still reaches extraction below).
            unit_confirmation_status="confirmed_qualifying" if result.unit_count is not None else None,
        )
        session.add(app)
        imported.append(app)

    session.commit()
    print(f"[applications] {len(imported)} qualifying applications available "
          f"({skipped_existing} already existed, {skipped_not_qualifying} did not qualify under current rules)")
    return imported


def import_documents(session, applications: list[Application]) -> int:
    by_reference = {a.reference: a for a in applications}

    df = pd.read_csv(DOCUMENT_TEXT_CSV)
    df = df[df["extraction_status"] == "ok_pymupdf"].copy()
    df["Reference"] = df["Reference"].astype(str)

    added = 0
    for _, row in df.iterrows():
        reference = row["Reference"].strip()
        app = by_reference.get(reference)
        if app is None:
            continue  # document belongs to a reference that didn't qualify / wasn't imported

        text = row.get("extracted_text")
        if pd.isna(text) or not str(text).strip():
            continue

        document_name = str(row.get("document_label") or row.get("filename") or "")
        doc_type = standardise_document_type(document_name, "")

        exists = session.execute(
            select(Document).where(Document.application_id == app.id, Document.document_name == document_name)
        ).scalar_one_or_none()
        if exists is not None:
            continue

        session.add(Document(
            application_id=app.id,
            doc_type=doc_type,
            document_name=document_name,
            local_path=str(row.get("file_path") or ""),
            text_extracted=True,
            extracted_text=str(text),
        ))
        added += 1

    session.commit()
    print(f"[documents] {added} document-text rows imported")
    return added


def main():
    councils = load_councils()
    council = councils[COUNCIL_CODE]

    with get_session() as session:
        ensure_council_row(session, council)

        applications = import_applications(session, council)
        import_documents(session, applications)

        n_linked = stage_link_sites(session, council)
        print(f"[link] {n_linked} applications linked to sites")

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)
            extraction_result = stage_extraction(session, client, council)
            print(f"[extraction] {extraction_result.succeeded} schemes extracted "
                  f"({extraction_result.no_usable_text} no usable text, {extraction_result.failed} failed)")
        else:
            print("[extraction] skipped - OPENAI_API_KEY not set")

        n_geocoded = stage_geocode_sites(session, council)
        print(f"[geocode] {n_geocoded} sites geocoded")

        n_build_status = stage_check_build_status(session, council, os.getenv("EPC_API_KEY"))
        print(f"[build-status] {n_build_status} sites checked")


if __name__ == "__main__":
    main()
