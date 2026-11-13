"""What every response carries, and what is written down about every request (decision 0025).

Written as plain ASGI rather than decorated middleware so that it also covers responses made
by error handlers, and so an unexpected exception becomes a plain 500 here: with no message,
no stack trace and no request data in the response or the log.
"""

import json
import logging
import re
import time
import traceback
import uuid
from types import TracebackType
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# The interactive API reference loads scripts, so it cannot carry the strict policy below.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def security_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "cross-origin-resource-policy": "same-origin",
        "permissions-policy": "camera=(), microphone=(), geolocation=()",
    }
    if settings.environment == "production":
        # Browsers remember to use HTTPS for a year, for this host and its subdomains.
        headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
    return headers


# An API response is data, never a page: nothing in it may run, load, or be framed.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class HttpSafetyMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._headers = security_headers(settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        started = time.perf_counter()
        path: str = scope["path"]
        outcome: dict[str, Any] = {"status": 500, "sent": False}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                outcome["status"] = message["status"]
                outcome["sent"] = True
                self._add_headers(message, path, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as error:
            _log_failure(error, request_id)
            if outcome["sent"]:
                raise
            await _send_failure(send_with_headers, request_id)
        finally:
            self._log_request(scope, request_id, outcome["status"], started)

    @staticmethod
    def _request_id(scope: Scope) -> str:
        for name, value in scope["headers"]:
            if name == REQUEST_ID_HEADER.encode():
                supplied = value.decode("latin-1")
                if _SAFE_REQUEST_ID.match(supplied):
                    return supplied
        return uuid.uuid4().hex

    def _add_headers(self, message: Message, path: str, request_id: str) -> None:
        headers: list[tuple[bytes, bytes]] = message.setdefault("headers", [])
        present = {name.lower() for name, _ in headers}

        def add(name: str, value: str) -> None:
            if name.encode() not in present:
                headers.append((name.encode(), value.encode()))

        for name, value in self._headers.items():
            add(name, value)
        add(REQUEST_ID_HEADER, request_id)
        if path.startswith("/api") and not path.startswith(_DOCS_PATHS):
            add("content-security-policy", API_CONTENT_SECURITY_POLICY)
            # Responses hold private records, so no browser or proxy should keep a copy.
            add("cache-control", "no-store")

    @staticmethod
    def _log_request(scope: Scope, request_id: str, status: int, started: float) -> None:
        route = scope.get("route")
        # The route's template, such as /api/organizations/{organization_id}/requests, never
        # the real path or the query string, which can hold ids, names and search text.
        template = getattr(route, "path", None) or "unmatched"
        logger.info(
            "%s %s %s %dms id=%s",
            scope["method"],
            template,
            status,
            (time.perf_counter() - started) * 1000,
            request_id,
        )


def frames_of(tb: TracebackType | None) -> str:
    """Where an error happened, as file, line and function: no source text, no values."""
    return "\n".join(
        f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in traceback.extract_tb(tb)
    )


def _log_failure(error: Exception, request_id: str) -> None:
    # The type and the place, but not the message: a database error's message can contain the
    # values of the query, and so a person's name or email address.
    logger.error(
        "Unhandled %s id=%s\n%s", type(error).__name__, request_id, frames_of(error.__traceback__)
    )


async def _send_failure(send: Send, request_id: str) -> None:
    body = json.dumps({"detail": "Something went wrong.", "request_id": request_id}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class PrivateLogFormatter(logging.Formatter):
    """One JSON object per line, and no exception messages."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            entry["error"] = type(error).__name__
            entry["frames"] = frames_of(record.exc_info[2])
        return json.dumps(entry)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(PrivateLogFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # The server's own access log prints the full URL, query string included.
    logging.getLogger("uvicorn.access").disabled = True
