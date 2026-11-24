#!/usr/bin/env bash
# Opt-in check of the whole Docker Compose stack. Needs Docker and internet
# (it downloads the ATT&CK data and the embedding model on the first run).
# Uses the offline answerer, so no API key and no cost.
#
#   scripts/compose-smoke.sh
#
# Checks: one command starts everything, health checks go green, every
# container is non-root, `ask` works through the containers, and the data
# survives stopping and restarting without re-loading it.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 2; }

export COMPOSE_PROJECT_NAME=attack-graph-smoke
export ATTACK_GRAPH_LLM=offline
export ATTACK_GRAPH_PORT="${ATTACK_GRAPH_PORT:-18000}"
URL="http://127.0.0.1:${ATTACK_GRAPH_PORT}"
QUESTION='{"question": "how do attackers get in through email?"}'

fail() { echo "FAIL: $*" >&2; exit 1; }
cleanup() { docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

ask_works() {
  local reply
  reply=$(curl -fsS "$URL/ask" -d "$QUESTION")
  echo "$reply" | grep -q '"success":true' || fail "ask did not succeed: $reply"
  echo "$reply" | grep -q '"status":"answered"' || fail "ask was not answered from the data: $reply"
  echo "$reply" | grep -q 'T1566' || fail "ask did not retrieve Phishing (T1566): $reply"
}

echo "1/5 starting the whole system with one command"
docker compose up -d --build --wait

echo "2/5 health checks"
for service in sparql chroma app; do
  state=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q "$service")")
  [ "$state" = healthy ] || fail "$service is $state, expected healthy"
done
curl -fsS "$URL/health" | grep -q '"success":true' || fail "GET /health failed"

echo "3/5 containers run as a non-root user"
for service in sparql chroma app; do
  uid=$(docker compose exec -T "$service" id -u)
  [ "$uid" != 0 ] || fail "$service runs as root"
done

echo "4/5 ask through the containers"
ask_works

echo "5/5 data survives a restart (the load/index job is NOT run again)"
docker compose stop app sparql chroma
docker compose up -d --wait --no-deps sparql chroma app
ask_works

echo "OK: the Compose stack works"
