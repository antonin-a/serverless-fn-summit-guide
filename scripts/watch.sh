#!/usr/bin/env bash
# watch.sh <url> [seconds=60] [rate_per_second=2]
#
# Calls the function URL at a steady rate and keeps one live line over the
# last 20 seconds: share of answers per release and per HTTP status, and the
# p95 latency seen by the client. During a canary you see v2 at about 10 %;
# after Promote the p95 drops from seconds (v1 waits for the Velib' feed on
# every call) to milliseconds (v2 cache); when the platform rolls a broken v3
# back you see the 500s stop and v3 disappear. It is also the traffic the
# platform needs to compute an error rate: run it for the whole sequence.
set -euo pipefail
url="${1:?usage: watch.sh <url> [seconds] [rate]}"; dur="${2:-60}"; rate="${3:-2}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
end=$(( $(date +%s) + dur )); total=0; window=$(( rate * 20 ))
tmp="$(mktemp)"; trap 'rm -f "$tmp"; echo' EXIT
while (( $(date +%s) < end )); do
  for _ in $(seq 1 "$rate"); do
    { rc=0; out="$(curl -s -m 10 -w '\n%{http_code} %{time_total}' "$url")" || rc=$?
      last="${out##*$'\n'}"; body="${out%$'\n'*}"
      code="${last%% *}"; secs="${last##* }"
      # No HTTP answer: tell a 10 s timeout from a refused or cut connection.
      case "$rc" in 0) ;; 28) code="timeout" ;; *) code="curl-error-$rc" ;; esac
      rel="$(jq -r '.release // "?"' <<<"$body" 2>/dev/null || echo "?")"
      echo "$code ${rel:-?} ${secs:-10}" >> "$tmp"; } &
  done
  wait
  total=$(wc -l < "$tmp" | tr -d ' ')
  recent="$(tail -n "$window" "$tmp")"
  p95="$(awk '{print $3}' <<<"$recent" | sort -n | awk '{v[NR] = $1} END {i = int(NR * 0.95 + 0.999); if (i < 1) i = 1; printf (v[i] < 1 ? "%d ms" : "%.1f s"), (v[i] < 1 ? v[i] * 1000 : v[i])}')"
  line="$(awk '{k = ($1 == "200") ? $2 : "HTTP " $1; c[k]++; n++} END {for (k in c) printf "%s %d%%   ", k, 100 * c[k] / n}' <<<"$recent" | tr -s ' ')"
  printf '\r\033[K%4d calls   last 20 s: p95 %s   %s' "$total" "$p95" "$line"
  sleep 1
done
echo; echo "summary over $total calls:"; awk '{c[$1" release="$2]++} END {for (k in c) printf "  %-24s %d\n", k, c[k]}' "$tmp" | sort
