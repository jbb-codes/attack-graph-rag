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
- **Knowledge graph:** a graph of facts about one topic (here ATT&CK). It gives exact answers, where vector search only gives close ones.
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
- **Ollama:** a free tool that runs open models on your own machine and serves them over a local HTTP address.

## HTTP API

- **HTTP API:** a program other programs talk to over the web, with requests and replies.
- **FastAPI:** the Python web framework we use. Like Express, with typed helpers.
- **uvicorn:** the server that runs a FastAPI app. Like `node server.js`.
- **Endpoint:** one URL plus method, such as `POST /ask`.
- **Response shape:** the fixed JSON layout every reply uses: `success`, `data`, `error`.
- **Status code:** the number in a reply: 200 fine, 400 your mistake, 429 slow down, 500 our crash.
- **Rate limiting:** refusing a client that sends too many requests too fast.
- **Sliding window:** counting requests in the last N seconds, not in fixed clock slots.
- **Retry-After:** a reply header saying how many seconds to wait.
- **Injected clock:** time passed in as a function so tests can move it by hand.
- **Security headers:** reply headers that tell browsers to be strict, such as `nosniff`.
- **Health endpoint:** a cheap URL that says the service is up, for monitors.
- **Stack trace:** the list of code locations from a crash. Never show it to clients.
- **Test client:** calls the app in memory, with no real network or port.
- **Embed (verb):** turn a piece of text into its vector of numbers. We embed every technique at `index` time and the question at search time.
- **MiniLM (`all-MiniLM-L6-v2`):** the small model that makes our embeddings (384 numbers per text). Runs on your CPU, no key, one ~80 MB download.
- **Citation check:** after the LLM replies, we keep only technique IDs we really retrieved. A reply citing none is thrown away.

## Prompt injection

- **Prompt injection:** text that tries to give the model new orders ("ignore your rules"). The model cannot always tell data from instructions.
- **Untrusted data:** any text we did not write: the question, and the retrieved ATT&CK text.
- **Delimiter breakout:** untrusted text writing `</facts>` to end its block early and pose as rules.
- **Escaping:** replacing `<` and `>` with `&lt;` and `&gt;` so text cannot form a tag.
- **Prompt leak:** the model repeating its rules back to the user.
- **Output filter:** a check on the reply before the user sees it.
- **Poisoned data:** retrieved text with an attack hidden inside.
- **Injection corpus:** a file of attack strings reused by many tests.
- **Defense in depth:** several weak layers together, since none is a guarantee.

## Docker and Compose

- **Image:** a frozen, packaged copy of a program plus everything it needs to run. Like a zipped, ready-to-run `node_modules` and Node.
- **Container:** a running copy of an image, isolated from the rest of your machine. Throw it away and start another any time.
- **Dockerfile:** the recipe for building an image, one instruction per step.
- **Layer:** each Dockerfile step is saved. Unchanged steps are reused, so rebuilds are fast.
- **Multi-stage build:** build in one image, copy only the result into a clean final one, so build tools never ship.
- **Digest (`@sha256:...`):** a fingerprint of an exact image. Pinning it means a rebuild gets identical bytes.
- **Volume:** a folder Docker keeps outside the container, so data survives it being removed.
- **Bind to 0.0.0.0:** listen on every network address inside the container. Safe, because Compose picks what is reachable from outside.
- **Port mapping:** `127.0.0.1:8000:8000` opens container port 8000 on your machine only.
- **Healthcheck:** a command Docker runs repeatedly. Exit 0 means the container is `healthy`.
- **Docker Compose:** one file (`compose.yaml`) that describes several containers and starts them together.
- **Service:** one container definition in Compose, such as `sparql` or `app`.
- **`depends_on` with a condition:** wait until another service is healthy, or finished successfully, before starting.
- **One-off job:** a service that does its work and exits, like `setup`. Restarting it is safe because it is idempotent.
- **Non-root user:** the container's program runs as an ordinary user, so a break-in has less power.
- **Capability:** one small slice of root's powers. `cap_drop: ALL` removes them all.
- **Read-only filesystem:** the container cannot write files except where a volume or `/tmp` is mounted.
- **SPARQL server (Oxigraph):** a separate program that stores the graph and answers SPARQL over HTTP.
- **Chroma server:** Chroma run as its own program, so the vector index lives outside the app.
- **Smoke test:** a quick check that the whole thing starts and does its main job.

- **Kubernetes (k8s):** software that runs containers across machines and keeps them matching the YAML you gave it.
- **kind:** Kubernetes in Docker; makes a throwaway local cluster for learning and tests.
- **Cluster / node:** the whole Kubernetes system, and one machine inside it.
- **Pod:** one running copy of your program (a container, plus its network). Pods are disposable; Kubernetes replaces them freely.
- **Deployment:** a standing order: "keep 1 copy of this pod running". If the pod crashes or you edit the YAML, it makes a fresh one.
- **Service (Kubernetes):** a permanent name for a group of pods. Pods get a new address every restart, so other programs call `http://sparql:7878` and Kubernetes forwards to whichever pod is alive. `ClusterIP` means reachable only inside the cluster.
- **Namespace:** a named folder for cluster objects; deleting it deletes everything in it.
- **ConfigMap:** plain, non-secret settings handed to pods as environment variables.
- **Secret (Kubernetes):** sensitive settings handed to pods. Base64 only, not encryption.
- **PVC (PersistentVolumeClaim):** a request for a disk, like "I need 2 GB to keep the graph". A pod's own files vanish when it is replaced; a PVC's disk stays, and the next pod gets it back.
- **Probe:** a health check Kubernetes runs on a timer. Readiness: "ready for traffic?" Liveness: "alive? If not, restart." Startup: "still booting, wait."
- **Job (Kubernetes):** a pod that runs once to completion.
- **initContainer:** a container that must finish before the pod's main containers start.
- **Label and selector:** key-value tags on objects, and the query a Deployment or Service uses to find them.
- **Pod Security level `restricted`:** a namespace setting; Kubernetes refuses pods that are root or hold extra privileges.
- **Port-forward:** `kubectl port-forward` opens a local port that tunnels to a Service or pod.
- **Resource request / limit:** the memory and CPU a pod reserves, and the ceiling it is killed or throttled at.
- **Volume:** a disk or folder mounted into a container. A PVC is how a pod asks for one that lasts.
- **Cluster:** the whole Kubernetes system. **Node:** one machine in it. kind makes a one-node cluster inside Docker.
- **YAML manifest:** a text file describing what you want ("a Deployment named app"). `kubectl apply -f` makes the cluster match it.
- **MiniLM (`all-MiniLM-L6-v2`):** the small embedding model (about 80 MB) that turns text into 384 numbers, run on your machine.
- **Oxigraph:** the program that stores the graph facts and answers SPARQL over HTTP.
- **kubectl apply:** make the cluster match the YAML files given.

## Evals

- **Eval set:** a fixed list of questions with known-good expectations, used to measure answer quality.
- **Eval run:** asking every eval question once and scoring the replies. Uses the real model, so it costs a little and only runs on request.
- **Case kinds:** `specific` (names one technique), `vague` (everyday wording), `unsupported` (should be refused), `injection` (an attack hidden in a question).
- **Score check:** a simple yes/no test on one reply: right status, expected IDs cited, required words present, forbidden words absent.
- **Forbidden text:** words an attack tries to force into the answer (like `PWNED`). Seeing them means the attack worked.
- **Results file:** one JSON per run in `eval-results/` (git-ignored), so runs can be compared.
- **Regression:** a case that passed in the previous run and fails now.
