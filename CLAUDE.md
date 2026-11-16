# Notion Study Assistant — CLAUDE.md

CS146S Week 2 assignment: a Python MCP server that will let an MCP
client (e.g. Claude) search, read, and eventually write Notion pages
on the user's behalf.

## Verified Architecture

- `server.py` — FastMCP server entry point, runs over stdio
  (`mcp.run(transport="stdio")`). Currently exposes exactly one tool,
  `health()`, which reports server status without contacting Notion.
- `oauth.py` — OAuth configuration loading (`.env`), browser-based
  login flow with a local callback server on `localhost:8765`, state
  (CSRF) validation, authorization-code exchange, token cache
  read/write (`.tokens/notion.json`, written atomically with `0600`
  file / `0700` directory permissions), token refresh, and
  `verify_api_access()` (refresh-once-after-401 check against
  `/search`).
- `notion_api.py` — `NotionAPIClient`, the shared HTTP layer:
  - `request()`: sends authenticated calls to the Notion API, retries
    exactly once after an HTTP 401 by refreshing cached tokens, and
    turns all failure modes (network error, bad JSON, 403/404/429/5xx)
    into a structured `{"error": {code, message, retryable,
    suggested_action}}` dict instead of raising.
  - `search_pages()`: calls `/search` with a page-object filter,
    validates the response shape, and returns shaped
    `{"ok", "pages": [{id, title, url}], "has_more", "next_cursor"}`.
- `check_notion_api.py`, `check_search_pages.py` — manual scripts for
  exercising the request layer / search against the real Notion API
  from the terminal. Not automated tests.
- `tests/` — pytest suite, all mocked (no live network calls):
  - `test_oauth_refresh.py` — 401 → refresh → retry logic in
    `oauth.verify_api_access`.
  - `test_notion_api.py` — same refresh logic inside
    `NotionAPIClient.request()`, plus a broken-token-cache case.
  - `test_search_pages.py` — response shaping and error passthrough
    for `search_pages()`.
  - `test_protpcpl.py` — real MCP stdio protocol check (launches
    `server.py` as a subprocess, calls `tools/list` and `tools/call`).
  - `async_prac.py` — scratch file for practicing `asyncio`, unrelated
    to the server.
- `.env.example` — template for `NOTION_CLIENT_ID`,
  `NOTION_CLIENT_SECRET`, `NOTION_REDIRECT_URI`. No real values.
- `.mcp.json.example` — placeholder, currently empty.

### Implemented

- MCP skeleton with a `health` tool, verified over real MCP stdio.
- Notion OAuth login, token caching, and refresh.
- Shared request layer with one refresh attempt after a 401.
- Page search (`search_pages`) with shaped output and cursor
  pagination.

### Planned, not implemented

- Reading page content (page metadata + child blocks, including
  pagination and nested blocks).
- Page creation, with a preview step before committing.
- Title-update operation (keep only if it ends up implemented and
  justified).
- Exposing any Notion operation (search, read, write) as an actual
  `@mcp.tool()` in `server.py` — right now only `health` is exposed.
- MCP host integration and a recorded multi-tool / failure-recovery
  workflow.

Do not describe anything in this "Planned" list as done in commits,
docs, or code comments until it is actually implemented and tested.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# OAuth: one-time login (opens browser, requires .env configured)
python oauth.py login

# OAuth: inspect cached tokens without network calls
python oauth.py status

# OAuth: verify API access, refreshing once on 401
python oauth.py verify

# OAuth: force a token refresh
python oauth.py refresh

# Manual live checks against the real Notion API
python check_notion_api.py
python check_search_pages.py "some query" --page-size 10

# Run the automated test suite (mocked, no network calls)
pytest

# Run the MCP server directly (normally launched by an MCP client)
python server.py
```

## Credential Handling Rules

- Real secrets live only in `.env` (git-ignored); `.env.example` holds
  placeholder keys only.
- OAuth tokens are cached only in `.tokens/notion.json` (git-ignored),
  written with `0600` permissions inside a `0700` directory.
- Never commit `.env`, anything under `.tokens/`, or a real
  `.mcp.json` — all are excluded in `.gitignore`.
- Never print, log, or paste access tokens, refresh tokens, or raw
  private Notion page content into chat, commits, or this file.
- Before committing, check `git status` / staged diffs for
  accidentally included credential or token-cache files.
- Debug `print()` statements that could leak request/response bodies
  (see commented-out debug lines in `notion_api.py`) must stay
  commented out or removed before submission.

## Learning Workflow

The user is learning Python and practicing English through this
project. When working here:

- Use clear English and explain unfamiliar technical terms.
- Before implementing a feature, explain its purpose, inputs,
  outputs, and how it fits into the existing code.
- Work in small steps. Only implement the step the user requests.
- After each step, explain the changes and provide verification
  commands with expected results.
- Distinguish mocked tests from live API checks.
- Do not run live API calls, use subagents, or commit or push
  changes unless the user explicitly requests them.
- Never read or display `.env`, token caches, or credentials.
