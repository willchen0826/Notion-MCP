# Notion Study Assistant — Development Writeup

## Project Goal

Build a Python MCP server for the CS146S Week 2 assignment.

The intended workflow is:

1. Search for a Notion page.
2. Read its content.
3. Preview a new study or revision page.
4. Create the page when the write is explicitly requested.

The project uses FastMCP with stdio and a custom Notion API client.

## Current Architecture

- server.py: MCP server entry point.
- oauth.py: OAuth configuration, browser login, token caching,
  token refresh, and credential verification.
- notion_api.py: Shared HTTP request handling and page search.
- check_notion_api.py: Live check of the shared request layer.
- check_search_pages.py: Live title-search and pagination checks.
- tests/: Automated tests.
- .env.example: Configuration template without real credentials.

Real credentials and token cache files must not be committed.

## Phase 0 — MCP Skeleton

Status: Previously reported as completed.

Implemented a FastMCP server using stdio with a health tool.
Initial protocol checks exercised tools/list and tools/call.

The current protocol test should be rerun before final submission.
This does not yet demonstrate the final Notion tools through MCP.

## Phase 1 — Notion OAuth

Status: Core OAuth flow implemented and exercised.

Implemented:

- Loading OAuth configuration from environment variables.
- Browser authorization with a random state value.
- Local callback handling and state validation.
- Authorization-code exchange.
- Saving and loading access and refresh tokens.
- Refreshing credentials and updating the token cache.
- A verification command that attempts refresh after an initial 401.
- Actionable errors when authorization cannot be recovered.

Observed validation:

- python oauth.py login completed and saved tokens.
- python oauth.py status loaded both tokens in a separate process.
- The cache directory had mode 700 and the cache file had mode 600.
- python oauth.py verify returned ok: true.
- python oauth.py refresh returned ok: true.
- A subsequent verify command succeeded.
- Two OAuth refresh tests passed.

Remaining assignment-level checks:

- Verify failure handling through the final MCP tools.
- Document and justify the final permission set.
- Check tracked files and Git history for exposed credentials.
- Confirm that real MCP configuration is ignored and a safe
  .mcp.json.example is included.

## Phase 2.1 — Shared Notion Request Layer

Status: Implemented and exercised.

Implemented NotionAPIClient.request() to:

- Load cached credentials.
- Send authenticated requests to the Notion API.
- Attempt one refresh after an initial HTTP 401.
- Reload credentials and retry once after successful refresh.
- Return actionable errors for cache, authentication, network,
  and HTTP failures.

Validation:

- A live search request through check_notion_api.py succeeded.
- A mocked test verified refresh after a 401 and use of the new
  access token for the retry.
- A mocked test verified that a broken cache returns
  TOKEN_CACHE_ERROR without sending an HTTP request.

These tests validate the Python request layer, not the MCP protocol.

## Phase 2.2 — Page Search

Status: Implemented and exercised, with an observed matching limitation.

Implemented title search with shaped output containing page IDs,
titles, URLs, and pagination metadata.

The search method reuses the shared request layer and preserves
actionable errors.

Validation:

- Live search returned accessible pages.
- A deliberately unlikely query returned an empty result.
- Cursor pagination returned subsequent results.
- All six OAuth, request-layer, and search tests passed.

Observed limitation:
Some live search results did not contain the literal query text
in their titles. These results were already present in the raw
API response. The server-side matching cause remains unconfirmed.

The client preserves API results and pagination. Callers should
inspect returned titles before selecting a page ID.

## Phase 2.3 — Read Page Content

Status: Planned; not implemented in the progress recorded here.

Goal:
Read a page using an ID returned by search_pages().

Planned work:

1. Retrieve page metadata and the first batch of child blocks.
2. Extract useful text from supported block types.
3. Handle pagination and nested blocks.
4. Bound request count, nesting depth, and output size.
5. Clearly report unread, truncated, or unsupported content.
6. Add focused tests and perform a live read-only check.

Reuse the existing request layer and OAuth behavior.

## Remaining Roadmap

- Finish Phase 2: Page reading, page creation with preview,
  and the planned title-update operation.
- Phase 3: Expose the Notion operations as MCP tools.
- Phase 4: Verify schema constraints, output shaping, structured
  errors, tool descriptions, annotations, and write safeguards.
- Phase 5: Integrate with an MCP host, record a real multi-tool
  workflow and a failure-recovery example, and test via MCP.
- Phase 6: Complete the assignment writeup and submission checks.

The title-update operation is planned to justify retaining the
Update content capability. If it is not implemented, reassess
whether that capability is necessary.

## Evidence Policy

Only record tests and live checks that were actually performed.
Do not describe planned features as completed.
Do not include tokens, secrets, or raw private page content.

This document is a development progress record, not yet the final
assignment submission report.
