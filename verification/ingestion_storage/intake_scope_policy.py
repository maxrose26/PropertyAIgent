"""Reviewed immutable intake scopes. No credentials, issuance or recovery logic."""
from dataclasses import dataclass, asdict
from app.ingestion.ledger import Denied, digest

@dataclass(frozen=True)
class IntakeScope:
    period: str
    council: str
    semantics: str
    start: str
    end: str
    contract: str
    qualification_sha256: str
    requests: int = 10
    retries: int = 0
    received_bytes: int = 3_000_000
    response_bytes: int = 500_000
    pages: int = 6
    records: int = 60
    source_seconds: int = 45
    source_group_bytes: int = 1024**3

    def window(self): return dict(start=self.start, end=self.end)
    def councils(self):
        return {self.council: dict(contract=self.contract, qualification_sha256=self.qualification_sha256)}
    def fingerprint(self): return digest(asdict(self))
    def row(self): return dict(council=self.council, semantics=self.semantics, **self.window())

# Qualification is the retained, independently hash-verified Idox source audit;
# it does not assert completeness for this new window.
BOLTON = IntakeScope('b-bolton-20261103-1105-01', 'bolton', 'RECEIVED',
    '2026-11-03', '2026-11-05', 'bolton-received-intake-v1',
    '5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a')

def reviewed(period):
    return BOLTON if period == BOLTON.period else None

def require_scope(period, policy):
    scope = reviewed(period)
    if scope is None or policy.get('fixed_window') != scope.window() or policy.get('councils') != scope.councils():
        raise Denied('INTAKE_REVIEWED_SCOPE')
    return scope
