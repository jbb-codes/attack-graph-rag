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
- **RAG:** retrieval first, then an LLM writes an answer from only those facts.
- **LLM:** a chat model that writes text. It is not used in this issue.
