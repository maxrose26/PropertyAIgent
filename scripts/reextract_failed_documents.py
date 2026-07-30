"""One-off recovery pass: re-attempt text extraction for every Document row
that previously failed (text_extracted=False), now that the multiprocessing
deadlock in extract_document_text has been fixed (see pdf_text.py - a
document producing a moderately large result would deadlock and silently
return "" after burning the full timeout, indistinguishable from a genuine
extraction failure). Local files only, no network calls.

Usage:
    python -m scripts.reextract_failed_documents
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.db.models import Document
from app.db.session import get_session, init_db
from app.extraction.pdf_text import clean_document_text, extract_document_text


def main() -> None:
    init_db()
    session = get_session()

    failed = session.execute(
        select(Document).where(Document.text_extracted == False, Document.local_path.is_not(None))  # noqa: E712
    ).scalars().all()
    print(f"[reextract] {len(failed)} previously-failed documents with a local file to retry")

    recovered = 0
    still_failed = 0
    missing_file = 0
    for doc in failed:
        path = Path(doc.local_path)
        if not path.exists():
            missing_file += 1
            continue
        text = extract_document_text(path)
        if text:
            doc.text_extracted = True
            doc.extracted_text = clean_document_text(text)
            recovered += 1
            print(f"  [reextract] {doc.document_name}: recovered {len(text)} chars")
        else:
            still_failed += 1
        session.commit()

    print(f"\n[reextract] {recovered} recovered, {still_failed} still failed (genuinely unextractable "
          f"or over the size guard), {missing_file} local files no longer present")


if __name__ == "__main__":
    main()
