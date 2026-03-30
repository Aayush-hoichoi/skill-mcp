import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

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


def _get_tool_names(app) -> set:
    """Extract registered tool names from a FastMCP app."""
    components = app._local_provider._components
    return {
        key.split(":")[1].split("@")[0]
        for key in components
        if key.startswith("tool:")
    }


def test_create_app_returns_fastmcp(mock_cache, mock_discovery, sources):
    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    assert app is not None
    tool_names = _get_tool_names(app)
    expected = {"list_skills", "get_skill", "get_reference", "search_skills",
                "install_skill", "refresh_skills", "add_source", "remove_source"}
    assert expected == tool_names


@pytest.mark.asyncio
async def test_list_skills_empty(mock_cache, mock_discovery, sources):
    """list_skills returns empty list when cache is fresh and empty."""
    mock_cache.is_fresh.return_value = True
    mock_cache.list_skills.return_value = []

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("list_skills", {})
    result = tool_result.structured_content.get("result", tool_result.structured_content)
    assert result == []


@pytest.mark.asyncio
async def test_list_skills_with_results(mock_cache, mock_discovery, sources, sample_skill):
    """list_skills returns skill metadata from cache."""
    mock_cache.is_fresh.return_value = True
    mock_cache.list_skills.return_value = [sample_skill.metadata()]

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("list_skills", {})
    result = tool_result.structured_content.get("result", tool_result.structured_content)
    assert len(result) == 1
    assert result[0]["name"] == "my-skill"


@pytest.mark.asyncio
async def test_list_skills_triggers_fetch_when_stale(mock_cache, mock_discovery, sources):
    """list_skills fetches from discovery when cache is stale."""
    mock_cache.is_fresh.return_value = False
    mock_cache.list_skills.return_value = []
    mock_discovery.discover.return_value = []

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    await app.call_tool("list_skills", {})
    mock_discovery.discover.assert_called_once()



@pytest.mark.asyncio
async def test_get_skill_not_found(mock_cache, mock_discovery, sources):
    """get_skill returns error dict when skill is not found."""
    mock_cache.is_fresh.return_value = True
    mock_cache.get_skill.return_value = None

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("get_skill", {"name": "nonexistent"})
    result = tool_result.structured_content
    assert "error" in result
    assert "nonexistent" in result["error"]


@pytest.mark.asyncio
async def test_get_skill_found(mock_cache, mock_discovery, sources, sample_skill):
    """get_skill returns skill data with reference file list (not contents)."""
    mock_cache.is_fresh.return_value = True
    mock_cache.get_skill.return_value = sample_skill

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("get_skill", {"name": "my-skill"})
    result = tool_result.structured_content
    assert result["name"] == "my-skill"
    assert result["content"] == "# My Skill\nBody"
    assert "references" not in result
    assert result["reference_files"] == ["ref.md"]


@pytest.mark.asyncio
async def test_get_skill_with_references(mock_cache, mock_discovery, sources, sample_skill):
    """get_skill includes full reference contents when include_references=True."""
    mock_cache.is_fresh.return_value = True
    mock_cache.get_skill.return_value = sample_skill

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("get_skill", {"name": "my-skill", "include_references": True})
    result = tool_result.structured_content
    assert result["name"] == "my-skill"
    assert result["references"] == {"ref.md": "ref content"}


@pytest.mark.asyncio
async def test_get_reference_found(mock_cache, mock_discovery, sources, sample_skill):
    """get_reference returns content of a single reference file."""
    mock_cache.is_fresh.return_value = True
    mock_cache.get_skill.return_value = sample_skill

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("get_reference", {"skill_name": "my-skill", "reference_path": "ref.md"})
    result = tool_result.structured_content
    assert result["content"] == "ref content"
    assert result["skill"] == "my-skill"


@pytest.mark.asyncio
async def test_get_reference_not_found(mock_cache, mock_discovery, sources, sample_skill):
    """get_reference returns error with available files when reference doesn't exist."""
    mock_cache.is_fresh.return_value = True
    mock_cache.get_skill.return_value = sample_skill

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("get_reference", {"skill_name": "my-skill", "reference_path": "nope.md"})
    result = tool_result.structured_content
    assert "error" in result
    assert result["available"] == ["ref.md"]


