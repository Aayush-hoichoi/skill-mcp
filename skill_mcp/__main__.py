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
