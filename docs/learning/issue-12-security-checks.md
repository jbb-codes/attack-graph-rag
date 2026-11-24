# Issue #12: Security checks

What was built: security-event logging that carries no sensitive data, a scan script (dependencies, our code, Dockerfile and Kubernetes files, and images when Docker exists), recorded results, and a review of every item on the project security checklist.

Related: [glossary](glossary.md), [Python for Node/TS developers](python-for-node-devs.md), [issue #7](issue-07-http-api.md), [issue #8](issue-08-prompt-injection-defenses.md), [decisions](../decisions.md), [scan results](../security/scan-results.md), [checklist review](../security/checklist-review.md).

Note: Docker was not available, so **the container images were not scanned**. The results page has an empty table and the one command to fill it (`scripts/security-scan.sh images`).

## New ideas in plain English

- **Security event:** one log line saying something suspicious happened (too many requests, bad input). It says what and why, never the content.
- **Log policy:** type, reason and numbers only. No question text, no keys, no exception messages, no addresses.
- **Opaque client id:** the caller's address run through a keyed hash. You can tell "the same caller again" but not who it is, and it resets on restart.
- **Vulnerability scan:** compare the exact versions you ship against a public list of known bugs (CVEs).
- **Accepted finding:** a known issue we chose to keep, written down with the reason. Not hidden, not ignored.
- **Image scan vs source scan:** an image also contains the operating system's packages, which the lockfile does not list. Only an image scan sees them.

## The big picture

**Key**

- **Teal boxes are data:** requests, log lines, reports.
- **Purple boxes are code:** programs and functions.

```mermaid
---
config:
  flowchart:
    padding: 24
    wrappingWidth: 300
---
flowchart TD
  REQ["`**request**
  question, address`"] --> API["`**api.py**
  checks input`"]
  API --> ANS["`**Answerer**
  reply checks`"]
  API --> LOG["`**log_event**
  type + reason + numbers`"]
  ANS --> LOG
  REQ --> IDS["`**ClientIds**
  address to hash`"]
  IDS --> LOG
  LOG --> LINE["`**event line**
  no question text`"]
  LOCK["`**uv.lock**
  pinned packages`"] --> SCAN["`**security-scan.sh**
  audit and lint`"]
  FILES["`**Dockerfile, k8s**
  config files`"] --> SCAN
  IMG["`**images**
  needs Docker`"] --> SCAN
  SCAN --> RES["`**scan-results.md**
  findings and reasons`"]
  classDef data fill:#9FE1CB,stroke:#0F6E56,stroke-width:2px,color:#04342C
  classDef code fill:#CECBF6,stroke:#534AB7,stroke-width:2px,color:#26215C
  class REQ,LINE,LOCK,FILES,IMG,RES data
  class API,ANS,LOG,IDS,SCAN code
```

## Files and purpose

- `src/attack_graph/security_log.py`: `log_event`, `ClientIds`, `configure_logging`.
- `src/attack_graph/api.py`: logs rate-limit hits, rejected input, crashes.
- `src/attack_graph/answer.py`: logs model failures and withheld replies.
- `src/attack_graph/cli.py`: turns logging on for `serve` and turns the address-printing access log off.
- `src/attack_graph/config.py`: `ATTACK_GRAPH_LOCAL_URL` is now checked like the other addresses.
- `tests/test_security_events.py`: events appear, and secrets never do.
- `scripts/security-scan.sh`: the repeatable scans.
- `docs/security/scan-results.md`: what the scans found and why each kept finding is accepted.
- `docs/security/checklist-review.md`: every checklist item as pass, fail or n/a, with evidence.
- `docs/decisions.md`: the logging policy and the scan choices.

## Code tour

### security_log.py

- `log_event("rate_limited", client=..., retry_after=5)` writes `event=rate_limited client=... retry_after=5`. Values lose their whitespace so one value cannot fake a second field.
- `ClientIds.of(address)` is an HMAC with a random key made at startup. The key is never saved.
- `configure_logging()` adds a stderr handler once. Python hides INFO logs unless something configures them.

### api.py and answer.py

- Each place that rejects or withholds something calls `log_event` with a reason and a length, never the text itself.
- Crashes log only the exception's class name: the message could hold a key or the question.

### tests/test_security_events.py

- The tests plant a secret-looking question, key and exception message, trigger each event, and assert the log contains the event but none of the secrets (`caplog` captures log output).

### scripts/security-scan.sh

- `pip-audit` reads the packages from `uv.lock`; `bandit` reads our Python; `checkov` reads the Dockerfile and Kubernetes files. `images` mode builds both images and runs `trivy`.
- Accepted findings are listed at the top of the script with a reason, so a new finding still fails the run.

## What to try

1. **Run the scans:** `scripts/security-scan.sh` (needs internet, no Docker).
2. **Image scan:** with Docker and trivy installed, `scripts/security-scan.sh images`, then fill in the table in `scan-results.md`.
3. **See an event:** run `uv run attack-graph serve`, send `curl -s localhost:8000/ask -d 'not json'`, and read the `input_rejected` line on stderr.
