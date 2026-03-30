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
