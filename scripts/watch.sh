#!/usr/bin/env bash
# watch.sh <url> [seconds=60] [rate_per_second=5]
#
# Calls the function URL at a steady rate and keeps one live line with the
# share of answers per release and per HTTP status: during a canary you see
# v2 at about 10 %, and when the platform rolls a broken v3 back you see the
# 500s stop and v3 disappear. It is also the traffic the platform needs to
# compute an error rate: run it for the whole release sequence.
set -euo pipefail
url="${1:?usage: watch.sh <url> [seconds] [rate]}"; dur="${2:-60}"; rate="${3:-5}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
end=$(( $(date +%s) + dur )); total=0
tmp="$(mktemp)"; trap 'rm -f "$tmp"; echo' EXIT
while (( $(date +%s) < end )); do
  for _ in $(seq 1 "$rate"); do
    { out="$(curl -s -m 10 -w '\n%{http_code}' "$url" || printf '\n000')"
      code="${out##*$'\n'}"; body="${out%$'\n'*}"
      rel="$(jq -r '.release // "?"' <<<"$body" 2>/dev/null || echo "?")"
      echo "$code $rel" >> "$tmp"; } &
  done
  wait
  total=$(wc -l < "$tmp" | tr -d ' ')
  line="$(awk -v t="$total" '{k = ($1 == "200") ? $2 : "HTTP " $1; c[k]++} END {for (k in c) printf "%s %d%%   ", k, 100 * c[k] / t}' "$tmp" | tr -s ' ')"
  printf '\r%4d calls   %s' "$total" "$line"
  sleep 1
done
echo; echo "summary over $total calls:"; awk '{c[$1" release="$2]++} END {for (k in c) printf "  %-24s %d\n", k, c[k]}' "$tmp" | sort
