# Skill MCP Server — Design Specification

**Date:** 2026-03-30
**Status:** Approved
**Author:** Aayush Kumar

---

## 1. Overview

A Python MCP server that dynamically fetches Claude skills from GitHub repositories and exposes them as tools to Claude via Streamable HTTP. Deployed on Render, connected to claude.ai.

**Problem:** Claude cannot auto-discover or load skills from GitHub. Users must manually upload/paste skill files.

**Solution:** An MCP server that acts as a bridge — authenticates with GitHub via a GitHub App (private repos) or unauthenticated access (public repos), discovers skills in configured repos, caches them locally, and serves them to Claude through 7 MCP tools. Acts as a **Central Skill Repository** — any user can connect any public skill repo from any GitHub user/org.

---

## 2. Architecture

```
┌─────────────┐         HTTPS          ┌──────────────────────┐
│  claude.ai  │ ◄──────────────────────►│   Skill MCP Server   │
│  (client)   │    Streamable HTTP      │   (Render, FastMCP)  │
└─────────────┘                         └──────────┬───────────┘
                                                   │
                                        ┌──────────┴───────────┐
                                        │                      │
                                   ┌────▼─────┐        ┌──────▼──────┐
                                   │  GitHub   │        │  File Cache │
                                   │  API v3   │        │  /tmp/cache │
                                   │ (App Auth)│        │  TTL-based  │
                                   └──────────┘        └─────────────┘
```

### Components

1. **FastMCP Server** — single Python process, serves 7 MCP tools over Streamable HTTP
2. **GitHub Client** — dual auth mode: GitHub App (private/installed repos, 5,000 req/hr) or unauthenticated (public repos, 60 req/hr)
3. **File Cache** — disk-based cache at `/tmp/skill-mcp-cache/` with auth-mode-aware TTL (1 hour for `app`, 4 hours for `public`)
4. **Source Registry** — list of configured GitHub sources, initialized from env vars, mutable at runtime via `add_source`/`remove_source` tools

### Request Flow

1. Claude calls an MCP tool (e.g., `search_skills`)
2. Server checks file cache for fresh data
3. If cache miss/expired → checks source `auth_mode`:
   - `app` → fetches using GitHub App installation token
   - `public` → fetches unauthenticated (no token)
4. Processes, caches, and returns result to Claude

---

## 3. Skill Format

Based on the loglineai reference skill at `/Users/aayushk/Desktop/skill_builder/logline-skill/.claude/skills/loglineai/`.

### Directory Structure

```
skill-name/
├── SKILL.md                          # YAML frontmatter (name, description) + markdown body
└── references/                       # Optional, organized by topic subdirectories
    ├── topic-group/
    │   ├── file1.md
    │   └── file2.md
    ├── another-group/
    │   └── file.md
    └── standalone.md                 # Can also be flat files at references/ root
```

### SKILL.md Format

```yaml
---
name: skill-name
description: >
  Multi-line description of what the skill covers
  and when to use it.
---

# Skill Title

## Markdown body with full documentation
...

## References

Table mapping reference file paths to their contents.
```

### Key Constraints

- YAML frontmatter must have `name` (string) and `description` (string, can be multi-line with `>`)
- All content files are `.md` format
- References can be nested in subdirectories or flat at the `references/` root
- The `references/` directory is optional

---

## 4. Data Models

### SkillSource

A configured GitHub location to scan for skills.

```python
@dataclass(frozen=True)
class SkillSource:
    type: Literal["repo", "collection"]       # single skill repo vs multi-skill repo
    owner: str                                 # GitHub org or user
    repo: str                                  # repo name
    path: str = "/"                            # subdirectory to scan
    branch: str = "main"                       # branch to fetch from
    auth_mode: Literal["app", "public"] = "app"  # auth strategy for this source
```

- `auth_mode="app"`: uses GitHub App installation token (5,000 req/hr). Requires the App to be installed on the repo.
- `auth_mode="public"`: unauthenticated access (60 req/hr shared). Works for **any public repo** without App installation.

- `collection`: scans subdirectories at `path` for folders containing `SKILL.md`
- `repo`: expects `SKILL.md` at `path` (or `path/SKILL.md`)

### Skill

A parsed skill with its content.

```python
@dataclass(frozen=True)
class Skill:
    name: str                             # from SKILL.md frontmatter
    description: str                      # from SKILL.md frontmatter
    content: str                          # full SKILL.md body (without frontmatter)
    references: dict[str, str]            # relative_path → content
    source_url: str                       # GitHub URL for attribution
    repo: str                             # owner/repo
    path: str                             # path within repo
    last_fetched: datetime                # cache timestamp
```

### Discovery Logic

1. **Collection sources:** list directory contents at `path` via GitHub API → for each subdirectory, check if it contains `SKILL.md` → parse each found skill
2. **Repo sources:** check for `SKILL.md` at `path` → parse if found
3. **Reference scanning:** for each skill directory, recursively scan `references/` subdirectory for all `.md` files

---

## 5. MCP Tools

Seven tools exposed to Claude:

