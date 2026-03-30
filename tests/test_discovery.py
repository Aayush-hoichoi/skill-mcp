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

    mock_github.list_directory.side_effect = [
        # list collection dir
        [
            {"name": "skill-a", "type": "dir", "path": "skills/skill-a"},
            {"name": "skill-b", "type": "dir", "path": "skills/skill-b"},
            {"name": "README.md", "type": "file", "path": "skills/README.md"},
        ],
        # list skill-a dir
        [
            {"name": "SKILL.md", "type": "file", "path": "skills/skill-a/SKILL.md"},
        ],
        # list skill-a/references (empty)
        [],
        # list skill-b dir
        [
            {"name": "SKILL.md", "type": "file", "path": "skills/skill-b/SKILL.md"},
        ],
        # list skill-b/references (empty)
        [],
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
