# Notion Study Assistant — Development Writeup

## Project goal

Build a Python MCP server for the CS146S Week 2 assignment. A student should be able to ask an agent to find their notes, read them, preview a revision page, and create it after approval. The read workflow is implemented in the Python client. Page creation and the final MCP tools are planned.

## Current architecture

| File            | Responsibility                                                                                     |
| --------------- | -------------------------------------------------------------------------------------------------- |
| `server.py`     | FastMCP entry point using stdio. The initial `health` tool exercises the protocol.                 |
| `oauth.py`      | Configuration, interactive login, token cache, refresh, and credential verification.               |
| `notion_api.py` | Authenticated HTTP requests, page search, metadata retrieval, and bounded reading of page content. |
| `check_*.py`    | Manual checks against an authorized Notion workspace.                                              |
| `tests/`        | Automated checks for individual layers and the MCP skeleton.                                       |
| `.env.example`  | Configuration template with placeholders.                                                          |

## Phase 0 — MCP skeleton

The initial protocol checks exercised `tools/list` and `tools/call` using the health tool. Repeat the protocol test with a Notion tool after the final tools are registered.

## Phase 1 — OAuth

The `login` command generates a random `state`, starts a local callback listener, and opens the authorization page. The listener compares the returned `state` with the value from this login before accepting the authorization code. The program exchanges the code for access and refresh tokens and saves them locally. Caching lets a new process reuse the authorization. A successful refresh replaces the cached credentials so the next request can use the new pair.

**Observed checks.** `python oauth.py login` saved the tokens. A separate `status` process loaded both. The cache directory had mode `700` and the cache file had mode `600`. Both `verify` and `refresh` succeeded, and a second `verify` succeeded after refresh. Two OAuth tests passed. The successful live verification calls reported `refreshed: false`. The automatic 401 recovery path was exercised with a simulated response.

## Phase 2.1 — Shared request handling

All operations use `NotionAPIClient.request()`. After an initial HTTP 401, it attempts exactly one silent refresh; only if that refresh succeeds does it reload the cache and retry the original request once. If the refresh itself fails, or credentials still fail after the retry, the caller receives an error with a suggested action. Only explicit login opens a browser. The request layer also distinguishes read and write failures. A timed-out write may already have reached Notion, so its error tells the caller to check before trying again.

**Observed checks.** `check_notion_api.py` completed a live search request. Mocked tests verified that a retry used the new access token and that a broken cache returned `TOKEN_CACHE_ERROR` before any network request.

## Phase 2.2 — Page search

`search_pages()` returns one batch of page IDs, titles, and URLs, plus `has_more` and `next_cursor`. The title helps the agent choose a page. The ID is the input to the reader. To fetch another batch, the caller keeps the query and passes the returned cursor back as `start_cursor`.

**Observed checks.** Live searches returned accessible pages, an unlikely query returned an empty result, and a cursor retrieved the next batch. Six OAuth, request-layer, and search tests passed at this checkpoint. Some titles in the raw API response lacked the literal query text. The cause remains unconfirmed. The client preserves the results so callers can inspect titles before selecting a page.

## Phase 2.3 — Reading page content

`get_page_content(page_id)` answers three questions in one result. Which page did we read? What text did we recover? How much of the page does that text represent?

| Step  | Implementation                                                                                                                   | Design decision                                                                                                                                      |
| ----- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2.3.1 | `get_page()` retrieves the page ID, title, and URL.                                                                              | Get metadata first. If the page is inaccessible, return the error before requesting its body.                                                        |
| 2.3.2 | `get_block_children()` retrieves one batch of direct children for one parent.                                                    | `has_more` means there are more siblings under this parent. A block's `has_children` means there is another level to read under that block's ID.     |
| 2.3.3 | `_walk_block_tree()` and `_walk_children()` visit each parent before its descendants and keep a separate cursor for each parent. | Preserve reading order, including table rows, while bounding depth and child-list calls. Skip descent into linked child pages and databases.         |
| 2.3.4 | `read_page_blocks()` extracts text as each block is visited.                                                                     | One traversal handles both structure and text. Its `on_block` callback can stop further fetching when the next block would exceed the output budget. |
| 2.3.5 | `get_page_content()` combines metadata and the body result.                                                                      | Preserve partial text, warnings, and unsupported types so the agent can explain what it read.                                                        |

**What the limits mean.** `page_size` controls the size of each batch. `max_blocks` limits the number of entries returned across all batches and levels. `max_characters` limits total emitted text. `max_depth=0` reads the page's direct children. `max_request_calls` bounds calls to `get_block_children()`. The metadata lookup and any HTTP retry inside one child-list call fall outside this budget.

**How partial results work.** A table container contributes an empty string, and its rows supply the cell text. An unsupported block contributes `text=None` and its type is reported. If a later batch fails, the reader keeps the recovered blocks and includes an actionable warning. If the first child-list call fails, the reader returns the structured error. A caller can therefore receive `ok=True` and `complete=False` together and inspect the reason before summarizing the notes.

### Recorded live evidence

| Check                                                       | Observed outcome                                                                                               |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Metadata lookup                                             | Returned the selected page's ID, title, and URL.                                                               |
| Direct children with `page_size=2`                          | Returned a heading and a table. The table had children, and the page had another batch.                        |
| Traversal with `max_depth=0`                                | Recorded 17 direct children in one call and reported `max_depth_reached=true`.                                 |
| Traversal with one allowed call and `page_size=2`           | Recorded two blocks and reported `max_requests_reached=true`.                                                  |
| Text read with `max_depth=1`, `max_blocks=6`, `page_size=2` | Returned a heading, a table, and four table rows in four child-list calls. Only `max_blocks_reached` was true. |

