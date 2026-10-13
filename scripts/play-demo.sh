#!/usr/bin/env bash
# play-demo.sh : the three-release sequence from a laptop, with a pause
# (Enter) between steps. Rehearsal tool, and the on-stage fallback when the
# release workflow cannot reach the platform.
#
#   1. v1 serves 100 %                     (creates the function if needed)
#   2. v2 as a 10 % canary, then promote   (new feature, faster thanks to the cache)
#   3. v3 as a 10 % canary with a 5 % error threshold: v3 is broken, the
#      platform rolls it back on its own; status shows OUT_OF_SYNC
#
# Traffic comes from scripts/watch.sh, started in the background against the
# function URL for the whole sequence (the platform needs requests to compute
# an error rate).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pause() { printf '\n>>> %s  [Enter]' "$1"; read -r _; }

pause "Step 1: deploy v1 (100 %)"
"$DIR/release-deploy.sh" v1 --full | tee /tmp/sg-deploy.out
URL="$(sed -n 's/^SLS_URL=//p' /tmp/sg-deploy.out)"; [[ -n "$URL" ]] || { echo "no URL" >&2; exit 1; }
echo "URL: $URL"

pause "Start traffic (5 calls/s for 15 min, in the background)"
"$DIR/watch.sh" "$URL" 900 5 > /tmp/sg-watch.log 2>&1 &
WATCH=$!; trap 'kill $WATCH 2>/dev/null || true' EXIT
echo "traffic running (tail -f /tmp/sg-watch.log to see the live split)"

pause "Step 2: release v2 as a 10 % canary"
"$DIR/release-deploy.sh" v2 --canary 10 --threshold 5 | tee /tmp/sg-deploy.out
V2_REV="$(sed -n 's/^SLS_REVISION=//p' /tmp/sg-deploy.out)"
"$DIR/traffic.sh" status
pause "Promote v2 to 100 %"
"$DIR/traffic.sh" promote

pause "Step 3: release v3 (broken) as a 10 % canary, auto-rollback above 5 % errors"
"$DIR/release-deploy.sh" v3 --canary 10 --threshold 5
echo "watching the platform until it rolls back (Ctrl-C to stop)"
while :; do
  s="$("$DIR/traffic.sh" status)"; printf '\n%s\n' "$s"
  grep -q 'OUT_OF_SYNC' <<<"$s" && { echo; echo "automatic rollback: v3 no longer receives traffic"; break; }
  sleep 5
done

pause "Acknowledge the rollback: declare v2 (revision $V2_REV) at 100 %"
# Not "promote": latest is the broken v3. Pin the stable revision instead.
"$DIR/traffic.sh" rollback "$V2_REV"
echo; echo "last traffic summary:"; tail -5 /tmp/sg-watch.log
