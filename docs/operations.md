# Operations guide

How to run, configure and troubleshoot attack-graph-rag. For what the project is, see the [README](../README.md); for why it is built this way, see [decisions](decisions.md).

## Verification status

Read this first. Some of what follows was written on a machine with no Docker, kind, kubectl or API key, so it has **not** all been run.

| Part                                                                                                                                   | Status                                                       | How to check it yourself                                                                    |
| -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Fast test suite (fixture, fake LLM, fake servers)                                                                                      | Verified, passes                                             | `uv run pytest`                                                                             |
| CLI and HTTP API with the offline answerer on the bundled fixture                                                                      | Verified                                                     | the demo in the [README](../README.md#demo)                                                 |
| Full ATT&CK v20.1 load, index, search, ask, restart persistence against real Oxigraph and Chroma servers, run natively (no containers) | Verified during issue #9                                     | see decisions, "Docker stack design"                                                        |
| Source security scans (pip-audit, bandit, checkov)                                                                                     | Verified, results recorded                                   | `scripts/security-scan.sh`, [results](security/scan-results.md)                             |
| Dockerfiles, `compose.yaml`                                                                                                            | **Written, never run**                                       | `scripts/compose-smoke.sh`                                                                  |
| Kubernetes manifests in `k8s/`                                                                                                         | **Written, never run**; only parsed and checked offline      | `scripts/k8s-smoke.sh`                                                                      |
| Container image vulnerability scan                                                                                                     | **Not run** (needs Docker and trivy); results table is empty | `scripts/security-scan.sh images`, then fill in [scan-results.md](security/scan-results.md) |
| `ask` with the real Claude model                                                                                                       | **Not run** (no API key); only the live test and fakes exist | `uv run pytest -m live`                                                                     |
| Eval set against a real model                                                                                                          | **Not run**; expected IDs are untuned                        | `uv run attack-graph eval`                                                                  |

Likeliest first-run surprises (from the decisions log): the read-only root filesystem on `app`, the memory limit for the embedding model, and volume permissions on kind. If the smoke scripts fail, fix and record it.

## 1. Run locally (plain Python)

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run attack-graph load                # full ATT&CK Enterprise v20.1, ~55 MB, once into data/
uv run attack-graph index               # embeds every technique; first run downloads an ~80 MB model
```

Without `load`, lookups and `index` use the bundled 20-technique fixture, which is enough to try everything.

Pick how answers are written (see [configuration](#4-configuration)), then:

```bash
export ATTACK_GRAPH_LLM=offline         # no key; restates the first fact, for trying the pipeline
uv run attack-graph ask "how do attackers get in through email?"
uv run attack-graph technique T1566.001
uv run attack-graph group APT29
uv run attack-graph search "how do attackers use email?" --limit 5
```

HTTP API (binds to `127.0.0.1:8000`; options `--host`, `--port`):

```bash
uv run attack-graph serve
curl -s localhost:8000/health
curl -s localhost:8000/ask -d '{"question": "how do attackers get in through email?"}'
```

Every reply is `{"success": ..., "data": ..., "error": ...}`. `/ask` returns 200 for both `answered` and `not_found`; 400 for an empty or over-500-character question; 413 for a body over 4 KB; 429 with `Retry-After` past 20 requests per 60 s per client; 502 when the model call fails; 503 when the index is missing; 500 for anything unexpected.

Tests and evals:

```bash
uv run pytest                           # fast, offline, no key
uv run pytest -m live                   # one real Claude call, needs a key, costs a little
uv run attack-graph eval                # real-model eval set, needs index first, saves eval-results/<time>.json
```

`eval` exits 1 if any case fails. It reads `evals/questions.json` and `tests/injection_corpus.json` and compares with the previous saved run. Options: `--cases`, `--corpus`, `--results-dir`.

## 2. Run with Docker Compose

Needs Docker with Compose. **Not run yet, see [verification status](#verification-status).**

```bash
cp .env.example .env                    # set the API key, or ATTACK_GRAPH_LLM=offline
docker compose up -d --wait             # first start downloads ~135 MB (data and model)
curl -s localhost:8000/ask -d '{"question": "how do attackers get in through email?"}'
```

Four services: `sparql` (Oxigraph graph server), `chroma` (vector server), `setup` (one-off `load` then `index`), `app` (the API, waits for `setup`). The API is published on `127.0.0.1` only; set `ATTACK_GRAPH_PORT` to change the host port. Data lives in named volumes and survives restarts.

```bash
docker compose logs app                 # what the API logged
docker compose down                     # stop, keep data
docker compose down -v                  # stop and erase data
scripts/compose-smoke.sh                # opt-in end-to-end check, offline answerer, own project name
```

## 3. Deploy on Kubernetes (kind)

Needs Docker, [kind](https://kind.sigs.k8s.io/) and kubectl. **Not run yet, see [verification status](#verification-status).** Plain manifests in `k8s/`, no Helm.

```bash
kind create cluster --name attack-graph
docker build -t attack-graph-rag:local .
docker build -t attack-graph-oxigraph:local deploy/oxigraph
kind load docker-image attack-graph-rag:local attack-graph-oxigraph:local --name attack-graph
kubectl apply -f k8s/00-namespace.yaml
kubectl -n attack-graph create secret generic attack-graph-secrets --from-literal "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"
kubectl apply -f k8s/
kubectl -n attack-graph wait --for=condition=complete job/setup --timeout=900s
kubectl -n attack-graph get pods
kubectl -n attack-graph port-forward svc/app 8000:8000
```

Skip the Secret step if you set `ATTACK_GRAPH_LLM: offline` in `k8s/10-configmap.yaml`. The key goes from your shell straight to the cluster and never touches a file. Then `curl` as above from a second terminal. Clean up with `kubectl delete namespace attack-graph` (removes the disks) or `kind delete cluster --name attack-graph`. Step-by-step with explanations: [issue 10 page](learning/issue-10-kubernetes.md). Whole-flow check: `scripts/k8s-smoke.sh` (creates and deletes its own cluster, offline answerer).

## 4. Configuration

Environment variables only; nothing is read from a config file. Copy `.env.example` to `.env` (git-ignored) and run `set -a; source .env; set +a`. Values are checked before any data is opened, and an error names the variable, never its value.

| Variable                    | Needed when  | Meaning                                                                                                  |
| --------------------------- | ------------ | -------------------------------------------------------------------------------------------------------- |
| `ATTACK_GRAPH_LLM`          | optional     | `claude` (default), `local`, or `offline`                                                                |
| `ANTHROPIC_API_KEY`         | `claude`     | API key. Held only in the environment (a Kubernetes Secret on a cluster)                                 |
| `ATTACK_GRAPH_CLAUDE_MODEL` | optional     | default `claude-opus-5-5`; a cheaper one such as `claude-sonnet-5-5` is one variable away                |
| `ATTACK_GRAPH_LOCAL_MODEL`  | `local`      | model name your local server serves                                                                      |
| `ATTACK_GRAPH_LOCAL_URL`    | optional     | default `http://localhost:11434/v1` (Ollama style); `http` or `https`, no credentials                    |
| `ATTACK_GRAPH_SPARQL_URL`   | optional     | keep the graph in a SPARQL server instead of a local file; `load` then uploads and writes no local graph |
| `ATTACK_GRAPH_CHROMA_URL`   | optional     | keep vectors in a Chroma server instead of local files                                                   |
| `ATTACK_GRAPH_PORT`         | Compose only | host port for the API (default 8000)                                                                     |

Compose and the Kubernetes ConfigMap set the two store addresses for you. The pinned ATT&CK version, URL and SHA-256 are in `src/attack_graph/release.py`; to upgrade, change the three together and re-run `load` then `index`.

## 5. Troubleshooting

| Symptom                                                                  | Likely cause and fix                                                                                                                                                                                |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "ANTHROPIC_API_KEY is not set"                                           | `ATTACK_GRAPH_LLM` defaults to `claude`. Export the key, or set `ATTACK_GRAPH_LLM=offline` or `local`.                                                                                              |
| "ATTACK_GRAPH_LOCAL_MODEL is not set"                                    | You chose `local`; set the model name and make sure the local server is running.                                                                                                                    |
| "must be an http:// or https:// address with no username or password"    | A store or local-model address is malformed or has credentials in it.                                                                                                                               |
| `ask` or `search` says the index is missing; API returns 503 `not_ready` | Run `uv run attack-graph index`. In Compose or Kubernetes, `setup` may still be running or may have failed: `docker compose logs setup`, `kubectl -n attack-graph logs job/setup`.                  |
| Answers come from the 20-technique fixture, not full ATT&CK              | `load` has not run. Run `load`, then `index` again.                                                                                                                                                 |
| `load` fails the checksum                                                | The download did not match the pinned SHA-256 and is rejected on purpose. Retry; if it persists, the release file changed or the pin is wrong.                                                      |
| `not_found` for a question you think is covered                          | The vector search found nothing closer than cosine distance 0.75. Rephrase, or see the "Nothing relevant" decision. On the full data Phishing can fall outside the top 5 for vague email questions. |
| `502` from `/ask`                                                        | The model call failed; the reply is deliberately generic. Check the key, model name, network or local server. The log line is `event=answer_failed` with the error class only.                      |
| `429`                                                                    | Rate limit (20 per 60 s per client). Wait `Retry-After` seconds. Behind a proxy everyone shares one address.                                                                                        |
| First `index` is slow                                                    | It downloads the ~80 MB embedding model once into `~/.cache/chroma`.                                                                                                                                |
| Compose `app` never healthy                                              | `docker compose ps` and `docker compose logs`; the app exits at startup if the graph server is down.                                                                                                |
| Kubernetes pod `Pending` or `CrashLoopBackOff`                           | `kubectl -n attack-graph describe pod <name>`; events at the bottom. See likeliest surprises under verification status. Images must be loaded with `kind load`; the pull policy is `IfNotPresent`.  |
| A reply was withheld                                                     | Security event `reply_withheld` (`rules_leak` or `no_verified_citation`); the caller sees `not_found`.                                                                                              |

Logs: `uv run attack-graph serve` writes one `event=name key=value` line per security event to stderr (reasons and numbers only, never the question, reply or key). The server access log is off on purpose because it prints addresses.

## 6. Security scans

```bash
scripts/security-scan.sh                # dependencies, our code, Dockerfile, k8s files, secrets; needs internet, no Docker
scripts/security-scan.sh images         # builds both images and runs trivy; needs Docker and trivy
```

Accepted findings (the ChromaDB server advisories, some Kubernetes checks) are listed with reasons in [scan-results.md](security/scan-results.md) and in the script. Open gaps (no TLS or authentication on the API, per-peer rate limit, no NetworkPolicy) are in the [checklist review](security/checklist-review.md). The API is meant for localhost or a private network; do not expose it to the internet as is.
