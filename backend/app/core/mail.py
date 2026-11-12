"""Outgoing email behind a replaceable interface (decision 0007).

Application code depends only on EmailSender. A real provider is added during production
readiness (Phase 10) as another implementation. Send after the database commit, so nobody
is emailed about a change that was rolled back.
"""

import logging
import uuid
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage as MimeMessage
from email.utils import format_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from app.core.clock import utc_now

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

# Links are long. The default policy would re-encode any line over 78 characters, which
# breaks them for someone reading the file in a text editor, so long lines are kept as is.
_FILE_POLICY = policy.default.clone(max_line_length=998)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str

    def __post_init__(self) -> None:
        # Line breaks in headers would let attackers inject extra recipients or headers.
        for value in (self.to, self.subject):
            if "\r" in value or "\n" in value:
                raise ValueError("Email recipients and subjects cannot contain line breaks")


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class MemoryEmailSender:
    """Keeps messages in memory so tests can inspect what a request sent."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def clear(self) -> None:
        self.sent.clear()


class FileEmailSender:
    """Writes each message as a .eml file, which any mail client can open."""

    def __init__(self, directory: Path, from_address: str) -> None:
        self._directory = directory
        self._from_address = from_address

    def send(self, message: EmailMessage) -> None:
        now = utc_now()
        mime = MimeMessage(policy=_FILE_POLICY)
        mime["From"] = self._from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Date"] = format_datetime(now)
        mime.set_content(message.body, cte="8bit")

        self._directory.mkdir(parents=True, exist_ok=True)
        # Microseconds keep files sorted in the order they were sent.
        stamp = now.strftime("%Y%m%dT%H%M%S%f")
        path = self._directory / f"{stamp}-{uuid.uuid4().hex[:8]}.eml"
        path.write_bytes(mime.as_bytes())
        # The body is not logged because it may contain single-use links.
        logger.info("Email to %s written to %s", message.to, path)


def build_email_sender(settings: "Settings") -> EmailSender:
    if settings.email_backend == "memory":
        return MemoryEmailSender()
    return FileEmailSender(settings.email_outbox_dir, settings.email_from)
