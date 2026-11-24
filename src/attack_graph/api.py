"""Thin HTTP layer over `Answerer.ask`.

Every response, success or failure, has the same shape:
`{"success": bool, "data": ... | null, "error": {"code", "message"} | null}`.
Error messages are fixed strings: no stack traces, paths, or library text ever
reach the client. Business rules (question limits, citations) stay in `ask`.
"""

import json
import logging
import logging
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from attack_graph.answer import Answer, Answerer
from attack_graph.security_log import ClientIds, log_event
from attack_graph.vector import VectorStoreError

# A question is at most 500 characters; this leaves room for JSON escaping and
# keeps a huge body from ever being parsed.
MAX_BODY_BYTES = 4096
# Past this many tracked clients, idle ones are dropped so memory stays bounded.
_SWEEP_THRESHOLD = 10_000

Clock = Callable[[], float]

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    # An API returns only JSON, so nothing may load or run in a browser.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}

_ERRORS = {
    "invalid_request": (400, "The request body must be JSON like {\"question\": \"...\"}."),
    "invalid_question": (400, "The question is not valid."),
    "payload_too_large": (413, f"The request body is too large (limit {MAX_BODY_BYTES} bytes)."),
    "rate_limited": (429, "Too many requests. Please slow down."),
    "answer_failed": (502, "The answer could not be generated. Please try again."),
    "not_ready": (503, "The service is not ready yet."),
    "internal_error": (500, "Something went wrong."),
    "not_found": (404, "No such endpoint."),
    "method_not_allowed": (405, "Method not allowed."),
}


@dataclass(frozen=True)
class RateLimit:
    max_requests: int = 20
    window_seconds: float = 60.0


class _SlidingWindowLimiter:
    """Allows `max_requests` per client in any `window_seconds` span."""

    def __init__(self, limit: RateLimit, clock: Clock) -> None:
        self._limit = limit
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}

    def retry_after(self, client: str) -> int | None:
        """None if the request may proceed (and is counted); else whole seconds to wait."""
        now = self._clock()
        cutoff = now - self._limit.window_seconds
        if len(self._seen) > _SWEEP_THRESHOLD:
            self._seen = {k: v for k, v in self._seen.items() if v and v[-1] > cutoff}
        hits = self._seen.setdefault(client, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self._limit.max_requests:
            return max(1, math.ceil(hits[0] + self._limit.window_seconds - now))
        hits.append(now)
        return None


def create_app(
    answerer: Answerer,
    *,
    rate_limit: RateLimit = RateLimit(),
    clock: Clock = time.monotonic,
) -> FastAPI:
    # No interactive docs or schema: less surface for an API this small.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    limiter = _SlidingWindowLimiter(rate_limit, clock)
    client_ids = ClientIds()

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "internal_error")
        return _fail(code)

    @app.get("/health")
    async def health() -> JSONResponse:
        return _ok({"status": "ok"})

    @app.post("/ask")
    async def ask(request: Request) -> JSONResponse:
        client = request.client.host if request.client else "unknown"
        wait = limiter.retry_after(client)
        if wait is not None:
            log_event("rate_limited", client=client_ids.of(client), retry_after=wait)
            return _fail("rate_limited", headers={"Retry-After": str(wait)})

        question = await _read_question(request)
        if isinstance(question, JSONResponse):
            return question

        try:
            answer = await run_in_threadpool(answerer.ask, question)
        except VectorStoreError:
            log_event("index_missing", level=logging.ERROR)
            return _fail("not_ready")
        except Exception as exc:
            # Only the exception type is logged: its message may hold secrets or the question.
            log_event("internal_error", level=logging.ERROR, error=type(exc).__name__)
            return _fail("internal_error")
        return _answer_response(answer, question)

    return app


async def _read_question(request: Request) -> str | JSONResponse:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return _reject("payload_too_large", "payload_too_large", size=int(declared))
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return _reject("payload_too_large", "payload_too_large", size=len(raw))
    try:
        payload = json.loads(raw)
    except ValueError:
        return _reject("invalid_request", "invalid_json", size=len(raw))
    question = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(question, str):
        return _reject("invalid_request", "missing_question", size=len(raw))
    return question


def _reject(code: str, reason: str, **fields: int) -> JSONResponse:
    log_event("input_rejected", reason=reason, **fields)
    return _fail(code)


def _answer_response(answer: Answer, question: str) -> JSONResponse:
    if answer.status == "invalid":
        # Only the length is logged: the question itself may hold anything.
        reason = "empty" if not question.strip() else "too_long"
        log_event("input_rejected", reason=reason, length=len(question.strip()))
        return _fail("invalid_question", message=answer.text)
    if answer.status == "error":
        return _fail("answer_failed")
    return _ok({
        "status": answer.status,
        "answer": answer.text,
        "cited": [_ref(r) for r in answer.cited],
        "retrieved": [_ref(r) for r in answer.retrieved],
    })


def _ref(ref: Any) -> dict[str, str]:
    return {"attack_id": ref.attack_id, "name": ref.name}


def _ok(data: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"success": True, "data": data, "error": None})


def _fail(
    code: str,
    *,
    message: str | None = None,
    status: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    default_status, default_message = _ERRORS.get(code, (400, ""))
    body = {"success": False, "data": None, "error": {"code": code, "message": message or default_message}}
    return JSONResponse(body, status_code=status or default_status, headers=headers)
