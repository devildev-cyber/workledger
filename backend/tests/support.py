"""Helpers shared by API tests that sign in as different people."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.api.deps import CSRF_HEADER_NAME
from app.core.config import Settings

PASSWORD = "correct horse battery staple"
ClientFactory = Callable[[Settings | None], TestClient]


class SignedInClient:
    """A signed-in browser: a client plus the CSRF token needed for changes."""

    def __init__(self, client: TestClient, csrf_token: str) -> None:
        self.client = client
        self.headers = {CSRF_HEADER_NAME: csrf_token}

    def get(self, path: str) -> Any:
        return self.client.get(path)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.client.post(path, headers=self.headers, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.client.put(path, headers=self.headers, **kwargs)

    def delete(self, path: str) -> Any:
        return self.client.delete(path, headers=self.headers)


def sign_in_as(client_factory: ClientFactory, email: str) -> SignedInClient:
    client = client_factory(None)
    response = client.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return SignedInClient(client, response.json()["csrf_token"])
