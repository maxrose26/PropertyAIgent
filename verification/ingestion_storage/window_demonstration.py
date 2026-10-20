"""The restricted GitHub-hosted half of the Bolton WINDOW DEMONSTRATION (specification 032 section 14): the accepted stable pipeline - connection qualification, the checkout binding, ONE form GET that must be a valid form
before any listing request, the listing collection under the EXISTING completeness contract (an explicit total is required), durable retention before the ledger checkpoint, source-free screening, publication-then-closure -
for ONE exact scope (Bolton RECEIVED 28 September to 4 October 2026) under its own authority name, evidence directory and registered manifest. Nothing here can register an authority, hold an administrative credential or
change a credential, and no resource ceiling differs from the accepted pipeline's."""
from datetime import date
from verification.discovery.idox_window import WindowConfig
from . import stable_pipeline as sp
from .operational_owner import WINDOW_SCOPE
from .operational_runner import WINDOW_AUTHORITY,WINDOW_EVIDENCE_DIRECTORY,WINDOW_HOSTED_AUTHORITY

WINDOW_MANIFEST_PATH='docs/design/ingestion-window-demonstration-20261023/MANIFEST.json'


class WindowHostedRunner(sp.HostedRunner):
    EVIDENCE=WINDOW_EVIDENCE_DIRECTORY
    AUTHORITY=WINDOW_AUTHORITY
    MODE_NAME='BOLTON_WINDOW_DEMONSTRATION_HOSTED'
    MANIFEST=WINDOW_MANIFEST_PATH
    scope=WINDOW_SCOPE
    window_config=WindowConfig('bolton','RECEIVED',date.fromisoformat(WINDOW_SCOPE['start']),date.fromisoformat(WINDOW_SCOPE['end']),0)


def main(argv=None):
    return sp.main(argv,authority=WINDOW_HOSTED_AUTHORITY,runner_class=WindowHostedRunner,manifest_path=WINDOW_MANIFEST_PATH,scope=WINDOW_SCOPE)


if __name__=='__main__':main()
