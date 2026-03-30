# Skill MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that fetches Claude skills from GitHub repos and exposes them as tools via Streamable HTTP, deployed on Render for claude.ai.

**Architecture:** Single FastMCP process with dual GitHub auth (App + public), file-based cache with auth-mode-aware TTL, 7 MCP tools. Monolithic — one codebase, one deployment.

**Tech Stack:** Python 3.12, FastMCP 3.x, httpx, PyJWT, cryptography, pyyaml, pytest + pytest-asyncio

---

### Task 0: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `skill_mcp/__init__.py`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/aayushk/Desktop/skill_mcp
git init
```

- [ ] **Step 2: Check Python 3.12 is available (FastMCP requires >= 3.10)**

```bash
python3.12 --version
```

If not installed, install via `brew install python@3.12` or `pyenv install 3.12`.

- [ ] **Step 3: Create `.python-version`**

```
3.12
```

- [ ] **Step 4: Create `pyproject.toml`**

```toml
[project]
name = "skill-mcp"
version = "0.1.0"
description = "MCP server that fetches Claude skills from GitHub repositories"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.0.0,<4.0.0",
    "httpx>=0.27.0,<1.0.0",
    "PyJWT>=2.8.0,<3.0.0",
    "cryptography>=42.0.0,<44.0.0",
    "pyyaml>=6.0,<7.0",
    "python-dotenv>=1.0.0,<2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
]

