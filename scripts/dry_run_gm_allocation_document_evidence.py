"""GM Allocation <-> Planning Activity document-evidence dry run (Stage 2C, CLI).

READ ONLY. Makes zero database mutations - never sets matched_site_id or
any other LocalPlanSite/Site/Application attribute. Combines Stage 2A's
fuzzy name/address matching (app.policy.allocation_site_dry_run_matching)
with Stage 2C's independent document-evidence layer (app.policy.
allocation_document_evidence) into one combined report, and writes a
machine-readable JSON+CSV artefact (default: data/stage2c_allocation_document_evidence/,
already gitignored - this is a review artefact, not a production
ingestion manifest) alongside a console summary.

    python -m scripts.dry_run_gm_allocation_document_evidence
    python -m scripts.dry_run_gm_allocation_document_evidence --council bolton
    python -m scripts.dry_run_gm_allocation_document_evidence --output-dir C:/tmp/stage2c
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db.models import LocalPlanSite
from app.db.session import get_session, init_db
from app.policy.allocation_document_evidence import (
    DOCUMENT_CONFIRMED_APPLICATION_ONLY,
    DOCUMENT_CONFIRMED_SITE,
    DOCUMENT_CONTRADICTS_FUZZY,
    FUZZY_SUPPORTED_BY_DOCUMENT,
    MULTIPLE_DOCUMENT_SUPPORTED_SITES,
    NO_DOCUMENT_EVIDENCE,
    AllocationEvidenceResult,
    run_document_evidence_dry_run,
)
from app.policy.allocation_site_dry_run_matching import run_dry_run_matching

DEFAULT_OUTPUT_DIR = Path("data") / "stage2c_allocation_document_evidence"


def _console_safe(text: str) -> str:
    """PDF-extracted text can contain characters (bullets, smart quotes,
    ligatures) the Windows console's default cp1252 codepage can't encode -
    this only affects what gets PRINTED; the JSON/CSV artefacts always
    keep the full original Unicode text via UTF-8."""
    import sys
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", action="append", default=None, help="Restrict to one council code (repeatable). Default: all councils.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write the JSON/CSV artefact into.")
    parser.add_argument("--examples-per-outcome", type=int, default=8, help="How many console examples to print per recommendation outcome.")
    return parser.parse_args()


def _result_to_dict(result: AllocationEvidenceResult) -> dict:
    return {
        "allocation_id": result.allocation_id,
        "council": result.council,
        "policy_reference": result.policy_reference,
        "allocation_name": result.allocation_name,
        "stage2a_classification": result.stage2a_classification,
        "stage2a_candidate_site_ids": result.stage2a_candidate_site_ids,
        "recommended_outcome": result.recommended_outcome,
        "contradiction_flag": result.contradiction_flag,
        "multi_site_flag": result.multi_site_flag,
        "evidenced_site_ids": sorted(result.evidenced_site_ids),
        "applications": sorted({h.application_id for h in result.positive_hits}),
        "source_documents": sorted({h.document_id for h in result.positive_hits + result.contradictory_hits}),
        "positive_hits": [
            {
                "document_id": h.document_id, "document_type": h.document_type, "weight": h.weight,
                "application_id": h.application_id, "application_reference": h.application_reference,
                "site_id": h.site_id, "matched_reference": h.matched_reference,
                "category": h.category, "evidence_snippet": h.snippet,
            }
            for h in result.positive_hits
        ],
        "contradictory_hits": [
            {
                "document_id": h.document_id, "document_type": h.document_type, "weight": h.weight,
                "application_id": h.application_id, "application_reference": h.application_reference,
                "site_id": h.site_id, "matched_reference": h.matched_reference,
                "category": h.category, "evidence_snippet": h.snippet,
            }
            for h in result.contradictory_hits
        ],
    }


def _write_artefacts(results: list[AllocationEvidenceResult], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"stage2c_evidence_{timestamp}.json"
    csv_path = output_dir / f"stage2c_evidence_{timestamp}.csv"

    payload = [_result_to_dict(r) for r in results]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "allocation_id", "council", "policy_reference", "allocation_name",
            "stage2a_classification", "recommended_outcome", "contradiction_flag",
            "multi_site_flag", "evidenced_site_ids", "positive_hit_count", "contradictory_hit_count",
        ])
        for r in results:
            writer.writerow([
                r.allocation_id, r.council, r.policy_reference or "", r.allocation_name,
                r.stage2a_classification, r.recommended_outcome, r.contradiction_flag,
                r.multi_site_flag, ";".join(str(s) for s in sorted(r.evidenced_site_ids)),
                len(r.positive_hits), len(r.contradictory_hits),
            ])

    return json_path, csv_path


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()

    print("[gm-allocation-document-evidence] DRY RUN - zero database mutations will be made\n")

    stage2a = run_dry_run_matching(session, council_codes=args.council)
    stage2a_by_id = {r.allocation_id: r for r in stage2a["results"]}

    query = select(LocalPlanSite).where(LocalPlanSite.matched_site_id.is_(None))
    if args.council:
        query = query.where(LocalPlanSite.council_code.in_(args.council))
    unmatched_allocations = list(session.execute(query).scalars().all())

    results = run_document_evidence_dry_run(session, stage2a_by_id, unmatched_allocations)

    outcome_counts: dict[str, int] = {}
    for r in results:
        outcome_counts[r.recommended_outcome] = outcome_counts.get(r.recommended_outcome, 0) + 1

    print("=== BASELINE ===")
    print(f"allocations evaluated: {len(results)}")
    print(f"documents matching at least one candidate term: "
          f"{len({h.document_id for r in results for h in r.positive_hits + r.contradictory_hits})}")

    print("\n=== RECOMMENDED OUTCOME COUNTS ===")
    for outcome, count in sorted(outcome_counts.items()):
        print(f"  {outcome}: {count}")

    print("\n=== STAGE 2A HIGH_CONFIDENCE AUDIT ===")
    high_confidence = [r for r in results if r.stage2a_classification == "HIGH_CONFIDENCE_CANDIDATE"]
    supported = [r for r in high_confidence if r.recommended_outcome in (FUZZY_SUPPORTED_BY_DOCUMENT, DOCUMENT_CONFIRMED_SITE)]
    unsupported = [r for r in high_confidence if r.recommended_outcome == NO_DOCUMENT_EVIDENCE]
    contradicted = [r for r in high_confidence if r.recommended_outcome == DOCUMENT_CONTRADICTS_FUZZY]
    print(f"  total HIGH_CONFIDENCE_CANDIDATE: {len(high_confidence)}")
    print(f"  document-supported: {len(supported)}")
    print(f"  no document evidence at all: {len(unsupported)}")
    print(f"  document-contradicted: {len(contradicted)}")
    for r in high_confidence:
        print(f"    allocation {r.allocation_id} ({r.council}/{r.policy_reference!r}) {r.allocation_name!r} "
              f"-> {r.recommended_outcome}")

    for label, outcome in (
        ("MULTIPLE_DOCUMENT_SUPPORTED_SITES", MULTIPLE_DOCUMENT_SUPPORTED_SITES),
        ("DOCUMENT_CONFIRMED_SITE", DOCUMENT_CONFIRMED_SITE),
        ("DOCUMENT_CONFIRMED_APPLICATION_ONLY", DOCUMENT_CONFIRMED_APPLICATION_ONLY),
        ("FUZZY_SUPPORTED_BY_DOCUMENT", FUZZY_SUPPORTED_BY_DOCUMENT),
        ("DOCUMENT_CONTRADICTS_FUZZY", DOCUMENT_CONTRADICTS_FUZZY),
    ):
        matching = [r for r in results if r.recommended_outcome == outcome]
        print(f"\n=== {label} examples ({len(matching)} total) ===")
        for r in matching[: args.examples_per_outcome]:
            print(f"  allocation {r.allocation_id} ({r.council}/{r.policy_reference!r}) {r.allocation_name!r} "
                  f"stage2a={r.stage2a_classification}")
            for h in (r.positive_hits + r.contradictory_hits)[:2]:
                print(f"      [{h.category}] app {h.application_reference} doc_type={h.document_type}: "
                      f"{_console_safe(h.snippet[:160])}")

    json_path, csv_path = _write_artefacts(results, Path(args.output_dir))
    print("\n=== ARTEFACTS ===")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")

    print("\n=== RESULT ===")
    print("DRY RUN COMPLETE - NO WRITES MADE")


if __name__ == "__main__":
    main()
