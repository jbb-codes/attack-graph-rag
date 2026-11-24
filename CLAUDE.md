# attack-graph-rag

Question-answering service over MITRE ATT&CK Enterprise. Vector search (Chroma) finds relevant techniques by meaning, a knowledge graph (RDF/SPARQL) supplies exact facts, and an LLM writes a short answer that cites technique IDs. Learning and portfolio project, built in small stages.

## Source of truth

- Scope and requirements: GitHub issue #1 (the spec). If scope changes, edit the issue.
- Decisions made while building: [docs/decisions.md](docs/decisions.md). Add an entry whenever a real choice is made.

## Current stage

Stage 1 done: fixture graph and lookup CLI (issue #2); full ATT&CK Enterprise load (issue #3). Stage 2 done: vector search by meaning (issue #4). Stage 3 done: `ask` pipeline with a fake LLM done (issue #5); real LLM client and config done (issue #6); HTTP API (issue #7). Stage 4 done: Docker and Compose (issue #9; `scripts/compose-smoke.sh` passes). Stage 5 written: Kubernetes manifests in `k8s/` (issue #10; no cluster tooling was available, so run `scripts/k8s-smoke.sh` before relying on them). Stage 6 started: prompt-injection defenses (issue #8). Stages, each shippable on its own:

1. Graph load and SPARQL queries (plain Python)
2. Vector store and retrieval (plain Python)
3. Full `ask` pipeline with LLM
4. Docker and Compose
5. Kubernetes (plain manifests, local cluster)
6. Security hardening, eval set, documentation (including README)

Update this section when a stage starts or finishes.

## Working agreements

- The author is new to Docker, Kubernetes, and RDF/SPARQL. Explain new concepts in plain English and keep steps small.
- Do not introduce Docker before stages 1 to 3 work in plain Python. Avoid debugging several new technologies at once.
- One test seam: `ask(question)`. Test external behavior through it; do not test internals.
- Fast tests use a small ATT&CK fixture and a fake LLM. Evals use the real LLM, run on demand, and stay out of the normal test run.
- Public repo: no secrets, no personal data in code, docs, or commits.
- README is deliberately deferred to stage 6.

## Definition of done for an issue

An issue is done when all its acceptance criteria are met and tests pass. At that point, before offering a commit or PR, update `docs/learning/` in the same change:

- A Mermaid diagram of what was built, in the issue's page (`docs/learning/issue-NN-<short-name>.md`). Use teal for data and purple for code, keep box text short, and include a key.
- New keywords in `glossary.md`.
- New rows and syntax tips in `python-for-node-devs.md`.
- A files-and-purpose list and a code tour for the issue.

Plain English, one line per entry, written for a Node/TS developer new to Python.

## Commands

- Install: `uv sync`
- Test: `uv run pytest`
- Load full ATT&CK Enterprise (pinned v20.1, downloads ~55 MB once into `data/`): `uv run attack-graph load`
- Look up a technique: `uv run attack-graph technique T1566.001`
- Look up a group (name or alias): `uv run attack-graph group APT29`
- Embed all techniques for search (first run downloads the ~80 MB embedding model once): `uv run attack-graph index`
- Find techniques by meaning: `uv run attack-graph search "how do attackers use email?" --limit 5`
- Ask a question (cites technique IDs; needs `index` first; needs `ANTHROPIC_API_KEY`, or `ATTACK_GRAPH_LLM=offline` / `local`, see `.env.example`): `uv run attack-graph ask "how do attackers get in through email?"`
- Run the HTTP API (same config as `ask`; needs `index` first; binds to 127.0.0.1:8000): `uv run attack-graph serve`, then `curl -s localhost:8000/ask -d '{"question": "how do attackers get in through email?"}'`; health check at `GET /health`. Options: `--host`, `--port`
- Whole stack in Docker (needs Docker; copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`, or `ATTACK_GRAPH_LLM=offline`; first start downloads ~135 MB): `docker compose up -d --wait`, then `curl -s localhost:8000/ask -d '{"question": "how do attackers get in through email?"}'`; stop with `docker compose down` (data kept; `down -v` erases it)
- Check the Docker stack end to end (opt-in, needs Docker and internet, uses the offline answerer): `scripts/compose-smoke.sh`
- Kubernetes on a local kind cluster (needs Docker, kind, kubectl; build and load the two images first, see `docs/learning/issue-10-kubernetes.md` for each step): `kubectl apply -f k8s/`, create the secret with `kubectl -n attack-graph create secret generic attack-graph-secrets --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"` (skip with `ATTACK_GRAPH_LLM=offline`), then `kubectl -n attack-graph port-forward svc/app 8000:8000` and `curl` as above; remove with `kubectl delete namespace attack-graph`
- Check the Kubernetes setup end to end (opt-in, needs Docker, kind, kubectl and internet, creates and deletes its own cluster, offline answerer): `scripts/k8s-smoke.sh`
- Real-Claude test (opt-in, costs a little, needs `ANTHROPIC_API_KEY`): `uv run pytest -m live`
- Use another STIX file (overrides loaded data): `uv run attack-graph --data path/to/bundle.json technique T1566`

Lookups and `index` use the loaded data if `load` has run, otherwise the bundled fixture. `search` and `ask` need `index` first.

## Configuration (environment variables)

Read from the environment only; copy `.env.example` to `.env` (git-ignored) and `set -a; source .env; set +a`. Checked before `ask` runs.

- `ATTACK_GRAPH_LLM`: `claude` (default), `local`, or `offline`.
- `ANTHROPIC_API_KEY`: required for `claude`. `ATTACK_GRAPH_CLAUDE_MODEL`: optional, default `claude-opus-5-5`.
- `ATTACK_GRAPH_LOCAL_MODEL`: required for `local`. `ATTACK_GRAPH_LOCAL_URL`: optional, default `http://localhost:11434/v1`.
- `ATTACK_GRAPH_SPARQL_URL` / `ATTACK_GRAPH_CHROMA_URL`: optional. Set (Compose does) to keep the graph in a SPARQL server and vectors in a Chroma server instead of local files. `load` then uploads to the server and writes no local graph file.
