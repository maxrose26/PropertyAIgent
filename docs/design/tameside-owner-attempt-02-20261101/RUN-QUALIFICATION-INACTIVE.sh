#!/bin/bash
# INACTIVE: exactly one separate Tameside listing qualification approval, never B.
set -euo pipefail
package_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
checkout=/home/maxrose26/stage4-owner/tameside-owner-attempt-02-20261101
python=/home/maxrose26/stage4-owner/storage-controller-venv/bin/python
output=/home/maxrose26/stage4-owner/tameside-listing-qualification-evidence-02
consumed=/home/maxrose26/stage4-owner/tameside-qualification-20261024-30-attempt-02-consumed.json
/usr/bin/env -i HOME=/home/maxrose26 PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  "$python" -B "$package_dir/CHECK-PACKAGE.py"
if [[ ${1-} == --check ]]; then
  [[ $# == 1 ]] || exit 2
  exit 0
fi
[[ $# == 0 && -t 0 && -t 2 ]] || { echo 'REFUSED: exact reviewed owner-terminal invocation required'; exit 2; }
[[ ! -e "$output" && ! -L "$output" && ! -e "$consumed" && ! -L "$consumed" ]] || { echo 'STOP: consumed or existing evidence; reconcile without retry'; exit 2; }
echo 'Requires separate approval: Tameside RECEIVED 24–30 October 2026, listing metadata only, ONE separately approved ATTEMPT_02 in a manually opened Ubuntu terminal.'
read -r -p 'Approval phrase: ' approved
[[ "$approved" == EXECUTE_ONE_TAMESIDE_LISTING_QUALIFICATION_ATTEMPT_02 ]] || exit 2
cd -- "$checkout"
exec /usr/bin/env -i HOME=/home/maxrose26 PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  /usr/bin/timeout --signal=INT --kill-after=2s 58s "$python" -B -m verification.discovery.tameside_qualification \
  --output "$output" --authority ONE_TAMESIDE_LISTING_METADATA_QUALIFICATION_20261024_30_ATTEMPT_02