[build-system]
requires = ["setuptools>=69.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [ ] **Step 5: Create `requirements.txt`**

```
fastmcp>=3.0.0,<4.0.0
httpx>=0.27.0,<1.0.0
PyJWT>=2.8.0,<3.0.0
cryptography>=42.0.0,<44.0.0
pyyaml>=6.0,<7.0
python-dotenv>=1.0.0,<2.0.0
```

- [ ] **Step 6: Create `skill_mcp/__init__.py`**

```python
"""Skill MCP Server — fetches Claude skills from GitHub repos."""
```

- [ ] **Step 7: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.egg-info/
dist/
build/
.pytest_cache/
.venv/
```

- [ ] **Step 8: Create `.env.example`**

```bash
# GitHub App credentials (required only for auth_mode="app" sources)
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY=
GITHUB_APP_INSTALLATION_ID=

# Skill sources (JSON array)
SKILL_SOURCES=[]

# Cache TTL
CACHE_TTL_SECONDS=3600
CACHE_TTL_PUBLIC_SECONDS=14400

# Server
PORT=8000

# Optional: protect MCP endpoint
API_KEY=
```

- [ ] **Step 9: Create venv and install deps**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 10: Verify imports**

```bash
source .venv/bin/activate
python -c "import fastmcp; import httpx; import jwt; import yaml; print('All imports OK')"
```

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml requirements.txt skill_mcp/__init__.py .python-version .gitignore .env.example
git commit -m "chore: initialize project with dependencies and structure"
```

---

### Task 1: Data Models (`models.py`)

**Files:**
- Create: `skill_mcp/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for SkillSource and Skill**

Create `tests/__init__.py` (empty) and `tests/test_models.py`:

```python
from datetime import datetime, timezone

from skill_mcp.models import Skill, SkillSource


def test_skill_source_defaults():
    source = SkillSource(type="repo", owner="myorg", repo="my-repo")
    assert source.path == "/"
    assert source.branch == "main"
    assert source.auth_mode == "app"


def test_skill_source_public_mode():
    source = SkillSource(
        type="collection",
        owner="community",
        repo="skills",
        path="skills",
        auth_mode="public",
    )
    assert source.auth_mode == "public"
    assert source.type == "collection"


def test_skill_source_is_frozen():
    source = SkillSource(type="repo", owner="a", repo="b")
    try:
        source.owner = "changed"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_skill_source_cache_key():
    source = SkillSource(type="repo", owner="myorg", repo="my-repo")
    assert source.cache_key == "myorg__my-repo"


def test_skill_source_from_dict():
    data = {"type": "repo", "owner": "org", "repo": "r", "auth_mode": "public"}
    source = SkillSource.from_dict(data)
    assert source.owner == "org"
    assert source.auth_mode == "public"
    assert source.path == "/"
    assert source.branch == "main"


def test_skill_source_to_dict():
    source = SkillSource(type="repo", owner="org", repo="r", auth_mode="public")
    d = source.to_dict()
    assert d == {
        "type": "repo",
        "owner": "org",
        "repo": "r",
        "path": "/",
        "branch": "main",
        "auth_mode": "public",
    }


def test_skill_creation():
    now = datetime.now(timezone.utc)
    skill = Skill(
        name="test-skill",
        description="A test skill",
        content="# Test\nBody here",
        references={"ref.md": "ref content"},
        source_url="https://github.com/org/repo",
        repo="org/repo",
        path="skills/test-skill",
        last_fetched=now,
        auth_mode="app",
    )
    assert skill.name == "test-skill"
    assert skill.references == {"ref.md": "ref content"}
    assert skill.auth_mode == "app"


def test_skill_metadata():
    now = datetime.now(timezone.utc)
    skill = Skill(
        name="my-skill",
        description="desc",
        content="body",
        references={},
        source_url="https://github.com/o/r",
        repo="o/r",
        path="s",
        last_fetched=now,
        auth_mode="public",
    )
    meta = skill.metadata()
    assert meta == {
        "name": "my-skill",
        "description": "desc",
        "repo": "o/r",
        "path": "s",
        "auth_mode": "public",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/aayushk/Desktop/skill_mcp
source .venv/bin/activate
pytest tests/test_models.py -v
```

Expected: FAIL — `cannot import name 'Skill' from 'skill_mcp.models'`

- [ ] **Step 3: Implement models**

Create `skill_mcp/models.py`:

```python
"""Data models for Skill MCP Server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class SkillSource:
    """A configured GitHub location to scan for skills."""

    type: Literal["repo", "collection"]
    owner: str
    repo: str
    path: str = "/"
    branch: str = "main"
    auth_mode: Literal["app", "public"] = "app"

    @property
    def cache_key(self) -> str:
        return f"{self.owner}__{self.repo}"

    @classmethod
    def from_dict(cls, data: dict) -> SkillSource:
        return cls(
            type=data["type"],
            owner=data["owner"],
            repo=data["repo"],
            path=data.get("path", "/"),
            branch=data.get("branch", "main"),
            auth_mode=data.get("auth_mode", "app"),
        )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "owner": self.owner,
            "repo": self.repo,
            "path": self.path,
            "branch": self.branch,
            "auth_mode": self.auth_mode,
        }


@dataclass(frozen=True)
class Skill:
    """A parsed skill with its content."""

    name: str
    description: str
    content: str
    references: dict[str, str]
    source_url: str
    repo: str
    path: str
    last_fetched: datetime
    auth_mode: str

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "repo": self.repo,
            "path": self.path,
            "auth_mode": self.auth_mode,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skill_mcp/models.py tests/__init__.py tests/test_models.py
git commit -m "feat: add SkillSource and Skill data models"
```

---

### Task 2: Configuration (`config.py`)

**Files:**
- Create: `skill_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
import os
from unittest.mock import patch

import pytest

from skill_mcp.config import load_config, Config


def _base_env(**overrides):
    env = {"SKILL_SOURCES": "[]"}
    env.update(overrides)
    return env


def test_load_config_minimal():
    with patch.dict(os.environ, _base_env(), clear=True):
        cfg = load_config()
    assert cfg.sources == []
    assert cfg.cache_ttl_seconds == 3600
    assert cfg.cache_ttl_public_seconds == 14400
    assert cfg.port == 8000
    assert cfg.api_key is None
    assert cfg.github_app_id is None


def test_load_config_with_github_app():
    env = _base_env(
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        GITHUB_APP_INSTALLATION_ID="456",
    )
    with patch.dict(os.environ, env, clear=True):
        cfg = load_config()
    assert cfg.github_app_id == "123"
    assert cfg.github_app_installation_id == "456"
    assert "fake" in cfg.github_app_private_key


def test_load_config_with_sources():
    sources_json = '[{"type":"repo","owner":"org","repo":"r","path":"skills/s","auth_mode":"public"}]'
    with patch.dict(os.environ, _base_env(SKILL_SOURCES=sources_json), clear=True):
        cfg = load_config()
    assert len(cfg.sources) == 1
    assert cfg.sources[0].owner == "org"
    assert cfg.sources[0].auth_mode == "public"


def test_load_config_app_source_without_app_credentials_raises():
    sources_json = '[{"type":"repo","owner":"org","repo":"r","auth_mode":"app"}]'
    with patch.dict(os.environ, _base_env(SKILL_SOURCES=sources_json), clear=True):
        with pytest.raises(ValueError, match="GitHub App credentials required"):
            load_config()


def test_load_config_custom_ttl():
    env = _base_env(CACHE_TTL_SECONDS="600", CACHE_TTL_PUBLIC_SECONDS="7200")
    with patch.dict(os.environ, env, clear=True):
        cfg = load_config()
    assert cfg.cache_ttl_seconds == 600
    assert cfg.cache_ttl_public_seconds == 7200


def test_load_config_missing_skill_sources_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="SKILL_SOURCES"):
            load_config()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — `cannot import name 'load_config' from 'skill_mcp.config'`

- [ ] **Step 3: Implement config**

Create `skill_mcp/config.py`:

```python
"""Configuration loading from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from skill_mcp.models import SkillSource


@dataclass(frozen=True)
class Config:
    """Application configuration."""

    sources: list[SkillSource]
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_app_installation_id: str | None = None
    cache_ttl_seconds: int = 3600
    cache_ttl_public_seconds: int = 14400
    port: int = 8000
    api_key: str | None = None

    @property
    def has_github_app(self) -> bool:
        return all([
            self.github_app_id,
            self.github_app_private_key,
            self.github_app_installation_id,
        ])


def load_config() -> Config:
    """Load configuration from environment variables."""
    sources_raw = os.environ.get("SKILL_SOURCES")
    if sources_raw is None:
        raise ValueError("SKILL_SOURCES environment variable is required")

    sources = [SkillSource.from_dict(s) for s in json.loads(sources_raw)]

    github_app_id = os.environ.get("GITHUB_APP_ID")
    github_app_private_key = os.environ.get("GITHUB_APP_PRIVATE_KEY")
    github_app_installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID")

    has_app_creds = all([github_app_id, github_app_private_key, github_app_installation_id])
    has_app_sources = any(s.auth_mode == "app" for s in sources)

    if has_app_sources and not has_app_creds:
        raise ValueError(
            "GitHub App credentials required (GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, "
            "GITHUB_APP_INSTALLATION_ID) when using auth_mode='app' sources"
        )

    return Config(
        sources=sources,
        github_app_id=github_app_id,
        github_app_private_key=github_app_private_key,
        github_app_installation_id=github_app_installation_id,
        cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", "3600")),
        cache_ttl_public_seconds=int(os.environ.get("CACHE_TTL_PUBLIC_SECONDS", "14400")),
        port=int(os.environ.get("PORT", "8000")),
        api_key=os.environ.get("API_KEY"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skill_mcp/config.py tests/test_config.py
git commit -m "feat: add config loading from environment variables"
```

---

### Task 3: GitHub Client (`github_client.py`)

**Files:**
- Create: `skill_mcp/github_client.py`
- Create: `tests/test_github_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_github_client.py`:

```python
import base64
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from skill_mcp.github_client import GitHubClient


@pytest.fixture
def public_client():
    return GitHubClient(auth_mode="public")


@pytest.fixture
def app_client():
    return GitHubClient(
        auth_mode="app",
        app_id="123",
        private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        installation_id="456",
    )


@pytest.mark.asyncio
@respx.mock
async def test_get_contents_public(public_client):
    content = base64.b64encode(b"# Hello").decode()
    respx.get("https://api.github.com/repos/org/repo/contents/SKILL.md").mock(
        return_value=httpx.Response(
            200,
            json={"content": content, "encoding": "base64", "type": "file"},
            headers={"X-RateLimit-Remaining": "55"},
        )
    )
    result = await public_client.get_file_content("org", "repo", "SKILL.md", "main")
    assert result == "# Hello"


@pytest.mark.asyncio
@respx.mock
async def test_get_contents_public_no_auth_header(public_client):
    content = base64.b64encode(b"data").decode()
    route = respx.get("https://api.github.com/repos/org/repo/contents/f.md").mock(
        return_value=httpx.Response(
            200,
            json={"content": content, "encoding": "base64", "type": "file"},
            headers={"X-RateLimit-Remaining": "50"},
        )
    )
    await public_client.get_file_content("org", "repo", "f.md", "main")
    request = route.calls[0].request
    assert "Authorization" not in request.headers


@pytest.mark.asyncio
@respx.mock
async def test_list_directory_public(public_client):
    respx.get("https://api.github.com/repos/org/repo/contents/skills").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "skill-a", "type": "dir", "path": "skills/skill-a"},
                {"name": "readme.md", "type": "file", "path": "skills/readme.md"},
            ],
            headers={"X-RateLimit-Remaining": "50"},
        )
    )
    dirs = await public_client.list_directory("org", "repo", "skills", "main")
    assert len(dirs) == 2
    assert dirs[0]["name"] == "skill-a"


