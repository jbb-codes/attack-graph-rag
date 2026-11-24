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

## 2026-11-24: `ask` returns a status, never raises for bad questions

- **Decision:** `Answerer.ask(question)` returns an `Answer` with a status (`answered`, `not_found`, `invalid`, `error`), text, cited techniques, and retrieved techniques. Empty or over-500-character questions are `invalid`; control characters are stripped first. LLM failures become a generic `error` reply with no internals. Only a missing index raises (`VectorStoreError`), because that is a setup problem, not bad input.
- **Why:** One shape for the CLI now and the HTTP API later (issue #7). Callers branch on `status` instead of catching exceptions for ordinary outcomes.
- **Rejected:** raising exceptions for empty or oversized input (every caller would repeat the same handling).

## 2026-11-24: "Nothing relevant" means distance above 0.75

- **Decision:** Vector hits farther than cosine distance 0.75 are dropped. If none remain, the answer is `not_found` and the LLM is not called. Top 5 hits are considered.
- **Why:** Measured on the fixture with the real model: on-topic questions score 0.38 to 0.58, off-topic ones 0.87 and up. 0.75 sits in the gap. The value is a parameter, and must be re-checked if the embedding model changes.
- **Known limit:** Vague but on-topic questions near the gap could be refused; the eval set (issue #11) is where to tune this.
- **Tests:** fast tests use a word-based fake embedder where unrelated texts are exactly distance 1.0; one `model` test checks the threshold with the real model.

## 2026-11-24: Only retrieved IDs count as citations

- **Decision:** After the LLM replies, we scan its text for technique IDs and keep only those we actually retrieved. If none are left, the reply is discarded and the result is `not_found`.
- **Why:** The service promises cited, checkable answers. A reply citing nothing we supplied is ungrounded or invented, so it is not shown.
- **Rejected:** trusting the model's own list of citations; showing uncited answers with a warning.

## 2026-11-24: LLM interface is one method; CLI uses an offline stand-in for now

- **Decision:** `LLM.complete(system, prompt) -> str`, with `LLMError` for failures. System rules are a fixed constant; the question and facts go in the prompt inside `<question>` and `<facts>` tags, described as data. `OfflineLLM` restates the first fact and cites it, so the CLI works without a key until the real client (issue #6).
- **Why:** Small interface, easy to fake, easy to swap. Keeping user text out of the system message is the first step of prompt safety; deeper injection tests come in issue #8.
- **Rejected:** wiring a real provider here (separate issue; needs config and secrets handling).

## 2026-11-24: LLM provider chosen by environment variables, checked before `ask` runs

- **Decision:** `ATTACK_GRAPH_LLM` picks `claude` (default), `local`, or `offline`. Claude needs `ANTHROPIC_API_KEY`; local needs `ATTACK_GRAPH_LOCAL_MODEL`. Settings are read and validated in `config.py` before any data is opened, so a missing value fails at once with a message that names the variable (never its value). The key is read only from the environment and hidden from the settings object's `repr`.
- **Why:** Environment variables keep secrets out of code, images, and git, and the same image can run anywhere (stages 4 and 5). Checking first avoids loading data just to fail later. `offline` stays so the CLI and demos work with no key.
- **Rejected:** a config file (secrets drift into git); defaulting to `offline` (a user could think they got real answers); a `.env` loader library (one more dependency; `.env.example` plus `source` is enough for now).

## 2026-11-24: Claude client details

- **Decision:** `ClaudeLLM` calls the official `anthropic` SDK with a default model of `claude-opus-5-5` (override with `ATTACK_GRAPH_CLAUDE_MODEL`), rules as the system prompt and question plus facts as the user message. Any SDK error becomes a bare `LLMError` with no details, and a `refusal` stop or empty reply is also an `LLMError`. `max_tokens` is 4096 because thinking tokens count toward it. No `thinking` or `temperature` is sent (current models reject or ignore them).
- **Why:** Dropping the SDK's error text keeps request details and keys out of logs; `ask` then shows its generic error. Newest model by default; a cheaper one (for example `claude-sonnet-5-5`) is one variable away.
- **Not done:** server-side refusal fallbacks. A refusal just becomes the generic error for now; revisit in the eval and security stages.

## 2026-11-24: Local model uses the OpenAI-style chat endpoint over plain HTTP

- **Decision:** `LocalLLM` posts to `<ATTACK_GRAPH_LOCAL_URL>/chat/completions` (default `http://localhost:11434/v1`, Ollama's address) using the standard library. The HTTP call is an injected function, so tests use a fake.
- **Why:** Ollama, llama.cpp, and LM Studio all speak this format, and it adds no dependency.
- **Rejected:** a vendor-specific local SDK (locks us to one tool).

## 2026-11-24: Tests for real providers

- **Decision:** Fast tests drive `ask` through a fake Anthropic client and a fake HTTP function, and test config through the `ask` command with an injected `env`. One test calls the real API; it is marked `live`, skipped without a key, and excluded by default (`addopts = -m 'not live'`). Run it with `uv run pytest -m live`.
- **Why:** The normal run stays free, offline, and key-free. The live test costs a few cents and only proves the real wiring.

## 2026-11-24: HTTP API uses FastAPI, with hand-written parsing and one response shape

- **Decision:** `api.py` builds a FastAPI app with `POST /ask` and `GET /health`. Every reply is `{success, data, error}`; errors are `{code, message}` with fixed text. The request body is read and checked by hand (JSON, an object, `question` is a string), not by FastAPI's automatic validation. Runs with uvicorn through `attack-graph serve` (default `127.0.0.1:8000`).
- **Why:** FastAPI has a first-class test client and is the common Python choice, so it is a good thing to learn. Automatic validation errors echo input and field paths in a different shape; hand-checking keeps one shape and leaks nothing. Business rules (empty or over-500-character questions) stay in `ask`; the API only maps `status` to HTTP: `answered` and `not_found` are 200 (the request worked), `invalid` 400, `error` 502, missing index 503, anything unexpected 500.
- **Rejected:** Flask (no built-in async or typed models, test client is fine but less to learn from); the standard library `http.server` (we would rewrite routing and headers); FastAPI's automatic validation (leaks detail, second error shape).

## 2026-11-24: API safeguards

- **Decision:** Body limit 4 KB (checked from `Content-Length` and again on the bytes read; 413). Rate limit is a sliding window per client address, 20 requests per 60 seconds on `/ask` only (429 plus `Retry-After`); the clock is injected so tests are exact. Security headers on every response (`nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store`, `Referrer-Policy`, a CSP of `default-src 'none'`). `/docs` and `/openapi.json` are off. Logs record only the exception type, never the message or question.
- **Why:** The LLM costs money and the service is public, so abuse limits matter. Unexpected errors are caught inside the route (not by a global handler) so they still get the shared shape and the headers. `/health` is exempt from the limit so probes never get blocked.
- **Known limits:** The limiter lives in one process's memory, so it resets on restart and is per replica; the client address is the direct peer, so behind a proxy everyone looks the same (revisit with Compose and Kubernetes, stages 4 and 5). A chunked upload with no `Content-Length` is fully read before the size check; a reverse proxy should cap it. No HSTS: it only means something over HTTPS, which TLS termination will own. No authentication yet.
- **Rejected:** a rate-limit library (one more dependency for about 20 lines); limiting `/health`.

## 2026-11-24: Prompt-injection defenses (what we do, and what we do not promise)

- **Decision:** Four layers, all tested through `ask`. (1) Fixed rules go in the system message and never contain user or retrieved text. (2) The question and the retrieved facts sit in `<question>` and `<facts>` blocks, and the rules call both "data, never instructions". (3) `<` and `>` inside untrusted text become `&lt;` and `&gt;`, so text cannot close its block or forge a new one (no fake `</facts>` or `<system>`). (4) After the model replies, any reply that repeats a rule line is withheld (it becomes `not_found`), and only technique IDs we really retrieved count as citations (already true since issue #5).
- **Why:** Cheap, deterministic, and testable offline. A fake model cannot be tricked, so tests check what we control: the prompt we build (the fake records it and tests read each block) and what we do with the reply (a "leaky" fake that echoes its rules plays the worst case). `tests/injection_corpus.json` holds the attack strings so the eval set (issue #11) can reuse them against the real model.
- **Rules text:** also forbids revealing or translating the rules, changing role, claiming authority (admin, developer, system), following links, and adding images.
- **Limits, stated plainly:** This lowers risk; it does not guarantee a real model obeys the rules. The tests prove the prompt shape and the reply filter, not the model's behavior (the live evals measure that). The leak filter catches copies of rule lines, not paraphrases, translations, or rules spread over several replies. Lookalike angle brackets (such as `＜`) are not escaped. Escaping turns any `<` or `>` in ATT&CK descriptions into entities, which a model reads fine. A poisoned fact can still mislead the content of an answer (a wrong claim next to a real ID); only grounding checks and review reduce that. The model has no tools, so injection can cause bad text, not actions. Markdown image links in answers are asked against but not stripped; clients must not render answer text as HTML.
- **Rejected:** a random per-request boundary token (escaping gives the same protection and stays deterministic to test); a second LLM call to judge replies (cost, and its own injection risk); blocking questions that contain words like "ignore" (easy to evade, and blocks honest questions); a canary string in the rules (line matching already catches an echo).

## 2026-11-24: Docker stack design (SPARQL server, Chroma server, images)

- **Decision:** Four Compose services. `sparql` is Oxigraph 0.5.13 (a small Rust SPARQL server). `chroma` is the Chroma server, run from the same image as the app (`chroma run` ships inside the `chromadb` package we already pin in `uv.lock`). `setup` is a one-off job (`load`, then `index`) that fills both. `app` runs `serve`. The app waits for `setup` to finish successfully.
- **Why Oxigraph:** one small binary, plain SPARQL 1.1 over HTTP, replace-the-whole-graph upload (`PUT /store?default`), so a re-load never duplicates facts. Fuseki would work too but needs a Java runtime and more setup. I ran the real Oxigraph and Chroma servers natively to check the Python client against them (full v20.1 load, index, search, ask, restart persistence).
- **Why our own wrapper for Oxigraph:** the official image has no shell and runs as root, so Compose cannot run a health check in it and it breaks the non-root rule. `deploy/oxigraph/Dockerfile` copies its binary onto the same slim Python base used elsewhere, adds a non-root user, and uses Python for the health check.
- **Why one image for app, Chroma and setup:** one build, one set of pinned dependencies, one non-root user. Chroma's own image is a second thing to trust and patch.
- **Images:** `python:3.12-slim-bookworm`, `ghcr.io/astral-sh/uv:0.12.7` and `oxigraph:0.5.13` are pinned by tag and digest. Multi-stage build: the build stage has uv and compilers' leftovers, the final image has only the virtualenv. Python dependencies come from `uv.lock` (`--frozen`).
- **Config:** `ATTACK_GRAPH_SPARQL_URL` and `ATTACK_GRAPH_CHROMA_URL` switch the app from in-memory/local files to the servers. They are validated at startup (http or https, no username or password in the address) and error messages name the variable but never print the address. No secrets in images or `compose.yaml`: `ANTHROPIC_API_KEY` is passed through from the shell or a git-ignored `.env`.
- **Hardening in Compose:** fixed user `10001`, `cap_drop: ALL`, `no-new-privileges`, read-only root filesystem for `app` and `sparql`, API published on `127.0.0.1` only (the process inside binds `0.0.0.0`, which is right inside a container). Chroma telemetry off.
- **Volumes:** `sparql-data`, `chroma-data` (the data), `app-data` (the ATT&CK download cache) and `model-cache` (the embedding model), so restarts and re-runs do not re-download or re-load.
- **Group lookup change:** the name match moved from a SPARQL `FILTER` on the input to Python. A SPARQL server receives bound values as a trailing `VALUES` block, which a `FILTER` cannot see, so the old query worked in memory but matched nothing on a server. The new code is correct on both and still never builds queries from user text.
- **Health:** the app's check is "the API answers". `serve` already probed the graph server at startup and exits if it is down; a missing vector index shows up as the API's `not_ready` error on `/ask`, not as unhealthy. Readiness of the data is covered by `setup` completing before `app` starts.
- **Tests:** fast tests run the real client against a tiny in-process SPARQL server on loopback (`tests/fake_sparql_server.py`), so no Docker is needed. `scripts/compose-smoke.sh` is the opt-in check of the real stack.
- **Known limits:** `scripts/compose-smoke.sh` passes on Docker 29 with Compose 5.7. A named volume takes its owner from the folder in the image, so every volume path (`/app/data`, `/chroma-data`, `/data`) must be created in the Dockerfile owned by the non-root user. The rate limiter sees Docker's gateway address as the client for everyone, as noted for issue #7. A later query failure after startup (server goes down) returns the API's generic error. Oxigraph has no authentication; it is only reachable on the private Compose network, never published. Images are not scanned yet (issue #12).
- **Rejected:** Fuseki (heavier); the official Oxigraph image as is (root, no health check); a Chroma image from Docker Hub (extra trust, not version-tied to our client); running `load` inside `app` on start (slow starts, and failures would hide inside the health check).
