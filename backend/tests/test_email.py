import email
from email import policy
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import EmailSenderDep
from app.core.config import Settings
from app.core.mail import (
    EmailMessage,
    FileEmailSender,
    MemoryEmailSender,
    build_email_sender,
)

MESSAGE = EmailMessage(
    to="alex@example.com",
    subject="You are invited",
    body="Join Harbor: https://workledger.example/invite/abc123\n",
)


def test_memory_sender_records_messages_in_order() -> None:
    sender = MemoryEmailSender()
    second = EmailMessage(to="sam@example.com", subject="Hello", body="Hi")

    sender.send(MESSAGE)
    sender.send(second)

    assert sender.sent == [MESSAGE, second]
    sender.clear()
    assert sender.sent == []


@pytest.mark.parametrize(
    ("to", "subject"),
    [
        ("alex@example.com\nBcc: attacker@example.com", "Hello"),
        ("alex@example.com", "Hello\r\nBcc: attacker@example.com"),
    ],
)
def test_line_breaks_in_headers_are_rejected(to: str, subject: str) -> None:
    with pytest.raises(ValueError, match="line breaks"):
        EmailMessage(to=to, subject=subject, body="Hi")


def test_file_sender_writes_a_readable_email(tmp_path: Path) -> None:
    outbox_dir = tmp_path / "nested" / "outbox"
    sender = FileEmailSender(outbox_dir, "WorkLedger <no-reply@workledger.local>")

    sender.send(MESSAGE)

    [path] = outbox_dir.glob("*.eml")
    parsed = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    assert parsed["From"] == "WorkLedger <no-reply@workledger.local>"
    assert parsed["To"] == "alex@example.com"
    assert parsed["Subject"] == "You are invited"
    assert parsed["Date"]
    assert parsed.get_content().strip() == MESSAGE.body.strip()


def test_file_sender_writes_one_file_per_message(tmp_path: Path) -> None:
    sender = FileEmailSender(tmp_path, "no-reply@workledger.local")

    sender.send(MESSAGE)
    sender.send(MESSAGE)

    assert len(list(tmp_path.glob("*.eml"))) == 2


def test_backend_setting_chooses_the_sender(tmp_path: Path) -> None:
    memory = build_email_sender(Settings(_env_file=None, email_backend="memory"))
    files = build_email_sender(
        Settings(_env_file=None, email_backend="file", email_outbox_dir=tmp_path)
    )

    assert isinstance(memory, MemoryEmailSender)
    assert isinstance(files, FileEmailSender)


def test_requests_can_send_email_and_tests_can_read_it(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    router = APIRouter()

    @router.post("/api/probe/email")
    def send_probe(sender: EmailSenderDep) -> dict[str, str]:
        sender.send(MESSAGE)
        return {"status": "sent"}

    app.include_router(router)

    assert client.post("/api/probe/email").status_code == 200
    assert outbox.sent == [MESSAGE]
