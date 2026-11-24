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
  - `request()`: sends authenticated calls to the Notion API. On an
    HTTP 401 it attempts exactly one token refresh; the original
    request is retried only if that refresh succeeds, otherwise the
    refresh's own error is returned immediately. It turns all failure
    modes (network error, bad JSON, 403/404/429/5xx, a failed refresh)
    into a structured `{"error": {code, message, retryable,
    suggested_action}}` dict instead of raising.
  - `search_pages()`: calls `/search` with a page-object filter,
    validates the response shape, and returns shaped
    `{"ok", "pages": [{id, title, url}], "has_more", "next_cursor"}`.
  - `get_page(page_id)`: retrieves page metadata only
    (`{id, title, url}`); validates the ID before requesting.
  - `get_block_children(block_id, page_size=100, start_cursor=None)`:
    one batch of a block's direct children; never auto-paginates.
  - `_walk_block_tree()` / `_walk_children()`: bounded, depth-first,
    preorder traversal of a page's block tree, with a shared request
    budget, depth bound, cursor-cycle detection, and child_page/
    child_database boundary reporting. Internal; no public tool uses
    it directly.
  - `read_page_blocks(page_id, ...)`: readable text for a page's
    blocks, built on `_walk_block_tree()` via an `on_block` callback;
    bounds output live with `max_blocks`/`max_characters` instead of
    fetching everything and trimming afterward.
  - `get_page_content(page_id, ...)`: combines `get_page()` and
    `read_page_blocks()` into one result (page metadata + body text +
    read status); short-circuits on a metadata error.
  - `create_page(parent_page_id, title, content, *, dry_run=True)`:
    Phase 2.4.1 + 2.4.2, mocked only so far (no live Notion write has
    been made). With `dry_run=True` (the default), validates inputs —
    including Notion's size limits — and returns a preview
    (`parent_page_id`, `title`, `content`) with zero calls to
    `request()`. With `dry_run=False`, builds a page-create payload
    (one `paragraph` block per line of `content`, text chunked to
    Notion's 2000-character rich-text limit instead of truncated) and
    calls `request()` once (`POST /pages`); returns the new page's
    `id`/`title`/`url` on success, passes request-layer errors through
    unchanged, and returns a distinct error for a malformed success
    response. Live creation against the real workspace is Phase 2.4.3.
- `check_notion_api.py`, `check_search_pages.py`, `check_get_page.py`,
  `check_get_block_children.py`, `check_block_tree.py`,
  `check_read_page_blocks.py`, `check_get_page_content.py`,
  `check_create_page_live.py` — manual scripts for exercising each
  layer above against the real Notion API from the terminal. Not
  automated tests. `check_create_page_live.py` (Phase 2.4.3) always
  previews first; only with `--create` does it actually create a page
  and read it back — not yet run against the real API (see
  `PROJECT_CONTEXT.md`).
- `tests/` — pytest suite, all mocked (no live network calls):
  - `test_oauth_refresh.py` — 401 → refresh → retry logic in
    `oauth.verify_api_access`.
  - `test_notion_api.py` — same refresh logic inside
    `NotionAPIClient.request()`, plus a broken-token-cache case.
  - `test_search_pages.py` — response shaping and error passthrough
    for `search_pages()`.
  - `test_get_page.py` — `get_page()` shaping and validation.
  - `test_get_block_children.py` — `get_block_children()` batch
    shaping, validation, and malformed-response handling.
  - `test_block_tree.py` — `_walk_block_tree()` traversal order,
    pagination, budgets, boundaries, and failure handling.
  - `test_read_page_blocks.py` — `read_page_blocks()` text extraction
    and output-limit enforcement.
  - `test_get_page_content.py` — `get_page_content()` combining and
    short-circuit behavior.
  - `test_create_page.py` — `create_page()` local-preview validation,
    `dry_run` defaulting/branching, multiline content preservation,
    mocked live page creation (payload shape, success/error handling),
    and Notion size-limit enforcement.
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
- Page metadata retrieval (`get_page`).
- One batch of a block's direct children (`get_block_children`).
- Bounded, depth-first block-tree traversal (`_walk_block_tree`).
- Readable, bounded text extraction from page content
  (`read_page_blocks`).
- Combined page metadata + body read (`get_page_content`).
- Page creation (`create_page`, Phases 2.4.1 + 2.4.2), mocked only:
  `dry_run=True` (the default) validates and previews with zero
  `request()` calls; `dry_run=False` builds and sends a real
  page-create payload via one `request()` call. No live Notion write
  has been made against the authorized workspace yet (Phase 2.4.3).

Automated tests exist and pass for all of the above — mocked Notion
API tests plus a real local MCP stdio protocol test (`pytest tests/`
— 77 passed as of 2026-11-23). Most of these also have a manual live
check script (`check_*.py`); see `PROJECT_CONTEXT.md` for which live
checks have actually been run versus which are still pending.

### Planned, not implemented

- A real, approved live call to `create_page(..., dry_run=False)`
  against the authorized workspace, followed by reading the new page
  back with `get_page_content()` to confirm the round-trip (Phase
  2.4.3). `check_create_page_live.py` is written and ready for this
  (run `python check_create_page_live.py YOUR_PARENT_PAGE_ID` for a
  preview only, or add `--create` for the live write + read-back) but
  has not actually been run against the real API; its outcome is
  pending until the user runs it. A possible title-update operation
  remains undecided too (keep only if implemented and justified).
- Exposing any Notion operation (search, read, write) as an actual
  `@mcp.tool()` in `server.py` — right now only `health` is exposed
  (Phase 3).
- MCP host integration and a recorded multi-tool / failure-recovery
  workflow (Phase 5).

See `PROJECT_CONTEXT.md` for the full roadmap, phase-by-phase design
decisions, and the chronological instruction log.

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

## Maintenance Routine (PROJECT_CONTEXT.md)

`PROJECT_CONTEXT.md` holds the project's resumable memory: a "Resume
here" summary, the roadmap, phase-by-phase design decisions, and a
chronological log of every project instruction and its outcome. A new
session should:

1. Read `PROJECT_CONTEXT.md`'s "Resume here" section (and the relevant
   phase section) before starting work.
2. When a new project instruction is received, append a log entry for
   it under "Chronological instruction log" (original wording, with
   any sensitive values replaced by `[REDACTED]`; phase; requested
   outcome/acceptance criteria).
3. Before finishing that task, fill in the entry's outcome: files or
   functions changed, decisions and reasons, commands actually run,
   observed results, and what remains. Update "Resume here" if the
   current phase or next action changed.
4. Keep English for code, CLI output, and this repository's own
   documentation; preserve the user's original language when quoting
   their instructions verbatim.
5. Update `writeup.md` when there is new assignment-facing evidence to
   report (e.g. a test suite actually run, a live check actually
   performed) — not for internal process notes, which belong in
   `PROJECT_CONTEXT.md` instead.
