# attack-graph-rag

Question-answering service over MITRE ATT&CK Enterprise. Vector search (Chroma) finds relevant techniques by meaning, a knowledge graph (RDF/SPARQL) supplies exact facts, and an LLM writes a short answer that cites technique IDs. Learning and portfolio project, built in small stages.

## Source of truth

- Scope and requirements: GitHub issue #1 (the spec). If scope changes, edit the issue.
- Decisions made while building: [docs/decisions.md](docs/decisions.md). Add an entry whenever a real choice is made.

## Current stage

Stage 1 not started. Stages, each shippable on its own:

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

## Commands

None yet. Add test, run, and load commands here as they are created.
