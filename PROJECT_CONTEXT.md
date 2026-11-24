# PROJECT_CONTEXT.md — Notion Study Assistant

Persistent project memory for the CS146S Week 2 assignment. Read this
file (at least "Resume here") before starting work in a new session.
See `CLAUDE.md` for architecture, dev commands, and the learning
workflow; see `writeup.md` for the assignment-facing report.

---

## Resume here

**Goal.** A Python MCP server so an agent (e.g. Claude) can search,
read, and eventually write Notion pages on the user's behalf, for the
CS146S Week 2 assignment. The user is learning Python and practicing
English through this project.

**Current phase.** Phase 2.3 (reading page content) is complete,
through subphase 2.3.5. Phase 2.4.1 (local preview) and Phase 2.4.2
(live page creation) are both now complete, mocked only. Phase 2.4.3
(live creation, then read the new page back) is planned next but not
started.

**Last verified result.** `python -m pytest tests/ -v` → **77 passed**
on 2026-11-23 — mocked Notion API tests plus a real local MCP stdio
protocol test (`test_protpcpl.py`); no live Notion calls (71 from
before Phase 2.4.2, plus 6 net new in `tests/test_create_page.py`:
18 total there now, up from 12). All of Phase 2.4.2's tests, including
the one that actually exercises `create_page(..., dry_run=False)`
end to end, mock `NotionAPIClient.request()` — no real POST to
`/pages` has been made. Separately, per the user's own terminal
evidence (`writeup.md`'s "Recorded live evidence" table): page-metadata
retrieval, the direct-children batch, the depth-zero traversal, and
the bounded text read have all been exercised live against the real
Notion API and matched expectations. Only the combined
`get_page_content()` live check (`check_get_page_content.py`) is still
pending for Phase 2.3; `create_page()` has no live check yet at all
(neither dry_run mode has been exercised against the real API).

**Open questions.**
- Phase 2.2: some titles in the raw `/search` response lacked the
  literal query text. Cause unconfirmed.
- Phase 2.3 final acceptance: the live run of
  `check_get_page_content.py "YOUR_W2_TEST_PAGE_ID"` is the only
  remaining open item.

**Next action.** The user runs the live Phase 2.4.3 check themselves:
`python check_create_page_live.py YOUR_PARENT_PAGE_ID` for a preview
only, `... --create` to actually create a page and read it back, or
`... --verify-id NEW_PAGE_ID` to retry only the read-back for a page
that was already created live (never re-run `--create` to recover
from a failed read). This script exists and is syntax-checked but has
**not** been run against the real API in any session recorded here —
its outcome is pending until the user runs it and reports the result.
Do not run it without the user's explicit request — the Learning
Workflow rule in `CLAUDE.md` says to work in small, explicitly
requested steps, and live writes need explicit approval.

---

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | FastMCP stdio skeleton, `health` tool | Done |
| 1 | OAuth login, token cache, refresh | Done |
| 2.1 | Shared authenticated request layer, one 401 retry | Done |
| 2.2 | Page search (`search_pages`) | Done |
| 2.3.1 | Page metadata (`get_page`) | Done |
| 2.3.2 | One batch of child blocks (`get_block_children`) | Done |
| 2.3.3 | Bounded block-tree traversal (`_walk_block_tree`/`_walk_children`) | Done |
| 2.3.4 | Readable text extraction (`read_page_blocks`) | Done |
| 2.3.5 | Combined metadata + body (`get_page_content`) | Done |
| 2.4.1 | Local preview for page creation (`create_page`, `dry_run`) | Done |
| 2.4.2 | Page creation (`create_page`, `dry_run=False`, mocked only) | Done |
| 2.4.3 | Live creation, then read the new page back (`check_create_page_live.py`) | Script ready; live result pending |
| (maybe) | Title-update operation | Planned, keep only if implemented and justified |
| 3 | Register operations as `@mcp.tool()`s in `server.py` | Planned |
| 4 | Tool schemas with parameter limits, workflow instructions, read-only annotations, write preview | Planned |
| 5 | Register with an MCP host; recorded multi-tool + failure/recovery transcript; protocol test | Planned |
| 6 | Submission writeup; credential/`.mcp.json` hygiene check | Planned |

---

## Phase history

Each entry: goal → plan → main files/functions → design decisions and
reasons → verification evidence, with implementation / tests-in-repo /
tests-run / live-results kept distinct and missing evidence marked
**pending**.

### Phase 0 — MCP skeleton
*Reconstructed summary (no verbatim prompt available; from
`server.py`, `writeup.md`, commit `d1b6324`).*

- **Goal.** Stand up a minimal FastMCP server over stdio to prove the
  protocol works before any Notion logic exists.
- **Files.** `server.py` — exposes exactly one tool, `health()`, which
  reports server status without contacting Notion.
- **Verification.** `tests/test_protpcpl.py::test_mcp_protocol` launches
  `server.py` as a subprocess and calls `tools/list` / `tools/call`
  over real MCP stdio. **Tests in repo:** yes. **Tests run:** yes, as
  part of the full suite on 2026-11-22 (passed). **Live host
  integration:** pending (Phase 5).

### Phase 1 — OAuth
*Reconstructed summary (no verbatim prompt available; from `oauth.py`,
`CLAUDE.md`, `writeup.md`, commits `d1b6324`, `34a7f80`).*

- **Goal.** Let the server obtain and reuse Notion credentials without
  re-prompting the user every run.
- **Plan / design decisions.**
  - Authorization-code flow with a random `state` value and a local
    callback listener on `localhost:8765`; the listener compares the
    returned `state` against the one generated at login before
    accepting the code — CSRF protection.
  - Tokens are cached in `.tokens/notion.json`, written atomically
    with `0600` file / `0700` directory permissions, and are
    git-ignored — reason: avoid leaking long-lived credentials via
    version control or loose file permissions.
  - `verify_api_access()` does one refresh-after-401 check against
    `/search` so a caller can confirm access without a full login.
- **Files.** `oauth.py` — config loading, login flow, token cache
  read/write, refresh, `verify_api_access()`.
- **Verification.**
  - **Tests in repo:** `tests/test_oauth_refresh.py` (401 → refresh →
    retry; rejected-refresh-returns-error-without-browser).
  - **Tests run:** yes, part of the full suite 2026-11-22 (2 passed).
  - **Live results reported by the user (per `writeup.md`):**
    `python oauth.py login` saved tokens; a separate `status` process
    loaded them; cache file/directory modes were `600`/`700`; `verify`
    and `refresh` succeeded, and a second `verify` after refresh
    reported `refreshed: false`. These are the user's own prior
    observations, not re-verified in this session.

### Phase 2.1 — Shared request handling
*Reconstructed summary (no verbatim prompt available; from
`notion_api.py`, `writeup.md`, commit `31c0751`).*

- **Goal.** One place that attaches credentials, retries once after a
  401, and turns every failure mode into a structured, actionable
  error instead of raising.
- **Design decisions.**
  - Exactly one refresh attempt after a 401; the original request is
    retried only if that refresh succeeds — a failed refresh returns
    its own error immediately, with no retry. Never a loop — reason:
    avoid masking a genuinely broken credential behind repeated
    silent refreshes.
  - `read_only` flag on `request()` changes whether network/5xx/JSON
    errors are marked `retryable` and what `suggested_action` says —
    reason: a timed-out *write* may have already reached Notion, so
    the caller is told to check before retrying; a failed *read* is
    always safe to retry.
- **Files.** `notion_api.py::NotionAPIClient.request()`,
  `_http_error()`, `_load_credentials()`.
- **Verification.**
  - **Tests in repo:** `tests/test_notion_api.py` (refresh-and-retry
    uses the new token; broken token cache → `TOKEN_CACHE_ERROR`
    before any network call).
  - **Tests run:** yes, 2026-11-22 (2 passed).
  - **Live results reported by the user (per `writeup.md`):**
    `check_notion_api.py` completed a live search request successfully.

### Phase 2.2 — Page search
*Reconstructed summary (no verbatim prompt available; from
`notion_api.py`, `writeup.md`, commit `53ed7af`).*

- **Goal.** Let an agent find a page by title and get back an ID it
  can pass into the reader.
- **Design decisions.** `search_pages()` returns one batch
  (`pages`, `has_more`, `next_cursor`); the client does not enforce
  exact substring matching on titles, so callers should inspect
  returned titles before picking a page — reason: Notion's own search
  is not an exact-match search, and some titles in raw responses
  lacked the literal query text (cause still unconfirmed).
- **Files.** `notion_api.py::NotionAPIClient.search_pages()`,
  `_extract_page_title()`.
- **Verification.**
  - **Tests in repo:** `tests/test_search_pages.py` (title shaping +
    pagination preserved; request-error passthrough).
  - **Tests run:** yes, 2026-11-22 (2 passed).
  - **Live results reported by the user (per `writeup.md`):** live
    searches returned accessible pages; an unlikely query returned an
    empty result; a cursor retrieved the next batch.

### Phase 2.3 — Reading page content

Split into five subphases, each adding one function on top of the
last, ending in a single combined entry point. This part of the
history comes from the current session's own record of the requests
(not reconstructed) for 2.3.1–2.3.4; 2.3.5 was implemented and
committed outside any session recorded here, so it is a reconstructed
summary.

#### 2.3.1 — Page metadata (`get_page`)

- **Requested outcome.** Retrieve a page's ID, title, and URL given a
  `page_id` from `search_pages()`, reusing `request()` with
  `read_only=True`; validate the ID; add focused tests; no live calls,
  no MCP tool registration, no commit/push performed by the assistant.
- **Decision and reason.** Metadata is fetched before any body read so
  an inaccessible page's error surfaces before spending any
  child-block budget on it.
- **Files/functions.** `notion_api.py::get_page()`,
  `_extract_page_title()` (reused from Phase 2.2).
- **Verification.** **Tests in repo:**
  `tests/test_get_page.py` (6 cases: success shaping, dashless ID
  accepted, invalid/non-string ID rejected without a request,
  request-error passthrough, malformed response →
  `INVALID_PAGE_RESPONSE`). **Tests run:** yes, 2026-11-22 (6 passed).
  **Live check:** user-reported terminal evidence (`writeup.md`'s
  "Recorded live evidence" table; reconciled into this record
  2026-11-23) — the metadata lookup returned the selected page's ID,
  title, and URL. Source: the user; not observed directly in any
  session recorded here.

#### 2.3.2 — One batch of child blocks (`get_block_children`)

- **Requested outcome.** A one-batch helper —
  `get_block_children(block_id, page_size=100, start_cursor=None)` —
  with pagination controlled by the caller/traversal, not by this
  method itself; strict input validation with specific error codes
  (`INVALID_BLOCK_ID`, `INVALID_PAGE_SIZE`, `INVALID_CURSOR`,
  `INVALID_BLOCK_CHILDREN_RESPONSE`); tests covering batch shaping,
  no auto-pagination, and malformed-response rejection.
- **Decision and reason.** Kept to exactly one batch, matching the
  existing `search_pages()` convention — reason given by the user:
  the caller/traversal (Phase 2.3.3) needs to own cursor state across
  many different parents, which a self-paginating method could not
  support.
- **Files/functions.** `notion_api.py::get_block_children()`.
- **Verification.** **Tests in repo:** `tests/test_get_block_children.py`
  (13 cases). **Tests run:** yes, 2026-11-22 (13 passed). **Live
  check:** user-reported terminal evidence (`writeup.md`'s "Recorded
  live evidence" table; reconciled 2026-11-23) — a direct-children
  call with `page_size=2` returned a heading and a table; the table
  had children, and the page had another batch. Source: the user; not
  observed directly in any session recorded here.

#### 2.3.3 — Bounded block-tree traversal (`_walk_block_tree`)

- **Requested outcome.** Depth-first, preorder traversal of a page's
  block tree: `_walk_block_tree(page_id, *, max_depth, max_request_calls,
  page_size)` plus a recursive `_walk_children()`. Direct children are
  depth 0. All budgets (depth, request calls) are shared across the
  whole traversal, not per-branch. Preserve block IDs, parent IDs,
  depth, and document order, including table rows. Do not skip
  text-bearing descendants just because their container has no text.
  Define behavior for pagination/nested-read failures, malformed
  responses, and repeated cursors; never report incomplete content as
  complete. Add `tests/test_block_tree.py` covering output limits,
  empty pages, invalid IDs, mid-read failures, container traversal,
  and budget boundaries.
- **Decisions and reasons.**
  - A shared mutable `state` dict (not globals, not per-call return
    values) carries `blocks`, `request_calls`, `partial`, `warnings`,
    and a `stopped` flag through every recursive call — this is what
    makes the request budget and the halt signal genuinely global
    across the whole traversal.
  - A **root** request failure (the very first `get_block_children()`
    call of the whole traversal) returns the raw structured error
    directly; **any later** failure is recorded as a `request_failed`
    warning and halts the traversal, but the blocks already collected
    are kept — reason: a root failure means nothing was read at all,
    while a later failure still leaves a genuinely partial, useful
    result.
  - `child_page`/`child_database` blocks are traversal *boundaries*:
    the walk does not descend into them (they are separate Notion
    objects with their own access rules), but if one `has_children`,
    a `page_boundary` warning is recorded so the caller knows content
    was deliberately left unread.
  - Cursor-cycle detection (`repeated_cursor`) is scoped **per parent**
    via a locally-scoped `used_cursors` set inside each
    `_walk_children()` call, not globally — a judgment call made to
    resolve an ambiguity in the original request, so that a cycle
    under one branch does not abort unrelated branches.
  - `complete=True` means every block reachable within the bounds was
    recorded, with no cursor cycles and no unreported page/database
    boundary — it does *not* certify that text extraction (2.3.4) can
    represent every block.
- **Files/functions.** `notion_api.py::_walk_block_tree()`,
  `_walk_children()`.
- **Verification.** **Tests in repo:** `tests/test_block_tree.py`
  (16 cases, listed in the roadmap/history above by name in the test
  file itself). **Tests run:** yes, 2026-11-22 (16 passed). **Live
  check:** user-reported terminal evidence (`writeup.md`'s "Recorded
  live evidence" table; reconciled 2026-11-23) — a traversal with
  `max_depth=0` recorded 17 direct children in one call and reported
  `max_depth_reached=true`; a traversal limited to one allowed call
  with `page_size=2` recorded two blocks and reported
  `max_requests_reached=true`. Source: the user; not observed directly
  in any session recorded here.

#### 2.3.4 — Readable text extraction (`read_page_blocks`)

- **Requested outcome.** Bounded, readable text extraction —
  `_extract_rich_text()`, `_extract_block_text()`, and a new public
  `read_page_blocks()` — supporting a defined set of block types;
  `max_blocks`/`max_characters` enforced *live* during traversal, not
  by fetching everything and trimming afterward; reuse the existing
  traversal via a callback rather than duplicating the
  pagination/recursion algorithm; add `tests/test_block_tree.py`
  additions plus a new `tests/test_read_page_blocks.py`, and a
  `check_read_page_blocks.py` CLI. Explicitly out of scope: wiring MCP
  tools, page creation, title updates, or marking any live validation
  as completed in `writeup.md`.
- **Decisions and reasons.**
  - Text extraction is added as an optional `on_block(entry, state)`
    callback invoked from inside `_walk_children()`'s existing loop,
    rather than a second traversal function — this was an explicit
    requirement, so that the pagination/recursion logic has exactly
    one implementation.
  - The callback can set `state["stopped"] = True` to halt the whole
    traversal immediately — this is how `max_blocks`/`max_characters`
    stop further `get_block_children()` calls as soon as the next
    block would exceed the budget, mirroring how `max_depth` and
    `max_request_calls` already behaved in 2.3.3. A block that would
    push output over either limit is left out entirely rather than
    truncated.
  - `_extract_block_text()` returns `""` for structural containers
    (`table`/`column_list`/`column`, which carry no text of their own)
    and for supported-but-empty content (e.g. an empty paragraph), but
    `None` for a genuinely unsupported block type or malformed
    type-specific data — these three cases are kept distinct in the
    result (`unsupported_block_types` vs. plain empty text).
  - Rich-text fragments are joined with no added separator, since
    Notion splits rich text only at formatting boundaries, not word
    boundaries. Table rows join cells with `" | "`. A to-do is
    prefixed with `"[x] "`/`"[ ] "`.
- **Files/functions.** `notion_api.py::_extract_rich_text()`,
  `_extract_block_text()`, `read_page_blocks()`;
  `RICH_TEXT_BLOCK_TYPES`, `STRUCTURAL_CONTAINER_TYPES` constants;
  `check_read_page_blocks.py`.
- **Verification.** **Tests in repo:** `tests/test_read_page_blocks.py`
  (13 cases). **Tests run:** yes, 2026-11-22 (13 passed, also
  confirmed in the prior session after an accidental overwrite was
  restored — 54/54 at that time, before 2.3.5's tests existed). **Live
  check:** user-reported terminal evidence (`writeup.md`'s "Recorded
  live evidence" table; reconciled 2026-11-23) — a text read with
  `max_depth=1`, `max_blocks=6`, `page_size=2` returned a heading, a
  table, and four table rows across four child-list calls, with only
  `max_blocks_reached=true`. Source: the user; not observed directly
  in any session recorded here.
- **Incident.** Between this subphase's implementation and 2.3.5, the
  user accidentally overwrote `notion_api.py` with an older editor
  buffer, losing all of 2.3.4's additions. They were restored from the
  conversation record in the same session, preserving one unrelated
  comment the user had separately added inside `_walk_children()`
  (documenting `get_block_children()`'s response shape, still present
  at lines 647–652 of the current file). Verified afterward with the
  full suite then available (54 passed).

#### 2.3.5 — Combined metadata + body (`get_page_content`)
*Reconstructed summary (no verbatim prompt available — implemented
and committed as `5db7d6a` outside any session recorded here; details
below are read from `notion_api.py`, `tests/test_get_page_content.py`,
`check_get_page_content.py`, and `writeup.md`).*

- **Goal (from `writeup.md`).** Answer three questions in one call:
  which page was read, what text was recovered, and how much of the
  page that text represents.
- **Decision and reason.** `get_page_content()` calls `get_page()`
  first; on error, returns immediately without calling
  `read_page_blocks()` at all — reason, matching 2.3.1's own
  rationale: don't spend body-read budget on a page that is already
  known to be inaccessible. `request_calls` in the combined result
  only counts `get_block_children()` calls made while reading the
  body; the `get_page()` call itself is not counted.
- **Files/functions.** `notion_api.py::get_page_content()`.
- **Verification.**
  - **Tests in repo:** `tests/test_get_page_content.py` (4 cases:
    combines metadata+body and forwards all limits unchanged;
    preserves a partial body result and its reason; returns a
    metadata error without calling `read_page_blocks()`; returns a
    body error unchanged).
  - **Tests run:** yes, 2026-11-22, as part of the full suite
    (4 passed).
  - **Live check:** `check_get_page_content.py` hard-codes expected
    values from a specific real page (title `"W2 - New MCP"`, a
    heading + table layout, Chinese cell text) and a `max_blocks=6`
    boundary. Per `writeup.md`, this live run's outcome is still
    **pending** — it is not confirmed in this record whether it has
    actually been executed against the real API. As of the 2026-11-23
    reconciliation, this is the only Phase 2.3 live check still
    pending.

### Phase 2.4 — Preview and page creation

#### 2.4.1 — Local preview (`create_page`) — Done, 2026-11-23

- **Requested outcome.** Add `create_page(parent_page_id, title,
  content, *, dry_run=True)` to `NotionAPIClient`. Validate
  `parent_page_id` (UUID with dashes or 32 hex digits), `title`
  (non-blank), `content` (non-blank, preserving internal whitespace
  and line breaks), and `dry_run` (must be a real `bool`), all
  locally. With `dry_run` omitted or `True`, return `{ok: True,
  dry_run: True, created: False, preview: {parent_page_id, title,
  content}}`. With `dry_run=False`, return a structured error, since
  live creation is Phase 2.4.2's job. Every path makes zero calls to
  `request()`. Add focused tests in `tests/test_create_page.py`,
  including an omitted-`dry_run` main test using
  `request.assert_not_called()`. MCP registration stays out of scope
  (Phase 3); no live Notion check; no commit.
- **Decisions and reasons.**
  - `parent_page_id` reuses the existing `PAGE_ID_PATTERN` (the same
    one `get_page()`/`get_block_children()` use) rather than a new,
    narrower pattern — reason: consistency with the rest of the
    codebase; it already accepts both a dashed UUID and 32 hex
    digits, which is a superset of, but compatible with, what was
    asked.
  - `parent_page_id` and `title` are stripped before being validated
    and returned; `content` is left completely untouched (only
    `.strip()`'d for the blank-check, never reassigned) — reason:
    the spec asked for whitespace/line breaks in the *body* to be
    preserved exactly, while a page title or ID with stray
    surrounding whitespace is very unlikely to be intentional.
  - `dry_run` is validated with `type(dry_run) is not bool`, not
    `isinstance`, so truthy/falsy non-bool values (`1`, `"True"`,
    etc.) are rejected rather than silently coerced — the same style
    already used for `page_size`/`max_depth` elsewhere, flipped to
    require exactly `bool` here.
  - The validated, stripped values are exactly what the preview
    shows — there is no separate "prepare" step that could drift
    from the preview, so Phase 2.4.2 can reuse these same values
    for the real Notion write without re-deriving them.
- **Files/functions.** `notion_api.py::create_page()`.
- **Verification.**
  - **Tests in repo:** `tests/test_create_page.py` (12 cases: preview
    with `dry_run` omitted and asserting `request.assert_not_called()`;
    explicit `dry_run=True`; dashless parent ID accepted; explicit
    `dry_run=False` → `PAGE_CREATION_NOT_IMPLEMENTED`; multiline/blank-
    line content preserved exactly; invalid/non-string parent ID;
    blank/non-string title; blank/non-string content; non-boolean
    `dry_run`).
  - **Tests run:** yes — `python -m pytest tests/test_create_page.py
    -v` → 12 passed; `python -m pytest tests/ -v` (full regression)
    → **71 passed**, both on 2026-11-23.
  - **Live check:** none exists or is needed yet — every path in this
    phase makes zero network calls by design.

#### 2.4.2 — Page creation (`create_page`, `dry_run=False`) — Done, 2026-11-23 (mocked only)

- **Requested outcome.** Replace the `PAGE_CREATION_NOT_IMPLEMENTED`
  branch with a real `POST /pages` call when `create_page()` is
  called with `dry_run=False`. Reuse Phase 2.4.1's validation and
  stripped values; keep the preview as the default. Build the Notion
  payload from `parent.page_id`, `properties.title`, and paragraph
  blocks in `children`. Validate applicable Notion size limits
  consistently for preview and creation, with no silent truncation.
  On success, return `ok=True, dry_run=False, created=True`, and page
  metadata (`id`, `title`, `url`), validating the response before
  reporting success. Pass request-layer errors through unchanged. If
  the success response is malformed, tell the caller to check the
  parent page before retrying, since creation may have already
  succeeded. Also check whether a previously identified
  partially-dashed-UUID regression in `PAGE_ID_PATTERN` was already
  fixed and covered by a test. Update `tests/test_create_page.py`
  accordingly; no live Notion write; no commit/push; MCP registration
  stays Phase 3.
- **Regression found and fixed.** `PAGE_ID_PATTERN` was **not** fixed
  and had no regression test anywhere in the repo. Each dash in the
  pattern was independently optional
  (`[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?...`), so a UUID with only *some*
  of its dashes removed — e.g. `PARENT_ID.replace("-", "", 1)`,
  `"111111111111-1111-1111-111111111111"` — still matched, even
  though it is neither a well-formed dashed UUID nor 32 raw hex
  digits. Verified directly: `PAGE_ID_PATTERN.match(partial)` returned
  a match before the fix. Replaced the pattern with a single
  alternation — `(?:8-4-4-4-12 with required dashes)|(?:32 hex digits,
  no dashes)` — so a page/block ID must now be fully dashed or
  completely dashless, never a mix. This pattern is shared by
  `get_page()`, `get_block_children()`, `_walk_block_tree()`, and
  `create_page()`, so the fix applies to all four; a regression test
  was added only in `tests/test_create_page.py`
  (`test_create_page_rejects_partially_dashed_parent_id`), since that
  is the file this instruction scoped the work to — the other three
  methods' own test files do not yet have an equivalent case.
- **Decisions and reasons.**
  - Each line of `content` (split on `"\n"`) becomes one paragraph
    block in `children`, including an empty line becoming an empty
    paragraph block (`rich_text: []`) — reason: Notion blocks are the
    natural unit for a line break, and this preserves blank lines and
    per-line leading whitespace (indentation) exactly, rather than
    collapsing everything into one block's `rich_text` and losing
    which parts were separate lines.
  - A new `_chunk_rich_text()` helper splits any string into Notion
    rich_text segments of at most 2000 characters each (Notion's own
    per-segment limit), used for both the title and every paragraph's
    text — reason: this represents arbitrarily long text as several
    rich_text objects within one block instead of silently truncating
    it, satisfying "never silently truncate the user's notes" without
    needing multiple Notion blocks just to hold one long line.
  - A line count over `NOTION_MAX_CHILD_BLOCKS` (100, matching
    Notion's documented append-children batch size) is rejected with
    `CONTENT_TOO_LARGE` **before** building any payload or calling
    `request()`, in both `dry_run` modes — reason: a single `/pages`
    call cannot carry more than ~100 children blocks, so the preview
    must fail the same way creation would, rather than previewing
    successfully and then failing only at creation time.
  - Title length is capped at the same 2000-character rich_text limit
    (reusing the existing `INVALID_TITLE` error code with a
    length-specific message) — same reasoning as the line-count
    check: one consistent set of size checks for both preview and
    creation.
  - A malformed-but-2xx response (missing/invalid `id` or `url`, or
    the wrong `object` type) returns a new `INVALID_CREATE_PAGE_RESPONSE`
    error whose `suggested_action` explicitly says to check the parent
    page before retrying — reason: unlike a read, a malformed response
    to a *write* does not mean the write failed; Notion may have
    already created the page, so blindly retrying could create a
    duplicate.
  - Request-layer errors (`"error" in response`) are returned
    completely unchanged, with no wrapping — reason: `request()`
    already attaches the correct `retryable`/`suggested_action` for
    each failure mode (network error, 403/404/429/5xx, failed
    refresh); re-describing them here would risk drifting from that
    single source of truth.
- **Files/functions.** `notion_api.py`: `PAGE_ID_PATTERN` (fixed),
  `NOTION_RICH_TEXT_MAX_LENGTH`, `NOTION_MAX_CHILD_BLOCKS` (new
  constants), `_chunk_rich_text()` (new), `create_page()` (dry_run=False
  branch replaced).
- **Verification.**
  - **Tests in repo:** `tests/test_create_page.py` now has 18 cases
    (up from 12): all 12 original preview/validation cases kept (still
    zero-`request()`-call), plus a partially-dashed-UUID regression
    test, a title-too-long test, a too-many-lines test, and four new
    `dry_run=False` cases — a full success path asserting the exact
    `("POST", "/pages")` call, the exact payload shape (`parent`,
    `properties.title`, `children` as one paragraph block per line),
    `read_only=False`, and exactly one call to `request()`; a dedicated
    blank-line/indentation-preservation case asserting the built
    `children` list directly; a request-error-passthrough case; and a
    malformed-success-response case.
  - **Tests run:** yes — `python -m pytest tests/test_create_page.py
    -v` → **18 passed**; `python -m pytest tests/ -v` (full regression)
    → **77 passed**, both on 2026-11-23.
  - **Live check:** none — every test in this phase mocks
    `NotionAPIClient.request()`; no real `POST /pages` has been made
    against the authorized workspace. That live call, followed by a
    `get_page_content()` read-back, is Phase 2.4.3.

#### 2.4.3 — Live creation and read-back — script ready, live result pending

*Implemented in two passes on 2026-11-23: an initial version (see the
"Prepare Phase 2.4.3" log entry below), then revised the same day
(see "Implement Phase 2.4.3" below) with fixed test inputs shared
with `check_create_page.py`, a stricter three-paragraph check, and a
`--verify-id` read-only recovery path. This section describes the
current (revised) version only.*

- **Requested outcome.** `check_create_page_live.py`, reusing
  `create_page()` and `get_page_content()`, with `check_create_page.py`
  (the existing mocked/offline check) left untouched. Fixed test
  inputs shared between preview and creation: title `"W2 MCP
  round-trip check"`, body `"Review OAuth.\n\n    Check token
  refresh."`. CLI: positional `parent_page_id`; `--create` and
  `--verify-id NEW_PAGE_ID` as mutually exclusive optional flags.
  Always preview first and display the parent ID, title, and body; a
  preview error prints the structured error and exits nonzero; with
  no `--create`, exit after preview. With `--create` and a successful
  preview, call `create_page(dry_run=False)` exactly once, print the
  new page's ID/URL immediately, then call `get_page_content()` and
  check: the read is complete, the returned page ID matches the new
  ID, the title matches, and the body has exactly three top-level
  paragraphs equal to the body split on `"\n"` (blank paragraph and
  the four leading spaces on the last paragraph preserved exactly).
  On a read-back failure, print the new ID and point at `--verify-id`
  to retry only the read; `--verify-id` skips preview and creation
  entirely and runs the same checks against an already-created page,
  so a failed read can be retried without ever creating a second
  page. Run offline checks only; leave the live result pending.
- **Decisions and reasons.**
  - `TITLE`/`CONTENT` are fixed module-level constants, not
    generated per run, and `CONTENT` is exactly the same string
    `check_create_page.py` already uses — reason: the user's
    instruction gave these as literal fixed inputs so the preview and
    the live write agree, and reusing the same content as the
    existing mocked check means the mocked and live checks exercise
    the identical blank-line/indentation case.
  - Read-back verification is factored into one `_verify_read_back()`
    helper, called both right after a live `create_page()` and from
    `--verify-id` — reason: these are meant to be the exact same
    check; a second, slightly different implementation for the retry
    path could silently diverge from what the create-then-verify path
    actually checks.
  - The returned page ID is compared with `UUID(...) ==
    UUID(...)` rather than plain string equality — reason: matches
    the existing convention in `check_get_page_content.py`, which
    normalizes dash formatting the same way, so a cosmetic ID-format
    difference from Notion cannot register as a false failure.
  - `--create` and `--verify-id` are an `argparse` mutually exclusive
    group — reason: this was an explicit requirement, enforced by
    `argparse` itself (verified: passing both exits with code 2 and
    an error) rather than by an `if` check after parsing, so it cannot
    be bypassed by a programming mistake elsewhere in `main()`.
  - On every failure branch (creation error, read-back error,
    incomplete read, or any check mismatch) the script prints an
    actionable message and returns a nonzero exit code, but never
    calls `create_page()` a second time — reason: once a page may
    already exist, retrying creation risks a duplicate; `--verify-id`
    exists precisely so the read can be retried without that risk.
- **Files/functions.** `check_create_page_live.py` (rewritten):
  `TITLE`, `CONTENT` constants; `_verify_read_back()` (new, shared
  helper); `main()` (now has three modes: preview-only, `--create`,
  `--verify-id`). `check_create_page.py` left unchanged. No changes
  to `notion_api.py` or any test.
- **Verification.**
  - **Offline checks run:** `python -m py_compile
    check_create_page_live.py` — passed. `python
    check_create_page_live.py --help` — confirmed `--create`/
    `--verify-id` render as a mutually exclusive group. `python
    check_create_page_live.py parent-id --create --verify-id abc` —
    confirmed `argparse` itself rejects passing both (exit code 2).
    `python check_create_page.py` — the existing mocked check still
    passes unchanged (preview, payload shape including the blank
    paragraph and indented line, and the mocked creation result all
    still PASS). `python -m pytest tests/ -v` (full suite, unaffected
    since no production code was touched) — **77 passed**. All on
    2026-11-24.
  - **Live check:** **pending.** Neither preview, `--create`, nor
    `--verify-id` has been run against the real Notion API in any
    session recorded here. The user will run it themselves and
    report the actual result.

### Phase 3 and later (planned, not started)

- **Phase 3.** Expose the Python operations as `@mcp.tool()`s in
  `server.py`. Document how a page ID returned by search becomes the
  input to reading or creation. (Per the Learning Workflow rule in
  `CLAUDE.md`, no MCP tool other than `health` has been registered in
  any session recorded here.)
- **Phase 4.** Encode parameter limits in tool schemas; add workflow
  instructions, read-only annotations, and a write preview; verify
  errors tell the agent whether and how to retry.
- **Phase 5.** Register with an MCP host; capture a real multi-tool
  transcript and a failure/recovery example; protocol-test a final
  tool; verify expired/revoked credentials produce an actionable
  result during a tool call.
- **Phase 6.** Finish the submission writeup; confirm
  `.mcp.json.example` holds only placeholders and the real
  `.mcp.json` stays git-ignored; check tracked files and Git history
  for exposed credentials.

---

## Design decisions (index)

A flat index of the decisions above, for quick lookup. Each links back
to the phase section with the full reasoning.

1. Metadata before body, short-circuit on metadata error — 2.3.1, 2.3.5.
2. `get_block_children()` is one batch only; the traversal owns cursor
   state — 2.3.2.
3. Shared mutable `state` dict as the single source of truth for
   budgets and the halt flag across all recursive calls — 2.3.3.
4. Root request failure → raw error; later failure → warning + halt,
   keep partial results — 2.3.3.
5. `child_page`/`child_database` are traversal boundaries, flagged via
   warning rather than descended into — 2.3.3.
6. Cursor-cycle detection is per-parent, not global — 2.3.3 (explicit
   judgment call on an ambiguous spec).
7. Text extraction reuses traversal via an `on_block` callback instead
   of a second traversal implementation — 2.3.4 (explicit requirement).
8. Output limits (`max_blocks`/`max_characters`) are enforced live
   during traversal via the callback, not by fetch-then-trim — 2.3.4.
9. `_extract_block_text()` distinguishes "" (supported, no text),
   `None` (unsupported/malformed), and real text — 2.3.4.
10. `read_only` flag changes retry/`suggested_action` semantics for
    request-layer errors — 2.1.
11. Exactly one 401 refresh attempt; the original request retries
    only after that refresh succeeds, never a loop — 2.1.
12. Tokens cached in a git-ignored, permission-restricted file, never
    printed — Phase 1, `CLAUDE.md` Credential Handling Rules.
13. `create_page()` strips `parent_page_id`/`title` but leaves
    `content` untouched, to preserve study-note whitespace/line
    breaks exactly while still normalizing IDs/titles — 2.4.1.
14. `create_page()`'s validated values are themselves the preview —
    no separate internal "prepare" representation that could drift
    from what the preview shows — 2.4.1.
15. `PAGE_ID_PATTERN` must require a fully-dashed UUID or completely
    dashless 32 hex digits, never a mix — fixed a regression where
    each dash was independently optional — 2.4.2.
16. One paragraph block per line of `content` (empty line → empty
    paragraph), so line breaks and blank lines survive as separate
    blocks instead of being collapsed into one block's `rich_text` —
    2.4.2.
17. Long text is chunked into multiple ≤2000-character rich_text
    segments (`_chunk_rich_text()`) rather than truncated; a
    too-many-lines content is rejected before any request, in both
    `dry_run` modes — 2.4.2.
18. A malformed-but-2xx create-page response tells the caller to
    check the parent page before retrying, since the write may have
    already succeeded — 2.4.2.

---

## Chronological instruction log

Each entry records one project instruction as received, its requested
outcome/acceptance criteria, and — once done — what actually changed.
Entries for phases before this record's own sessions are reconstructed
summaries, not verbatim prompts; see each entry's note.

### [Reconstructed] Phases 0, 1, 2.1, 2.2
No verbatim prompt is available for these phases in any session
recorded here. Outcomes are documented in the Phase history section
above, sourced from `writeup.md`, `CLAUDE.md`, and commits `d1b6324`,
`34a7f80`, `31c0751`, `53ed7af`.

### Initial project review (date not recorded in commit history)
> "I am building a Notion MCP server for the CS146S Week 2 assignment.
> Please inspect this project before making changes. [...] Do not read
> or display .env, token cache files, or credentials. Do not modify
> files or run live API calls yet. Do not use subagents for this
> initial review. [...] Please explain: 1. The responsibilities of
> each main file. 2. How a search request flows through the code.
> 3. What is implemented versus only planned. 4. Any issues that could
> affect reading page content."

- **Phase.** Pre-2.3 review (read-only).
- **Requested outcome / acceptance criteria.** A read-only explanation
  of file responsibilities, the search request flow, implemented vs.
  planned status, and issues affecting future page-content reading —
  no edits, no live calls, no subagents.
- **Outcome.** Explanation given; no files changed. This review's
  findings became the basis for the first `CLAUDE.md`.

### Create CLAUDE.md
> "Based on your review, create a concise CLAUDE.md in the project
> root. Only edit CLAUDE.md in this step. Include the verified
> architecture, development commands, credential handling rules, and
> the learning workflow below. Keep it factual. Do not mark planned
> features as implemented."
>
> Learning Workflow wording (user's exact text, supplied after an
> earlier garbled paste):
> "- Use clear English and explain unfamiliar technical terms.
> - Before implementing a feature, explain its purpose, inputs,
>   outputs, and how it fits into the existing code.
> - Work in small steps. Only implement the step I request.
> - After each step, explain the changes and provide verification
>   commands with expected results.
> - Distinguish mocked tests from live API checks.
> - Do not run live API calls, use subagents, or commit or push
>   changes unless I explicitly request them.
> - Never read or display .env, token caches, or credentials."

- **Phase.** Pre-2.3 (project-wide documentation).
- **Requested outcome.** `CLAUDE.md` only, containing verified
  architecture, dev commands, credential rules, and this exact
  Learning Workflow text.
- **Files changed.** `CLAUDE.md` created.
- **Outcome.** Done; no other files touched.

### Plan Phase 2.3
> "Let's plan Phase 2.3: reading Notion page content. [...] Split the
> work into small subphases. For now, propose the plan only. Do not
> edit code."

followed by a revision instruction with 7 numbered clarifications
(one-batch `get_block_children()`, public name `get_page_content()`,
depth-0-for-direct-children with shared budgets, preserving IDs/depth/
order including table rows, never skipping text-bearing descendants,
defined failure/malformed-response/repeated-cursor behavior, and a
specific test-coverage list), ending with: "After revising the plan,
implement only Phase 2.3.1 [...]".

- **Phase.** 2.3 planning → 2.3.1.
- **Requested outcome / acceptance criteria.** See Phase 2.3.1 in the
  Phase history section above.
- **Files/functions changed.** `notion_api.py::get_page()`;
  `tests/test_get_page.py` added.
- **Decisions and reasons, commands run, results.** See Phase 2.3.1
  above. Tests run 2026-11-22 as part of the full suite: 6 passed.
- **Remaining at the time.** 2.3.2 onward not yet started.

### Implement Phase 2.3.2
> "Implement Phase 2.3.2 only: retrieve one batch of direct child
> blocks from Notion. [...] Add this method to NotionAPIClient:
> get_block_children(block_id: str, page_size: int = 100, start_cursor:
> str | None = None) -> dict[str, Any] [...] Keep all code, docstrings,
> and error messages in English. Do not read or display .env or
> token-cache contents. Do not make live API calls, modify server.py,
> register MCP tools, commit, or push in this step."

- **Phase.** 2.3.2.
- **Outcome.** See Phase 2.3.2 above. `notion_api.py::get_block_children()`
  added; `tests/test_get_block_children.py` added (13 cases, all
  passed). No live calls, no MCP registration, no commit/push.

### Implement Phase 2.3.3
> "Implement Phase 2.3.3: bounded traversal of a Notion page's block
> tree. [...] Reuse the existing architecture and preserve unrelated
> changes. [10-point requirement list, including the suggested
> `_walk_block_tree` signature and return shape, a 14-item test
> coverage list, and instructions to explain the approach before
> editing and walk through a worked example afterward]"

(A diagram request for the Phase 2.3.2 commit was started in the same
turn and interrupted by the user before completion; it was abandoned,
not retried.)

- **Phase.** 2.3.3.
- **Outcome.** See Phase 2.3.3 above. `notion_api.py::_walk_block_tree()`
  / `_walk_children()` added; `tests/test_block_tree.py` added
  (16 cases). A test-helper bug (`patched_client()` returning a tuple
  instead of a context manager) was found and fixed during this step.
  All 16 passed; full regression at the time: 41 passed.

### Implement Phase 2.3.4
> "Implement Phase 2.3.4: readable block content with bounded output.
> [...] Reuse the existing request layer, OAuth behavior, traversal
> order, and structured errors. [5 numbered requirement groups,
> including the explicit instruction to add check_read_page_blocks.py,
> not wire MCP tools, not implement page creation/title updates, and
> not mark live validation as completed in writeup.md]"

(A second diagram request, for Phase 2.3.3, was started and again
interrupted by the user before completion; abandoned.)

- **Phase.** 2.3.4.
- **Outcome.** See Phase 2.3.4 above. `notion_api.py::_extract_rich_text()`,
  `_extract_block_text()`, `read_page_blocks()` added;
  `tests/test_read_page_blocks.py` and `check_read_page_blocks.py`
  added. 13 new tests passed; full regression at the time: 54 passed.
  `writeup.md` was not edited to claim live validation.

### Recover from accidental overwrite
> "I accidentally overwrote your Phase 2.3.4 changes in notion_api.py
> with an older editor buffer. [...] Please compare the current file
> with your earlier edits in this conversation and restore the missing
> Phase 2.3.4 changes. Preserve my unrelated edits and inspect the
> existing tests before changing them. Run the relevant tests again
> and report the actual results. Do not commit or push."

- **Phase.** 2.3.4 (incident during, not a new phase).
- **Outcome.** Restored `_extract_rich_text()`, `_extract_block_text()`,
  `read_page_blocks()`, and the `on_block` callback plumbing; preserved
  the user's own comment inside `_walk_children()`. Full suite
  re-run: 54 passed. No commit/push performed.

### [Reconstructed] Phase 2.3.5
No verbatim prompt is available; implemented and committed
(`5db7d6a`, `c89e660`) outside any session recorded here. See Phase
2.3.5 in the Phase history section above for what changed and what
evidence exists.

### Set up persistent project context (this instruction)
> "Set up persistent project context for my CS146S Notion Study
> Assistant. [...] This is a documentation task. Create or update
> CLAUDE.md and PROJECT_CONTEXT.md in the repository root. [...]"
> (full text on request — the complete original instruction is kept
> in this session's own transcript; summarized here as: reconstruct
> project history into `PROJECT_CONTEXT.md` with a "Resume here"
> section, roadmap, phase history, design decisions, and a
> chronological instruction log; add a maintenance routine to
> `CLAUDE.md`; update `writeup.md` only if there is new assignment
> evidence.)

- **Phase.** Documentation / process, not a numbered implementation
  phase.
- **Requested outcome / acceptance criteria.** `PROJECT_CONTEXT.md`
  created with the structure above; `CLAUDE.md` updated with a
  maintenance routine; `writeup.md` updated only with genuinely new
  evidence; no invented verbatim prompts, test results, commit
  hashes, or design reasons.
- **Files/functions changed.** `PROJECT_CONTEXT.md` created (this
  file). `CLAUDE.md` updated: architecture section brought up to date
  through Phase 2.3.5, Implemented/Planned lists corrected, a
  maintenance-routine section added. `writeup.md`: the Phase 2.3
  acceptance-check line was updated with the now-confirmed full-suite
  mocked result (59 passed, 2026-11-22); the live combined-check
  outcome remains marked pending, since it was not run in this
  session.
- **Commands actually run.** `git log`, `git status`, `git diff
  --stat` (clean tree, confirmed before writing); `python -m pytest
  tests/ -v` → 59 passed, 2026-11-22.
- **Decisions and reasons.** Phases without a verbatim prompt in any
  recorded session are explicitly labeled "Reconstructed summary"
  rather than presented as directly quoted; no commit hash, test
  count, or design rationale was invented — each is sourced from a
  specific file, test run, or commit referenced inline.
- **What remains.** The items listed under "Open questions" above
  (live checks for `check_get_page.py`, `check_get_block_children.py`,
  `check_block_tree.py`, `check_read_page_blocks.py`, and
  `check_get_page_content.py`) were all still pending **as of this
  session** — none were run in this step, per the standing rule
  against running live API calls without an explicit request. This
  reflects what this session itself had observed, not whether those
  checks had already happened elsewhere; see the 2026-11-23
  reconciliation entry below, which found that four of the five had
  already been run by the user and reported in `writeup.md` before
  this session began.

### Reconcile documentation before Phase 2.4.1 (2026-11-23)
> "Please reconcile CLAUDE.md, PROJECT_CONTEXT.md, and writeup.md
> before we start Phase 2.4.1. This is a documentation-only task.
>
> 1. Keep the recorded result of 59 passing tests on 2026-11-22.
>    Remove the contradictory statement that the full pytest run is
>    pending. Describe the suite as mocked Notion API tests plus a
>    real local MCP stdio protocol test.
> 2. Record the earlier live checks as user-reported terminal
>    evidence. Metadata retrieval succeeded. The direct-children check
>    returned a heading and a table. The depth-zero traversal returned
>    17 blocks in one call. The bounded text read returned six blocks
>    in four child-list calls with max_blocks_reached=true. Only the
>    combined get_page_content() live check is still pending for
>    Phase 2.3.
> 3. Keep historical entries accurate about what happened in their own
>    sessions. Update the current status and add a dated reconciliation
>    entry that identifies the user as the source of the earlier live
>    results.
> 4. State the Phase 2.4.1 contract explicitly: dry_run defaults to
>    True. Omitting it must return a local preview of the parent,
>    title, and content with zero calls to request().
> 5. Correct the request() description: an initial 401 triggers one
>    refresh attempt, and the original request is retried only after a
>    successful refresh.
> 6. Inspect the Markdown files in the repository. Fix escaped
>    headings, tables, or code fences only if the formatting problem
>    exists in those files."

- **Phase.** Documentation / process, not a numbered implementation
  phase.
- **Requested outcome / acceptance criteria.** The six numbered points
  above; show the "Resume here" section when done; leave
  implementation, live API calls, and Git commits for the next
  instruction.
- **Source of the live-check evidence.** The four Phase 2.3 live
  checks for 2.3.1–2.3.4 (metadata lookup; direct-children batch;
  depth-zero traversal; bounded text read) are **user-reported
  terminal evidence**, already present in `writeup.md`'s "Recorded
  live evidence" table before this entry existed. No session recorded
  in this log observed those live runs directly — the user is their
  source. This entry supersedes the "pending" label those four checks
  carried in the Phase 2.3.1–2.3.4 sections above and in the "What
  remains" note directly above this entry; those earlier labels were
  accurate for what each session itself had observed at the time, not
  inaccurate history — the live evidence itself predates and is
  independent of those sessions.
- **Files/functions changed.** `PROJECT_CONTEXT.md`: "Resume here"
  (last verified result, open questions, next action); Phase 2.1's
  design decision and its index entry (`request()` retry-only-after-
  success wording); Phase 2.3.1–2.3.4's "Live check" bullets (pending
  → user-reported, done); Phase 2.3.5's note (now the only pending
  Phase 2.3 live check); Phase 2.4.1's contract (made explicit); this
  log entry added. `CLAUDE.md`: the test-suite summary line (now names
  the real local MCP stdio protocol test alongside the mocked Notion
  API tests) and the `request()` architecture bullet (retry only
  after a successful refresh). `writeup.md`: Phase 2.1's paragraph
  (retry only after a successful refresh) and the Phase 2.3
  acceptance-check line (now also names the mocked-plus-protocol-test
  suite explicitly).
- **Commands actually run.** None — this was a text-only
  reconciliation; no pytest run, no live API call, no git command.
- **Markdown inspection (point 6).** Checked `CLAUDE.md`,
  `PROJECT_CONTEXT.md`, and `writeup.md` for escaped headings,
  malformed tables, and unbalanced code fences, via `grep` for lines
  starting with an escaped `#`, for escaped pipes, and for
  triple-backtick-fence counts. `CLAUDE.md` and `writeup.md` each have
  exactly one balanced fence pair; `PROJECT_CONTEXT.md` has none; no
  escaped headings or pipes were found; every table in `writeup.md`
  and `PROJECT_CONTEXT.md` has a correctly-sized dash separator row
  under its header. **No formatting problems existed, so nothing was
  changed under point 6.**
- **What remains.** Only the combined `get_page_content()` live check
  (`check_get_page_content.py`) is still pending for Phase 2.3. Phase
  2.4.1 implementation itself has not started.

### Implement Phase 2.4.1 (2026-11-23)
> "Implement Phase 2.4.1 of my Notion Study Assistant: local preview
> for creating a child page. Read CLAUDE.md and the "Resume here"
> section of PROJECT_CONTEXT.md first. Briefly explain the flow, then
> implement it.
>
> Add this method to NotionAPIClient in notion_api.py:
>
>     create_page(parent_page_id: str, title: str, content: str,
>                 *, dry_run: bool = True)
>
> The parent_page_id identifies the existing page where the new page
> would be created. It can come from search_pages().
>
> For this phase:
> - Validate the parent page ID, title, content, and dry_run locally.
>   Accept a UUID with standard dashes or 32 hexadecimal digits.
>   Require a nonblank title and nonblank text content for this
>   study-note workflow. Preserve meaningful whitespace and line
>   breaks in the body. Require a real boolean for dry_run.
> - Prepare the data for a child page under that parent: the parent
>   page ID, title, and paragraph content. Keep the prepared text
>   consistent with what the preview shows, so Phase 2.4.2 can reuse
>   it.
> - When dry_run is omitted or True, return ok=True, dry_run=True,
>   created=False, and a preview containing parent_page_id, title, and
>   content. A local preview only validates the inputs; it cannot
>   confirm that the parent exists or that the connection can write
>   there.
> - If dry_run=False, return an actionable structured error explaining
>   that live creation is planned for Phase 2.4.2. Every path in 2.4.1
>   must make zero calls to request(). Reuse the existing error
>   format.
>
> Add focused tests in tests/test_create_page.py. In the main test,
> omit dry_run deliberately, assert the preview fields, and use
> request.assert_not_called(). Also cover explicit True, explicit
> False, invalid inputs, and preservation of multiline content. Use
> synthetic data and the project's existing mock patterns.
>
> Run the focused tests and the full automated suite. Update the
> project records with the commands and results actually observed.
> Keep this change in the Python client and its tests; MCP
> registration belongs to Phase 3. Do not run a live Notion check or
> commit changes."

- **Phase.** 2.4.1.
- **Requested outcome / acceptance criteria.** See the quoted
  instruction above; full detail of what was built is in the Phase
  2.4.1 history section above.
- **Files/functions changed.** `notion_api.py::create_page()` added
  (after `search_pages()`). `tests/test_create_page.py` added (12
  cases).
- **Decisions and reasons.** See Phase 2.4.1 above (reuse of
  `PAGE_ID_PATTERN`; stripping ID/title but not content; strict
  `type(...) is not bool` check; no separate "prepare" step since the
  validated values are the preview).
- **Commands actually run and results observed.**
  `python -m pytest tests/test_create_page.py -v` → 12 passed.
  `python -m pytest tests/ -v` → 71 passed (full suite, 2026-11-23).
  No live Notion call was made; no commit was made.
- **What remains.** Phase 2.4.2 (live creation, after explicit
  approval of the preview) and 2.4.3 (live creation + read-back) are
  still planned, not started. MCP registration remains Phase 3.

### Implement Phase 2.4.2 (2026-11-23)
> "Implement Phase 2.4.2: create a Notion child page when create_page()
> is explicitly called with dry_run=False. Read CLAUDE.md, the "Resume
> here" section of PROJECT_CONTEXT.md, and the existing create_page()
> method and tests first.
>
> Keep the Phase 2.4.1 preview as the default. Reuse its input
> validation and preserve the exact body text, including blank lines
> and indentation. Check whether the previously identified partially
> dashed UUID regression is already fixed and covered by a test.
>
> Replace the PAGE_CREATION_NOT_IMPLEMENTED branch. Build the Notion
> payload using parent.page_id, properties.title, and paragraph
> blocks in children. Validate applicable Notion size limits
> consistently for preview and creation. If the input cannot be
> represented, return an actionable validation error before sending a
> request. Never silently truncate the user's notes.
>
> Use the existing request layer:
>     self.request("POST", "/pages", json_body=payload, read_only=False)
>
> On success, return a compact result with ok=True, dry_run=False,
> created=True, and page metadata containing the new page's ID,
> title, and URL. Validate the response before reporting success.
> Pass existing request-layer errors through unchanged. If a success
> response is malformed, tell the caller to inspect the parent page
> before retrying, because creation may already have succeeded. Keep
> retry handling in the existing request layer.
>
> Update tests/test_create_page.py. Replace the obsolete test that
> expects PAGE_CREATION_NOT_IMPLEMENTED. Use distinct synthetic
> parent and new-page IDs so the success test catches returning the
> wrong ID. Verify the exact request path, payload, read_only=False,
> and one call to self.request(). Cover multiline body preservation,
> request-error passthrough, malformed success responses, and the
> chosen size-limit behavior. Keep the existing zero-request preview
> and validation tests.
>
> Run the focused tests and full automated suite. Update
> PROJECT_CONTEXT.md and writeup.md with the actual results, clearly
> labeling the write tests as mocked. Explain one successful call
> from input to output. Leave live Notion writes for Phase 2.4.3 and
> MCP registration for Phase 3. Do not commit or push."

- **Phase.** 2.4.2.
- **Requested outcome / acceptance criteria.** See the quoted
  instruction above; full detail of what was built is in the Phase
  2.4.2 history section above.
- **Files/functions changed.** `notion_api.py`: `PAGE_ID_PATTERN`
  fixed; `NOTION_RICH_TEXT_MAX_LENGTH`, `NOTION_MAX_CHILD_BLOCKS`,
  `_chunk_rich_text()` added; `create_page()`'s `dry_run=False` branch
  replaced. `tests/test_create_page.py`: 6 new cases added (18 total,
  up from 12).
- **Decisions and reasons.** See Phase 2.4.2 above (shared
  `PAGE_ID_PATTERN` regression fix; one paragraph block per line;
  rich-text chunking instead of truncation; size limits enforced
  before any request, in both `dry_run` modes; malformed-response
  handling distinct from a request-layer error).
- **Commands actually run and results observed.**
  `python -m pytest tests/test_create_page.py -v` → 18 passed.
  `python -m pytest tests/ -v` → 77 passed (full suite, 2026-11-23).
  No live Notion call was made; no commit was made.
- **What remains.** Phase 2.4.3 (a real live `create_page(...,
  dry_run=False)` call, followed by `get_page_content()` on the
  result to confirm the round-trip) is still planned, not started.
  MCP registration remains Phase 3.

### Prepare Phase 2.4.3 (2026-11-23)
> "Prepare Phase 2.4.3: a live create-and-read-back check. Read
> CLAUDE.md and the "Resume here" section of PROJECT_CONTEXT.md first.
>
> Add check_create_page_live.py alongside the existing offline
> checker. Reuse NotionAPIClient.create_page() and
> get_page_content().
>
> The CLI should accept a positional parent_page_id and an optional
> --create flag. Use a clearly identifiable test title and a short
> body containing a blank line and an indented line. Keep the example
> inputs identical between preview and creation.
>
> 1. Always show the local preview first. With no --create flag, exit
>    after preview. A preview error must stop the script before any
>    write.
> 2. With --create and a successful preview, call create_page() once
>    with dry_run=False. Print the returned new page ID and URL
>    immediately.
> 3. Read that new page using get_page_content(). Require a complete
>    read. Compare the returned title and the paragraph texts against
>    the original inputs, preserving blank lines and indentation.
> 4. If creation or read-back fails, print an actionable English
>    message and exit with a nonzero status. Never retry by creating
>    another page.
> 5. Run offline checks only. Report the commands actually run and
>    leave the live result pending in PROJECT_CONTEXT.md until I run
>    it myself."

- **Phase.** 2.4.3 (preparation only; the live check itself is not
  run in this entry).
- **Requested outcome / acceptance criteria.** See the quoted
  instruction above; full detail is in the Phase 2.4.3 history section
  above.
- **Files/functions changed.** `check_create_page_live.py` added (new
  file; no changes to `notion_api.py` or any existing test). `CLAUDE.md`:
  architecture's `check_*.py` list and the "Planned, not implemented"
  section updated to mention the new script and its pending status.
- **Decisions and reasons.** See Phase 2.4.3 above (identical
  preview/creation inputs; a clearly-deletable test title; a body
  exercising both a blank line and an indented line; never retrying
  by creating a second page on any failure, including after the page
  already exists).
- **Commands actually run and results observed.** `python -m
  py_compile check_create_page_live.py` → passed (syntax only, no
  network, no credentials read). `python -m pytest tests/ -v` → 77
  passed (full suite, unchanged, since no production code was
  touched). No live Notion call was made; no commit was made.
- **What remains.** The live result is **pending**: the user runs
  `python check_create_page_live.py YOUR_PARENT_PAGE_ID` (preview) and,
  when ready, `... --create` (live write + read-back) themselves and
  reports the actual outcome before Phase 2.4.3 can be marked Done.

### Implement Phase 2.4.3 (2026-11-24)
> "Implement the Phase 2.4.3 live create-and-read-back check. Read
> CLAUDE.md and the current handoff in PROJECT_CONTEXT.md first.
>
> Add check_create_page_live.py in the project root. Reuse the
> existing NotionAPIClient.create_page() and get_page_content()
> methods. Keep the existing offline check_create_page.py available
> for mocked checks.
>
> Use these fixed test inputs so the preview and write commands
> agree:
> - Title: W2 MCP round-trip check
> - Python body literal: "Review OAuth.\n\n    Check token refresh."
>
> Accept a positional parent_page_id and an optional --create flag.
> First call create_page() in preview mode and display the parent
> ID, title, and body. Exit after preview by default. If preview
> fails, print the structured error and exit with a nonzero status.
>
> With --create, call create_page(..., dry_run=False) once using the
> same inputs. Immediately print the returned new page ID and URL.
> Then call get_page_content(new_page_id). Check that the read is
> complete, the returned page ID matches the new ID, the title
> matches, and the body contains exactly three top-level paragraphs
> whose texts equal the original body split on "\n". Preserve the
> empty paragraph and the four leading spaces in the last paragraph
> when comparing.
>
> If read-back fails, print the new ID and make it possible to retry
> only the read using --verify-id NEW_PAGE_ID. Make --verify-id and
> --create mutually exclusive. Never repeat creation to recover from
> a failed read. Use English CLI messages and a nonzero exit status
> for errors or mismatches.
>
> Run offline checks only. Record the actual results and leave live
> acceptance pending until I run the command. Do not commit or push."

- **Phase.** 2.4.3 (revision of the previous "Prepare Phase 2.4.3"
  entry's script; the live check itself is still not run in this
  entry).
- **Note on `check_create_page.py`.** This instruction assumes a
  file `check_create_page.py` already exists as the offline/mocked
  counterpart. It was found present in the repo at the start of this
  turn (a mocked preview + `dry_run=False` demonstration using
  `unittest.mock.patch`), created outside any session recorded here.
  It was left completely unchanged, per the instruction.
- **Requested outcome / acceptance criteria.** See the quoted
  instruction above; full detail is in the (revised) Phase 2.4.3
  history section above.
- **Files/functions changed.** `check_create_page_live.py` rewritten
  (fixed `TITLE`/`CONTENT` constants matching `check_create_page.py`'s
  own content string; new `_verify_read_back()` helper shared between
  the post-creation read-back and `--verify-id`; `--create`/
  `--verify-id` as an `argparse` mutually exclusive group).
  `check_create_page.py` untouched. `CLAUDE.md`'s `check_*.py`
  description updated. No changes to `notion_api.py` or any test.
- **Decisions and reasons.** See the Phase 2.4.3 section above (fixed
  inputs shared with the existing mocked check; one shared
  verification helper instead of duplicating the checks for the
  retry path; UUID-normalized ID comparison matching
  `check_get_page_content.py`'s convention; `argparse`-enforced
  mutual exclusivity instead of a manual check; never retrying
  creation on any failure).
- **Commands actually run and results observed.**
  `python -m py_compile check_create_page_live.py` → passed.
  `python check_create_page_live.py --help` → confirmed the
  mutually-exclusive `--create`/`--verify-id` group renders correctly.
  `python check_create_page_live.py parent-id --create --verify-id abc`
  → `argparse` rejected it with exit code 2, as required.
  `python check_create_page.py` → the existing mocked check still
  passes unchanged (all PASS lines, including the blank-paragraph and
  indented-line payload check). `python -m pytest tests/ -v` → 77
  passed (full suite, unchanged). No live Notion call was made; no
  commit was made.
- **What remains.** The live result is still **pending**: the user
  runs `python check_create_page_live.py YOUR_PARENT_PAGE_ID`
  (preview), `... --create` (live write + read-back), and/or
  `... --verify-id NEW_PAGE_ID` (read-only retry) themselves and
  reports the actual outcome before Phase 2.4.3 can be marked Done.