@pytest.mark.asyncio
@respx.mock
async def test_get_contents_rate_limited(public_client):
    respx.get("https://api.github.com/repos/org/repo/contents/f.md").mock(
        return_value=httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0"},
        )
    )
    with pytest.raises(Exception, match="rate limit"):
        await public_client.get_file_content("org", "repo", "f.md", "main")


@pytest.mark.asyncio
@respx.mock
async def test_get_contents_not_found(public_client):
    respx.get("https://api.github.com/repos/org/repo/contents/missing.md").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    result = await public_client.get_file_content("org", "repo", "missing.md", "main")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_get_tree_public(public_client):
    respx.get("https://api.github.com/repos/org/repo/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={
                "sha": "abc",
                "tree": [
                    {"path": "SKILL.md", "type": "blob"},
                    {"path": "references/ref.md", "type": "blob"},
                    {"path": "references", "type": "tree"},
                ],
            },
            headers={"X-RateLimit-Remaining": "50"},
        )
    )
    tree = await public_client.get_tree("org", "repo", "main")
    blobs = [e for e in tree if e["type"] == "blob"]
    assert len(blobs) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_github_client.py -v
```

Expected: FAIL — `cannot import name 'GitHubClient'`

- [ ] **Step 3: Implement GitHub client**

Create `skill_mcp/github_client.py`:

```python
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
            return None  # Not modified — caller should use cache
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_github_client.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skill_mcp/github_client.py tests/test_github_client.py
git commit -m "feat: add GitHub client with dual auth mode (app + public)"
```

---

### Task 4: File Cache (`cache.py`)

**Files:**
- Create: `skill_mcp/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cache.py`:

```python
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skill_mcp.cache import SkillCache
from skill_mcp.models import Skill, SkillSource


@pytest.fixture
def tmp_cache(tmp_path):
    return SkillCache(cache_dir=str(tmp_path), ttl_app=3600, ttl_public=14400)


@pytest.fixture
def sample_source():
    return SkillSource(type="repo", owner="org", repo="repo", auth_mode="public")


@pytest.fixture
def sample_skill():
    return Skill(
        name="test-skill",
        description="A test",
        content="# Test body",
        references={"ref.md": "ref content"},
        source_url="https://github.com/org/repo",
        repo="org/repo",
        path="skills/test-skill",
        last_fetched=datetime.now(timezone.utc),
        auth_mode="public",
    )


def test_store_and_get_skill(tmp_cache, sample_source, sample_skill):
    tmp_cache.store_skill(sample_source, sample_skill)
    result = tmp_cache.get_skill(sample_source, "test-skill")
    assert result is not None
    assert result.name == "test-skill"
    assert result.content == "# Test body"
    assert result.references == {"ref.md": "ref content"}


def test_get_skill_not_found(tmp_cache, sample_source):
    result = tmp_cache.get_skill(sample_source, "nonexistent")
    assert result is None


def test_is_fresh_within_ttl(tmp_cache, sample_source, sample_skill):
    tmp_cache.store_skill(sample_source, sample_skill)
    assert tmp_cache.is_fresh(sample_source) is True


def test_is_fresh_expired(tmp_cache, sample_source, sample_skill):
    expired_cache = SkillCache(
        cache_dir=tmp_cache._cache_dir, ttl_app=0, ttl_public=0
    )
    expired_cache.store_skill(sample_source, sample_skill)
    assert expired_cache.is_fresh(sample_source) is False


def test_is_fresh_no_cache(tmp_cache, sample_source):
    assert tmp_cache.is_fresh(sample_source) is False


def test_invalidate(tmp_cache, sample_source, sample_skill):
    tmp_cache.store_skill(sample_source, sample_skill)
    assert tmp_cache.is_fresh(sample_source) is True
    tmp_cache.invalidate(sample_source)
    assert tmp_cache.is_fresh(sample_source) is False


def test_list_skills(tmp_cache, sample_source, sample_skill):
    tmp_cache.store_skill(sample_source, sample_skill)
    skills = tmp_cache.list_skills(sample_source)
    assert len(skills) == 1
    assert skills[0]["name"] == "test-skill"


def test_store_meta_with_etag(tmp_cache, sample_source):
    tmp_cache.store_meta(sample_source, etag='"abc123"', skills=["s1"])
    meta = tmp_cache.get_meta(sample_source)
    assert meta is not None
    assert meta["etag"] == '"abc123"'
    assert meta["skills"] == ["s1"]


