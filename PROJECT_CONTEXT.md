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
through subphase 2.3.5. Phase 2.4 (local preview, then page creation)
is planned next but not started.

**Last verified result.** `python -m pytest tests/ -v` → **59 passed**
(mocked, no network), run 2026-11-22. This is the first time the
*full* suite's count was confirmed in this record — `writeup.md`
previously listed it as pending. The Phase 2.3 **live** combined-read
check (`check_get_page_content.py`) has not been run in any session
recorded here; its expected assertions are written into the script
(see Phase 2.3.5 below) but the actual outcome is still pending.

**Open questions.**
- Phase 2.2: some titles in the raw `/search` response lacked the
  literal query text. Cause unconfirmed.
- Phase 2.3.5 / final acceptance: the live run of
  `check_get_page_content.py "YOUR_W2_TEST_PAGE_ID"` and a live run of
  the full pytest suite are both still pending in this record.

**Next action.** Per the active plan (reconstructed from a separate
ChatGPT handoff, see Phase 2.4 below): implement Phase 2.4.1, a local
preview for page creation. The next implementation test is expected to
omit `dry_run`, check that the preview correctly identifies the parent,
title, and content, and assert that `request()` is never called for a
preview-only call. Do not start this without the user's explicit
request — the Learning Workflow rule in `CLAUDE.md` says to work in
small, explicitly requested steps.

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
| 2.4.1 | Local preview for page creation (`dry_run`) | Planned |
| 2.4.2 | Page creation | Planned |
| 2.4.3 | Live creation, then read the new page back | Planned |
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
  - Exactly one refresh-and-retry attempt after a 401, not a loop —
    reason: avoid masking a genuinely broken credential behind
    repeated silent refreshes.
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
  **Live check:** `check_get_page.py` exists; not run in any session
  recorded here — pending.

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
  check:** `check_get_block_children.py` exists; not run in any session
  recorded here — pending.

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
  check:** `check_block_tree.py` exists; not run in any session
  recorded here — pending.

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
  check:** `check_read_page_blocks.py` exists; not run in any session
  recorded here — pending.
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
    actually been executed against the real API.

### Phase 2.4 — Preview and page creation (planned, not started)
*Reconstructed summary — decisions below come from a separate ChatGPT
conversation's handoff notes, not from a prompt available in any
session recorded here. Do not treat these as already implemented.*

- **2.4.1 — Local preview.** A `dry_run` (or similarly named) mode that
  identifies the intended parent, title, and content of a page to be
  created, without calling `request()`. The next planned test: call
  the preview path with `dry_run` omitted (i.e. relying on whatever
  default the implementation chooses), assert it still only previews
  (identifies parent/title/content correctly) and that `request()` is
  never called.
- **2.4.2 — Page creation.** Create the page only after explicit
  approval of the preview; return the new page's ID and URL.
- **2.4.3 — Live creation and read-back.** Create a real page live,
  then read it back with `get_page_content()` to confirm the written
  content round-trips.
- **Capability justification (from `writeup.md`).** `Read content` is
  justified by search + read; `Insert content` by creation;
  `Update content` only if a title-update operation ships. Reassess
  the final Notion integration's capability set once 2.4 lands.

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
11. Exactly one 401-refresh-and-retry, never a loop — 2.1.
12. Tokens cached in a git-ignored, permission-restricted file, never
    printed — Phase 1, `CLAUDE.md` Credential Handling Rules.

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
  `check_block_tree.py`, `check_read_page_blocks.py`,
  `check_get_page_content.py`, and the full live Phase 2.3 acceptance
  check) are all still pending — none were run in this step, per the
  standing rule against running live API calls without an explicit
  request.
