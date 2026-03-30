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
