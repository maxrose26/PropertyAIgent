# PropertyAIgent

PropertyAIgent is a planning intelligence platform for UK residential development. It builds the richest possible understanding of every residential development opportunity in the UK, centred on a single core object: the **Site**. Planning applications, policy allocations, visual evidence, companies and contacts all exist to enrich a Site — nothing exists in isolation.

Today the platform covers 10 Greater Manchester councils: automated planning-application scraping and reconciliation, Local Plan / Places for Everyone policy tracking with ongoing monitoring, deterministic visual-evidence extraction and matching, and on-demand company/contact enrichment — all running as a single local Python application (SQLite + Streamlit), with no cloud deployment or multi-tenancy.

## Documentation

**Start here for product direction:** [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md) — mission, target users, the six-layer capability stack, and the platform's core philosophy (AI explains evidence, it does not invent conclusions).

| Document | What it answers |
|---|---|
| [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md) | Why does this platform exist, and who is it for? |
| [docs/PLATFORM_ARCHITECTURE.md](docs/PLATFORM_ARCHITECTURE.md) | What does each capability do, functionally, today and in future? |
| [docs/PRODUCT_ROADMAP.md](docs/PRODUCT_ROADMAP.md) | What gets built next, and in what order? |
| [docs/USER_JOURNEYS.md](docs/USER_JOURNEYS.md) | What does using the platform actually look like, per user type? |
| [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md) | What rules does every feature have to follow? |
| [docs/ARCHITECTURE_STATUS_v2.md](docs/ARCHITECTURE_STATUS_v2.md) | What's actually built today, sprint by sprint, and what's known to be missing? |
| [specifications/](specifications/) | Detailed, per-feature specifications (the "what and why" behind each capability, written before implementation) |

`specifications/001-platform-vision.md` is the platform's original vision document, superseded by `docs/PRODUCT_VISION.md` and retained only for historical context — see the notice at the top of that file.

## Getting Started

1. **Install dependencies** (Python 3.11+, a virtual environment recommended):
   ```
   pip install -r requirements.txt
   playwright install
   ```
2. **Configure API keys** — copy `.env.example` to `.env` and fill in the keys you have (OpenAI is required for AI extraction/summaries; Companies House, Apollo, Hunter, SerpAPI and EPC are used by specific enrichment/build-status features and can be added incrementally).
3. **Initialise the database** — `data/deal_finder.db` (SQLite) is created automatically the first time a pipeline stage or the UI runs against `app/db/models.py`.
4. **Run the weekly pipeline** for a council:
   ```
   python -m app.pipeline.run_weekly --council bury
   ```
5. **Launch the UI:**
   ```
   streamlit run app/ui/streamlit_app.py
   ```

Council-specific behaviour lives in config (`config/councils.yaml`, `config/policy_sources.yaml`), not in code — onboarding a new council is a config change. See [CLAUDE.md](CLAUDE.md) for the engineering conventions and workflow this repository follows, and [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md) for the principles every feature is expected to follow.
