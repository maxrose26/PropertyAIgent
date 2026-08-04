"""Configurable expected-document checklist (Sprint 3D, "Policy Document
Coverage & Discovery", Part 1) - what planning-policy documents SHOULD
exist for a council, read from config/expected_policy_documents.yaml
rather than hardcoded here (Part 1: "Do not hardcode the list. Create a
configurable vocabulary"). app.policy.coverage is the only caller that
turns this checklist into a real discovered-vs-missing inventory; this
module only knows what OUGHT to exist, never whether it actually does -
same "config says WHAT, code says HOW" split app.policy.sources already
established for MonitoredSource registration.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from app.policy.document_types import POLICY_DOCUMENT_TYPES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DOCUMENTS_YAML = PROJECT_ROOT / "config" / "expected_policy_documents.yaml"


def load_expected_documents_config(path: Path = EXPECTED_DOCUMENTS_YAML) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def expected_document_types(council_code: str, config: dict | None = None) -> list[str]:
    """Returns the deduplicated, order-preserved list of PolicyDocumentType
    slugs expected for this council - the shared "default" list plus this
    council's own "additional" entries, minus anything it explicitly
    "exclude"s. Every returned value is guaranteed to be a real
    POLICY_DOCUMENT_TYPES member - an unrecognised slug in the YAML is
    silently dropped rather than surfaced as a phantom expected document
    the rest of the platform can never actually satisfy."""
    config = config if config is not None else load_expected_documents_config()
    default = list(config.get("default") or [])
    council_entry = (config.get("councils") or {}).get(council_code) or {}
    additional = list(council_entry.get("additional") or [])
    excluded = set(council_entry.get("exclude") or [])

    combined = [t for t in (default + additional) if t not in excluded]
    seen: set[str] = set()
    result: list[str] = []
    for doc_type in combined:
        if doc_type not in POLICY_DOCUMENT_TYPES or doc_type in seen:
            continue
        seen.add(doc_type)
        result.append(doc_type)
    return result
