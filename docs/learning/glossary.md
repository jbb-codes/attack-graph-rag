# Glossary

Plain-English keywords for a Node/TS developer new to Python, RDF, and SPARQL. One line each. New terms are added as issues are implemented.

## ATT&CK data

- **ATT&CK:** MITRE's public catalog of attacker behavior.
- **Technique:** one attacker method, with an ID like `T1566` (phishing).
- **Group:** an attacker crew, like APT29 (`G0016`).
- **Software:** malware or tools attackers use (`S...`).
- **Mitigation:** a defense against a technique (`M...`).
- **Tactic:** the goal a technique serves, like `persistence`.
- **STIX:** the JSON format MITRE publishes ATT&CK in. It has objects plus "relationship" objects that link them.
- **Fixture:** a small fake dataset for tests, so they run fast and offline.

## Graph and queries

- **RDF:** a way to store facts as `subject - predicate - object` triples.
- **Triple:** one fact, like `T1566 - hasName - "Phishing"`.
- **Graph:** a pile of triples. Things link to other things.
- **SPARQL:** SQL for triples. You describe a pattern and it returns every match.
- **rdflib:** the Python library that holds the graph and runs SPARQL.
- **`initBindings`:** safely plugs values into a query, like a `?` placeholder in SQL.

## Tooling and testing

- **Seam:** the one place tests plug in. Later this will be `ask()`.
- **Exit code:** 0 means success, 1 means "not found", 2 means bad input.
- **stdout / stderr:** normal output vs error output.
- **Entry point:** a command name mapped to a function.
- **venv:** an isolated folder of packages for one project.
- **Lockfile:** an exact record of installed versions, so every machine gets the same ones.

## Loading real data

- **Pinned version:** one exact ATT&CK release we always use, so results are repeatable.
- **Checksum (SHA-256):** a fingerprint of a file. If the download's fingerprint differs, it is corrupt or tampered with.
- **Idempotent:** running it twice gives the same result as running it once.
- **N-Triples:** the simplest text format for RDF: one triple per line. Our saved graph is one.
- **Atomic write:** write to a temp file, then rename it. A crash never leaves a half-written file.
- **Dependency injection:** passing in a collaborator (here, the downloader) so tests can swap in a fake.

## Search by meaning

- **Embedding:** a text turned into a list of numbers. Similar meaning gives similar numbers.
- **Embed (verb):** turn text into numbers that capture its meaning.
- **Embedding model:** the program that makes embeddings. Ours is `all-MiniLM-L6-v2`, run locally.
- **Vector:** that list of numbers (384 of them for our model).
- **Vector search:** embed the question, then find the stored vectors closest to it.
- **Cosine distance:** how far apart two vectors point. Smaller means closer in meaning.
- **Chroma:** a vector database. It stores vectors and finds the closest ones fast. Ours runs embedded, saved in a folder.
- **Collection:** Chroma's "table". Ours is `techniques`.
- **Index (verb):** embed every technique and store it. We rebuild it from scratch each time.
- **Protocol:** a Python interface. Anything with the right methods fits, no `implements` needed.
- **Embed (verb):** run text through the embedding model to get its vector.
- **VectorStore:** our two-method interface (`index`, `search`). The rest of the app depends on it, not on Chroma.
- **Embedder:** the `embed` function passed into the store. Production uses the real model, tests use a tiny fake.
- **Retrieval:** finding the relevant facts before any answer is written.

## The ask pipeline

- **RAG:** retrieval-augmented generation. Fetch facts first, then let the LLM write only from them.
- **LLM:** a large language model. Text in, text out.
- **System prompt:** fixed rules sent to the LLM, separate from the user's text.
- **Prompt:** the question and facts we send for one request.
- **Grounded:** an answer backed by facts we supplied, not the model's memory.
- **Citation:** a technique ID in the answer, so a reader can check the source.
- **Fake LLM:** a test stand-in that answers instantly, for free, the same way every time.
- **Relevance cutoff:** the distance above which a search hit counts as unrelated (0.75).
- **Not found:** our answer when nothing relevant exists. The LLM is not called.

## Real LLM and configuration

- **Provider:** who runs the model: Claude (Anthropic's API), a local model, or the offline stand-in.
- **Environment variable:** a named setting outside the code, set in your shell. Like `process.env.X`.
- **API key:** a secret password for the Claude API. Lives only in an environment variable.
- **Fail fast:** check settings at startup and stop with a clear message, instead of failing later.
- **`.env.example`:** a template of settings with no real values. Safe to commit; your `.env` is not.
- **Anthropic SDK:** Anthropic's official Python library for calling Claude.
- **Local model:** a model running on your own machine (for example via Ollama). No key, no cost.
- **OpenAI-style API:** a common chat HTTP format that many local servers copy.
- **Refusal:** Claude declining a request; we turn it into our generic error.
- **Live test:** a test that calls the real API. It costs a little, so it only runs on request.
