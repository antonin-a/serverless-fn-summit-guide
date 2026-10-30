#!/usr/bin/env bash
# probe.sh <url> [calls=10]
#
# One line per call, one after the other: the time seen by the client next
# to the time the function spent waiting for the Velib' feed (fetchMs). It
# shows where the latency comes from: with v1 most calls take about 0.2 s and
# some take 5 to 6 s, all of it in fetchMs (the open data feed is erratic);
# with v2 the cache answers in about 1 ms and only a refresh pays the feed.
set -euo pipefail
url="${1:?usage: probe.sh <url> [calls]}"; n="${2:-10}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
r="$(mktemp)"; trap 'rm -f "$r"' EXIT
for _ in $(seq 1 "$n"); do
  t="$(curl -s -m 15 -o "$r" -w '%{http_code} %{time_total}' "$url" || echo "000 15")"
  printf '%-4s client %6.0f ms   ' "${t%% *}" "$(awk '{print $2 * 1000}' <<<"$t")"
  jq -r '"Velib fetch \(.fetchMs) ms   cache \(.cache.stationStatus // "none")   \(.release)"' "$r" 2>/dev/null || echo "(no JSON answer)"
done