def test_sources_persistence(tmp_cache, sample_source):
    tmp_cache.save_sources([sample_source])
    loaded = tmp_cache.load_sources()
    assert len(loaded) == 1
    assert loaded[0].owner == "org"
    assert loaded[0].auth_mode == "public"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cache.py -v
```

Expected: FAIL — `cannot import name 'SkillCache'`

- [ ] **Step 3: Implement cache**

Create `skill_mcp/cache.py`:

```python
"""File-based cache for skills with auth-mode-aware TTL."""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from skill_mcp.models import Skill, SkillSource

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = "/tmp/skill-mcp-cache"


class SkillCache:
    """Disk-based skill cache with TTL expiry."""

    def __init__(
        self,
        cache_dir: str = DEFAULT_CACHE_DIR,
        ttl_app: int = 3600,
        ttl_public: int = 14400,
    ):
        self._cache_dir = cache_dir
        self._ttl_app = ttl_app
        self._ttl_public = ttl_public
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    def _source_dir(self, source: SkillSource) -> Path:
        return Path(self._cache_dir) / source.cache_key

    def _skill_dir(self, source: SkillSource, skill_name: str) -> Path:
        return self._source_dir(source) / skill_name

    def _meta_path(self, source: SkillSource) -> Path:
        return self._source_dir(source) / "_meta.json"

    def _ttl_for(self, source: SkillSource) -> int:
        return self._ttl_public if source.auth_mode == "public" else self._ttl_app

    def store_skill(self, source: SkillSource, skill: Skill) -> None:
        """Write a skill to disk cache."""
        skill_dir = self._skill_dir(source, skill.name)
        skill_dir.mkdir(parents=True, exist_ok=True)

        (skill_dir / "SKILL.md").write_text(skill.content, encoding="utf-8")

        for ref_path, ref_content in skill.references.items():
            ref_file = skill_dir / "references" / ref_path
            ref_file.parent.mkdir(parents=True, exist_ok=True)
            ref_file.write_text(ref_content, encoding="utf-8")

        meta_data = {
            "name": skill.name,
            "description": skill.description,
            "source_url": skill.source_url,
            "repo": skill.repo,
            "path": skill.path,
            "auth_mode": skill.auth_mode,
            "last_fetched": skill.last_fetched.isoformat(),
        }
        (skill_dir / "_skill_meta.json").write_text(
            json.dumps(meta_data), encoding="utf-8"
        )
        self.store_meta(source, skills=self._collect_skill_names(source))

    def get_skill(self, source: SkillSource, skill_name: str) -> Skill | None:
        """Read a skill from disk cache. Returns None if not found."""
        skill_dir = self._skill_dir(source, skill_name)
        skill_md = skill_dir / "SKILL.md"
        meta_file = skill_dir / "_skill_meta.json"

        if not skill_md.exists() or not meta_file.exists():
            return None

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        content = skill_md.read_text(encoding="utf-8")

        references: dict[str, str] = {}
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in refs_dir.rglob("*.md"):
                rel = str(ref_file.relative_to(refs_dir))
                references[rel] = ref_file.read_text(encoding="utf-8")

        return Skill(
            name=meta["name"],
            description=meta["description"],
            content=content,
            references=references,
            source_url=meta["source_url"],
            repo=meta["repo"],
            path=meta["path"],
            last_fetched=datetime.fromisoformat(meta["last_fetched"]),
            auth_mode=meta["auth_mode"],
        )

    def is_fresh(self, source: SkillSource) -> bool:
        """Check if cache for a source is within TTL."""
        meta = self.get_meta(source)
        if meta is None:
            return False
        fetched_at = meta.get("fetched_at", 0)
        return (time.time() - fetched_at) < self._ttl_for(source)

    def invalidate(self, source: SkillSource) -> None:
        """Delete cache for a source."""
        source_dir = self._source_dir(source)
        if source_dir.exists():
            shutil.rmtree(source_dir)

    def list_skills(self, source: SkillSource) -> list[dict]:
        """List skill metadata from cache for a source."""
        results = []
        source_dir = self._source_dir(source)
        if not source_dir.exists():
            return results
        for skill_dir in sorted(source_dir.iterdir()):
            meta_file = skill_dir / "_skill_meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                results.append({
                    "name": meta["name"],
                    "description": meta["description"],
                    "repo": meta["repo"],
                    "path": meta["path"],
                    "auth_mode": meta["auth_mode"],
                })
        return results

    def store_meta(
        self,
        source: SkillSource,
        etag: str | None = None,
        skills: list[str] | None = None,
    ) -> None:
        """Write source-level metadata."""
        meta_path = self._meta_path(source)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.get_meta(source) or {}
        existing["fetched_at"] = time.time()
        if etag is not None:
            existing["etag"] = etag
        if skills is not None:
            existing["skills"] = skills
        meta_path.write_text(json.dumps(existing), encoding="utf-8")

    def get_meta(self, source: SkillSource) -> dict | None:
        """Read source-level metadata."""
        meta_path = self._meta_path(source)
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def save_sources(self, sources: list[SkillSource]) -> None:
        """Persist source list to disk."""
        path = Path(self._cache_dir) / "sources.json"
        data = [s.to_dict() for s in sources]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_sources(self) -> list[SkillSource]:
        """Load persisted source list from disk."""
        path = Path(self._cache_dir) / "sources.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [SkillSource.from_dict(s) for s in data]

    def _collect_skill_names(self, source: SkillSource) -> list[str]:
        source_dir = self._source_dir(source)
        names = []
        if source_dir.exists():
            for d in sorted(source_dir.iterdir()):
                if d.is_dir() and (d / "_skill_meta.json").exists():
                    names.append(d.name)
        return names
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cache.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skill_mcp/cache.py tests/test_cache.py
git commit -m "feat: add file-based skill cache with auth-mode-aware TTL"
```

---

### Task 5: Skill Discovery (`discovery.py`)

**Files:**
- Create: `skill_mcp/discovery.py`
- Create: `tests/test_discovery.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_discovery.py`:

```python
import base64
from unittest.mock import AsyncMock

