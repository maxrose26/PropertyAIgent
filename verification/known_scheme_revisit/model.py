"""Offline contract model only: supplied responses, no I/O or operational worker."""
from copy import deepcopy
from hashlib import sha256
import json

from app.pipeline.lookup_outcome import reference_key


ROUTES = (("documents", "register"), ("relationships", "citation_search"))
RELATIONS = {"variation", "discharge", "reserved_matters", "amendment", "supersedes"}


def identity(council, reference):
    if not council.strip() or not reference.strip():
        raise ValueError("empty identity")
    return council.strip().casefold(), reference_key(reference)


def work_key(cycle, council, reference, stage, route):
    return json.dumps([cycle, *identity(council, reference), stage, route])


class Revisit:
    def __init__(self, state=None):
        self.state = deepcopy(state) if state is not None else {
            "work": {}, "versions": {}, "edges": [], "observations": []}

    def seed(self, cycle, council, reference, routes=ROUTES):
        council, reference = identity(council, reference)
        for stage, route in routes:
            if stage not in {"documents", "relationships"}:
                raise ValueError("unknown stage")
            key = work_key(cycle, council, reference, stage, route)
            previous = [w["last_success"] for w in self.state["work"].values()
                        if (w["council"], w["reference"], w["stage"], w["route"]) ==
                        (council, reference, stage, route) and w["last_success"] is not None]
            self.state["work"].setdefault(key, dict(
                cycle=cycle, council=council, reference=reference, stage=stage, route=route,
                cursor="start", applied=[], last_attempt=None,
                last_success=max(previous) if previous else None, next_due=0,
                failures=0, outcome="pending", reason="", new=0, revised=0))

    def _apply(self, key, response, now, max_work):
        w = self.state["work"][key]
        if response.get("error"):
            raise ValueError(response["error"])
        if response.get("cursor") != w["cursor"]:
            raise ValueError("cursor mismatch")
        if "next" not in response:
            raise ValueError("coverage end unspecified")
        if response["next"] in w["applied"] or response["next"] == w["cursor"]:
            raise ValueError("cursor loop")
        if w["stage"] == "documents":
            for doc in response.get("documents", []):
                if not isinstance(doc.get("body"), bytes):
                    raise ValueError("body unavailable; validators insufficient")
                scope = identity(doc["council"], doc["reference"])
                if scope != (w["council"], w["reference"]):
                    raise ValueError("document application mismatch")
                logical = json.dumps([*scope, doc["url"]])
                versions = self.state["versions"].setdefault(logical, [])
                evidence = dict(sha256=sha256(doc["body"]).hexdigest(),
                                body_hex=doc["body"].hex(),
                                issued=doc.get("issued"), published=doc.get("published"),
                                stage=doc["stage"], proposed=deepcopy(doc.get("proposed", {})))
                previous = {k: v for k, v in versions[-1].items() if k != "observed"} if versions else None
                if evidence != previous:
                    w["revised" if versions else "new"] += 1
                    versions.append(dict(evidence, observed=now))
                    self.state["observations"].append(dict(
                        application=list(scope), url=doc["url"], version=len(versions),
                        review="unreviewed", **deepcopy(versions[-1])))
        else:
            for edge in response.get("edges", []):
                target = identity(edge["council"], edge["reference"])
                verified = (edge.get("confidence") == "verified_reference"
                            and bool(edge.get("citation")) and target[0] == w["council"]
                            and edge.get("type") in RELATIONS)
                record = dict(source=[w["council"], w["reference"]], target=list(target),
                              type=edge["type"], route=w["route"], citation=edge.get("citation"),
                              confidence="verified_reference" if verified else "review_candidate")
                if record not in self.state["edges"]:
                    self.state["edges"].append(record)
                if verified:
                    self.seed(w["cycle"], *target)
                    if sum(x["cycle"] == w["cycle"] for x in self.state["work"].values()) > max_work:
                        raise ValueError("frontier budget")
        w["applied"].append(w["cursor"])
        w["cursor"] = response["next"]
        w.update(reason="", failures=0, next_due=0)
        if w["cursor"] is None:
            w.update(outcome="complete", last_success=now)
        else:
            w.update(outcome="partial", reason="continuation pending")

    def run_slice(self, cycle, responses, council_order, now, *, steps=8,
                  per_council=2, body_limit=4096, total_bytes=16384, max_work=32):
        """Replay one bounded fixture slice; caller checkpoints returned state.

        No ownership token here: this is not executable portal admission. The
        production integration must verify the real inherited owner, not this API.
        """
        if min(steps, per_council, body_limit, total_bytes, max_work) <= 0:
            raise ValueError("limits must be positive")
        order = [c.strip().casefold() for c in council_order]
        if len(order) != len(set(order)):
            raise ValueError("duplicate council allocation")
        used, consumed, allocations = 0, 0, {}
        due = [(k, w) for k, w in self.state["work"].items()
               if w["cycle"] == cycle and w["outcome"] != "complete"]
        due.sort(key=lambda pair: (order.index(pair[1]["council"]) if pair[1]["council"] in order else len(order),
                                  pair[1]["last_attempt"] if pair[1]["last_attempt"] is not None else -1,
                                  pair[0]))
        for key, _ in due:
            w = self.state["work"][key]
            if w["next_due"] > now:
                continue
            if w["council"] not in order or used >= steps or allocations.get(w["council"], 0) >= per_council:
                w.update(outcome="deferred", reason="slice budget or council not admitted")
                continue
            used += 1
            allocations[w["council"]] = allocations.get(w["council"], 0) + 1
            w["last_attempt"] = now
            response = responses.get((key, w["cursor"]), {"error": "response unavailable"})
            sizes = [len(d["body"]) for d in response.get("documents", []) if isinstance(d.get("body"), bytes)]
            if any(size > body_limit for size in sizes) or consumed + sum(sizes) > total_bytes:
                w.update(outcome="partial", reason="body budget")
                continue
            consumed += sum(sizes)
            trial = Revisit(self.state)
            try:
                trial._apply(key, response, now, max_work)
            except (ValueError, KeyError) as exc:
                w.update(outcome="partial", reason=str(exc))
                if str(exc) == "frontier budget":
                    continue
                w["failures"] += 1
                delay = min(86400 * 2 ** min(w["failures"] - 1, 3), 604800)
                w["next_due"] = now + max(delay, response.get("retry_after", 0))
            else:
                self.state = trial.state
        return dict(attempts=used, body_bytes=consumed, **self.workload(cycle))

    def workload(self, cycle):
        work = [w for w in self.state["work"].values() if w["cycle"] == cycle]
        return dict(applications=len({(w["council"], w["reference"]) for w in work}),
                    document_checks=sum(w["stage"] == "documents" for w in work),
                    relationship_lookups=sum(w["stage"] == "relationships" for w in work),
                    deferred=sum(w["outcome"] == "deferred" for w in work),
                    incomplete=sum(w["outcome"] != "complete" for w in work))

    def coverage(self, cycle):
        result = {}
        for w in self.state["work"].values():
            if w["cycle"] != cycle:
                continue
            app = json.dumps([w["council"], w["reference"]])
            result.setdefault(app, {})[w["stage"] + ":" + w["route"]] = deepcopy(w)
        return result
