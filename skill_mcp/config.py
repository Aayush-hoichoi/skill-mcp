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
