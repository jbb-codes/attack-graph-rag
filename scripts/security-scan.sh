#!/usr/bin/env bash
# Opt-in security scans. Results are recorded by hand in docs/security/scan-results.md.
#
#   scripts/security-scan.sh           source scans: no Docker needed, needs internet
#   scripts/security-scan.sh images    image scans: needs Docker and trivy
#
# Source scans:
#   1. pip-audit  known vulnerabilities in the pinned Python packages (uv.lock)
#   2. bandit     risky patterns in our Python code (medium and above)
#   3. checkov    Dockerfile, Kubernetes manifest and secret-in-file checks
# Image scans build both images and run trivy on them (OS packages and Python
# packages inside the images), failing on any HIGH or CRITICAL finding.
#
# A check fails the script unless it is listed below WITH a reason. The same
# reasons are written up in docs/security/scan-results.md.
set -euo pipefail
cd "$(dirname "$0")/.."

# Accepted advisories: all are ChromaDB *server* bugs. chromadb 1.5.9 is the
# newest release and none has a fix yet. Chroma is only reachable on the private
# Compose/Kubernetes network. Remove these ids as soon as a fixed chromadb is
# out and pinned.
ACCEPTED_VULNS=(PYSEC-2026-311 PYSEC-2026-3813 PYSEC-2026-3814 PYSEC-2026-3815 GHSA-f4j7-r4q5-qw2c)

# Accepted Kubernetes findings:
#   CKV_K8S_43  image digest: images are built locally and loaded into kind, so no digest exists
#   CKV_K8S_15  pull policy Always: would try to download local-only images and fail
#   CKV_K8S_11  CPU limits: deliberately unset so the embedding model is not throttled
#   CKV_K8S_22  read-only root filesystem: chroma and the setup job must write to their volumes
#   CKV_K8S_35  secret as env var: the app reads configuration from the environment only (a documented design choice)
#   CKV2_K8S_6  NetworkPolicy: kind's default network plugin does not enforce them
ACCEPTED_K8S=CKV_K8S_43,CKV_K8S_15,CKV_K8S_11,CKV_K8S_22,CKV_K8S_35,CKV2_K8S_6

section() { printf '\n== %s ==\n' "$*"; }

source_scans() {
  command -v uvx >/dev/null || { echo "uv is not installed" >&2; exit 2; }

  section "pip-audit (Python dependencies from uv.lock)"
  local reqs ignore=()
  reqs=$(mktemp)
  uv export --frozen --no-dev --no-hashes --no-emit-project -o "$reqs" >/dev/null
  for id in "${ACCEPTED_VULNS[@]}"; do ignore+=(--ignore-vuln "$id"); done
  uvx pip-audit -r "$reqs" --no-deps --disable-pip "${ignore[@]}"
  rm -f "$reqs"

  section "bandit (our code, medium severity and above)"
  uvx bandit -r src -q --severity-level medium

  section "checkov (Dockerfile, Kubernetes manifests, secrets in files)"
  uvx checkov -d . --framework dockerfile,kubernetes,secrets --quiet --compact \
    --skip-path .venv --skip-path .claude --skip-path .git --skip-path data \
    --skip-check "$ACCEPTED_K8S"
}

image_scans() {
  command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 2; }
  command -v trivy >/dev/null || { echo "trivy is not installed (https://trivy.dev)" >&2; exit 2; }

  section "build"
  docker build -t attack-graph-rag:local .
  docker build -t attack-graph-oxigraph:local deploy/oxigraph

  mkdir -p security-results
  local status=0 image report
  for image in attack-graph-rag:local attack-graph-oxigraph:local; do
    section "trivy $image (HIGH and CRITICAL)"
    report="security-results/${image%%:*}.txt"
    # --exit-code 1 makes any HIGH or CRITICAL finding fail the command.
    if ! trivy image --severity HIGH,CRITICAL --exit-code 1 --format table --output "$report" "$image"; then
      cat "$report"
      echo "findings above: fix or document them" >&2
      status=1
    fi
  done
  echo "Full reports are in security-results/ (git-ignored). Copy the summary into docs/security/scan-results.md."
  exit "$status"
}

case "${1:-source}" in
  source) source_scans ;;
  images) image_scans ;;
  *) echo "usage: $0 [source|images]" >&2; exit 2 ;;
esac
