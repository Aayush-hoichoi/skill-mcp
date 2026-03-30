"""Vercel serverless entry point for Skill MCP Server."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from skill_mcp.cache import SkillCache
from skill_mcp.config import load_config
from skill_mcp.discovery import SkillDiscovery
from skill_mcp.github_client import GitHubClient
from skill_mcp.server import create_app

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

config = load_config()

cache = SkillCache(
    cache_dir="/tmp/skill-mcp-cache",
    ttl_app=config.cache_ttl_seconds,
    ttl_public=config.cache_ttl_public_seconds,
)

persisted = cache.load_sources()
all_sources = list(config.sources)
existing_keys = {s.cache_key for s in all_sources}
for p in persisted:
    if p.cache_key not in existing_keys:
        all_sources.append(p)

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

default_client = github_clients.get("app", github_clients["public"])
discovery = SkillDiscovery(default_client)

mcp = create_app(
    sources=all_sources,
    cache=cache,
    discovery=discovery,
    github_clients=github_clients,
)

app = mcp.http_app()
