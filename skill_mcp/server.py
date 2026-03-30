"""FastMCP server with 7 skill management tools."""

from __future__ import annotations

import logging
import re
from typing import Literal

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from skill_mcp.cache import SkillCache
from skill_mcp.discovery import SkillDiscovery
from skill_mcp.github_client import GitHubClient, RateLimitError
from skill_mcp.models import Skill, SkillSource

logger = logging.getLogger(__name__)

OWNER_REPO_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _validate_name(value: str, field: str) -> None:
    """Validate that a GitHub owner or repo name contains only safe characters."""
    if not OWNER_REPO_RE.match(value):
        raise ValueError(f"Invalid {field}: must match [a-zA-Z0-9_.-]+")


def create_app(
    sources: list[SkillSource],
    cache: SkillCache,
    discovery: SkillDiscovery,
    github_clients: dict[str, GitHubClient],
) -> FastMCP:
    """Create and configure the FastMCP application."""

    mcp = FastMCP(
        name="Skill MCP Server",
        instructions=(
            "This server provides tools to discover, search, and fetch Claude skills "
            "from GitHub repositories. Use list_skills to see available skills, "
            "get_skill to fetch full content, and search_skills to find by keyword."
        ),
    )

    # Mutable list captured by closures — new objects are created when modified
    _sources: list[SkillSource] = list(sources)

    async def _ensure_cached(source_filter: str | None = None) -> None:
        """Populate cache for stale sources; skip if fresh."""
        for s in _sources:
            if source_filter and f"{s.owner}/{s.repo}" != source_filter:
                continue
            if not cache.is_fresh(s):
                try:
                    skills = await discovery.discover(s)
                    for skill in skills:
                        cache.store_skill(s, skill)
                except RateLimitError:
                    logger.warning(
                        "Rate limited fetching %s/%s, using stale cache",
                        s.owner,
                        s.repo,
                    )

    @mcp.tool
    async def list_skills(source: str | None = None) -> list[dict]:
        """List all available skills. Optionally filter by source (owner/repo)."""
        await _ensure_cached(source)
        results = []
        for s in _sources:
            if source and f"{s.owner}/{s.repo}" != source:
                continue
            results.extend(cache.list_skills(s))
        return results

    @mcp.tool
    async def get_skill(name: str, include_references: bool = False) -> dict:
        """Fetch a skill's SKILL.md content by name. References are listed by name only — use get_reference to fetch individual reference files."""
        await _ensure_cached()
        for s in _sources:
            skill = cache.get_skill(s, name)
            if skill is not None:
                result: dict = {
                    "name": skill.name,
                    "description": skill.description,
                    "content": skill.content,
                    "source_url": skill.source_url,
                    "repo": skill.repo,
                    "path": skill.path,
                    "auth_mode": skill.auth_mode,
                    "reference_files": list(skill.references.keys()),
                }
                if include_references:
                    result["references"] = skill.references
                return result
        return {"error": f"Skill '{name}' not found"}

    @mcp.tool
    async def get_reference(skill_name: str, reference_path: str) -> dict:
        """Fetch a single reference file from a skill. Use get_skill first to see available reference_files."""
        await _ensure_cached()
        for s in _sources:
            skill = cache.get_skill(s, skill_name)
            if skill is not None:
                content = skill.references.get(reference_path)
                if content is not None:
                    return {
                        "skill": skill_name,
                        "reference": reference_path,
                        "content": content,
                    }
                return {
                    "error": f"Reference '{reference_path}' not found in skill '{skill_name}'",
                    "available": list(skill.references.keys()),
                }
        return {"error": f"Skill '{skill_name}' not found"}

    @mcp.tool
    async def search_skills(query: str, source: str | None = None) -> list[dict]:
        """Search skills by keyword across name, description, and content."""
        await _ensure_cached(source)
        query_lower = query.lower()
        results = []
        for s in _sources:
            if source and f"{s.owner}/{s.repo}" != source:
                continue
            for meta in cache.list_skills(s):
                skill = cache.get_skill(s, meta["name"])
                if skill is None:
                    continue
                searchable = f"{skill.name} {skill.description} {skill.content}".lower()
                if query_lower in searchable:
                    results.append(skill.metadata())
        return results

    @mcp.tool
    async def install_skill(
        name: str, target_dir: str = "~/.claude/skills/"
    ) -> dict:
        """Download a skill to local disk. Not available from claude.ai."""
        return {
            "error": (
                "install_skill is not available when connected via claude.ai. "
                "Use get_skill to read skill content instead."
            )
        }

    @mcp.tool
    async def refresh_skills(source: str | None = None) -> dict:
        """Force re-fetch skills from GitHub, busting the cache."""
        count = 0
        for s in _sources:
            if source and f"{s.owner}/{s.repo}" != source:
                continue
            cache.invalidate(s)
            try:
                skills = await discovery.discover(s)
                for skill in skills:
                    cache.store_skill(s, skill)
                count += len(skills)
            except RateLimitError as exc:
                return {"error": str(exc), "skills_refreshed": count}
        return {"skills_refreshed": count}

    @mcp.tool
    async def add_source(
        owner: str,
        repo: str,
        type: Literal["repo", "collection"],
        path: str = "/",
        branch: str = "main",
        auth_mode: Literal["app", "public"] = "app",
    ) -> dict:
        """Add a new GitHub repo as a skill source at runtime."""
        _validate_name(owner, "owner")
        _validate_name(repo, "repo")

        for existing in _sources:
            if existing.owner == owner and existing.repo == repo:
                return {"error": f"Source {owner}/{repo} already exists"}

        new_source = SkillSource(
            type=type,
            owner=owner,
            repo=repo,
            path=path,
            branch=branch,
            auth_mode=auth_mode,
        )
        _sources.append(new_source)
        cache.save_sources(_sources)

        skills: list[Skill] = []
        try:
            skills = await discovery.discover(new_source)
            for skill in skills:
                cache.store_skill(new_source, skill)
        except RateLimitError as exc:
            return {
                "added": f"{owner}/{repo}",
                "warning": str(exc),
                "skills_found": 0,
            }

        result: dict = {"added": f"{owner}/{repo}", "skills_found": len(skills)}
        if auth_mode == "public":
            result["note"] = (
                "Using public mode (60 req/hr shared). "
                "For higher limits, install the GitHub App on this repo."
            )
        return result

    @mcp.tool
    async def remove_source(owner: str, repo: str) -> dict:
        """Remove a skill source and its cached data."""
        _validate_name(owner, "owner")
        _validate_name(repo, "repo")

        to_remove: SkillSource | None = None
        for s in _sources:
            if s.owner == owner and s.repo == repo:
                to_remove = s
                break

        if to_remove is None:
            return {"error": f"Source {owner}/{repo} not found"}

        skill_count = len(cache.list_skills(to_remove))
        cache.invalidate(to_remove)
        _sources.remove(to_remove)
        cache.save_sources(_sources)

        return {"removed": f"{owner}/{repo}", "skills_removed": skill_count}

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        app_sources = [s for s in _sources if s.auth_mode == "app"]
        public_sources = [s for s in _sources if s.auth_mode == "public"]
        total_skills = sum(len(cache.list_skills(s)) for s in _sources)
        return JSONResponse({
            "status": "healthy",
            "total_sources": len(_sources),
            "app_sources": len(app_sources),
            "public_sources": len(public_sources),
            "total_skills_cached": total_skills,
        })

    return mcp
