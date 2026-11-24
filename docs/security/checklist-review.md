# Security checklist review

Checked against the project checklist (OWASP Top Ten 2025 aligned) on 2026-11-24, at the end of issue #12.
Status is **pass**, **fail** (a real gap, left open and listed under "Open gaps"), or **n/a** (does not apply to this service, with the reason).
"Evidence" points at code or tests you can read; `uv run pytest` runs them all.

Scope reminder from the spec: no accounts, no authentication, public ATT&CK data, no personal data stored. That is why several items are n/a.

## A01: Broken access control

| Item | Status | Evidence |
| --- | --- | --- |
| Authorization on every endpoint (deny by default) | n/a | No users or roles exist (spec: out of scope). Only `GET /health` and `POST /ask` exist; every other route and method returns 404 or 405 (`test_unknown_route_and_wrong_method_use_shared_shape`). |
| No IDOR | n/a | No per-user resources and no ids taken from the client. |
| CSRF protection | n/a | No cookies, sessions or browser-held credentials, so a forged cross-site request has no authority to borrow. |
| Rate limiting on all endpoints | pass | `/ask` is limited per client (20 per 60 s, 429 plus `Retry-After`): `test_api.py` rate-limit tests. `/health` is deliberately exempt so probes are never blocked; it does no work. Unknown routes cost almost nothing. Limit is per process and per direct peer address (see gaps). |

## A02: Security misconfiguration

| Item | Status | Evidence |
| --- | --- | --- |
| Security headers set in code | pass | `_SECURITY_HEADERS` in `api.py` on every response (`nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store`, `Referrer-Policy`, CSP `default-src 'none'`); tested in `test_api.py`. No HSTS: it only means something over HTTPS (see A04). |
| Debug mode and stack traces off | pass | `docs_url`, `redoc_url`, `openapi_url` disabled; no `reload` or `debug` anywhere; crashes return a fixed message (`test_unexpected_crash_leaks_no_internals_and_logs_no_question`). |
| Container and cluster hardening | pass | Non-root uid 10001, dropped capabilities, no-new-privileges, read-only filesystems where possible, `restricted` Pod Security level. checkov: 0 Dockerfile failures; Kubernetes findings accepted with reasons in [scan-results.md](scan-results.md). |

## A04: Cryptographic failures

| Item | Status | Evidence |
| --- | --- | --- |
| No hardcoded secrets | pass | Keys come only from the environment (`config.py`). checkov secret scan clean (one placeholder marked). `.env` is git-ignored; `.env.example` holds names only. `LLMSettings.api_key` has `repr=False`. |
| Sensitive data encrypted at rest and in transit | fail (accepted for now) | Nothing sensitive is stored (public data; the only secret is the API key, held in the environment or a Kubernetes Secret, which is base64 only unless the cluster encrypts). In transit: the app speaks plain HTTP on `127.0.0.1` and between containers; the call to the Claude API uses TLS (SDK default). No TLS in front of our own API. Needs a TLS-terminating proxy before any non-local use. |
| Strong algorithms only | pass | Only SHA-256 (checksum of the pinned ATT&CK file, `release.py`) and HMAC-SHA-256 (opaque client ids, `security_log.py`). No MD5, SHA-1 or DES anywhere in `src`. |
| Passwords hashed with bcrypt or Argon2 | n/a | No passwords. |

## A05: Injection

