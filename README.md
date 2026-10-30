# serverless-fn-summit-guide

A Python 3.12 function for the OVHcloud Serverless alpha demo: the three
Velib' stations nearest to the Carrousel du Louvre (OVHcloud Summit), live
from the Velib' Metropole open data feed. No key, no dependency. The handler
is `main` in `user.py`, it takes no argument and returns a small web page
(add `?format=json` for the raw data).

## Three releases, three product features

| Release | What changes | What it shows |
|---|---|---|
| `v1` | A page with the three nearest stations, bikes and docks. Every call waits for the Velib' feed: usually 0.2 s, sometimes 5 to 6 s (the open data feed is erratic) | Deploy from a GitHub tag: the revision records the commit; scale to zero, cold start |
| `v2` | Mechanical and electric bikes, walking time, a recommendation, and an in-instance cache (station list 1 h, availability 30 s): the wait for the feed (0.2 to 6 s) becomes about 1 ms on a warm instance | Canary at 10 %, then Promote; a faster release you can measure in the answer (`fetchMs`, `cache`) |
| `v3` | "Simpler bike type parsing" with a real bug: it reads a list as a dict, every call fails | Automatic rollback: as a 10 % canary its error rate passes the 5 % threshold and the platform sends all traffic back to v2 on its own (status OUT_OF_SYNC) |

`v1` and `v2` are on `main`. `v3` lives on the branch `release/v3` so that
`main` stays healthy.

## Running the sequence

From GitHub: publish the releases `v1`, `v2`, `v3` (tags already exist). The
`deploy-on-release` workflow deploys each one as a canary (the first one at
100 %). It needs the platform API to be reachable from GitHub runners.

From a laptop (rehearsal, and on-stage fallback):

```sh
git clone https://github.com/antonin-a/podinfo-sls ../podinfo-sls   # deploy tooling
export OVH_CLOUD_PROJECT=<project id>                                 # ~/.ovh.conf profile serverless-alpha
scripts/play-demo.sh
```

| Script | Role |
|---|---|
| `scripts/release-deploy.sh <tag> [--canary PCT \| --full] [--threshold PCT]` | Deploys a tag as a new revision |
| `scripts/traffic.sh promote \| rollback <rev> \| status` | Changes traffic only (no new revision); `status` shows declared and effective traffic |
| `scripts/watch.sh <url> [s] [rate]` | Steady traffic (default 2 calls/s) plus a live line over the last 20 s: split per release and HTTP status, client p95. The platform needs requests to compute an error rate |
| `scripts/probe.sh <url> [n]` | One line per call: time seen by the client next to the wait for the Velib' feed (`fetchMs`) and the cache state |
| `scripts/play-demo.sh` | The whole sequence with a pause between steps |

After an automatic rollback, acknowledge it by pinning v2 (`traffic.sh
rollback <v2 revision>`), not with `promote`: the latest revision is the
broken v3.

## Setup for the workflow

Variables: `SLS_DEPLOY_ENABLED=true`, `OVH_CLOUD_PROJECT`, optionally
`SLS_REGION`, `SLS_FUNCTION_NAME` (default `demo-summit-guide`),
`SLS_CANARY_PERCENT` (10), `SLS_ROLLBACK_THRESHOLD` (5).

Secrets: `OVH_ENDPOINT`, plus either classic API keys
(`OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY`, the
consumer key restricted to the `serverless` routes of the project) or an
OAuth2 service account (`OVH_CLIENT_ID`, `OVH_CLIENT_SECRET`), which has its
own identity in the revision's `deployedBy`.

## Assumptions to check on the platform

- An exception in the handler is answered as an HTTP 500, so v3 produces real
  5xx errors.
- The canary error rate counts 5xx only, as the API contract says, with a
  minimum number of requests before a rollback.
- Automatic rollback (`rollbackErrorThreshold`) is active on the platform.

Data: Velib' Metropole open data (GBFS).
