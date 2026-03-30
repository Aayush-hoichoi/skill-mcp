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
        source.owner = "changed"
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
