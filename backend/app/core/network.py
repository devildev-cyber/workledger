from fastapi import Request

from app.core.config import Settings


def client_address(request: Request, settings: Settings) -> str | None:
    """The caller's network address.

    Behind a proxy you run, the address that connects is the proxy's, so the real one is read
    from the last X-Forwarded-For entry, which is the one that proxy added. The header is
    ignored unless trust_forwarded_for is set, because anyone can send it.
    """
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else None
