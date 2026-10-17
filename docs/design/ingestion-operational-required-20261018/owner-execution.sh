#!/usr/bin/env bash
# NOT AUTHORISED NOW. After grouped approval, pass the exact released binding
# Git blob SHA and SHA256. Both arguments are non-secret; never pass a DB URL.
set -euo pipefail
test "$#" = 2
released_binding_blob=$1
released_binding_sha256=$2
[[ "$released_binding_blob" =~ ^[0-9a-f]{40}$ ]]
[[ "$released_binding_sha256" =~ ^[0-9a-f]{64}$ ]]
cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
git fetch origin master
git switch --detach ad8d5211afcc635c5bc50f4963adde4f31b4ef62
test "$(git rev-parse HEAD)" = ad8d5211afcc635c5bc50f4963adde4f31b4ef62
test "$(git rev-parse 'HEAD^{tree}')" = 8482c3d62c79bcbdb6ce91b1b8075751bcaf9893
test -z "$(git status --porcelain)"
test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"
test ! -e "$HOME/stage4-owner/operational-required-registration.json"
test ! -e "$HOME/.local/state/propertyaigent/operational-capture-queue-once-20261018"
gh api "repos/maxrose26/PropertyAIgent/git/blobs/$released_binding_blob" --jq .content |
  base64 --decode > "$HOME/stage4-owner/operational-required-registration.json"
printf '%s  %s\n' "$released_binding_sha256" "$HOME/stage4-owner/operational-required-registration.json" |
  sha256sum --check
"$HOME/stage4-owner/storage-controller-venv/bin/python" -m pip install \
  -r verification/ingestion_storage/operational-requirements.txt
exec systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 \
  -p OOMPolicy=kill -p RuntimeMaxSec=480s \
  "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B \
  -c 'import os,runpy,sys;sys.path.insert(0,os.getcwd());runpy.run_module("verification.ingestion_storage.operational_runner",run_name="__main__")' \
  --registration "$HOME/stage4-owner/operational-required-registration.json" \
  --registration-sha256 "$released_binding_sha256"
