"""Proposed fresh single-use binding; delegates unchanged shared admission/B2."""
from verification.discovery import material_admission as shared

WORKFLOW = '.github/workflows/stage4-route-qualified-material-admission-once.yml'
AUTHORITY = 'AUTHORISE_ROUTE_QUALIFIED_THREE_MATERIAL_ADMISSIONS_ONCE'

def main():
    # Separate workflow identity; do not edit or rerun the consumed workflow.
    shared.WORKFLOW = WORKFLOW
    shared.AUTHORITY = AUTHORITY
    shared.main()

if __name__ == '__main__':
    main()
