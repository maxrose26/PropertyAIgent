"""One-off recovery import for Stockport.

Stockport's live portal aggressively rate-limits/blocks a full scrape (confirmed
this session - 53 of 136 detail fetches 429'd in month 1 alone, then every
subsequent month's search page failed to load at all). The user has an older
scrape of the same portal already sitting in a previous project
("Property Acquistion Search AI"), including ~1.3GB of already-downloaded
planning documents. Rather than re-fighting Stockport's rate limiting, import
that recovered data directly - re-running it through *this* project's current
(and considerably more refined) qualifying-filter, document-typing and AI
extraction logic rather than trusting the old prototype's own classifications.

Usage:
    python -m scripts.import_stockport_recovery
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from sqlalchemy import select

from app.db.models import Application, Document
from app.db.session import get_session, init_db
from app.extraction.pdf_text import (
    USEFUL_DOC_TYPES,
    clean_document_text,
    extract_document_text,
    standardise_document_type,
)
from app.scrapers.idox_portal import keyval_from_url
from app.scrapers.unit_filter import qualify

OLD_PROJECT = Path(r"C:\Users\m4xee\Documents\Property\Property Acquistion Search AI")
CSV_PATH = OLD_PROJECT / "stockport_schemes_enriched_classified.csv"
DOCS_DIR = OLD_PROJECT / "downloaded_stockport_priority_documents"

FIELD_MAP = {
    "alternative_reference": "Alternative Reference",
    "address": "Address",
    "proposal": "Proposal",
    "status": "Status",
    "decision": "Decision",
    "decision_issued_date": "Decision Issued Date",
    "application_received": "Application Received",
    "application_validated": "Application Validated",
}


def doc_folder_for(reference: str) -> Path | None:
    folder = DOCS_DIR / reference.replace("/", "_")
    return folder if folder.is_dir() else None


def main() -> None:
    init_db()
    session = get_session()

    with CSV_PATH.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"[import] {len(rows)} rows in recovery CSV")

    batch_id = f"stockport_recovered_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    imported = 0
    skipped_not_qualifying = 0
    skipped_no_reference = 0
    docs_imported = 0

    for row in rows:
        reference = (row.get("Reference") or "").strip()
        if not reference:
            skipped_no_reference += 1
            continue

        proposal = row.get("Proposal") or row.get("raw_result_text") or ""
        result = qualify(proposal, unit_threshold=10)
        if not result.qualifies:
            skipped_not_qualifying += 1
            continue

        existing = session.execute(
            select(Application).where(Application.council_code == "stockport", Application.reference == reference)
        ).scalar_one_or_none()
        if existing is None:
            existing = Application(council_code="stockport", reference=reference)
            session.add(existing)

        for model_field, csv_field in FIELD_MAP.items():
            value = row.get(csv_field)
            if value:
                setattr(existing, model_field, value)

        existing.summary_url = row.get("Summary URL") or None
        existing.further_info_url = row.get("Further Information URL") or None
        existing.documents_url = row.get("Documents Page URL") or None
        existing.keyval = keyval_from_url(existing.summary_url) if existing.summary_url else None
        existing.estimated_unit_count = result.unit_count
        existing.application_category = result.category
        existing.opportunity_classification = result.classification
        existing.scrape_batch_id = batch_id
        if existing.estimated_unit_count is not None:
            existing.unit_confirmation_status = "confirmed_qualifying"

        session.flush()  # need existing.id before adding documents

        folder = doc_folder_for(reference)
        if folder is not None and not existing.documents:
            for path in folder.iterdir():
                if not path.is_file():
                    continue
                doc_type = standardise_document_type(path.name, "")
                if doc_type not in USEFUL_DOC_TYPES:
                    continue
                text = extract_document_text(path)
                session.add(
                    Document(
                        application_id=existing.id,
                        doc_type=doc_type,
                        document_name=path.name,
                        source_url=None,
                        local_path=str(path),
                        text_extracted=bool(text),
                        extracted_text=clean_document_text(text) if text else None,
                        downloaded_at=dt.datetime.now(dt.timezone.utc),
                    )
                )
                docs_imported += 1

        session.commit()
        imported += 1
        print(f"  [import] {reference}: qualifies ({result.unit_count} units est.), "
              f"{'documents found' if folder else 'no documents folder'}")

    print(f"\n[import] {imported} applications imported, {skipped_not_qualifying} skipped (didn't qualify), "
          f"{skipped_no_reference} skipped (no reference), {docs_imported} documents imported")


if __name__ == "__main__":
    main()
