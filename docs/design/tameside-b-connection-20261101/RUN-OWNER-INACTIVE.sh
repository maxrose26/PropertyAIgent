#!/bin/bash
# INACTIVE: separate approval of the exact selected phase and bindings is required.
set -euo pipefail
package_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
checkout=/home/maxrose26/stage4-owner/tameside-b-connection-20261101
python=/home/maxrose26/stage4-owner/storage-controller-venv/bin/python
/usr/bin/env -i HOME=/home/maxrose26 PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  "$python" -B "$package_dir/CHECK-PACKAGE.py"
if [[ ${1-} == --check ]]; then
  [[ $# == 1 ]] || exit 2
  exit 0
fi
cd -- "$checkout"
exec /usr/bin/env -i HOME=/home/maxrose26 PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  "$python" -B -m verification.ingestion_storage.intake_owner_client "$@"
