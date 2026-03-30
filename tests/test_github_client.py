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
