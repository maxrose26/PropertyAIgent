# Run once in the existing WSL terminal

No new authentication or database credential input. Do not run after original expiry. A guard failure is a stop; do not remove state or files to bypass it. Routine code download is outside the three secret-operation requests.

```bash
(
    set -euo pipefail
    cd "$HOME/stage4-owner/pr122-storage-acceptance"
    test "$(git rev-parse HEAD)" = 7cf8d32547b63d485de872afc2f717c3dce55322
    test "$(git rev-parse 'HEAD^{tree}')" = 68bf766cda023b1f15a19a63978903995391ec46
    test -z "$(git status --porcelain)"
    test ! -e "$HOME/stage4-owner/storage-final-secret-cleanup.py"
    test ! -e "$HOME/.local/state/propertyaigent/storage-final-secret-cleanup-20261017"

    gh api \
      'repos/maxrose26/PropertyAIgent/git/blobs/7059e05dfa9ab9678ef8e4e4d02ee0350953ad32' \
      --jq .content |
      base64 --decode > "$HOME/stage4-owner/storage-final-secret-cleanup.py"

    printf '%s  %s\n' \
      'c433684f4cfc77b4fffe4e23f0abf9fadcb00a5d8b613b4b1c3f1c735234df76' \
      "$HOME/stage4-owner/storage-final-secret-cleanup.py" |
      sha256sum --check

    exec systemd-run --user --scope \
      --unit=propertyaigent-storage-memory-20261017 \
      -p Delegate=memory \
      -p MemoryMax=268435456 \
      -p MemorySwapMax=0 \
      -p OOMPolicy=kill \
      "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B \
      "$HOME/stage4-owner/storage-final-secret-cleanup.py"
)
```

Return the printed final JSON and upload both new events.jsonl and final-result.json from ~/.local/state/propertyaigent/storage-final-secret-cleanup-20261017. Do not rerun after failure or uncertainty. Actual final acceptance requires that result; this preparation does not claim deletion.