import pytest

from skill_mcp.discovery import SkillDiscovery
from skill_mcp.models import SkillSource


SAMPLE_SKILL_MD = """---
name: test-skill
description: >
  A test skill for unit testing.
---

# Test Skill

This is the body.
"""

SAMPLE_REF = "# Reference\nSome content."


@pytest.fixture
def mock_github():
    client = AsyncMock()
    client.rate_limit_remaining = 50
    return client


@pytest.fixture
def discovery(mock_github):
    return SkillDiscovery(mock_github)


@pytest.mark.asyncio
async def test_discover_repo_source(discovery, mock_github):
    source = SkillSource(type="repo", owner="org", repo="r", path="skills/my-skill")

    mock_github.list_directory.return_value = [
        {"name": "SKILL.md", "type": "file", "path": "skills/my-skill/SKILL.md"},
        {"name": "references", "type": "dir", "path": "skills/my-skill/references"},
    ]
    mock_github.get_file_content.side_effect = [
        SAMPLE_SKILL_MD,  # SKILL.md
    ]
    mock_github.list_directory.side_effect = [
        # First call: skill directory listing
        [
            {"name": "SKILL.md", "type": "file", "path": "skills/my-skill/SKILL.md"},
            {"name": "references", "type": "dir", "path": "skills/my-skill/references"},
        ],
        # Second call: references listing
        [
            {"name": "ref.md", "type": "file", "path": "skills/my-skill/references/ref.md"},
        ],
    ]
    mock_github.get_file_content.side_effect = [
        SAMPLE_SKILL_MD,
        SAMPLE_REF,
    ]

    skills = await discovery.discover(source)
    assert len(skills) == 1
    assert skills[0].name == "test-skill"
    assert skills[0].description.strip() == "A test skill for unit testing."
    assert "# Test Skill" in skills[0].content
    assert skills[0].references == {"ref.md": SAMPLE_REF}


@pytest.mark.asyncio
async def test_discover_collection_source(discovery, mock_github):
    source = SkillSource(type="collection", owner="org", repo="r", path="skills")

    # First call: list collection directory → two skill dirs
    # Second call: list skill-a directory
    # Third call: list skill-a/references
    # Fourth call: list skill-b directory
    mock_github.list_directory.side_effect = [
        [
            {"name": "skill-a", "type": "dir", "path": "skills/skill-a"},
            {"name": "skill-b", "type": "dir", "path": "skills/skill-b"},
            {"name": "README.md", "type": "file", "path": "skills/README.md"},
        ],
        [
            {"name": "SKILL.md", "type": "file", "path": "skills/skill-a/SKILL.md"},
        ],
        [],  # no references dir contents
        [
            {"name": "SKILL.md", "type": "file", "path": "skills/skill-b/SKILL.md"},
        ],
        [],  # no references dir contents
    ]

    skill_a_md = SAMPLE_SKILL_MD
    skill_b_md = "---\nname: skill-b\ndescription: Second skill\n---\n# B\nBody B"

    mock_github.get_file_content.side_effect = [skill_a_md, skill_b_md]

    skills = await discovery.discover(source)
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"test-skill", "skill-b"}


@pytest.mark.asyncio
async def test_discover_repo_no_skill_md(discovery, mock_github):
    source = SkillSource(type="repo", owner="org", repo="r", path="empty")
    mock_github.list_directory.return_value = [
        {"name": "readme.md", "type": "file", "path": "empty/readme.md"},
    ]

    skills = await discovery.discover(source)
    assert skills == []


def test_parse_frontmatter(discovery):
    name, desc, body = discovery.parse_skill_md(SAMPLE_SKILL_MD)
    assert name == "test-skill"
    assert "test skill" in desc.lower()
    assert "# Test Skill" in body


def test_parse_frontmatter_no_frontmatter(discovery):
    name, desc, body = discovery.parse_skill_md("# No Frontmatter\nJust body.")
    assert name == ""
    assert desc == ""
    assert "# No Frontmatter" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_discovery.py -v
