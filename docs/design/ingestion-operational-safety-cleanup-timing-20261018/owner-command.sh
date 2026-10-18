(
    set -euo pipefail
    umask 077
    cd "$HOME/stage4-owner"
    test ! -e operational-cleanup-timing-owner-20261018.sh

    timeout 15s gh api \
      repos/maxrose26/PropertyAIgent/git/blobs/27f03a7b5596d7e5912a3954343d1f97843051b5 \
      --jq .content |
      base64 --decode > operational-cleanup-timing-owner-20261018.sh

    printf '%s  %s\n' \
      9d7dd7e6b75b334fceb046b2104b546d220fb970748655c08bca8d24510680ca \
      operational-cleanup-timing-owner-20261018.sh |
      sha256sum --check

    exec bash operational-cleanup-timing-owner-20261018.sh
)
