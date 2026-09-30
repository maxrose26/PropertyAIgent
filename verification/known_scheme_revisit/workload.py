"""Bounded synthetic workload; not a stored production inventory or benchmark."""
from .model import Revisit, work_key

APPLICATIONS = (
    ("stockport", "DC/085997"), ("stockport", "DC/093884"),
    ("stockport", "DC/094889"), ("stockport", "DC/098428"),
    ("stockport", "DC/095922"), ("tameside", "SITE/313"),
)


def measure():
    model = Revisit()
    slices = []
    for cycle in ("prior", "revisit"):
        responses = {}
        for council, reference in APPLICATIONS:
            model.seed(cycle, council, reference)
            document = dict(council=council, reference=reference,
                            url="fixture://" + reference, body=b"synthetic unchanged body",
                            stage="fixture_only", proposed={})
            for stage, route in (("documents", "register"), ("relationships", "citation_search")):
                responses[(work_key(cycle, council, reference, stage, route), "start")] = dict(
                    cursor="start", next=None, documents=[document] if stage == "documents" else [], edges=[])
        for turn in range(5):
            report = model.run_slice(cycle, responses, ["stockport", "tameside"],
                                     (0 if cycle == "prior" else 100) + turn,
                                     steps=4, per_council=2)
            if cycle == "revisit":
                slices.append(report)
    return dict(production_inventory="unmeasured; no production metadata queried",
                basis="six explicitly enumerated synthetic applications; one body and one empty citation page each",
                applications=[dict(council=c, reference=r) for c, r in APPLICATIONS],
                document_body_revalidations=6, relationship_pages=6,
                body_bytes=sum(s["body_bytes"] for s in slices),
                slices=slices, new_version_observations_during_revisit=len(model.state["observations"]) - 6,
                cadence="unapproved hypothesis; fixture steps are not seconds or portal throughput")
