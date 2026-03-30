"""File-based cache for skills with auth-mode-aware TTL."""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from skill_mcp.models import Skill, SkillSource

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = "/tmp/skill-mcp-cache"


class SkillCache:
    """Disk-based skill cache with TTL expiry."""

    def __init__(
        self,
        cache_dir: str = DEFAULT_CACHE_DIR,
        ttl_app: int = 3600,
        ttl_public: int = 14400,
    ):
        self._cache_dir = cache_dir
        self._ttl_app = ttl_app
        self._ttl_public = ttl_public
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    def _source_dir(self, source: SkillSource) -> Path:
        return Path(self._cache_dir) / source.cache_key

    def _skill_dir(self, source: SkillSource, skill_name: str) -> Path:
        return self._source_dir(source) / skill_name

    def _meta_path(self, source: SkillSource) -> Path:
        return self._source_dir(source) / "_meta.json"

    def _ttl_for(self, source: SkillSource) -> int:
        return self._ttl_public if source.auth_mode == "public" else self._ttl_app

    def store_skill(self, source: SkillSource, skill: Skill) -> None:
        """Write a skill to disk cache."""
        skill_dir = self._skill_dir(source, skill.name)
        skill_dir.mkdir(parents=True, exist_ok=True)

        (skill_dir / "SKILL.md").write_text(skill.content, encoding="utf-8")

        for ref_path, ref_content in skill.references.items():
            ref_file = skill_dir / "references" / ref_path
            ref_file.parent.mkdir(parents=True, exist_ok=True)
            ref_file.write_text(ref_content, encoding="utf-8")

        meta_data = {
            "name": skill.name,
            "description": skill.description,
            "source_url": skill.source_url,
            "repo": skill.repo,
            "path": skill.path,
            "auth_mode": skill.auth_mode,
            "last_fetched": skill.last_fetched.isoformat(),
        }
        (skill_dir / "_skill_meta.json").write_text(
            json.dumps(meta_data), encoding="utf-8"
        )
        self.store_meta(source, skills=self._collect_skill_names(source))

    def get_skill(self, source: SkillSource, skill_name: str) -> Skill | None:
        """Read a skill from disk cache. Returns None if not found."""
        skill_dir = self._skill_dir(source, skill_name)
        skill_md = skill_dir / "SKILL.md"
        meta_file = skill_dir / "_skill_meta.json"

        if not skill_md.exists() or not meta_file.exists():
            return None

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        content = skill_md.read_text(encoding="utf-8")

        references: dict[str, str] = {}
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in refs_dir.rglob("*.md"):
                rel = str(ref_file.relative_to(refs_dir))
                references[rel] = ref_file.read_text(encoding="utf-8")

        return Skill(
            name=meta["name"],
            description=meta["description"],
            content=content,
            references=references,
            source_url=meta["source_url"],
            repo=meta["repo"],
            path=meta["path"],
            last_fetched=datetime.fromisoformat(meta["last_fetched"]),
            auth_mode=meta["auth_mode"],
        )

    def is_fresh(self, source: SkillSource) -> bool:
        """Check if cache for a source is within TTL."""
        meta = self.get_meta(source)
        if meta is None:
            return False
        fetched_at = meta.get("fetched_at", 0)
        return (time.time() - fetched_at) < self._ttl_for(source)

    def invalidate(self, source: SkillSource) -> None:
        """Delete cache for a source."""
        source_dir = self._source_dir(source)
        if source_dir.exists():
            shutil.rmtree(source_dir)

    def list_skills(self, source: SkillSource) -> list[dict]:
        """List skill metadata from cache for a source."""
        results = []
        source_dir = self._source_dir(source)
        if not source_dir.exists():
            return results
        for skill_dir in sorted(source_dir.iterdir()):
            meta_file = skill_dir / "_skill_meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                results.append({
                    "name": meta["name"],
                    "description": meta["description"],
                    "repo": meta["repo"],
                    "path": meta["path"],
                    "auth_mode": meta["auth_mode"],
                })
        return results

    def store_meta(
        self,
        source: SkillSource,
        etag: str | None = None,
        skills: list[str] | None = None,
    ) -> None:
        """Write source-level metadata."""
        meta_path = self._meta_path(source)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.get_meta(source) or {}
        existing["fetched_at"] = time.time()
        if etag is not None:
            existing["etag"] = etag
        if skills is not None:
            existing["skills"] = skills
        meta_path.write_text(json.dumps(existing), encoding="utf-8")

    def get_meta(self, source: SkillSource) -> dict | None:
        """Read source-level metadata."""
        meta_path = self._meta_path(source)
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def save_sources(self, sources: list[SkillSource]) -> None:
        """Persist source list to disk."""
        path = Path(self._cache_dir) / "sources.json"
        data = [s.to_dict() for s in sources]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_sources(self) -> list[SkillSource]:
        """Load persisted source list from disk."""
        path = Path(self._cache_dir) / "sources.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [SkillSource.from_dict(s) for s in data]

    def _collect_skill_names(self, source: SkillSource) -> list[str]:
        source_dir = self._source_dir(source)
        names = []
        if source_dir.exists():
            for d in sorted(source_dir.iterdir()):
                if d.is_dir() and (d / "_skill_meta.json").exists():
                    names.append(d.name)
        return names