@pytest.mark.asyncio
async def test_search_skills_match(mock_cache, mock_discovery, sources, sample_skill):
    """search_skills returns skills matching query in name/description/content."""
    mock_cache.is_fresh.return_value = True
    mock_cache.list_skills.return_value = [sample_skill.metadata()]
    mock_cache.get_skill.return_value = sample_skill

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("search_skills", {"query": "great"})
    result = tool_result.structured_content.get("result", tool_result.structured_content)
    assert len(result) == 1
    assert result[0]["name"] == "my-skill"


@pytest.mark.asyncio
async def test_search_skills_no_match(mock_cache, mock_discovery, sources, sample_skill):
    """search_skills returns empty list when no skills match."""
    mock_cache.is_fresh.return_value = True
    mock_cache.list_skills.return_value = [sample_skill.metadata()]
    mock_cache.get_skill.return_value = sample_skill

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("search_skills", {"query": "zzz_no_match_xyz"})
    result = tool_result.structured_content.get("result", tool_result.structured_content)
    assert result == []


@pytest.mark.asyncio
async def test_install_skill_returns_error(mock_cache, mock_discovery, sources):
    """install_skill always returns error directing users to use get_skill."""
    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("install_skill", {"name": "my-skill"})
    result = tool_result.structured_content
    assert "error" in result
    assert "get_skill" in result["error"]


@pytest.mark.asyncio
async def test_refresh_skills(mock_cache, mock_discovery, sources, sample_skill):
    """refresh_skills invalidates cache and re-fetches skills."""
    mock_discovery.discover.return_value = [sample_skill]

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("refresh_skills", {})
    result = tool_result.structured_content
    mock_cache.invalidate.assert_called_once()
    mock_discovery.discover.assert_called_once()
    assert result["skills_refreshed"] == 1


@pytest.mark.asyncio
async def test_add_source_success(mock_cache, mock_discovery, sources):
    """add_source adds a new source and discovers its skills."""
    mock_discovery.discover.return_value = []
    mock_cache.save_sources.return_value = None

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool(
        "add_source",
        {"owner": "neworg", "repo": "newrepo", "type": "repo"},
    )
    result = tool_result.structured_content
    assert result["added"] == "neworg/newrepo"
    assert "skills_found" in result


@pytest.mark.asyncio
async def test_add_source_duplicate(mock_cache, mock_discovery, sources):
    """add_source returns error when source already exists."""
    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool(
        "add_source",
        {"owner": "org", "repo": "repo", "type": "repo"},
    )
    result = tool_result.structured_content
    assert "error" in result
    assert "already exists" in result["error"]


@pytest.mark.asyncio
async def test_add_source_invalid_owner(mock_cache, mock_discovery, sources):
    """add_source raises ToolError for invalid owner name (FastMCP wraps ValueError)."""
    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    with pytest.raises(ToolError, match="Invalid owner"):
        await app.call_tool(
            "add_source",
            {"owner": "org/bad", "repo": "repo", "type": "repo"},
        )


@pytest.mark.asyncio
async def test_remove_source_success(mock_cache, mock_discovery, sources):
    """remove_source removes an existing source and its cached data."""
    mock_cache.list_skills.return_value = []
    mock_cache.save_sources.return_value = None

    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("remove_source", {"owner": "org", "repo": "repo"})
    result = tool_result.structured_content
    assert result["removed"] == "org/repo"
    mock_cache.invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_remove_source_not_found(mock_cache, mock_discovery, sources):
    """remove_source returns error when source does not exist."""
    app = create_app(
        sources=sources,
        cache=mock_cache,
        discovery=mock_discovery,
        github_clients={},
    )
    tool_result = await app.call_tool("remove_source", {"owner": "ghost", "repo": "nope"})
    result = tool_result.structured_content
    assert "error" in result
    assert "not found" in result["error"]
