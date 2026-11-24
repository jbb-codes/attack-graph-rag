# Design decisions

A running log. Newest entries at the bottom. Each entry: what was decided, why, and what was rejected.

## 2026-11-22: Project concept

- **Decision:** Build a RAG assistant over the MITRE ATT&CK Enterprise knowledge graph, containerized with Docker and Kubernetes.
- **Why:** One small project covers the target role's skills: Python, Docker/Kubernetes, LLM/RAG, semantic web (RDF, SPARQL), and cybersecurity.
- **Rejected:** a log-triage pipeline and a requirements-to-ontology tool. Each covers fewer of the skills.

## 2026-11-22: Vector store stays in scope

- **Decision:** Include a vector store from the start.
- **Why:** The goal is a full RAG pipeline. The graph answers exact questions; vector search handles vague ones.
- **Rejected:** graph-only retrieval, which is simpler but weaker on vague questions.

## 2026-11-22: Chroma over pgvector

- **Decision:** Use Chroma.
- **Why:** It needs no server in early stages and has a container image for later. pgvector would add a full Postgres database to learn, with no other data in the project that needs one.
- **Revisit:** Listed as a future improvement.

## 2026-11-22: Single test seam, fake LLM plus separate evals

- **Decision:** All tests go through `ask(question)`. Fast tests use a small fixture and a fake LLM. Quality is measured separately with an on-demand eval set against the real LLM.
- **Why:** Tests survive internal refactors, stay fast, free, and deterministic. Evals measure real answer quality without slowing everyday testing.
- **Rejected:** testing with a real LLM in every run (slow, costly, non-deterministic).

## 2026-11-22: Stage order and README timing

- **Decision:** Build in six shippable stages, plain Python before Docker, Kubernetes late. README is written in stage 6.
- **Why:** Avoid debugging several new technologies at once. A README describes a finished system, so writing it early means rewriting it.
- **Fallback:** If Kubernetes proves too hard, stages 1 to 4 plus documentation are still a complete portfolio project.

## 2026-11-23: Fixture is a STIX bundle, loaded through the real loader

- **Decision:** The ~20-technique fixture is a trimmed STIX 2.1 JSON bundle (same shape as the official ATT&CK release). Stage 1 loads it with the same loader the full dataset will use. The CLI defaults to this bundled fixture until a full-data load exists.
- **Why:** Tests exercise the real parsing path, and swapping in the full dataset later changes only the file, not the code. IDs are real ATT&CK IDs; relationships are simplified and chosen for tests, not guaranteed to match upstream.
- **Rejected:** a hand-made custom format (would need a second loader and hide parsing bugs).

## 2026-11-23: Plain RDF with `uses` and `mitigates` only

- **Decision:** One namespace, five classes (Technique, Group, Software, Mitigation), and two relationship predicates. Tactics are stored as text on techniques, not as separate resources. SPARQL values are bound, never string-formatted.
- **Why:** Smallest model that answers the stage 1 lookups. Tactic resources and sub-technique links can be added when a query needs them.
- **Rejected:** modeling tactics and sub-techniques now (no consumer yet).

## 2026-11-24: Pin ATT&CK Enterprise v20.1, verified by checksum

- **Decision:** `attack-graph load` downloads `enterprise-attack-20.1.json` from MITRE's `attack-stix-data` repo (the official STIX release). The version, URL, and SHA-256 are pinned in `src/attack_graph/release.py`. A download that fails the checksum is rejected and never used.
- **Why:** Reproducible results, and protection against a corrupted or tampered download. To upgrade, change the three values together and run `load` again.
- **Rejected:** "latest" (results change under us); no checksum (silent corruption).

## 2026-11-24: Loaded graph is a file, rebuilt from scratch on every load

- **Decision:** `load` saves the graph as sorted N-Triples (`data/attack-graph.nt`) and keeps the download in `data/` (git-ignored). Each load rebuilds the whole file, then swaps it in atomically. Lookups use the loaded graph if it exists, then fall back to the bundled fixture. `--data` still overrides both.
- **Why:** The in-memory graph vanishes when the process ends, so a "load" needs somewhere to keep it. Rebuilding means re-running can never duplicate facts, and a version bump leaves no stale facts. Re-running also skips the 55 MB download. Reading the file is much faster than re-parsing the STIX JSON each lookup.
- **Rejected:** merging new triples into the old store (stale facts survive a version bump); a SPARQL server now (stage 4 territory); parsing the full STIX file on every lookup (slow).

## 2026-11-24: Chroma's default embedding model, run locally

- **Decision:** Embed `"<name>. <description>"` for each technique with Chroma's bundled `all-MiniLM-L6-v2` model (384 numbers per text, runs on the CPU via ONNX). Distance is cosine. No API key and no network at search time; the model downloads once (~80 MB) into `~/.cache/chroma`.
- **Why:** Free, private, and good enough for short technique text. Indexing all 706 techniques of v20.1 takes a few seconds. Name plus description lets short names like "Phishing" and longer prose both match.
- **Rejected:** a hosted embedding API (cost, secrets, network in tests); a larger local model (bigger download, slower, not needed yet).
- **Known limit:** on the full data, "how do attackers get in through email?" puts Phishing (T1566) in the top 10 but not the top 5, behind email-account and mail-protocol techniques. Acceptable for stage 2; the graph step and answer prompt can filter later. Changing the model needs a re-index.

## 2026-11-24: Vector index is rebuilt on every `index`; embeddings computed by us

- **Decision:** `index` drops the Chroma collection and rebuilds it from the loaded graph, stored at `data/chroma` (git-ignored). The store takes an `embed` function (default: the model above) and passes ready-made vectors to Chroma. `VectorStore` has two methods: `index(techniques)` and `search(question, limit)`.
- **Why:** Same reasoning as the graph load: re-running can never duplicate entries, and techniques removed from the data cannot linger. Injecting `embed` lets fast tests use a tiny offline fake, and keeps Chroma's embedding-plugin API out of our interface so the store stays swappable.
- **Tests:** store behavior (idempotent index, ordering, errors) uses the fake embedder. Two tests marked `model` use the real model to prove vague questions find the right techniques; they need the one-time download, then run offline.
- **Rejected:** upserting only changed techniques (more code, stale-entry risk, indexing is already fast); Chroma's embedding-function plug-in (ties our interface to Chroma's API).