### Final Phase 2.3 acceptance check

Four unit tests cover successful assembly and forwarding of limits, preservation of a partial read, a metadata error that skips the body, and a body error that reaches the caller unchanged. The full suite — mocked Notion API tests plus a real local MCP stdio protocol test (`pytest tests/ -v`) — was run on 2026-11-22: 59 passed. The combined live check (`check_get_page_content.py`) has not been run; its outcome remains pending in this record.

```bash
python -m pytest tests/ -q
python check_get_page_content.py "YOUR_W2_TEST_PAGE_ID"
```

Replace `YOUR_W2_TEST_PAGE_ID` with the authorized test page's ID. The live checker uses the known W2 page layout. It expects the correct metadata, six blocks including readable table rows, and `complete=False` with `max_blocks_reached=True`. Record the actual pytest count and live outcome after running both commands.

## Phase 2.4.1 — Local preview for page creation

`create_page(parent_page_id, title, content, *, dry_run=True)` validates its inputs and returns a preview of the child page it would create, without contacting Notion. `dry_run` defaults to `True`; omitting it returns the same local preview (`parent_page_id`, `title`, `content`), with zero calls to `request()`. Live creation (`dry_run=False`) is not implemented yet; it returns a structured error naming Phase 2.4.2 instead of attempting anything. The parent page ID and title are validated and stripped; the content is preserved exactly, including internal blank lines and whitespace, since it is study-note body text.

**Observed checks.** `python -m pytest tests/test_create_page.py -v` passed all 12 cases: the default preview (`dry_run` omitted), explicit `dry_run=True` and `dry_run=False`, a parent ID without dashes, multiline/blank-line content preserved exactly, and each invalid-input case (bad or non-string parent ID, blank or non-string title, blank or non-string content, a non-boolean `dry_run`). The full suite (`pytest tests/ -v`) passed 71 tests on 2026-11-23. No live Notion check applies to this phase, since every path makes zero calls to `request()`.

## Phase 2.4.2 — Page creation (mocked)

With `dry_run=False`, `create_page()` now builds a real Notion page-create payload from the same validated, stripped values the Phase 2.4.1 preview shows: `parent.page_id`, a `properties.title` built from the title, and one `paragraph` block per line of `content` in `children` (an empty line becomes an empty paragraph block, which is how blank lines and indentation survive as separate blocks instead of being collapsed). Text longer than Notion's 2000-character rich-text limit is split across multiple rich-text segments of one block rather than truncated; a title or a content line count that cannot be represented this way is rejected with an actionable error before any request is sent, in both `dry_run` modes. The payload is sent with exactly one call to `self.request("POST", "/pages", json_body=payload, read_only=False)`. On success, the response is validated the same way `get_page()` validates its own response; on success it returns `ok=True, dry_run=False, created=True`, and the new page's `id`, `title`, and `url`. A request-layer error (network, 401/refresh failure, 403/404/429/5xx) is returned unchanged. A malformed 2xx response returns a distinct error telling the caller to check the parent page before retrying, since the write may have already succeeded.

While implementing this phase, a pre-existing bug was found and fixed: `PAGE_ID_PATTERN` (shared by `get_page()`, `get_block_children()`, `_walk_block_tree()`, and `create_page()`) made every dash in a UUID independently optional, so a UUID with only *some* of its dashes removed incorrectly matched. The pattern now requires a UUID to be either fully dashed or completely dashless, never a mix.

**Observed checks (mocked only).** `python -m pytest tests/test_create_page.py -v` passed all 18 cases on 2026-11-23 (12 from Phase 2.4.1, plus 6 new): a full `dry_run=False` success path asserting the exact request path, payload shape, `read_only=False`, and one call to `request()`; a dedicated blank-line/indentation-preservation case; a request-error-passthrough case; a malformed-success-response case; a title-too-long case; and a too-many-content-lines case. The full suite (`pytest tests/ -v`) passed 77 tests on 2026-11-23. Every one of these tests mocks `NotionAPIClient.request()` — **no real `POST /pages` call has been made against the authorized workspace.** That live call, and reading the new page back to confirm the round-trip, is Phase 2.4.3.

## Remaining work

- **Phase 2.4.3, and planned title update.** Make a real, approved `create_page(..., dry_run=False)` call against the authorized workspace, then read the new page back with `get_page_content()` to confirm the written title/body round-trips. Justify `Read content` for search and reading, `Insert content` for creation, and `Update content` if the title-update operation ships. Reassess the final capability set against the implemented operations.
- **Phase 3.** Expose the Python operations as FastMCP tools. Document how a page ID returned by search becomes the input to reading or creation.
- **Phase 4.** Encode parameter limits in the tool schemas. Add workflow instructions, read-only annotations, and a write preview. Check that errors tell the agent whether and how to retry.
- **Phase 5.** Register the server with an MCP host. Capture a real multi-tool transcript, a failure and recovery example, and a protocol test against a final tool. Verify that expired or revoked credentials produce an actionable result during a tool call.
- **Phase 6.** Finish the submission writeup, verify that `.mcp.json.example` contains placeholders and the real `.mcp.json` is ignored, and check tracked files and Git history for exposed credentials.

Record observed results separately from expected behavior. Keep credentials and raw private page content out of the published evidence.
