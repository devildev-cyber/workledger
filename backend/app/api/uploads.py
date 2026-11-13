"""Pieces shared by every endpoint that accepts or serves an uploaded file (decision 0018)."""

from typing import Annotated, Protocol
from urllib.parse import quote

from fastapi import HTTPException, Query, Request, Response, status

from app.api.deps import FileStoreDep
from app.core.storage import FileNotStoredError

# Images are shown in the page. Everything else is downloaded.
INLINE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

FilenameQuery = Annotated[str, Query(min_length=1, max_length=255)]


async def read_upload(request: Request, limit: int) -> bytes:
    """Read the body, refusing as soon as it is too large rather than after it is all in memory."""
    too_large = HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"Files can be at most {limit // (1024 * 1024)} MB",
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


class StoredFile(Protocol):
    storage_key: str
    content_type: str
    filename: str


def file_response(store: FileStoreDep, item: StoredFile) -> Response:
    try:
        data = store.read(item.storage_key)
    except FileNotStoredError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found") from error
    disposition = "inline" if item.content_type in INLINE_TYPES else "attachment"
    return Response(
        content=data,
        media_type=item.content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(item.filename)}",
            # The type was decided from the file's bytes. Browsers must not second-guess it.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
