"""Security-relevant events, logged as one `event=name key=value ...` line each.

Policy (see docs/decisions.md): an event carries its type, a reason and safe
numbers (lengths, sizes, seconds). Never the question, the reply, a request
body, an API key, an exception message or a raw IP address. Callers pass only
values they built themselves, so nothing from a request can reach a log line.
"""

import hashlib
import hmac
import logging
import secrets
import sys

SECURITY_LOGGER = "attack_graph.security"

_log = logging.getLogger(SECURITY_LOGGER)


def log_event(event: str, *, level: int = logging.WARNING, **fields: str | int) -> None:
    parts = [f"event={event}", *(f"{key}={_one_token(value)}" for key, value in fields.items())]
    _log.log(level, " ".join(parts))


def _one_token(value: str | int) -> str:
    # Whitespace would let a value forge extra key=value pairs or lines.
    return "".join(str(value).split()) or "-"


class ClientIds:
    """Turns a client address into a short opaque id.

    The key is random per process and never stored, so an id shows that one
    client is hammering the API, but cannot be turned back into an address and
    changes on restart.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)

    def of(self, address: str) -> str:
        return hmac.new(self._key, address.encode(), hashlib.sha256).hexdigest()[:12]


class _StderrHandler(logging.StreamHandler):
    """Looks sys.stderr up on every write, so redirected output is honored."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def stream(self):  # type: ignore[override]
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


def configure_logging() -> None:
    """Show the app's INFO-and-up logs on stderr (Python hides them by default). Safe to call twice."""
    app_logger = logging.getLogger("attack_graph")
    if any(isinstance(h, _StderrHandler) for h in app_logger.handlers):
        return
    handler = _StderrHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