### `list_skills`

- **Input:** `source` (optional, filter by `owner/repo`)
- **Output:** List of `{name, description, repo, path, auth_mode}` for all discovered skills
- **Notes:** Lightweight — returns metadata only, no file contents. Shows `auth_mode` badge per skill.

### `get_skill`

- **Input:** `name` (required), `include_references` (optional, default `true`)
- **Output:** Full SKILL.md content + references dict `{"logline-os/agents.md": "content...", "brand-system.md": "content..."}`
- **Notes:** Returns the complete skill tree

### `search_skills`

- **Input:** `query` (required), `source` (optional, filter by repo)
- **Output:** List of matching skills with name, description, and relevance
- **Notes:** Keyword matching against name + description + SKILL.md content

### `install_skill`

- **Input:** `name` (required), `target_dir` (optional, default `~/.claude/skills/`)
- **Output:** Install path on success
- **Notes:** Downloads skill directory to local disk. Not functional from claude.ai (no local filesystem access). Available for future Claude Code integration.

### `refresh_skills`

- **Input:** `source` (optional, filter by repo)
- **Output:** Updated skill count
- **Notes:** Deletes cache for specified source (or all), re-fetches from GitHub

### `add_source`

- **Input:** `owner` (required), `repo` (required), `type` (required: "repo" or "collection"), `path` (optional), `branch` (optional, default "main"), `auth_mode` (optional, default "app": "app" or "public")
- **Output:** Confirmation with discovered skill count + rate limit warning if `public`
- **Notes:** Adds new source at runtime, persists to `sources.json` in cache directory. Use `auth_mode="public"` for any public repo without GitHub App installation.

### `remove_source`

- **Input:** `owner` (required), `repo` (required)
- **Output:** Confirmation with removed skill count
- **Notes:** Removes a source and its cached data. Persists removal to `sources.json`.

---

## 6. GitHub Authentication (Dual Mode)

### Auth Mode: `app` (GitHub App)

For private repos and repos where the GitHub App is installed.

**Setup:**

1. Create a GitHub App (e.g., "Skill MCP")
2. Grant `contents: read` repository permission
3. Install on repos/orgs containing skills
4. Configure credentials as environment variables

**Token Flow:**

1. Server starts → reads App credentials from env vars
2. Creates JWT signed with the App's private key
3. Exchanges JWT for installation access token (expires 1 hour)
4. Auto-refreshes token before expiry
5. All GitHub API calls for `app` sources use the installation token

**Rate limit:** 5,000 requests/hour per installation

**Why GitHub App:**

- Scoped to specific repos (not entire account)
- Private key doesn't expire (unlike PATs)
- Can be installed on external orgs (with approval)

### Auth Mode: `public` (Unauthenticated)

For any public GitHub repo — no App installation required.

**Behavior:**

- GitHub API calls made without `Authorization` header
- Works for **any public repo** from any user/org
- No setup required by the skill author

**Rate limit:** 60 requests/hour (shared across the entire server)

**Mitigations for low rate limit:**

- Longer cache TTL for public sources (4 hours default vs 1 hour for `app`)
- Aggressive ETag usage — GitHub returns 304 on unchanged repos (no rate limit cost)
- Graceful 403/429 handling: serve stale cache with message `"Rate limited on public GitHub API. Serving cached data until refresh is possible."`
- Log rate limit headers (`X-RateLimit-Remaining`) on every response

### Central Skill Repo Use Case

Any user can connect any public skill repo to the server:

1. Deploy the Skill MCP server (one central instance on Render)
2. In claude.ai → connect to the MCP server URL
3. User asks Claude to run: `add_source owner="anyuser" repo="their-skill-repo" type="repo" path="skills/my-skill" auth_mode="public"`
4. Skills become immediately available

For higher rate limits, skill authors can install the GitHub App on their repo → use `auth_mode="app"` instead.

---

## 7. File-Based Cache

### Cache Directory Structure

```
/tmp/skill-mcp-cache/
├── sources.json                    # Persisted source registry (from add_source)
├── owner__repo/                    # Double underscore separator
│   ├── _meta.json                  # Last fetched timestamp, etag, skill list
│   ├── skill-name/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── ... (mirrors GitHub structure)
│   └── another-skill/
│       └── ...
└── owner2__repo2/
    └── ...
```

### Cache Behavior

- **TTL (auth-mode-aware):**
  - `app` sources: 1 hour default (`CACHE_TTL_SECONDS`)
  - `public` sources: 4 hours default (`CACHE_TTL_PUBLIC_SECONDS`) — longer to conserve rate limit
- **Cache hit:** return from disk, no GitHub API call
- **Cache miss/expired:** fetch from GitHub, write to disk, return
- **Rate limit fallback:** if GitHub returns 403/429, serve stale cache with warning message
- **`refresh_skills` tool:** deletes cache dir for source, re-fetches immediately
- **GitHub ETags:** use `If-None-Match` header — if repo hasn't changed, GitHub returns 304 (saves bandwidth, doesn't count against rate limit)
- **`_meta.json` stores:** last fetched timestamp, etag, skill list, auth_mode, rate limit remaining

