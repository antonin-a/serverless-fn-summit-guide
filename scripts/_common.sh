# Shared setup for the scripts of this repository: loads the podinfo-sls
# deploy tooling (python-ovh API client, wait-until-ready, payload rendering).
# PODINFO_TOOLS points at podinfo-sls/tools; default: the clone next to this
# repository, or ./podinfo-sls/tools inside a GitHub Actions checkout.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${PODINFO_TOOLS:-}" ]]; then
  for c in "$HERE/podinfo-sls/tools" "$HERE/../podinfo-sls/tools"; do
    [[ -f "$c/lib.sh" ]] && PODINFO_TOOLS="$(cd "$c" && pwd)" && break
  done
fi
[[ -f "${PODINFO_TOOLS:-}/lib.sh" ]] || { echo "podinfo-sls tooling not found: clone antonin-a/podinfo-sls next to this repository or set PODINFO_TOOLS" >&2; exit 1; }
# shellcheck source=/dev/null
source "$PODINFO_TOOLS/lib.sh"

FUNCTION_NAME="${FUNCTION_NAME:-demo-summit-guide}"
REPO_URL="${REPO_URL:-https://github.com/antonin-a/serverless-fn-summit-guide}"
export SLS_REGION="${SLS_REGION:-EU-WEST-PAR}"
[[ -n "${OVH_CLOUD_PROJECT:-}" ]] || die "OVH_CLOUD_PROJECT is not set"
is_demo_name "$FUNCTION_NAME" || die "FUNCTION_NAME must start with demo-"
FN_PATH="$(sls_kind_path function)"

# current resource JSON, empty when absent
fn_get() { sls_get_resource function "$FUNCTION_NAME"; }
