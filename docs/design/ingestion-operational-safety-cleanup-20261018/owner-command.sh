(
    set -euo pipefail
    umask 077

    cd "$HOME/stage4-owner/pr122-storage-acceptance"
    test "$(git rev-parse HEAD)" = ad8d5211afcc635c5bc50f4963adde4f31b4ef62
    test "$(git rev-parse 'HEAD^{tree}')" = 8482c3d62c79bcbdb6ce91b1b8075751bcaf9893
    test -z "$(git status --porcelain)"
    test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"
    test ! -e "$HOME/.local/state/propertyaigent/operational-safety-cleanup-once-20261018"
    test ! -e "$HOME/stage4-owner/operational-cleanup-20261018.py"
    test ! -e "$HOME/stage4-owner/operational-cleanup-registration.json"

    gh api \
      repos/maxrose26/PropertyAIgent/git/blobs/2a100d7d9307f75cc58df9429e376d769cb608e1 \
      --jq .content |
      base64 --decode > "$HOME/stage4-owner/operational-cleanup-20261018.py"

    gh api \
      repos/maxrose26/PropertyAIgent/git/blobs/37a969bbab0c9e51850a506a26379e40ab7e834d \
      --jq .content |
      base64 --decode > "$HOME/stage4-owner/operational-cleanup-registration.json"

    printf '%s  %s\n' \
      a8f6e78399fe89585f45f9815ca96e15d8f4e9a7e118103bbe41de66fc8a212c \
      "$HOME/stage4-owner/operational-cleanup-20261018.py" \
      3c10291a1b2e7f3d81f463a619fca177a224259f1ed708f01d8d0a5e935cc377 \
      "$HOME/stage4-owner/operational-cleanup-registration.json" |
      sha256sum --check

    exec systemd-run --user --scope \
      --unit=propertyaigent-operational-cleanup-20261018 \
      -p MemoryMax=268435456 \
      -p MemorySwapMax=0 \
      -p OOMPolicy=kill \
      -p RuntimeMaxSec=45s \
      "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
      'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_path(sys.argv.pop(1),run_name="__main__")' \
      "$HOME/stage4-owner/operational-cleanup-20261018.py" \
      --registration "$HOME/stage4-owner/operational-cleanup-registration.json" \
      --registration-sha256 3c10291a1b2e7f3d81f463a619fca177a224259f1ed708f01d8d0a5e935cc377
)
