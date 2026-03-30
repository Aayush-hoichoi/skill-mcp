"""Skill discovery from GitHub repositories."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from skill_mcp.github_client import GitHubClient
from skill_mcp.models import Skill, SkillSource

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class SkillDiscovery:
    """Discovers and parses skills from GitHub sources."""

    def __init__(self, github_client: GitHubClient):
        self._github = github_client

    async def discover(self, source: SkillSource) -> list[Skill]:
        """Discover all skills from a source."""
        if source.type == "repo":
            return await self._discover_repo(source)
        return await self._discover_collection(source)

    async def _discover_repo(self, source: SkillSource) -> list[Skill]:
        """Discover a single skill from a repo source."""
        path = source.path.rstrip("/")
        entries = await self._github.list_directory(
            source.owner, source.repo, path, source.branch
        )
        has_skill_md = any(e["name"] == "SKILL.md" for e in entries)
        if not has_skill_md:
            return []

        skill = await self._fetch_skill(source, path)
        return [skill] if skill else []

    async def _discover_collection(self, source: SkillSource) -> list[Skill]:
        """Discover multiple skills from a collection source."""
        path = source.path.rstrip("/")
        entries = await self._github.list_directory(
            source.owner, source.repo, path, source.branch
        )
        dirs = [e for e in entries if e["type"] == "dir"]

        skills = []
        for d in dirs:
            # List each sub-directory to check for SKILL.md before fetching
            sub_entries = await self._github.list_directory(
                source.owner, source.repo, d["path"], source.branch
            )
            has_skill_md = any(e["name"] == "SKILL.md" for e in sub_entries)
            if not has_skill_md:
                continue
            skill = await self._fetch_skill(source, d["path"])
            if skill:
                skills.append(skill)
        return skills

    async def _fetch_skill(self, source: SkillSource, skill_path: str) -> Skill | None:
        """Fetch and parse a single skill from a directory path."""
        skill_md_path = f"{skill_path}/SKILL.md"
        content = await self._github.get_file_content(
            source.owner, source.repo, skill_md_path, source.branch
        )
        if content is None:
            return None

        name, description, body = self.parse_skill_md(content)
        if not name:
            logger.warning("SKILL.md at %s has no name in frontmatter", skill_md_path)
            return None

        references = await self._fetch_references(source, skill_path)

        return Skill(
            name=name,
            description=description,
            content=body,
            references=references,
            source_url=(
                f"https://github.com/{source.owner}/{source.repo}"
                f"/tree/{source.branch}/{skill_path}"
            ),
            repo=f"{source.owner}/{source.repo}",
            path=skill_path,
            last_fetched=datetime.now(timezone.utc),
            auth_mode=source.auth_mode,
        )

    async def _fetch_references(
        self, source: SkillSource, skill_path: str
    ) -> dict[str, str]:
        """Recursively fetch all .md files from references/ directory."""
        refs_path = f"{skill_path}/references"
        return await self._fetch_refs_recursive(source, refs_path, refs_path)

    async def _fetch_refs_recursive(
        self, source: SkillSource, current_path: str, base_path: str
    ) -> dict[str, str]:
        """Recursively list and fetch .md files."""
        entries = await self._github.list_directory(
            source.owner, source.repo, current_path, source.branch
        )
        references: dict[str, str] = {}

        for entry in entries:
            if entry["type"] == "file" and entry["name"].endswith(".md"):
                content = await self._github.get_file_content(
                    source.owner, source.repo, entry["path"], source.branch
                )
                if content is not None:
                    rel_path = entry["path"][len(base_path) + 1:]
                    references[rel_path] = content
            elif entry["type"] == "dir":
                nested = await self._fetch_refs_recursive(
                    source, entry["path"], base_path
                )
                references.update(nested)

        return references

    @staticmethod
    def parse_skill_md(raw: str) -> tuple[str, str, str]:
        """Parse SKILL.md into (name, description, body)."""
        match = FRONTMATTER_RE.match(raw)
        if not match:
            return "", "", raw

        frontmatter_text = match.group(1)
        body = raw[match.end():]

        name = ""
        description = ""
        lines = frontmatter_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                desc_value = line.split(":", 1)[1].strip()
                if desc_value in (">", "|"):
                    desc_lines = []
                    i += 1
                    while i < len(lines) and (
                        lines[i].startswith("  ") or not lines[i].strip()
                    ):
                        desc_lines.append(lines[i].strip())
                        i += 1
                    description = " ".join(desc_lines).strip()
                    continue
                else:
                    description = desc_value
            i += 1

        return name, description, body
