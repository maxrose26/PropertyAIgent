from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COUNCILS_YAML = PROJECT_ROOT / "config" / "councils.yaml"


@dataclass(frozen=True)
class CouncilConfig:
    code: str
    name: str
    base_url: str
    date_field_mode: str  # "received" | "validated"
    doc_system: str  # "idox" | "idox_anite"
    anite_base_url: str | None
    unit_threshold: int
    region: str | None
    country: str | None
    further_info_tab: str = "furtherInformation"  # Stockport confirmed uses "details" instead
    # Per-request pause for idox_portal.py's detail-page fetches. Global
    # default (0.4s) is fine for most councils - Stockport specifically
    # started 429'ing heavily partway through a full 25-month backfill (a
    # much higher request volume per month than the normal weekly
    # incremental run ever hits), so it gets a per-council override here
    # rather than slowing every other council down to accommodate the one
    # that's unusually strict.
    request_delay_seconds: float = 0.4

    # --- Policy Intelligence fields (Sprint 2, Part 2) - config-driven, not
    # hardcoded anywhere in app.policy: see app.pipeline.run_weekly.
    # ensure_council_row, which is what actually writes these onto the
    # Council DB row. ---
    gss_code: str | None = None
    authority_type: str | None = None
    website: str | None = None
    monitoring_enabled: bool = False

    @property
    def search_url(self) -> str:
        return f"{self.base_url}/search.do?action=advanced&searchType=Application"

    @property
    def date_start_field(self) -> str:
        if self.date_field_mode == "validated":
            return "date(applicationValidatedStart)"
        return "date(applicationReceivedStart)"

    @property
    def date_end_field(self) -> str:
        if self.date_field_mode == "validated":
            return "date(applicationValidatedEnd)"
        return "date(applicationReceivedEnd)"


def load_councils() -> dict[str, CouncilConfig]:
    raw = yaml.safe_load(COUNCILS_YAML.read_text(encoding="utf-8"))
    councils = {}
    for code, entry in raw["councils"].items():
        councils[code] = CouncilConfig(
            code=code,
            name=entry["name"],
            base_url=entry["base_url"],
            date_field_mode=entry["date_field_mode"],
            doc_system=entry["doc_system"],
            anite_base_url=entry.get("anite_base_url"),
            unit_threshold=int(entry.get("unit_threshold", 10)),
            region=entry.get("region"),
            country=entry.get("country"),
            further_info_tab=entry.get("further_info_tab", "furtherInformation"),
            request_delay_seconds=float(entry.get("request_delay_seconds", 0.4)),
            gss_code=entry.get("gss_code"),
            authority_type=entry.get("authority_type"),
            website=entry.get("website"),
            monitoring_enabled=bool(entry.get("monitoring_enabled", False)),
        )
    return councils


def get_council(code: str) -> CouncilConfig:
    councils = load_councils()
    if code not in councils:
        raise KeyError(f"Unknown council '{code}'. Known: {sorted(councils)}")
    return councils[code]
