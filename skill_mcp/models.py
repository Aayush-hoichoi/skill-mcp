"""Data models for Skill MCP Server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class SkillSource:
    """A configured GitHub location to scan for skills."""

    type: Literal["repo", "collection"]
    owner: str
    repo: str
    path: str = "/"
    branch: str = "main"
    auth_mode: Literal["app", "public"] = "app"

    @property
    def cache_key(self) -> str:
        return f"{self.owner}__{self.repo}"

    @classmethod
    def from_dict(cls, data: dict) -> SkillSource:
        return cls(
            type=data["type"],
            owner=data["owner"],
            repo=data["repo"],
            path=data.get("path", "/"),
            branch=data.get("branch", "main"),
            auth_mode=data.get("auth_mode", "app"),
        )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "owner": self.owner,
            "repo": self.repo,
            "path": self.path,
            "branch": self.branch,
            "auth_mode": self.auth_mode,
        }


@dataclass(frozen=True)
class Skill:
    """A parsed skill with its content."""

    name: str
    description: str
    content: str
    references: dict[str, str]
    source_url: str
    repo: str
    path: str
    last_fetched: datetime
    auth_mode: str

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "repo": self.repo,
            "path": self.path,
            "auth_mode": self.auth_mode,
        }