```

Expected: FAIL — `cannot import name 'SkillDiscovery'`

- [ ] **Step 3: Implement discovery**

Create `skill_mcp/discovery.py`:

```python
"""Skill discovery from GitHub repositories."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from skill_mcp.github_client import GitHubClient
from skill_mcp.models import Skill, SkillSource

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class SkillDiscovery:
    """Discovers and parses skills from GitHub sources."""

    def __init__(self, github_client: GitHubClient):
        self._github = github_client

    async def discover(self, source: SkillSource) -> list[Skill]:
        """Discover all skills from a source."""
        if source.type == "repo":
            return await self._discover_repo(source)
        return await self._discover_collection(source)

    async def _discover_repo(self, source: SkillSource) -> list[Skill]:
        """Discover a single skill from a repo source."""
        path = source.path.rstrip("/")
        entries = await self._github.list_directory(
            source.owner, source.repo, path, source.branch
        )
        has_skill_md = any(e["name"] == "SKILL.md" for e in entries)
        if not has_skill_md:
            return []

        skill = await self._fetch_skill(source, path)
        return [skill] if skill else []

    async def _discover_collection(self, source: SkillSource) -> list[Skill]:
        """Discover multiple skills from a collection source."""
        path = source.path.rstrip("/")
        entries = await self._github.list_directory(
            source.owner, source.repo, path, source.branch
        )
        dirs = [e for e in entries if e["type"] == "dir"]

        skills = []
        for d in dirs:
            skill = await self._fetch_skill(source, d["path"])
            if skill:
                skills.append(skill)
        return skills

    async def _fetch_skill(self, source: SkillSource, skill_path: str) -> Skill | None:
        """Fetch and parse a single skill from a directory path."""
        skill_md_path = f"{skill_path}/SKILL.md"
        content = await self._github.get_file_content(
            source.owner, source.repo, skill_md_path, source.branch
        )
        if content is None:
            return None

        name, description, body = self.parse_skill_md(content)
        if not name:
            logger.warning("SKILL.md at %s has no name in frontmatter", skill_md_path)
            return None

        references = await self._fetch_references(source, skill_path)

        return Skill(
            name=name,
            description=description,
            content=body,
            references=references,
            source_url=f"https://github.com/{source.owner}/{source.repo}/tree/{source.branch}/{skill_path}",
            repo=f"{source.owner}/{source.repo}",
            path=skill_path,
            last_fetched=datetime.now(timezone.utc),
            auth_mode=source.auth_mode,
        )

    async def _fetch_references(
        self, source: SkillSource, skill_path: str
    ) -> dict[str, str]:
        """Recursively fetch all .md files from references/ directory."""
        refs_path = f"{skill_path}/references"
        return await self._fetch_refs_recursive(source, refs_path, refs_path)

    async def _fetch_refs_recursive(
        self, source: SkillSource, current_path: str, base_path: str
    ) -> dict[str, str]:
        """Recursively list and fetch .md files."""
        entries = await self._github.list_directory(
            source.owner, source.repo, current_path, source.branch
        )
        references: dict[str, str] = {}

        for entry in entries:
            if entry["type"] == "file" and entry["name"].endswith(".md"):
                content = await self._github.get_file_content(
                    source.owner, source.repo, entry["path"], source.branch
                )
                if content is not None:
                    rel_path = entry["path"][len(base_path) + 1 :]
                    references[rel_path] = content
            elif entry["type"] == "dir":
                nested = await self._fetch_refs_recursive(
                    source, entry["path"], base_path
                )
                references.update(nested)

        return references

    @staticmethod
    def parse_skill_md(raw: str) -> tuple[str, str, str]:
        """Parse SKILL.md into (name, description, body)."""
        match = FRONTMATTER_RE.match(raw)
        if not match:
            return "", "", raw

        frontmatter_text = match.group(1)
        body = raw[match.end() :]

        name = ""
        description = ""
        lines = frontmatter_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                desc_value = line.split(":", 1)[1].strip()
                if desc_value in (">", "|"):
                    # Multi-line scalar
                    desc_lines = []
                    i += 1
                    while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                        desc_lines.append(lines[i].strip())
                        i += 1
                    description = " ".join(desc_lines).strip()
                    continue
                else:
                    description = desc_value
            i += 1

        return name, description, body
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_discovery.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skill_mcp/discovery.py tests/test_discovery.py
git commit -m "feat: add skill discovery for repo and collection sources"
```

---

### Task 6: MCP Server & Tools (`server.py`)

**Files:**
- Create: `skill_mcp/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server.py`:

```python
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skill_mcp.models import Skill, SkillSource
from skill_mcp.server import create_app


@pytest.fixture
def sample_skill():
    return Skill(
        name="my-skill",
        description="A great skill",
        content="# My Skill\nBody",
        references={"ref.md": "ref content"},
        source_url="https://github.com/org/repo/tree/main/skills/my-skill",
        repo="org/repo",
        path="skills/my-skill",
        last_fetched=datetime.now(timezone.utc),
        auth_mode="public",
    )


@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.list_skills.return_value = []
    cache.get_skill.return_value = None
    cache.is_fresh.return_value = True
    cache.load_sources.return_value = []
    return cache


@pytest.fixture
def mock_discovery():
    return AsyncMock()


@pytest.fixture
def sources():
    return [
        SkillSource(type="repo", owner="org", repo="repo", path="skills/s", auth_mode="public"),
    ]


def test_create_app_returns_fastmcp(mock_cache, mock_discovery, sources):
    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    assert app is not None
    tool_names = {t.name for t in app._tool_manager.list_tools()}
    expected = {"list_skills", "get_skill", "search_skills", "install_skill",
                "refresh_skills", "add_source", "remove_source"}
    assert expected == tool_names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_server.py -v
```

Expected: FAIL — `cannot import name 'create_app'`

- [ ] **Step 3: Implement server with 7 tools**

Create `skill_mcp/server.py`:

```python
"""FastMCP server with 7 skill management tools."""

from __future__ import annotations

import logging
import re
from typing import Literal

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from skill_mcp.cache import SkillCache
from skill_mcp.discovery import SkillDiscovery
from skill_mcp.github_client import GitHubClient, RateLimitError
from skill_mcp.models import Skill, SkillSource

logger = logging.getLogger(__name__)

OWNER_REPO_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _validate_name(value: str, field: str) -> None:
    if not OWNER_REPO_RE.match(value):
        raise ValueError(f"Invalid {field}: must match [a-zA-Z0-9_.-]+")


def create_app(
    sources: list[SkillSource],
    cache: SkillCache,
    discovery: SkillDiscovery,
    github_clients: dict[str, GitHubClient],
) -> FastMCP:
    """Create and configure the FastMCP application."""

    mcp = FastMCP(
        name="Skill MCP Server",
        instructions=(
            "This server provides tools to discover, search, and fetch Claude skills "
            "from GitHub repositories. Use list_skills to see available skills, "
            "get_skill to fetch full content, and search_skills to find by keyword."
        ),
    )

    _sources = list(sources)

    @mcp.tool
    async def list_skills(source: str | None = None) -> list[dict]:
        """List all available skills. Optionally filter by source (owner/repo)."""
        await _ensure_cached(source)
        results = []
        for s in _sources:
            if source and f"{s.owner}/{s.repo}" != source:
                continue
            results.extend(cache.list_skills(s))
        return results

    @mcp.tool
    async def get_skill(name: str, include_references: bool = True) -> dict:
        """Fetch a skill's full content by name. Returns SKILL.md body and references."""
        await _ensure_all_cached()
        for s in _sources:
            skill = cache.get_skill(s, name)
            if skill is not None:
                result = {
                    "name": skill.name,
                    "description": skill.description,
                    "content": skill.content,
                    "source_url": skill.source_url,
                    "repo": skill.repo,
                    "path": skill.path,
                    "auth_mode": skill.auth_mode,
                }
                if include_references:
                    result["references"] = skill.references
                return result
        return {"error": f"Skill '{name}' not found"}

    @mcp.tool
    async def search_skills(query: str, source: str | None = None) -> list[dict]:
        """Search skills by keyword across name, description, and content."""
        await _ensure_cached(source)
        query_lower = query.lower()
        results = []
        for s in _sources:
            if source and f"{s.owner}/{s.repo}" != source:
                continue
            for meta in cache.list_skills(s):
                skill = cache.get_skill(s, meta["name"])
                if skill is None:
                    continue
                searchable = f"{skill.name} {skill.description} {skill.content}".lower()
                if query_lower in searchable:
                    results.append(skill.metadata())
        return results

    @mcp.tool
    async def install_skill(
        name: str, target_dir: str = "~/.claude/skills/"
    ) -> dict:
        """Download a skill to local disk. Not available from claude.ai."""
        return {
            "error": "install_skill is not available when connected via claude.ai. "
            "Use get_skill to read skill content instead."
        }

    @mcp.tool
    async def refresh_skills(source: str | None = None) -> dict:
        """Force re-fetch skills from GitHub, busting the cache."""
        count = 0
        for s in _sources:
            if source and f"{s.owner}/{s.repo}" != source:
                continue
            cache.invalidate(s)
            try:
                skills = await discovery.discover(s)
                for skill in skills:
                    cache.store_skill(s, skill)
                count += len(skills)
            except RateLimitError as e:
                return {"error": str(e), "skills_refreshed": count}
        return {"skills_refreshed": count}

    @mcp.tool
    async def add_source(
        owner: str,
        repo: str,
        type: Literal["repo", "collection"],
        path: str = "/",
        branch: str = "main",
        auth_mode: Literal["app", "public"] = "app",
    ) -> dict:
        """Add a new GitHub repo as a skill source at runtime."""
        _validate_name(owner, "owner")
        _validate_name(repo, "repo")

        for existing in _sources:
            if existing.owner == owner and existing.repo == repo:
                return {"error": f"Source {owner}/{repo} already exists"}

        new_source = SkillSource(
            type=type,
            owner=owner,
            repo=repo,
            path=path,
            branch=branch,
            auth_mode=auth_mode,
        )
        _sources.append(new_source)
        cache.save_sources(_sources)

        try:
            skills = await discovery.discover(new_source)
            for skill in skills:
                cache.store_skill(new_source, skill)
        except RateLimitError as e:
            return {
                "added": f"{owner}/{repo}",
                "warning": str(e),
                "skills_found": 0,
            }

        result = {"added": f"{owner}/{repo}", "skills_found": len(skills)}
        if auth_mode == "public":
            result["note"] = (
                "Using public mode (60 req/hr shared). "
                "For higher limits, install the GitHub App on this repo."
            )
        return result

    @mcp.tool
    async def remove_source(owner: str, repo: str) -> dict:
        """Remove a skill source and its cached data."""
        _validate_name(owner, "owner")
        _validate_name(repo, "repo")

        to_remove = None
        for s in _sources:
            if s.owner == owner and s.repo == repo:
                to_remove = s
                break

        if to_remove is None:
            return {"error": f"Source {owner}/{repo} not found"}

        skill_count = len(cache.list_skills(to_remove))
        cache.invalidate(to_remove)
        _sources.remove(to_remove)
        cache.save_sources(_sources)

        return {"removed": f"{owner}/{repo}", "skills_removed": skill_count}

    async def _ensure_cached(self, source_filter: str | None = None) -> None:
        for s in _sources:
            if source_filter and f"{s.owner}/{s.repo}" != source_filter:
                continue
            if not cache.is_fresh(s):
                try:
                    skills = await discovery.discover(s)
                    for skill in skills:
                        cache.store_skill(s, skill)
                except RateLimitError:
                    logger.warning("Rate limited fetching %s/%s, using stale cache", s.owner, s.repo)

    async def _ensure_all_cached() -> None:
        await _ensure_cached(None)

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        app_sources = [s for s in _sources if s.auth_mode == "app"]
        public_sources = [s for s in _sources if s.auth_mode == "public"]
        total_skills = sum(len(cache.list_skills(s)) for s in _sources)
        return JSONResponse({
            "status": "healthy",
            "total_sources": len(_sources),
            "app_sources": len(app_sources),
            "public_sources": len(public_sources),
            "total_skills_cached": total_skills,
        })

    return mcp
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_server.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add skill_mcp/server.py tests/test_server.py
git commit -m "feat: add FastMCP server with 7 skill management tools"
```

---

### Task 7: Entry Point (`__main__.py`)

**Files:**
- Create: `skill_mcp/__main__.py`

- [ ] **Step 1: Create the entry point**

Create `skill_mcp/__main__.py`:

```python
"""Entry point for the Skill MCP Server."""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from skill_mcp.cache import SkillCache
from skill_mcp.config import load_config
from skill_mcp.discovery import SkillDiscovery
from skill_mcp.github_client import GitHubClient
from skill_mcp.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    try:
        config = load_config()
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    cache = SkillCache(
        ttl_app=config.cache_ttl_seconds,
        ttl_public=config.cache_ttl_public_seconds,
    )

    # Merge env sources with any persisted runtime sources
    persisted = cache.load_sources()
    all_sources = list(config.sources)
    existing_keys = {s.cache_key for s in all_sources}
    for p in persisted:
        if p.cache_key not in existing_keys:
            all_sources.append(p)

    # Create GitHub clients for each auth mode
    github_clients: dict[str, GitHubClient] = {
        "public": GitHubClient(auth_mode="public"),
    }
    if config.has_github_app:
        github_clients["app"] = GitHubClient(
            auth_mode="app",
            app_id=config.github_app_id,
            private_key=config.github_app_private_key,
            installation_id=config.github_app_installation_id,
        )

    # Use public client as default for discovery
    # Discovery will use the appropriate client based on source auth_mode
    default_client = github_clients.get("app", github_clients["public"])
    discovery = SkillDiscovery(default_client)

    app = create_app(
        sources=all_sources,
        cache=cache,
        discovery=discovery,
        github_clients=github_clients,
    )

    logger.info(
        "Starting Skill MCP Server on port %d with %d sources",
        config.port,
        len(all_sources),
    )
    app.run(transport="http", host="0.0.0.0", port=config.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test that the module is importable**

```bash
cd /Users/aayushk/Desktop/skill_mcp
source .venv/bin/activate
python -c "from skill_mcp.__main__ import main; print('Import OK')"
```

Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add skill_mcp/__main__.py
git commit -m "feat: add server entry point with config + client wiring"
```

---

### Task 8: Fix `_ensure_cached` Closure Bug & Integration Test

The `_ensure_cached` function in `server.py` incorrectly uses `self` — it's a closure, not a method. Fix this and add an integration-style test.

**Files:**
- Modify: `skill_mcp/server.py` — remove `self` parameter from `_ensure_cached`
- Create: `tests/test_integration.py`

- [ ] **Step 1: Fix the `_ensure_cached` signature in `server.py`**

Change:

```python
    async def _ensure_cached(self, source_filter: str | None = None) -> None:
```

To:

```python
    async def _ensure_cached(source_filter: str | None = None) -> None:
```

- [ ] **Step 2: Write integration test**

Create `tests/test_integration.py`:

```python
"""Integration test: full flow from discovery to tool output."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from skill_mcp.cache import SkillCache
from skill_mcp.discovery import SkillDiscovery
from skill_mcp.models import Skill, SkillSource
from skill_mcp.server import create_app


SAMPLE_SKILL = Skill(
    name="demo-skill",
    description="A demo skill for testing",
    content="# Demo\nThis is a demo skill.",
    references={"guide.md": "# Guide\nStep 1."},
    source_url="https://github.com/org/repo/tree/main/skills/demo-skill",
    repo="org/repo",
    path="skills/demo-skill",
    last_fetched=datetime.now(timezone.utc),
    auth_mode="public",
)


@pytest.fixture
def app(tmp_path):
    source = SkillSource(
        type="repo", owner="org", repo="repo", path="skills/demo-skill", auth_mode="public"
    )
    cache = SkillCache(cache_dir=str(tmp_path), ttl_app=3600, ttl_public=14400)
    cache.store_skill(source, SAMPLE_SKILL)

    discovery = AsyncMock(spec=SkillDiscovery)

    return create_app(
        sources=[source],
        cache=cache,
        discovery=discovery,
        github_clients={},
    )


def test_tools_registered(app):
    tool_names = {t.name for t in app._tool_manager.list_tools()}
    assert "list_skills" in tool_names
    assert "get_skill" in tool_names
    assert "search_skills" in tool_names
    assert "refresh_skills" in tool_names
    assert "add_source" in tool_names
    assert "remove_source" in tool_names
    assert "install_skill" in tool_names
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS across all test files.

- [ ] **Step 4: Commit**

```bash
git add skill_mcp/server.py tests/test_integration.py
git commit -m "fix: remove erroneous self param from closure, add integration test"
```

---

### Task 9: Render Deployment Files

**Files:**
- Create: `render.yaml`
- Create: `Procfile`

- [ ] **Step 1: Create `render.yaml` (Render Blueprint)**

```yaml
services:
  - type: web
    name: skill-mcp
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python -m skill_mcp
    healthCheckPath: /health
    envVars:
      - key: SKILL_SOURCES
        sync: false
      - key: GITHUB_APP_ID
        sync: false
      - key: GITHUB_APP_PRIVATE_KEY
        sync: false
      - key: GITHUB_APP_INSTALLATION_ID
        sync: false
      - key: CACHE_TTL_SECONDS
        value: "3600"
      - key: CACHE_TTL_PUBLIC_SECONDS
        value: "14400"
      - key: PORT
        value: "8000"
      - key: API_KEY
        generateValue: true
    disk:
      name: skill-cache
      mountPath: /tmp/skill-mcp-cache
      sizeGB: 1
```

- [ ] **Step 2: Create `Procfile`**

```
web: python -m skill_mcp
```

- [ ] **Step 3: Run all tests one final time**

```bash
cd /Users/aayushk/Desktop/skill_mcp
source .venv/bin/activate
pytest tests/ -v --tb=short
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add render.yaml Procfile
git commit -m "chore: add Render deployment configuration"
```

---

### Task 10: Final Verification & README

**Files:**
- Verify: all source files exist and are importable
- Create: `README.md` (brief setup instructions)

- [ ] **Step 1: Verify project structure**

```bash
find /Users/aayushk/Desktop/skill_mcp/skill_mcp -name "*.py" | sort
```

Expected output:
```
skill_mcp/__init__.py
skill_mcp/__main__.py
skill_mcp/cache.py
skill_mcp/config.py
skill_mcp/discovery.py
skill_mcp/github_client.py
skill_mcp/models.py
skill_mcp/server.py
```

- [ ] **Step 2: Verify all imports work**

```bash
source .venv/bin/activate
python -c "
from skill_mcp.models import Skill, SkillSource
from skill_mcp.config import load_config, Config
from skill_mcp.github_client import GitHubClient, RateLimitError
from skill_mcp.cache import SkillCache
from skill_mcp.discovery import SkillDiscovery
from skill_mcp.server import create_app
print('All imports OK')
"
```

- [ ] **Step 3: Run full test suite with coverage**

```bash
pip install pytest-cov
pytest tests/ -v --cov=skill_mcp --cov-report=term-missing
```

Expected: All tests pass, coverage > 80%.

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "chore: final verification — all tests passing"
```