---

## 8. Configuration

### Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `GITHUB_APP_ID` | No | — | GitHub App ID (required only if using `app` auth mode) |
| `GITHUB_APP_PRIVATE_KEY` | No | — | PEM private key (required only if using `app` auth mode) |
| `GITHUB_APP_INSTALLATION_ID` | No | — | Installation ID (required only if using `app` auth mode) |
| `SKILL_SOURCES` | Yes | `[]` | JSON array of source configs |
| `CACHE_TTL_SECONDS` | No | `3600` | Cache expiry for `app` sources (seconds) |
| `CACHE_TTL_PUBLIC_SECONDS` | No | `14400` | Cache expiry for `public` sources (seconds, default 4 hours) |
| `PORT` | No | `8000` | HTTP server port |
| `API_KEY` | No | — | Bearer token auth for MCP endpoint |

### SKILL_SOURCES Format

```json
[
  {
    "owner": "yourorg",
    "repo": "skills-collection",
    "type": "collection",
    "path": "skills",
    "auth_mode": "app"
  },
  {
    "owner": "yourorg",
    "repo": "logline-skill",
    "type": "repo",
    "path": ".claude/skills/loglineai",
    "auth_mode": "app"
  },
  {
    "owner": "community-user",
    "repo": "public-skill-repo",
    "type": "repo",
    "path": "skills/cool-skill",
    "auth_mode": "public"
  }
]
```

`auth_mode` defaults to `"app"` if omitted (backward compatible).

### API Key Protection

If `API_KEY` is set, all incoming MCP requests must include `Authorization: Bearer <key>` header. Prevents unauthorized access to the hosted server.

---

## 9. Deployment

### Render Configuration

- **Service type:** Web Service (Python)
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python -m skill_mcp`
- **Health check:** `GET /health` (returns total sources, app vs public count, cache stats, rate limit status)
- **Persistent disk:** mount at `/tmp/skill-mcp-cache` for cache survival across deploys

### Connecting to claude.ai

1. Deploy to Render → get URL (e.g., `https://skill-mcp-xxxx.onrender.com`)
2. In claude.ai → Settings → Integrations → Add MCP Server
3. Enter the server URL + API key
4. Claude now has access to all 6 tools

---

## 10. Project Structure

```
skill_mcp/
├── pyproject.toml                  # Dependencies & project metadata
├── requirements.txt                # Pinned deps for Render
├── skill_mcp/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point — starts FastMCP server
│   ├── server.py                   # FastMCP app definition, 7 tool handlers
│   ├── github_client.py            # GitHub App auth, JWT, API calls
│   ├── cache.py                    # File-based cache read/write/invalidate
│   ├── models.py                   # SkillSource, Skill frozen dataclasses
│   ├── discovery.py                # Skill discovery logic (collection vs repo)
│   └── config.py                   # Env var loading & validation
└── tests/
    ├── test_cache.py
    ├── test_discovery.py
    ├── test_github_client.py
    └── test_server.py
```

### Dependencies

- `fastmcp` — MCP server framework (Streamable HTTP + stdio)
- `httpx` — async HTTP client for GitHub API
- `PyJWT` — JWT creation for GitHub App auth
- `cryptography` — RSA key handling for JWT signing
- `pyyaml` — YAML frontmatter parsing
- `python-dotenv` — local env var loading (dev only)
- `pytest` / `pytest-asyncio` — testing

### File Size Targets

Each source file under 200 lines. 8 focused modules with single responsibilities:
- `config.py` — reads and validates env vars (~50 lines)
- `models.py` — frozen dataclasses (~40 lines)
- `github_client.py` — dual auth mode + API calls (~180 lines)
- `cache.py` — read/write/invalidate disk cache (~120 lines)
- `discovery.py` — skill scanning logic (~100 lines)
- `server.py` — 7 tool handlers (~200 lines)
- `__main__.py` — entry point (~20 lines)

---

## 11. Security Considerations

- GitHub App private key stored as Render environment variable, never in code
- API key protects the MCP endpoint from unauthorized access
- No user data stored — server is stateless except for skill cache
- Cache contains only public/authorized repo content
- All GitHub API calls use HTTPS
- Installation tokens auto-expire after 1 hour
- Input validation on all tool parameters — sanitize `owner`/`repo` to prevent path traversal
- Rate limit status logged for public sources to detect abuse

---

## 12. Limitations & Future Work

### Current Limitations

- `install_skill` tool doesn't work from claude.ai (no local filesystem)
- Single GitHub App installation (one set of repos) — multi-installation support is possible but not in v1
- Public mode: 60 req/hr shared across all public sources (mitigated by aggressive caching)
- Search is keyword-based, not semantic

### Future Enhancements

- Claude Code stdio transport support (when used locally)
- Semantic search using embeddings
- Skill versioning (pin to specific commit/tag)
- Web dashboard for managing sources
- Webhook-based cache invalidation (GitHub pushes trigger refresh)
- Multi-user support with per-user source configs