| Item | Status | Evidence |
| --- | --- | --- |
| All user input validated | pass | Body limit 4 KB, JSON object with a string `question`, question 1 to 500 characters after control characters are stripped (`answer.py`, `api.py`); startup settings validated in `config.py`. Gibberish and oversized input tests in `test_ask.py` and `test_api.py`. |
| Parameterized queries only (SQL) | pass | No SQL. SPARQL: user values go through rdflib `initBindings`; the one f-string in `graph.py` (`_refs`) interpolates fixed pattern constants, never request data. |
| XSS prevention | pass | The API returns only JSON with `nosniff` and a `default-src 'none'` CSP; there is no HTML. Clients must not render answer text as HTML (stated in decisions). |
| No dynamic queries or commands from user input | pass | No `subprocess`, `os.system`, `eval`, `exec` in `src`. Prompt injection is a separate defense: [issue #8 tests](../../tests/test_prompt_injection.py). |
| Outbound URLs from user input (SSRF-style) | pass | No request data ever becomes a URL. Configured addresses must be `http(s)` with no credentials. **Gap found and fixed:** `ATTACK_GRAPH_LOCAL_URL` was unchecked (`test_local_model_address_must_be_plain_http_without_credentials`). |

## A07: Authentication failures

| Item | Status | Evidence |
| --- | --- | --- |
| Auth checks on protected routes | n/a | No protected routes; the API is open by design and meant for localhost or a private network. Anyone who can reach it can spend the model budget, which the rate limit only slows. |
| Session tokens invalidated on logout | n/a | No sessions. |
| Brute-force protection on login | n/a | No login. The rate limit covers repeated requests generally. |

## A08: Software or data integrity failures

| Item | Status | Evidence |
| --- | --- | --- |
| Deserialization of untrusted data avoided or validated | pass | Request bodies are parsed with `json.loads` only. No `pickle` or unsafe YAML in `src`. The downloaded ATT&CK file is checked against a pinned SHA-256 before use (`release.py`) and its structure is validated on load. Base images and `uv` are pinned by digest; Python packages by `uv.lock`. |
| Known-vulnerable dependencies | fail (accepted) | 5 ChromaDB server advisories with no fix. Mitigations and reasoning in [scan-results.md](scan-results.md). |

## A09: Logging failures

| Item | Status | Evidence |
| --- | --- | --- |
| Security-relevant events logged | pass | `rate_limited`, `input_rejected` (with reason), `reply_withheld` (rules leak or ungrounded), `answer_failed`, `internal_error`, `index_missing`: `tests/test_security_events.py`. Not applicable: login failures and access denials (no login, no roles). |
| No sensitive data in logs | pass | Events hold a type, a reason and numbers only. Tests assert that question text, request bodies, API-key-like strings, exception messages and raw addresses never appear. Client addresses are replaced by a keyed hash that changes on every restart. The server access log (which prints addresses) is turned off. |

## A10: Mishandling of exceptional conditions

| Item | Status | Evidence |
| --- | --- | --- |
| Errors do not leak data or stack traces | pass | Fixed error messages and one response shape (`test_api.py`). Exception text is never logged, only its type. |
| Error paths fail closed | pass | A model failure or a reply that leaks the rules or cites nothing retrieved becomes an error or "not found", never the raw reply (`test_prompt_injection.py`). Missing configuration stops startup. |
| Unhandled exceptions caught at service boundaries | pass | `ask` route catches everything and answers `internal_error`; unknown routes and methods use the same shape. |

## Secret management

| Item | Status | Evidence |
| --- | --- | --- |
| No secrets in source | pass | See A04. |
| Environment variables or a secret manager | pass | Environment only; Compose passes it through from the shell; Kubernetes uses a Secret created from the shell. |
| Required secrets validated at startup | pass | `load_llm_settings` fails before any data is touched (`test_llm_config.py`). |

## Open gaps (not fixed in this issue)

1. **No TLS or authentication on our API.** Fine for localhost and a private network; not for exposure. Put a TLS-terminating proxy with auth in front before any wider use.
2. **ChromaDB server advisories** with no upstream fix (scan-results.md). Re-scan when a new release ships.
3. **Rate limiter sees the direct peer only.** Behind Docker's gateway, `kubectl port-forward` or a proxy, everyone looks like one client, so one caller can use up everyone's allowance. Per process, so also per replica.
4. **Container images not yet scanned.** Needs Docker: run `scripts/security-scan.sh images` and fill in [scan-results.md](scan-results.md).
5. **No NetworkPolicy** on Kubernetes (kind does not enforce them): a compromised pod could reach Chroma.
6. **Chunked uploads with no `Content-Length`** are read in full before the size check; a reverse proxy should cap request size.
