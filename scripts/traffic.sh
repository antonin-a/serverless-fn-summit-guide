#!/usr/bin/env bash
# traffic.sh promote | rollback <revision> | status
#
#   promote          the latest ready revision gets 100 % (ends a canary)
#   rollback <rev>   revision <rev> gets 100 %
#   status           declared and effective traffic, resource status (shows
#                    OUT_OF_SYNC after an automatic rollback), revisions
#
# Only the traffic changes: no template change, so no new revision.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
need_cmd jq
CURRENT="$(fn_get)"; [[ -n "$CURRENT" ]] || die "function '$FUNCTION_NAME' not found"
ID="$(jq -r '.id' <<<"$CURRENT")"

status() {
  jq -r '
    "status:    \(.resourceStatus)",
    "declared:  " + ([.targetSpec.traffic[]? | (if .latest then "latest" else "r\(.revision)" end) + " \(.weight)%"] | join(", ")),
    "effective: " + ([.currentState.traffic[]? | "r\(.revision) \(.weight)%"] | join(", ")),
    "revisions: " + ([.currentState.revisions[]? | "r\(.number) \(.status)"] | join(", ")),
    "threshold: \(.targetSpec.rollbackErrorThreshold // "none") % errors"' <<<"$1"
}

set_traffic() {
  local body; body="$(mktemp)"
  jq --argjson traffic "$1" '{checksum: .checksum, targetSpec: (.targetSpec | del(.region) | .traffic = $traffic)}' <<<"$CURRENT" > "$body"
  api PUT "$FN_PATH/$ID" --body "$body" --raw >/dev/null
  rm -f "$body"
  sleep 2
  status "$(api GET "$FN_PATH/$ID" --raw)"
}

case "${1:-status}" in
  status) status "$CURRENT" ;;
  promote) set_traffic '[{"latest": true, "weight": 100}]' ;;
  rollback)
    [[ -n "${2:-}" ]] || die "usage: traffic.sh rollback <revision>"
    set_traffic "$(jq -n --argjson r "$2" '[{revision: $r, weight: 100}]')" ;;
  *) die "usage: traffic.sh promote | rollback <revision> | status" ;;
esac
