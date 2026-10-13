#!/usr/bin/env bash
# write-ovh-conf.sh <path> : writes an ovh.conf for python-ovh and the ovhcloud
# CLI from environment variables, with a single profile "serverless-alpha".
#
#   OVH_ENDPOINT                                        required, API base URL
#   OVH_APPLICATION_KEY, OVH_APPLICATION_SECRET,
#   OVH_CONSUMER_KEY                                    classic API keys, or
#   OVH_CLIENT_ID, OVH_CLIENT_SECRET                    OAuth2 service account
#
# Classic keys win when all three are set. Exits 1 when neither set is complete.
set -euo pipefail
out="${1:?usage: write-ovh-conf.sh <path>}"
: "${OVH_ENDPOINT:?OVH_ENDPOINT is required (API base URL of the Serverless platform)}"

if [[ -n "${OVH_APPLICATION_KEY:-}" && -n "${OVH_APPLICATION_SECRET:-}" && -n "${OVH_CONSUMER_KEY:-}" ]]; then
  mode="api-keys"
  creds="application_key=${OVH_APPLICATION_KEY}
application_secret=${OVH_APPLICATION_SECRET}
consumer_key=${OVH_CONSUMER_KEY}"
elif [[ -n "${OVH_CLIENT_ID:-}" && -n "${OVH_CLIENT_SECRET:-}" ]]; then
  mode="service-account"
  creds="client_id=${OVH_CLIENT_ID}
client_secret=${OVH_CLIENT_SECRET}"
else
  echo "no credentials: set OVH_APPLICATION_KEY/SECRET/CONSUMER_KEY or OVH_CLIENT_ID/SECRET" >&2
  exit 1
fi

umask 077
cat > "$out" <<CONF
[default]
endpoint=serverless-alpha

[serverless-alpha]
endpoint=${OVH_ENDPOINT}
${creds}
CONF
echo "ovh.conf written ($mode)"
