"""Integration test: full flow from discovery to tool output."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

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
    """Verify all 7 tools are registered on the FastMCP app."""
    components = app._local_provider._components
    tool_names = {
        key.split(":")[1].split("@")[0]
        for key in components
        if key.startswith("tool:")
    }
    assert "list_skills" in tool_names
    assert "get_skill" in tool_names
    assert "search_skills" in tool_names
    assert "refresh_skills" in tool_names
    assert "add_source" in tool_names
    assert "remove_source" in tool_names
    assert "install_skill" in tool_names
