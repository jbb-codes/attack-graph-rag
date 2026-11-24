# Security scan results

How to repeat every scan: [`scripts/security-scan.sh`](../../scripts/security-scan.sh) (source scans, no Docker) and `scripts/security-scan.sh images` (needs Docker and [trivy](https://trivy.dev)).
Findings the script accepts are listed in the script itself with a one-line reason; the full reasoning is here.

## Run 1: 2026-11-24 (source scans)

Run by the author's assistant on macOS, no Docker. Tools were run through `uvx` (nothing installed globally).

| Scan | Tool | Result |
| --- | --- | --- |
| Python dependencies in `uv.lock` (runtime only) | pip-audit 2.10.1 | 5 advisories, all in `chromadb` 1.5.9. Accepted, see below. |
| Our code | bandit 1.9.4 (medium and above) | 3 findings (`urlopen` with unchecked schemes). Fixed: see below. |
| Dockerfile (95 checks) | checkov | 0 failures |
| Kubernetes manifests (339 checks) | checkov | 6 kinds of finding, all accepted below |
| Secrets in files | checkov | 1 false positive (placeholder in `k8s/examples/secret.example.yaml`), marked in the file |

### Image scan: NOT RUN

Docker is not installed where this was built, so neither image (`attack-graph-rag`, `attack-graph-oxigraph`) was scanned.
**To do (needs Docker and trivy):** run `scripts/security-scan.sh images`, then fill in this table.

| Image | Date | Tool and version | HIGH | CRITICAL | Notes |
| --- | --- | --- | --- | --- | --- |
| attack-graph-rag:local | _not yet run_ | | | | |
| attack-graph-oxigraph:local | _not yet run_ | | | | |

Rule for the table: every HIGH or CRITICAL finding is either fixed (rebuild with a newer base image or package) or listed below with a reason. Both images use `python:3.12-slim-bookworm`, so expect most OS-package findings to be shared and fixed by bumping the pinned digest in `Dockerfile` and `deploy/oxigraph/Dockerfile`.

### Accepted: ChromaDB advisories (HIGH or CRITICAL class, no fix exists)

| Advisory | What it is | CVE |
| --- | --- | --- |
| PYSEC-2026-311 / GHSA-f4j7-r4q5-qw2c | unauthenticated code injection through the server's create-collection endpoint | CVE-2026-45829 |
| PYSEC-2026-3814 | code injection by an authenticated user with update permission | CVE-2026-45833 |
| PYSEC-2026-3813 | any authenticated user can read or change any tenant's data | CVE-2026-45830 |
| PYSEC-2026-3815 | the simple role-based access provider ignores which tenant or collection a permission is for | CVE-2026-45831 |

- **No fix:** OSV lists every release up to 1.5.9 as affected, and 1.5.9 is the newest on PyPI (checked 2026-11-24).
- **Why the risk is low here:** every advisory is about the Chroma *server's* HTTP API. In Compose the `chroma` service publishes no port and is only on the private project network. In Kubernetes it is a ClusterIP Service, reachable only inside the cluster. The app never sends `trust_remote_code`, and no user text reaches Chroma's collection endpoints (the app only runs similarity search through the client). The two authorization advisories need Chroma's optional auth provider, which we do not enable.
- **What would change that:** publishing the Chroma port, or an attacker already inside the network (a compromised app container could reach it; Compose has no network policy and kind does not enforce NetworkPolicy). Both are called out in the Compose and Kubernetes decisions.
- **Follow-up:** re-run the scan when a new chromadb ships, bump the pin, and delete the ids from `ACCEPTED_VULNS` in the script. A longer-term option is to stop running the Chroma server at all (embedded Chroma in the app, or another store).

### Fixed during this scan

- **`ATTACK_GRAPH_LOCAL_URL` was not validated** (bandit B310 on the local-model HTTP call). A value such as `file:///...` would have been opened by `urllib`. It now gets the same check as the graph and Chroma addresses: `http` or `https`, a host, no username or password, and the error names the variable without echoing the value. The other two `urlopen` calls were already safe (pinned `https` release URL, and the already-validated SPARQL address); they carry a `# nosec B310` comment with the reason.

### Accepted: Kubernetes manifest findings

| Check | Why accepted |
| --- | --- |
| CKV_K8S_43 image should use a digest | Images are built locally and loaded into kind, so there is no registry digest. Pin by digest when images move to a registry. (Base images in the Dockerfiles are already pinned by digest.) |
| CKV_K8S_15 pull policy should be Always | `Always` would try to download local-only images and fail. `IfNotPresent` is deliberate. |
| CKV_K8S_11 CPU limits should be set | Deliberately unset so the embedding model is not throttled; CPU is requested. |
| CKV_K8S_22 read-only root filesystem | Set on `app`, `sparql` and the init container. `chroma` and the setup Job write to their volumes and caches. |
| CKV_K8S_35 secrets as files, not env vars | The app reads all configuration from environment variables. The Secret is created from the shell and never stored in a file. |
| CKV2_K8S_6 NetworkPolicy | kind's default network plugin does not enforce them, so they would look protective and do nothing. Add them on a real cluster. |

### Not run

- **hadolint** (Dockerfile style linter): not installed. checkov's 95 Dockerfile checks covered the security-relevant rules (non-root user, health check, no `ADD` from URLs, pinned base).
- **trivy filesystem scan:** replaced by pip-audit for Python packages. Trivy's value here is the OS packages inside images, which needs the images.
