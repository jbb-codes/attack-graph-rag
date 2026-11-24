#!/usr/bin/env bash
# Opt-in check of the Kubernetes manifests on a throwaway local kind cluster.
# Needs docker, kind and kubectl, plus internet (ATT&CK data and the embedding model
# are downloaded on the first run). Uses the offline answerer: no API key, no cost.
#
#   scripts/k8s-smoke.sh
#
# Checks: everything becomes ready, `ask` works through the cluster, the API key is
# not in any image, and data survives deleting every pod (the setup job is NOT re-run).
set -euo pipefail
cd "$(dirname "$0")/.."

for tool in docker kind kubectl curl; do
  command -v "$tool" >/dev/null || { echo "$tool is not installed" >&2; exit 2; }
done

CLUSTER=attack-graph-smoke
NS=attack-graph
LOCAL_PORT="${ATTACK_GRAPH_PORT:-18000}"
URL="http://127.0.0.1:${LOCAL_PORT}"
QUESTION='{"question": "how do attackers get in through email?"}'
PF_PID=""

fail() { echo "FAIL: $*" >&2; exit 1; }
stop_forward() { [ -z "$PF_PID" ] || { kill "$PF_PID" 2>/dev/null || true; wait "$PF_PID" 2>/dev/null || true; PF_PID=""; }; }
cleanup() { stop_forward; kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

forward() {
  stop_forward
  kubectl -n "$NS" port-forward svc/app "${LOCAL_PORT}:8000" >/dev/null &
  PF_PID=$!
  for _ in $(seq 30); do curl -fsS "$URL/health" >/dev/null 2>&1 && return; sleep 1; done
  fail "could not reach the API through port-forward"
}

ask_works() {
  local reply
  reply=$(curl -fsS "$URL/ask" -d "$QUESTION")
  echo "$reply" | grep -q '"success":true' || fail "ask did not succeed: $reply"
  echo "$reply" | grep -q '"status":"answered"' || fail "ask was not answered from the data: $reply"
  echo "$reply" | grep -q 'T1566' || fail "ask did not retrieve Phishing (T1566): $reply"
}

echo "1/6 creating a kind cluster and loading the images"
kind create cluster --name "$CLUSTER" --wait 120s
docker build -t attack-graph-rag:local .
docker build -t attack-graph-oxigraph:local deploy/oxigraph
kind load docker-image attack-graph-rag:local attack-graph-oxigraph:local --name "$CLUSTER"

echo "2/6 applying the manifests (offline answerer, so no Secret is needed)"
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/
kubectl -n "$NS" patch configmap attack-graph-config --type merge -p '{"data":{"ATTACK_GRAPH_LLM":"offline"}}'

echo "3/6 waiting for the setup job and for every deployment to be ready"
kubectl -n "$NS" wait --for=condition=complete job/setup --timeout=900s \
  || { kubectl -n "$NS" logs job/setup --all-containers --tail=50 >&2 || true; fail "setup job did not complete"; }
kubectl -n "$NS" rollout restart deployment/app   # pick up the patched ConfigMap
kubectl -n "$NS" rollout status deployment/sparql --timeout=300s
kubectl -n "$NS" rollout status deployment/chroma --timeout=300s
kubectl -n "$NS" rollout status deployment/app --timeout=600s

echo "4/6 ask through the cluster"
forward
ask_works

echo "5/6 configuration and secrets are not in the images"
for image in attack-graph-rag:local attack-graph-oxigraph:local; do
  docker image inspect "$image" --format '{{json .Config.Env}}' | grep -qi 'ANTHROPIC_API_KEY\|SPARQL_URL' \
    && fail "$image has configuration baked into its environment"
done

echo "6/6 data survives deleting every pod (the setup job is NOT run again)"
stop_forward
kubectl -n "$NS" delete pod -l 'app in (sparql,chroma,app)' --wait=true
kubectl -n "$NS" rollout status deployment/sparql --timeout=300s
kubectl -n "$NS" rollout status deployment/chroma --timeout=300s
kubectl -n "$NS" rollout status deployment/app --timeout=600s
forward
ask_works

echo "OK: the Kubernetes manifests work on kind"
