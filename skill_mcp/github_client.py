"""GitHub API client with dual auth mode (App + public)."""

from __future__ import annotations

import base64
import logging
import time
from typing import Literal

import httpx
import jwt

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class RateLimitError(Exception):
    """Raised when GitHub API rate limit is exceeded."""


class GitHubClient:
    """GitHub API client supporting App and public (unauthenticated) modes."""

    def __init__(
        self,
        auth_mode: Literal["app", "public"] = "public",
        app_id: str | None = None,
        private_key: str | None = None,
        installation_id: str | None = None,
    ):
        self._auth_mode = auth_mode
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._rate_limit_remaining: int | None = None
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _update_rate_limit(self, headers: httpx.Headers) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            self._rate_limit_remaining = int(remaining)
            if self._rate_limit_remaining < 10:
                logger.warning(
                    "GitHub rate limit low: %d remaining (auth_mode=%s)",
                    self._rate_limit_remaining,
                    self._auth_mode,
                )

    @property
    def rate_limit_remaining(self) -> int | None:
        return self._rate_limit_remaining

    async def _ensure_token(self) -> None:
        if self._auth_mode != "app":
            return
        if self._token and time.time() < self._token_expires_at - 60:
            return
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": self._app_id,
        }
        jwt_token = jwt.encode(payload, self._private_key, algorithm="RS256")
        resp = await self._client.post(
            f"/app/installations/{self._installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        self._token_expires_at = time.time() + 3600

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        etag: str | None = None,
    ) -> httpx.Response:
        await self._ensure_token()
        headers: dict[str, str] = {}
        if self._auth_mode == "app" and self._token:
            headers["Authorization"] = f"token {self._token}"
        if etag:
            headers["If-None-Match"] = etag
        resp = await self._client.request(method, path, params=params, headers=headers)
        self._update_rate_limit(resp.headers)
        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            raise RateLimitError(
                f"GitHub API rate limit exceeded (remaining={remaining}, "
                f"auth_mode={self._auth_mode})"
            )
        return resp

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        etag: str | None = None,
    ) -> str | None:
        """Fetch a single file's content. Returns None if not found."""
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
            etag=etag,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code == 304:
            return None
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    async def list_directory(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> list[dict]:
        """List contents of a directory. Returns list of entries."""
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()

    async def get_tree(
        self,
        owner: str,
        repo: str,
        branch: str,
        recursive: bool = True,
    ) -> list[dict]:
        """Get the full git tree for a branch."""
        params = {}
        if recursive:
            params["recursive"] = "1"
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/trees/{branch}",
            params=params,
        )
        resp.raise_for_status()
        return resp.json().get("tree", [])
