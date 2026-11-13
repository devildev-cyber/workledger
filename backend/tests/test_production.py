import json
import logging
import smtplib
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session
from support import ClientFactory, production_settings

from app.core.config import Settings
from app.core.http import PrivateLogFormatter, security_headers
from app.core.mail import EmailMessage, SmtpEmailSender, build_email_sender
from app.db.session import get_session

# --- Settings ----------------------------------------------------------------------------


def test_production_needs_https_postgresql_and_real_email() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, environment="production")

    message = str(caught.value)
    assert "frontend_url must use https://" in message
    assert "database_url must be PostgreSQL" in message
    assert "email_backend must be smtp" in message


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"frontend_url": "http://workledger.example"}, "frontend_url"),
        ({"database_url": "sqlite:///./workledger.db"}, "database_url"),
        ({"email_backend": "file"}, "email_backend"),
        ({"email_backend": "memory"}, "email_backend"),
    ],
)
def test_each_unsafe_production_setting_is_refused(override: dict[str, str], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        production_settings(**override)


def test_a_complete_production_configuration_is_accepted() -> None:
    assert production_settings().environment == "production"


def test_smtp_needs_a_host_in_every_environment() -> None:
    with pytest.raises(ValidationError, match="smtp_host"):
        Settings(_env_file=None, email_backend="smtp")


def test_the_smtp_password_is_not_shown_when_settings_are_printed() -> None:
    settings = production_settings(smtp_password="hunter2-hunter2")

    assert "hunter2" not in repr(settings)
    assert "hunter2" not in str(settings.model_dump())


# --- Email through SMTP ------------------------------------------------------------------


class FakeSmtp:
    """Stands in for smtplib so no network is used. Records what the sender did."""

    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.steps: list[str] = []
        self.sent: list[Any] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        self.steps.append("quit")

    def starttls(self, **_: Any) -> None:
        self.steps.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.steps.append(f"login {username} {password}")

    def send_message(self, message: Any) -> None:
        self.steps.append("send")
        self.sent.append(message)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    return FakeSmtp


def sender(**overrides: Any) -> SmtpEmailSender:
    values: dict[str, Any] = {
        "host": "smtp.example",
        "port": 587,
        "security": "starttls",
        "username": "mailer",
        "password": "s3cret",
        "from_address": "WorkLedger <no-reply@workledger.example>",
    }
    return SmtpEmailSender(**{**values, **overrides})


MESSAGE = EmailMessage(to="alex@example.com", subject="Hello", body="Line one\nLine two\n")


def test_smtp_upgrades_the_connection_before_logging_in(smtp: type[FakeSmtp]) -> None:
    sender().send(MESSAGE)

    [connection] = smtp.instances
    assert connection.steps == ["starttls", "login mailer s3cret", "send", "quit"]
    sent = connection.sent[0]
    assert sent["To"] == "alex@example.com"
    assert sent["From"] == "WorkLedger <no-reply@workledger.example>"
    assert sent["Subject"] == "Hello"
    assert "Line two" in sent.get_content()


def test_smtp_over_ssl_does_not_start_tls(smtp: type[FakeSmtp]) -> None:
    sender(security="ssl", port=465).send(MESSAGE)

    assert smtp.instances[0].steps == ["login mailer s3cret", "send", "quit"]


def test_a_local_relay_without_credentials_just_sends(smtp: type[FakeSmtp]) -> None:
    sender(security="none", username=None, password=None).send(MESSAGE)

    assert smtp.instances[0].steps == ["send", "quit"]


def test_a_connection_that_cannot_be_secured_sends_nothing(
    smtp: type[FakeSmtp], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: FakeSmtp, **_: Any) -> None:
        raise smtplib.SMTPException("STARTTLS extension not supported")

    monkeypatch.setattr(FakeSmtp, "starttls", refuse)

    with pytest.raises(smtplib.SMTPException):
        sender().send(MESSAGE)

    assert smtp.instances[0].sent == []


def test_the_smtp_backend_builds_the_smtp_sender() -> None:
    built = build_email_sender(
        production_settings(smtp_username="mailer", smtp_password="s3cret", smtp_port=2525)
    )

    assert isinstance(built, SmtpEmailSender)


def test_the_log_line_for_a_sent_email_has_no_address_or_body(
    smtp: type[FakeSmtp], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.core.mail"):
        sender().send(MESSAGE)

    assert "alex@example.com" not in caplog.text
    assert "Line one" not in caplog.text


# --- What every response carries ---------------------------------------------------------


def test_every_api_response_carries_the_security_headers(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


def test_errors_carry_the_headers_too(client: TestClient) -> None:
    for response in (client.get("/api/no-such-route"), client.get("/api/auth/me")):
        assert response.status_code in (401, 404)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"


def test_production_tells_browsers_to_insist_on_https(client_factory: ClientFactory) -> None:
    client = client_factory(production_settings())

    response = client.get("/api/health")

    assert response.headers["strict-transport-security"].startswith("max-age=31536000")
    assert "strict-transport-security" in security_headers(production_settings())


def test_a_download_keeps_its_own_cache_rule(client: TestClient) -> None:
    app = client.app
    router = APIRouter()

    @router.get("/api/test-cache")
    def cached() -> dict[str, str]:
        from fastapi.responses import JSONResponse

        return JSONResponse({"a": "b"}, headers={"Cache-Control": "private, max-age=5"})  # type: ignore[return-value]

    app.include_router(router)  # type: ignore[attr-defined]

    assert client.get("/api/test-cache").headers["cache-control"] == "private, max-age=5"


def test_the_api_reference_is_off_in_production(client_factory: ClientFactory) -> None:
    production = client_factory(production_settings())
    development = client_factory(Settings(_env_file=None, environment="development"))

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert production.get(path).status_code == 404
        assert development.get(path).status_code == 200
    # The reference loads scripts, so it must not carry the strict policy.
    assert "content-security-policy" not in development.get("/docs").headers


def test_a_request_id_is_returned_and_a_safe_one_is_kept(client: TestClient) -> None:
    assert len(client.get("/api/health").headers["x-request-id"]) == 32

    kept = client.get("/api/health", headers={"X-Request-ID": "abc-12345678"})
    assert kept.headers["x-request-id"] == "abc-12345678"

    replaced = client.get("/api/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert replaced.headers["x-request-id"] != "bad id\twith spaces"


# --- Logging that does not leak ----------------------------------------------------------


def test_requests_are_logged_by_route_without_query_strings(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/api/organizations/11111111-2222-3333-4444-555555555555/requests?search=Sam")
        client.get("/api/health")

    text = caplog.text
    assert "GET /health 200" in text
    assert "GET /organizations/{organization_id}/requests 401" in text
    assert "search=" not in text
    assert "Sam" not in text
    assert "11111111-2222" not in text


def test_an_unexpected_failure_is_a_plain_500_and_leaks_nothing(
    client_factory: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    client = client_factory(None)
    router = APIRouter()

    @router.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("could not find resident sam.okafor@demo.example (555-0142)")

    client.app.include_router(router)  # type: ignore[attr-defined]

    with caplog.at_level(logging.INFO):
        response = client.get("/api/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Something went wrong."
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "sam.okafor" not in response.text
    assert "x-content-type-options" in response.headers
    # The log names the kind of failure and where it happened, but not what it said.
    assert "RuntimeError" in caplog.text
    assert "boom" in caplog.text
    assert "sam.okafor" not in caplog.text
    assert "555-0142" not in caplog.text


def test_the_production_log_format_drops_exception_messages() -> None:
    try:
        raise ValueError("secret value: jordan.patel@demo.example")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "app.test", logging.ERROR, __file__, 1, "Could not do it", None, sys.exc_info()
        )

    line = PrivateLogFormatter().format(record)

    entry = json.loads(line)
    assert entry["message"] == "Could not do it"
    assert entry["error"] == "ValueError"
    assert "jordan.patel" not in line
    assert entry["level"] == "ERROR"


# --- Health ------------------------------------------------------------------------------


def test_readiness_checks_the_database(client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_fails_without_saying_why(
    client_factory: ClientFactory, db_session: Session
) -> None:
    client = client_factory(None)

    class BrokenSession:
        def execute(self, *_: object) -> None:
            raise RuntimeError("connection to postgres://workledger:hunter2@db failed")

    client.app.dependency_overrides[get_session] = lambda: BrokenSession()  # type: ignore[attr-defined]

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert "hunter2" not in response.text
    assert response.json()["detail"] == "Not ready"


def test_liveness_does_not_need_the_database(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
