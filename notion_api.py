import re
from typing import Any, Callable

import httpx

import oauth

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2026-03-11"

PAGE_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?"
    r"[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
)

# Block types whose text lives at block[type]["rich_text"].
RICH_TEXT_BLOCK_TYPES = frozenset(
    {
        "paragraph",
        "heading_1",
        "heading_2",
        "heading_3",
        "heading_4",
        "bulleted_list_item",
        "numbered_list_item",
        "toggle",
        "quote",
        "callout",
        "code",
    }
)

# Containers with no text of their own; their descendants are what
# carry text, so they are supported with an empty string, not
# reported as unsupported.
STRUCTURAL_CONTAINER_TYPES = frozenset({"table", "column_list", "column"})



class NotionAPIClient:
    """Send Notion API requests with cached OAuth credentials."""

    def __init__(self) -> None:
        self.config = oauth.load_oauth_config()

    def _load_credentials(self) -> dict[str, Any]:
        """Load credentials or return an actionable error."""
        try:
            tokens = oauth.load_tokens()
        except (ValueError, RuntimeError, OSError):
            return oauth.error_result(
                "TOKEN_CACHE_ERROR",
                "The token cache could not be read or validated.",
                False,
                "Check cache permissions and run python oauth.py login.",
            )

        if tokens is None:
            return oauth.error_result(
                "AUTH_REQUIRED",
                "No cached credentials were found.",
                False,
                "Run python oauth.py login.",
            )

        return {"ok": True, "tokens": tokens}
    
    
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        read_only: bool = False,
    ) -> dict[str, Any]:
        """Send a request and refresh credentials once after HTTP 401."""
        method = method.upper()

        if method not in {"GET", "POST", "PATCH"}:
            return oauth.error_result(
                "INVALID_METHOD",
                "The HTTP method is not supported.",
                False,
                "Use GET, POST, or PATCH.",
            )

        if not re.fullmatch(r"/[A-Za-z0-9/_-]+", path):
            return oauth.error_result(
                "INVALID_PATH",
                "Use a relative API path such as /search.",
                False,
                "Pass query parameters through params.",
            )

        url = NOTION_API_BASE + path
        refreshed = False

        for attempt in range(2):
            credentials = self._load_credentials()

            if "error" in credentials:
                return credentials

            access_token = credentials["tokens"]["access_token"]

            try:
                # print("DEBUG: HTTP method:", method)
                # print("DEBUG: HTTP URL:", url)
                # print("DEBUG: HTTP JSON body:", json_body)
                
                response = httpx.request(
                    method=method,
                    url=url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Notion-Version": NOTION_API_VERSION,
                        "Accept": "application/json",
                    },
                    params=params,
                    json=json_body,
                    timeout=20.0,
                    follow_redirects=False,
                )
            except httpx.RequestError:
                return oauth.error_result(
                    "NETWORK_ERROR",
                    "The API request could not be completed.",
                    read_only,
                    (
                        "Check connectivity and retry."
                        if read_only
                        else
                        "Check Notion before retrying: the write "
                        "may already have succeeded."
                    ),
                )

            if response.status_code == 401:
                if attempt == 1:
                    return oauth.error_result(
                        "AUTH_REQUIRED",
                        "Notion rejected the refreshed credentials.",
                        False,
                        "Run python oauth.py login.",
                    )

                try:
                    refresh_result = oauth.refresh_cached_tokens(
                        self.config
                    )
                except (ValueError, RuntimeError, OSError):
                    return oauth.error_result(
                        "AUTH_REFRESH_ERROR",
                        "Credentials could not be loaded or refreshed.",
                        False,
                        "Check local configuration and cache permissions. "
                        "Run python oauth.py login if needed.",
                    )

                if "error" in refresh_result:
                    return refresh_result

                refreshed = True
                continue

            if not 200 <= response.status_code < 300:
                return self._http_error(response, read_only=read_only)

            try:
                data = response.json()
                # if path == "/search":
                    # print("DEBUG: Raw search response:", data)
    
            except ValueError:
                return oauth.error_result(
                    "INVALID_API_RESPONSE",
                    "Notion returned invalid JSON.",
                    read_only,
                    (
                        "Retry the read-only request later."
                        if read_only
                        else
                        "Check Notion before retrying the write."
                    ),
                )

            if not isinstance(data, dict):
                return oauth.error_result(
                    "INVALID_API_RESPONSE",
                    "Notion returned an unexpected response structure.",
                    False,
                    "Check the API response contract.",
                )

            return {
                "ok": True,
                "data": data,
                "refreshed": refreshed,
            }

        raise RuntimeError("Unexpected end of the request loop.")
    
    
    
    def _http_error(
        self,
        response: httpx.Response,
        *,
        read_only: bool,
    ) -> dict[str, Any]:
        """Translate HTTP failures into actionable errors."""
        status = response.status_code

        if status == 403:
            return oauth.error_result(
                "FORBIDDEN",
                "Notion denied this operation.",
                False,
                "Check connection capabilities and resource access.",
            )

        if status == 404:
            return oauth.error_result(
                "NOT_FOUND_OR_INACCESSIBLE",
                "The resource was not found or is not accessible.",
                False,
                "Check the resource ID and whether access was granted.",
            )

        if status == 429:
            result = oauth.error_result(
                "RATE_LIMITED",
                "Notion rate-limited the request.",
                True,
                "Wait before retrying; follow Retry-After if provided.",
            )
            result["error"]["retry_after"] = response.headers.get(
                "Retry-After"
            )
            return result

        if status >= 500:
            return oauth.error_result(
                "NOTION_UNAVAILABLE",
                f"Notion returned HTTP {status}.",
                read_only,
                (
                    "Retry the read-only request later."
                    if read_only
                    else
                    "Check whether the write succeeded before retrying."
                ),
            )

        return oauth.error_result(
            "API_REQUEST_REJECTED",
            f"Notion returned HTTP {status}.",
            False,
            "Check the request parameters and API documentation.",
        )
        
    def _extract_page_title(self, page: dict[str, Any]) -> str:
        """Extract a page title from its title-type property."""
        properties = page["properties"]

        for property_value in properties.values():
            if property_value.get("type") == "title":
                parts = property_value["title"]
                title = "".join(part["plain_text"] for part in parts)
                return title.strip() or "Untitled"

        return "Untitled"

    def get_page(self, page_id: str) -> dict[str, Any]:
        """Retrieve page metadata only (no block content).

        page_id should come from search_pages() or get_page_content().
        Use get_page_content() to read the page's body text.
        """
        if not isinstance(page_id, str):
            return oauth.error_result(
                "INVALID_PAGE_ID",
                "page_id must be a string.",
                False,
                "Use an id returned by search_pages().",
            )

        page_id = page_id.strip()

        if not PAGE_ID_PATTERN.match(page_id):
            return oauth.error_result(
                "INVALID_PAGE_ID",
                "page_id must be a Notion page ID (a UUID, with or "
                "without dashes).",
                False,
                "Use an id returned by search_pages().",
            )

        response = self.request(
            "GET",
            f"/pages/{page_id}",
            read_only=True,
        )
        # print("get_page function response:  ")
        # print(response)
        if "error" in response:
            return response

        data = response["data"]

        try:
            if data["object"] != "page":
                raise ValueError("Unexpected object type")

            if not isinstance(data["id"], str) or not data["id"]:
                raise ValueError("Invalid page ID")

            if not isinstance(data["url"], str) or not data["url"]:
                raise ValueError("Invalid page URL")

            title = self._extract_page_title(data)

        except (KeyError, TypeError, ValueError, AttributeError):
            return oauth.error_result(
                "INVALID_PAGE_RESPONSE",
                "Notion returned an unexpected page response structure.",
                False,
                "Check the page response format and API version.",
            )

        return {
            "ok": True,
            "page": {
                "id": data["id"],
                "title": title,
                "url": data["url"],
            },
        }

    def get_block_children(
        self,
        block_id: str,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve one batch of a block's direct children.

        Returns only one level of children; it does not paginate or
        recurse. If has_more is true, call again with the same
        block_id and the returned next_cursor as start_cursor. For
        any returned block with has_children True, call this method
        again using that block's id to read its own children.
        """
        if not isinstance(block_id, str):
            return oauth.error_result(
                "INVALID_BLOCK_ID",
                "block_id must be a string.",
                False,
                "Use an id returned by search_pages() or a prior "
                "get_block_children() result.",
            )

        block_id = block_id.strip()

        if not PAGE_ID_PATTERN.match(block_id):
            return oauth.error_result(
                "INVALID_BLOCK_ID",
                "block_id must be a Notion block ID (a UUID, with or "
                "without dashes).",
                False,
                "Use an id returned by search_pages() or a prior "
                "get_block_children() result.",
            )

        if type(page_size) is not int or not 1 <= page_size <= 100:
            return oauth.error_result(
                "INVALID_PAGE_SIZE",
                "page_size must be an integer between 1 and 100.",
                False,
                "Use a page_size such as 100.",
            )

        if start_cursor is not None:
            if not isinstance(start_cursor, str) or not start_cursor.strip():
                return oauth.error_result(
                    "INVALID_CURSOR",
                    "start_cursor must be a non-empty string or None.",
                    False,
                    "Use next_cursor from a previous "
                    "get_block_children() response.",
                )

        params: dict[str, Any] = {"page_size": page_size}

        if start_cursor is not None:
            params["start_cursor"] = start_cursor

        response = self.request(
            "GET",
            f"/blocks/{block_id}/children",
            params=params,
            read_only=True,
        )

        if "error" in response:
            return response

        data = response["data"]

        try:
            if data["object"] != "list":
                raise ValueError("Unexpected object type")

            results = data["results"]
            has_more = data["has_more"]
            next_cursor = data["next_cursor"]

            if not isinstance(results, list):
                raise ValueError("Invalid results")

            if not isinstance(has_more, bool):
                raise ValueError("Invalid has_more")

            if next_cursor is not None and (
                not isinstance(next_cursor, str) or not next_cursor
            ):
                raise ValueError("Invalid next_cursor")

            if has_more and next_cursor is None:
                raise ValueError("Missing next_cursor")

            for block in results:
                if not isinstance(block, dict):
                    raise ValueError("Invalid block")

                if block["object"] != "block":
                    raise ValueError("Unexpected object type")

                if not isinstance(block["id"], str) or not block["id"]:
                    raise ValueError("Invalid block ID")

                if not isinstance(block["type"], str) or not block["type"]:
                    raise ValueError("Invalid block type")

                if not isinstance(block["has_children"], bool):
                    raise ValueError("Invalid has_children")

        except (KeyError, TypeError, ValueError, AttributeError):
            return oauth.error_result(
                "INVALID_BLOCK_CHILDREN_RESPONSE",
                "Notion returned an unexpected block children "
                "response structure.",
                False,
                "Check the block children response format and API "
                "version.",
            )

        return {
            "ok": True,
            "results": results,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def _walk_block_tree(
        self,
        page_id: str,
        *,
        max_depth: int = 3,
        max_request_calls: int = 20,
        page_size: int = 100,
        on_block: (
            Callable[[dict[str, Any], dict[str, Any]], None] | None
        ) = None,
    ) -> dict[str, Any]:
        """Traverse a page's block tree with bounded depth and requests.

        Internal helper for the future get_page_content(); no MCP tool
        uses this yet. Performs a depth-first, preorder walk: a block
        is recorded, then its children (if any, and within
        max_depth), then its next sibling. Pagination for each parent
        (the page itself, or any block with has_children) is tracked
        independently of every other parent.

        Reuses get_block_children() only; it never sends an HTTP or
        OAuth request directly, and never opens a browser (refresh,
        if needed, happens inside get_block_children()/request()).
        A failed request (authentication, rate limiting, or anything
        else) stops the entire traversal rather than continuing with
        partial siblings elsewhere.

        complete=True means every block reachable within max_depth
        and max_request_calls was recorded, with no cursor cycles and
        no unreported child_page/child_database boundary. It does not
        certify that a later text-extraction phase will represent
        every block's content; that is Phase 2.3.4's concern.

        on_block, if given, is called as on_block(entry, state) right
        after each raw block entry is appended to state["blocks"].
        It may set state["stopped"] = True to halt the traversal
        immediately (no further get_block_children() calls anywhere),
        which is how read_page_blocks() enforces its own output
        limits without fetching the whole tree first and trimming it
        afterward.
        
        on_block 本身通常在 read_page_blocks() 里定义，用来检查这个 block 能不能加入输出，以及有没有达到 max_blocks 限制。
        """
        if not isinstance(page_id, str):
            return oauth.error_result(
                "INVALID_PAGE_ID",
                "page_id must be a string.",
                False,
                "Use an id returned by search_pages().",
            )

        page_id = page_id.strip()

        if not PAGE_ID_PATTERN.match(page_id):
            return oauth.error_result(
                "INVALID_PAGE_ID",
                "page_id must be a Notion page ID (a UUID, with or "
                "without dashes).",
                False,
                "Use an id returned by search_pages().",
            )

        if type(max_depth) is not int or not 0 <= max_depth <= 10:
            return oauth.error_result(
                "INVALID_MAX_DEPTH",
                "max_depth must be an integer between 0 and 10.",
                False,
                "Use a max_depth such as 3.",
            )

        if (
            type(max_request_calls) is not int
            or not 1 <= max_request_calls <= 100
        ):
            return oauth.error_result(
                "INVALID_MAX_REQUEST_CALLS",
                "max_request_calls must be an integer between 1 and "
                "100.",
                False,
                "Use a max_request_calls such as 20.",
            )

        if type(page_size) is not int or not 1 <= page_size <= 100:
            return oauth.error_result(
                "INVALID_PAGE_SIZE",
                "page_size must be an integer between 1 and 100.",
                False,
                "Use a page_size such as 100.",
            )

        state: dict[str, Any] = {
            "blocks": [],
            "request_calls": 0,
            "partial": {
                "max_depth_reached": False,
                "max_requests_reached": False,
            },
            "warnings": [],
            "stopped": False,
        }

        root_error = self._walk_children(
            page_id,
            0,
            state,
            max_depth=max_depth,
            max_request_calls=max_request_calls,
            page_size=page_size,
            on_block=on_block,
        )

        if root_error is not None:
            return root_error

        complete = (
            not state["warnings"]
            and not state["partial"]["max_depth_reached"]
            and not state["partial"]["max_requests_reached"]
        )

        return {
            "ok": True,
            "complete": complete,
            "blocks": state["blocks"],
            "request_calls": state["request_calls"],
            "partial": state["partial"],
            "warnings": state["warnings"],
        }

    def _walk_children(
        self,
        parent_id: str,
        depth: int,
        state: dict[str, Any],
        *,
        max_depth: int,
        max_request_calls: int,
        page_size: int,
        on_block: (
            Callable[[dict[str, Any], dict[str, Any]], None] | None
        ) = None,
    ) -> dict[str, Any] | None:
        """Fetch and record one parent's children, recursing as needed.

        Returns a structured error only when the very first
        get_block_children() call of the whole traversal fails; every
        later failure is instead recorded as a warning in state, and
        state["stopped"] is set so no further calls are made anywhere
        in the traversal.
        """
        start_cursor: str | None = None
        used_cursors: set[str] = set()

        while True:
            if state["stopped"]:
                return None

            if start_cursor is not None:
                if start_cursor in used_cursors:
                    state["warnings"].append(
                        {
                            "type": "repeated_cursor",
                            "parent_id": parent_id,
                            "cursor": start_cursor,
                        }
                    )
                    return None

                used_cursors.add(start_cursor)

            if state["request_calls"] >= max_request_calls:
                state["partial"]["max_requests_reached"] = True
                state["stopped"] = True
                return None

            response = self.get_block_children(
                parent_id,
                page_size=page_size,
                start_cursor=start_cursor,
            )
            # response (get_block_children) is like {
            #     "ok": True,
            #     "results": [...],
            #     "has_more": ...,
            #     "next_cursor": ...,
            # }
            state["request_calls"] += 1

            if "error" in response:
                if state["request_calls"] == 1:
                    state["stopped"] = True
                    return response

                error = response["error"]
                state["warnings"].append(
                    {
                        "type": "request_failed",
                        "parent_id": parent_id,
                        "code": error.get("code"),
                        "message": error.get("message"),
                        "retryable": error.get("retryable"),
                        "suggested_action": error.get("suggested_action"),
                        "retry_after": error.get("retry_after"),
                    }
                )
                state["stopped"] = True
                return None

            results = response["results"]
            has_more = response["has_more"]
            next_cursor = response["next_cursor"]

            for block in results:
                if state["stopped"]:
                    return None

                state["blocks"].append(
                    {
                        "parent_id": parent_id,
                        "depth": depth,
                        "block": block,
                    }
                )

                if on_block is not None:
                    on_block(state["blocks"][-1], state)

                    if state["stopped"]:
                        return None

                block_type = block["type"]
                has_children = block["has_children"]

                if block_type in ("child_page", "child_database"):
                    if has_children:
                        state["warnings"].append(
                            {
                                "type": "page_boundary",
                                "block_id": block["id"],
                                "block_type": block_type,
                            }
                        )
                    continue

                if not has_children:
                    continue

                if depth >= max_depth:
                    state["partial"]["max_depth_reached"] = True
                    continue

                self._walk_children(
                    block["id"],
                    depth + 1,
                    state,
                    max_depth=max_depth,
                    max_request_calls=max_request_calls,
                    page_size=page_size,
                    on_block=on_block,
                )

                if state["stopped"]:
                    return None

            if state["stopped"]:
                return None

            if not has_more:
                return None

            start_cursor = next_cursor

    def _extract_rich_text(self, rich_text: Any) -> str:
        """Join plain_text fragments from a Notion rich_text array.

        Fragments are concatenated directly with no added separator,
        since Notion splits rich text only at formatting boundaries,
        not at word boundaries.
        """
        return "".join(fragment["plain_text"] for fragment in rich_text)

    def _extract_block_text(self, block: dict[str, Any]) -> str | None:
        """Return a block's readable text, or None if unsupported.

        "" is a valid result for a supported block with no text of
        its own (a structural container such as table/column_list/
        column) or with empty rich_text (an empty paragraph, for
        example). Neither case is "unsupported" -- that is reported
        separately through unsupported_block_types. Any malformed
        type-specific data (an unexpected shape for this block's own
        type) is also treated as unsupported rather than raised,
        matching this project's general response-validation style.
        """
        block_type = block["type"]

        try:
            if block_type in STRUCTURAL_CONTAINER_TYPES:
                return ""

            if block_type in ("child_page", "child_database"):
                return block[block_type].get("title", "")

            if block_type == "table_row":
                cells = block["table_row"]["cells"]
                return " | ".join(
                    self._extract_rich_text(cell) for cell in cells
                )

            if block_type == "to_do":
                to_do = block["to_do"]
                marker = "[x] " if to_do["checked"] else "[ ] "
                return marker + self._extract_rich_text(
                    to_do["rich_text"]
                )

            if block_type in RICH_TEXT_BLOCK_TYPES:
                return self._extract_rich_text(
                    block[block_type]["rich_text"]
                )

        except (KeyError, TypeError, AttributeError):
            return None

        return None

    def read_page_blocks(
        self,
        page_id: str,
        *,
        max_depth: int = 3,
        max_request_calls: int = 20,
        max_blocks: int = 500,
        max_characters: int = 20000,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Read a page's content as compact, readable text entries.

        Builds on _walk_block_tree()'s traversal (the same
        pagination, recursion, depth bound, and request-call bound)
        and adds two more output bounds on top: max_blocks (how many
        visited blocks are kept in the output) and max_characters
        (the total length of all emitted text, including separators
        the extractor itself adds, such as " | " between table cells
        or the "[x] "/"[ ] " marker on a to-do). Both are enforced
        while the raw traversal is still running, through the
        on_block callback: hitting either stops the traversal
        immediately, the same way hitting max_depth or
        max_request_calls does, so the full raw tree is never fetched
        and trimmed afterward. A block that would push the output
        over either limit is left out entirely rather than having
        its text cut short.

        request_calls counts get_block_children() calls, not the
        individual HTTP attempts request() may make internally (an
        initial 401 followed by one refreshed retry still counts as
        one get_block_children() call here).

        complete=True means every visited block was both traversed
        (per _walk_block_tree's own meaning: no depth/request-call
        limit hit, no cursor cycle, no unreported page/database
        boundary) and successfully turned into text within
        max_blocks and max_characters, with no unsupported block
        types along the way. A page can be complete at the
        traversal level but still have complete=False here, for
        example because one block type had no text extractor.
        """
        if type(max_blocks) is not int or max_blocks < 1:
            return oauth.error_result(
                "INVALID_MAX_BLOCKS",
                "max_blocks must be a positive integer.",
                False,
                "Use a max_blocks such as 500.",
            )

        if type(max_characters) is not int or max_characters < 1:
            return oauth.error_result(
                "INVALID_MAX_CHARACTERS",
                "max_characters must be a positive integer.",
                False,
                "Use a max_characters such as 20000.",
            )

        reader_state: dict[str, Any] = {
            "blocks": [],
            "char_total": 0,
            "unsupported_types": set(),
            "partial": {
                "max_blocks_reached": False,
                "max_characters_reached": False,
            },
        }

        def on_block(
            entry: dict[str, Any], state: dict[str, Any]
        ) -> None:
            if len(reader_state["blocks"]) >= max_blocks:
                reader_state["partial"]["max_blocks_reached"] = True
                state["stopped"] = True
                return

            block = entry["block"]
            text = self._extract_block_text(block)

            if text is None:
                reader_state["unsupported_types"].add(block["type"])
                text_length = 0
            else:
                text_length = len(text)

            if (
                reader_state["char_total"] + text_length
                > max_characters
            ):
                reader_state["partial"]["max_characters_reached"] = (
                    True
                )
                state["stopped"] = True
                return

            reader_state["char_total"] += text_length

            reader_state["blocks"].append(
                {
                    "id": block["id"],
                    "parent_id": entry["parent_id"],
                    "type": block["type"],
                    "depth": entry["depth"],
                    "text": text,
                }
            )

        walk_result = self._walk_block_tree(
            page_id,
            max_depth=max_depth,
            max_request_calls=max_request_calls,
            page_size=page_size,
            on_block=on_block,
        )

        if "error" in walk_result:
            return walk_result

        complete = (
            walk_result["complete"]
            and not reader_state["partial"]["max_blocks_reached"]
            and not reader_state["partial"]["max_characters_reached"]
            and not reader_state["unsupported_types"]
        )

        partial = dict(walk_result["partial"])
        partial.update(reader_state["partial"])

        return {
            "ok": True,
            "complete": complete,
            "blocks": reader_state["blocks"],
            "request_calls": walk_result["request_calls"],
            "partial": partial,
            "warnings": walk_result["warnings"],
            "unsupported_block_types": sorted(
                reader_state["unsupported_types"]
            ),
        }

    def get_page_content(
        self,
        page_id: str,
        *,
        max_depth: int = 3,
        max_request_calls: int = 20,
        max_blocks: int = 500,
        max_characters: int = 20000,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Read a page's metadata and body text in one combined result.

        Calls get_page(page_id) first. If that errors, the error is
        returned immediately and read_page_blocks() is never called.
        Otherwise calls read_page_blocks() with the same page_id,
        forwarding max_depth, max_request_calls, max_blocks,
        max_characters, and page_size unchanged. If the body reader
        errors, that error is also returned unchanged.

        On success, every field from read_page_blocks() -- complete,
        blocks, request_calls, partial, warnings, and
        unsupported_block_types -- is kept as-is, including
        complete=False and any partial flags/warnings/unsupported
        types for a partial read, and a "page" field (the shaped
        {id, title, url} from get_page()) is added alongside them.
        request_calls only counts get_block_children() calls made
        while reading the body; the get_page() call itself is not
        included.
        """
        page_result = self.get_page(page_id)

        if "error" in page_result:
            return page_result

        body_result = self.read_page_blocks(
            page_id,
            max_depth=max_depth,
            max_request_calls=max_request_calls,
            max_blocks=max_blocks,
            max_characters=max_characters,
            page_size=page_size,
        )

        if "error" in body_result:
            return body_result

        return {
            **body_result,
            "page": page_result["page"],
        }

    def search_pages(
        self,
        query: str,
        page_size: int = 10,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search accessible pages using Notion's title search.

        Return one batch of page IDs, titles, and URLs.
        This client does not enforce exact substring matching.
        Inspect returned titles before selecting a page ID.

        Use a returned page ID to retrieve the page content.
        If has_more is true, call again with the same query and
        the returned next_cursor as start_cursor.
        """
        if not isinstance(query, str) or not query.strip():
            return oauth.error_result(
                "INVALID_QUERY",
                "The search query must be a non-empty string.",
                False,
                "Provide a page title or part of a page title.",
            )

        if type(page_size) is not int or not 1 <= page_size <= 100:
            return oauth.error_result(
                "INVALID_PAGE_SIZE",
                "page_size must be an integer between 1 and 100.",
                False,
                "Use a page_size such as 10.",
            )

        if start_cursor is not None:
            if not isinstance(start_cursor, str) or not start_cursor.strip():
                return oauth.error_result(
                    "INVALID_CURSOR",
                    "start_cursor must be a non-empty string or None.",
                    False,
                    "Use next_cursor from a previous search response.",
                )

        body: dict[str, Any] = {
            "query": query.strip(),
            "page_size": page_size,
            "filter": {
                "property": "object",
                "value": "page",
            },
        }

        if start_cursor is not None:
            body["start_cursor"] = start_cursor

        # print("DEBUG: Search request body:", body)
        
        response = self.request(
            "POST",
            "/search",
            json_body=body,
            read_only=True,
        )

        if "error" in response:
            return response

        data = response["data"]

        try:
            results = data["results"]
            has_more = data["has_more"]
            next_cursor = data["next_cursor"]

            if not isinstance(results, list):
                raise ValueError("Invalid results")

            if not isinstance(has_more, bool):
                raise ValueError("Invalid has_more")

            if next_cursor is not None and (
                not isinstance(next_cursor, str) or not next_cursor
            ):
                raise ValueError("Invalid next_cursor")

            if has_more and next_cursor is None:
                raise ValueError("Missing next_cursor")

            pages = []

            for page in results:
                if page["object"] != "page":
                    raise ValueError("Unexpected object type")

                if not isinstance(page["id"], str) or not page["id"]:
                    raise ValueError("Invalid page ID")

                if not isinstance(page["url"], str) or not page["url"]:
                    raise ValueError("Invalid page URL")

                pages.append(
                    {
                        "id": page["id"],
                        "title": self._extract_page_title(page),
                        "url": page["url"],
                    }
                )

        except (KeyError, TypeError, ValueError, AttributeError):
            return oauth.error_result(
                "INVALID_SEARCH_RESPONSE",
                "Notion returned an unexpected search response structure.",
                False,
                "Check the search response format and API version.",
            )

        return {
            "ok": True,
            "pages": pages,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def create_page(
        self,
        parent_page_id: str,
        title: str,
        content: str,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Preview, and eventually create, a child page under a parent.

        parent_page_id identifies an existing page to create the new
        page under; it can come from search_pages() or get_page().

        dry_run defaults to True. With dry_run=True (or omitted), this
        only validates the inputs and returns a local preview of the
        parent_page_id, title, and content that would be sent to
        Notion -- it never calls request(), so it cannot confirm that
        the parent page exists or that this connection can write
        there. With dry_run=False, live creation is not implemented
        yet (planned for Phase 2.4.2); this returns a structured error
        instead of calling request().

        parent_page_id and title are stripped before use. content is
        kept exactly as given, including internal blank lines and
        leading/trailing whitespace on its own lines, since it is the
        study-note body text. Phase 2.4.2 can reuse these same
        stripped/validated values -- the preview shows precisely what
        would be sent.
        """
        if not isinstance(parent_page_id, str):
            return oauth.error_result(
                "INVALID_PARENT_PAGE_ID",
                "parent_page_id must be a string.",
                False,
                "Use an id returned by search_pages() or get_page().",
            )

        parent_page_id = parent_page_id.strip()

        if not PAGE_ID_PATTERN.match(parent_page_id):
            return oauth.error_result(
                "INVALID_PARENT_PAGE_ID",
                "parent_page_id must be a Notion page ID (a UUID, "
                "with or without dashes).",
                False,
                "Use an id returned by search_pages() or get_page().",
            )

        if not isinstance(title, str) or not title.strip():
            return oauth.error_result(
                "INVALID_TITLE",
                "title must be a non-empty string.",
                False,
                "Provide a short, descriptive page title.",
            )

        title = title.strip()

        if not isinstance(content, str) or not content.strip():
            return oauth.error_result(
                "INVALID_CONTENT",
                "content must be a non-empty string.",
                False,
                "Provide the study-note text to write to the page.",
            )

        if type(dry_run) is not bool:
            return oauth.error_result(
                "INVALID_DRY_RUN",
                "dry_run must be True or False.",
                False,
                "Use dry_run=True to preview, or omit it.",
            )

        if not dry_run:
            return oauth.error_result(
                "PAGE_CREATION_NOT_IMPLEMENTED",
                "Live page creation is planned for Phase 2.4.2 and "
                "is not implemented yet.",
                False,
                "Call create_page() with dry_run=True (the default) "
                "to preview the page.",
            )

        return {
            "ok": True,
            "dry_run": True,
            "created": False,
            "preview": {
                "parent_page_id": parent_page_id,
                "title": title,
                "content": content,
            },
        }