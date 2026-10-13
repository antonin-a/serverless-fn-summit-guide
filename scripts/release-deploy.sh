#!/usr/bin/env bash
# release-deploy.sh <ref> [--canary PCT] [--full] [--threshold PCT] [--timeout S]
#
# Deploys the function at a Git ref (a release tag such as v2) as a new
# revision. Used by the deploy-on-release workflow and from a laptop.
#
#   first deploy           creates the function at <ref>, 100 % of traffic
#   --canary PCT (default) new revision gets PCT % (default 10), the revision
#                          currently serving the majority keeps the rest; with
#                          --threshold the platform rolls back automatically
#                          when the canary's error rate passes it
#   --full                 new revision gets 100 % at once
#
# Only the source ref, SUMMIT_RELEASE and the traffic change: the rest of the
# current specification is sent back as read (secrets read back as null keep
# their stored value). One template edit, one revision.
#
# Env: OVH_CLOUD_PROJECT (required), FUNCTION_NAME (demo-summit-guide),
#      SLS_REGION (EU-WEST-PAR), REPO_URL, PODINFO_TOOLS.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

REF="${1:-}"; [[ -n "$REF" && "$REF" != -* ]] || die "usage: scripts/release-deploy.sh <ref> [--canary PCT|--full] [--threshold PCT]"
shift
MODE=canary; CANARY=10; THRESHOLD=5; TIMEOUT=900
while (( $# )); do
  case "$1" in
    --canary) MODE=canary; CANARY="$2"; shift ;;
    --full) MODE=full ;;
    --threshold) THRESHOLD="$2"; shift ;;
    --timeout) TIMEOUT="$2"; shift ;;
    *) die "unexpected argument: $1" ;;
  esac
  shift
done
need_cmd jq curl

code="$(curl -s -o /dev/null -w '%{http_code}' "$REPO_URL/tree/$REF")"
[[ "$code" == "200" ]] || die "ref '$REF' not found on $REPO_URL (HTTP $code): the platform clones it from there"

START=$(date +%s)
CURRENT="$(fn_get)"
if [[ -z "$CURRENT" ]]; then
  log "function '$FUNCTION_NAME' not found: creating it at $REF (100 % of traffic)"
  BODY="$(render_payload "$HERE/deploy/function-create.json" NAME="$FUNCTION_NAME" REGION="$SLS_REGION" \
    REPO_URL="$REPO_URL" REF="$REF" RELEASE="$REF" THRESHOLD="$THRESHOLD")"
  ID="$(api POST "$FN_PATH" --body "$BODY" --raw | jq -r '.id')"
  rm -f "$BODY"
  [[ -n "$ID" && "$ID" != "null" ]] || die "creation did not return an id"
  MIN_REV=1
else
  ID="$(jq -r '.id' <<<"$CURRENT")"
  STABLE="$(jq -r '.currentState.activeRevision // .currentState.latestReadyRevision // empty' <<<"$CURRENT")"
  PREV="$(jq -r '.currentState.latestReadyRevision // 0' <<<"$CURRENT")"
  if [[ "$MODE" == canary && -n "$STABLE" ]]; then
    TRAFFIC="$(jq -n --argjson s "$STABLE" --argjson c "$CANARY" '[{revision: $s, weight: (100 - $c)}, {latest: true, weight: $c}]')"
    log "canary: revision $STABLE keeps $((100 - CANARY)) %, $REF gets $CANARY %, auto-rollback above $THRESHOLD % errors"
  else
    TRAFFIC='[{"latest": true, "weight": 100}]'
    log "full: $REF gets 100 % of traffic"
  fi
  BODY="$(mktemp)"
  jq --arg ref "$REF" --argjson traffic "$TRAFFIC" --argjson thr "$THRESHOLD" '
    {checksum: .checksum,
     targetSpec: (.targetSpec | del(.region)
       | .template.function.source.repository.ref = $ref
       | .template.function.env = ([(.template.function.env // [])[] | select(.name != "SUMMIT_RELEASE")] + [{name: "SUMMIT_RELEASE", value: $ref}])
       | .traffic = $traffic
       | .rollbackErrorThreshold = $thr)}' <<<"$CURRENT" > "$BODY"
  api PUT "$FN_PATH/$ID" --body "$BODY" --raw >/dev/null
  rm -f "$BODY"
  MIN_REV=$((PREV + 1))
fi

sls_wait_ready function "$ID" "$TIMEOUT" "$MIN_REV" >/dev/null || die "revision for $REF did not become ready"
FINAL="$(api GET "$FN_PATH/$ID" --raw)"
URL="$(jq -r '.currentState.url // empty' <<<"$FINAL")"
REV="$(jq -r '.currentState.latestReadyRevision // empty' <<<"$FINAL")"
ELAPSED=$(( $(date +%s) - START ))
echo "SLS_URL=$URL"; echo "SLS_REVISION=$REV"; echo "SLS_ELAPSED=$ELAPSED"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  { echo "SLS_URL=$URL"; echo "SLS_REVISION=$REV"; echo "SLS_ELAPSED=$ELAPSED"; } >> "$GITHUB_OUTPUT"
fi
jq -r '"traffic: " + ([.currentState.traffic[]? | "r\(.revision) \(.weight)%"] | join(", "))' <<<"$FINAL"
