import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.storage import FileStore
from app.models import EventType, MaintenanceRequest, RequestAttachment, User, Visibility
from app.services.activity import record_event

MAX_ATTACHMENTS_PER_REQUEST = 10
MAX_FILENAME_LENGTH = 120


class AttachmentError(Exception):
    """A file that cannot be accepted. The message is safe to show."""


class AttachmentLimitError(AttachmentError):
    pass


def detect_content_type(data: bytes) -> str | None:
    """Identify an allowed file from its own first bytes, whatever the sender claimed.

    Only formats a browser shows safely are accepted. SVG is excluded on purpose: it can carry
    scripts. Anything not recognised here is refused.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def clean_filename(raw: str) -> str:
    """The name to show for a file. Folders and control characters are dropped."""
    name = re.split(r"[\\/]", raw)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        if dot and len(extension) <= 10:
            name = stem[: MAX_FILENAME_LENGTH - len(extension) - 1] + "." + extension
        else:
            name = name[:MAX_FILENAME_LENGTH]
    return name or "file"


def add_attachment(
    db: Session,
    store: FileStore,
    request: MaintenanceRequest,
    *,
    actor: User,
    filename: str,
    data: bytes,
    visibility: Visibility,
) -> RequestAttachment:
    if not data:
        raise AttachmentError("The file is empty")
    content_type = detect_content_type(data)
    if content_type is None:
        raise AttachmentError("Only JPEG, PNG, WebP images and PDF files can be attached")

    existing = db.scalar(
        select(func.count())
        .select_from(RequestAttachment)
        .where(RequestAttachment.request_id == request.id)
    )
    if (existing or 0) >= MAX_ATTACHMENTS_PER_REQUEST:
        raise AttachmentLimitError(
            f"A request can have at most {MAX_ATTACHMENTS_PER_REQUEST} attachments"
        )

    attachment_id = uuid.uuid4()
    # The key is made only of IDs, so nothing the sender typed ever reaches the file system.
    storage_key = f"{request.organization_id}/{request.id}/{attachment_id}"
    store.save(storage_key, data)

    attachment = RequestAttachment(
        id=attachment_id,
        organization_id=request.organization_id,
        request_id=request.id,
        uploaded_by_user_id=actor.id,
        visibility=visibility,
        filename=clean_filename(filename),
        content_type=content_type,
        size_bytes=len(data),
        storage_key=storage_key,
    )
    db.add(attachment)
    db.flush()
    record_event(
        db,
        event_type=EventType.REQUEST_ATTACHMENT_ADDED,
        organization_id=request.organization_id,
        actor=actor,
        subject_type="maintenance_request",
        subject_id=request.id,
        after={
            "attachment_id": str(attachment.id),
            "content_type": content_type,
            "size_bytes": len(data),
            "visibility": visibility,
        },
    )
    return attachment


def get_attachment(
    db: Session, *, request: MaintenanceRequest, attachment_id: uuid.UUID, include_internal: bool
) -> RequestAttachment | None:
    statement = select(RequestAttachment).where(
        RequestAttachment.id == attachment_id,
        RequestAttachment.request_id == request.id,
        RequestAttachment.organization_id == request.organization_id,
    )
    if not include_internal:
        statement = statement.where(RequestAttachment.visibility == Visibility.RESIDENT)
    return db.scalar(statement)
