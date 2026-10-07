"""One-off audit generator for verification/transition/frozen_v6_matcher.py (run from the repo root at a commit whose history contains 3cce081).

Method: `git show 3cce081:app/policy/buyer_matching.py` -> ast -> the verbatim source segment of the module-level function `assess_buyer_fit` (no edits) + the sha256 pins of every module-level
definition it references (excluding the one that changed in V7A: B2MatchingContext, which gained optional fields the v6 function never reads) + pins of the supporting modules.
"""
import ast
import builtins
import hashlib
import subprocess

COMMIT = "3cce0815fd6d243993edf5ca511094ae3a795285"
FILE = "app/policy/buyer_matching.py"


def git(*args):
    return subprocess.check_output(["git", *args])


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


blob_id = git("rev-parse", f"{COMMIT}:{FILE}").decode().strip()
src6 = git("show", f"{COMMIT}:{FILE}").decode("utf-8")
assert "\r" not in src6
tree = ast.parse(src6)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "assess_buyer_fit")
function_text = ast.get_source_segment(src6, fn)
assert fn.decorator_list == []

defs = {}
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        defs[node.name] = ast.get_source_segment(src6, node)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                defs[target.id] = ast.get_source_segment(src6, node)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            defs[(alias.asname or alias.name).split(".")[0]] = ("import", ast.get_source_segment(src6, node))

local = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
for n in ast.walk(fn):
    if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
        local.add(n.id)
    if isinstance(n, ast.FunctionDef):
        local.add(n.name)
    if isinstance(n, ast.arg):
        local.add(n.arg)
used = sorted({n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - local - set(dir(builtins)))

imported_from_profiles, imported_other, local_defs = [], [], []
pins = {}
for name in used:
    entry = defs[name]
    if isinstance(entry, tuple):                                     # imported into buyer_matching
        text = entry[1]
        (imported_from_profiles if "buyer_profiles" in text else imported_other).append(name)
    else:
        local_defs.append(name)
        if name != "B2MatchingContext":
            pins[name] = sha256(entry)
for extra in ("AFFORDABLE_STATE_UNKNOWN", "ControlAppetiteFacts", "DEFAULT_DISCOVERY_TOLERANCE_PERCENT", "DEVELOPMENT_STATE_COMPLETE", "DEVELOPMENT_STATE_PARTIALLY_COMPLETE", "DEVELOPMENT_STATE_UNDERWAY"):   # reached indirectly (via MatchingFacts / discovery_bounds)
    pins[extra] = sha256(defs[extra])

supporting = {}
for path in ("app/policy/buyer_profiles.py", "app/reporting/commercial_evidence.py", "app/reporting/residential_count.py", "app/reporting/scheme_reconciliation.py", "app/reporting/allocation_development_coverage.py"):
    text = git("show", f"{COMMIT}:{path}").decode("utf-8")
    assert "\r" not in text
    supporting[path] = sha256(text)

out = []
out.append('"""TRANSITION-ONLY, IMMUTABLE: the frozen accepted-v6 buyer matcher, used ONLY as the independent oracle for the V7C same-universe v6/v7 parity check.\n')
out.append(f'''
This is NOT application policy, NOT a fallback matcher and NOT a public API. Normal application code uses the v7 matcher (app.policy.buyer_matching) exclusively and must never
import this module (the application never imports `verification`; a test enforces it). Only the transition parity tooling (scripts/reonboard_stale_mandates.py via
verification.transition.v6_parity) and tests may call it.

DO NOT MODIFY. Future feature work must not edit this file or its pins. LIFECYCLE: it may remain through the production dry runs, the v7 transition and the immediate rollback window;
once v7 activation is accepted and the rollback window closes it is REMOVED in a dedicated cleanup (together with verification/transition/v6_parity.py and its tests).

PROVENANCE (immutable; recorded in PROVENANCE below and re-verified by tests/test_v7c_frozen_v6_oracle.py):
  source commit   {COMMIT} (master immediately before the first V7A commit d0a62da)
  source file     {FILE}
  source blob     {blob_id}   (git blob id of the whole file at that commit)
  source function assess_buyer_fit, lines {fn.lineno}-{fn.end_lineno} of that blob
  function sha256 {sha256(function_text)}
  extraction      `git show <commit>:<file>` -> ast.get_source_segment of the module-level function, copied VERBATIM (no edit of any character); extracted once by the audit generator
                  (verification/transition/audit_extract_frozen_v6.py). Reproduce: sha256 of the segment equals FUNCTION_SHA256 below.

INDEPENDENCE: classification-affecting logic is the verbatim v6 function body. The module-level names the function references were compared with v7: all are byte-identical
definitions except B2MatchingContext (v7 only ADDED optional fields the v6 body never reads). Those identical definitions are imported from app.policy.buyer_matching rather than copied;
DEPENDENCY_PINS records the sha256 of each v6 definition and the test recomputes the CURRENT definition and fails if any drifts, so the oracle can never silently delegate to changed logic.
The imported-name modules (buyer_profiles, commercial_evidence) are pinned by whole-file sha256 (LF-normalised).
"""
''')
out.append("from __future__ import annotations\n\n")
out.append("from app.policy.buyer_matching import (\n    " + ",\n    ".join(local_defs) + ",\n)\n")
out.append("from app.policy.buyer_profiles import (\n    " + ",\n    ".join(imported_from_profiles) + ",\n)\n")
for name in imported_other:
    assert name == "known_unit_count", name
    out.append("from app.reporting.commercial_evidence import known_unit_count\n")
out.append("\nPROVENANCE = {\n")
out.append(f'    "source_commit": "{COMMIT}",\n    "source_file": "{FILE}",\n    "source_blob": "{blob_id}",\n    "source_function": "assess_buyer_fit",\n')
out.append(f'    "source_lines": ({fn.lineno}, {fn.end_lineno}),\n    "function_sha256": "{sha256(function_text)}",\n    "policy_version_at_source": 6,\n')
out.append('    "extraction": "git show <commit>:<file>; ast.get_source_segment of the module-level function; verbatim copy",\n')
out.append("}\nFUNCTION_SHA256 = PROVENANCE[\"function_sha256\"]\n\n")
out.append("# sha256 of each v6 module-level definition the function references (B2MatchingContext excluded: v7 only added optional fields the v6 body never reads).\nDEPENDENCY_PINS = {\n")
for name in sorted(pins):
    out.append(f'    "{name}": "{pins[name]}",\n')
out.append("}\n\n# sha256 (LF-normalised) of the supporting modules whose names the function imports indirectly, as at the source commit.\nSUPPORTING_MODULE_SHA256 = {\n")
for path in sorted(supporting):
    out.append(f'    "{path}": "{supporting[path]}",\n')
out.append("}\n\n\n")
out.append(function_text + "\n")
open("verification/transition/frozen_v6_matcher.py", "w", encoding="utf-8", newline="\n").write("".join(out))
print("generated", len(function_text.splitlines()), "lines;", len(pins), "pins; function sha", sha256(function_text))
