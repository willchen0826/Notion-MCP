from unittest.mock import patch

from notion_api import NotionAPIClient


BLOCK_ID = "22222222-2222-2222-2222-222222222222"

PARAGRAPH_BLOCK = {
    "object": "block",
    "id": "33333333-3333-3333-3333-333333333333",
    "type": "paragraph",
    "has_children": False,
    "paragraph": {
        "rich_text": [{"plain_text": "Hello"}],
    },
}

TOGGLE_BLOCK_WITH_CHILDREN = {
    "object": "block",
    "id": "44444444-4444-4444-4444-444444444444",
    "type": "toggle",
    "has_children": True,
    "toggle": {
        "rich_text": [{"plain_text": "Expand me"}],
    },
}


def test_get_block_children_shapes_batch_and_uses_get_path():
    raw_data = {
        "object": "list",
        "results": [PARAGRAPH_BLOCK],
        "has_more": False,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ) as request,
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID, page_size=50)

    assert result == {
        "ok": True,
        "results": [PARAGRAPH_BLOCK],
        "has_more": False,
        "next_cursor": None,
    }

    assert request.call_args.args == ("GET", f"/blocks/{BLOCK_ID}/children")
    assert request.call_args.kwargs["params"] == {"page_size": 50}
    assert request.call_args.kwargs["read_only"] is True


def test_get_block_children_passes_cursor_for_subsequent_batch():
    raw_data = {
        "object": "list",
        "results": [],
        "has_more": False,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ) as request,
    ):
        client = NotionAPIClient()
        client.get_block_children(
            BLOCK_ID,
            page_size=10,
            start_cursor="previous-batch-cursor",
        )

    assert request.call_args.kwargs["params"] == {
        "page_size": 10,
        "start_cursor": "previous-batch-cursor",
    }


def test_get_block_children_does_not_auto_fetch_next_page():
    raw_data = {
        "object": "list",
        "results": [PARAGRAPH_BLOCK],
        "has_more": True,
        "next_cursor": "more-to-come",
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ) as request,
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result["has_more"] is True
    assert result["next_cursor"] == "more-to-come"
    request.assert_called_once()


def test_get_block_children_empty_results():
    raw_data = {
        "object": "list",
        "results": [],
        "has_more": False,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ),
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result == {
        "ok": True,
        "results": [],
        "has_more": False,
        "next_cursor": None,
    }


def test_get_block_children_preserves_has_children_without_recursing():
    raw_data = {
        "object": "list",
        "results": [TOGGLE_BLOCK_WITH_CHILDREN],
        "has_more": False,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ) as request,
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result["results"][0]["has_children"] is True
    assert result["results"][0] == TOGGLE_BLOCK_WITH_CHILDREN
    request.assert_called_once()


def test_get_block_children_rejects_invalid_block_id_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.get_block_children("not-a-real-id")

    assert result["error"]["code"] == "INVALID_BLOCK_ID"
    request.assert_not_called()


def test_get_block_children_rejects_non_string_block_id_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.get_block_children(None)

    assert result["error"]["code"] == "INVALID_BLOCK_ID"
    request.assert_not_called()


def test_get_block_children_rejects_bad_page_size_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()

        too_big = client.get_block_children(BLOCK_ID, page_size=101)
        zero = client.get_block_children(BLOCK_ID, page_size=0)
        boolean = client.get_block_children(BLOCK_ID, page_size=True)

    assert too_big["error"]["code"] == "INVALID_PAGE_SIZE"
    assert zero["error"]["code"] == "INVALID_PAGE_SIZE"
    assert boolean["error"]["code"] == "INVALID_PAGE_SIZE"
    request.assert_not_called()


def test_get_block_children_rejects_bad_cursor_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()

        blank = client.get_block_children(BLOCK_ID, start_cursor="   ")
        wrong_type = client.get_block_children(BLOCK_ID, start_cursor=123)

    assert blank["error"]["code"] == "INVALID_CURSOR"
    assert wrong_type["error"]["code"] == "INVALID_CURSOR"
    request.assert_not_called()


def test_get_block_children_preserves_request_error():
    error = {
        "error": {
            "code": "NOT_FOUND_OR_INACCESSIBLE",
            "message": "The resource was not found or is not accessible.",
            "retryable": False,
            "suggested_action": (
                "Check the resource ID and whether access was granted."
            ),
        }
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value=error,
        ),
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result == error


def test_get_block_children_flags_malformed_block():
    malformed_block = dict(PARAGRAPH_BLOCK)
    del malformed_block["has_children"]

    raw_data = {
        "object": "list",
        "results": [malformed_block],
        "has_more": False,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ),
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result["error"]["code"] == "INVALID_BLOCK_CHILDREN_RESPONSE"


def test_get_block_children_flags_has_more_without_next_cursor():
    raw_data = {
        "object": "list",
        "results": [],
        "has_more": True,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ),
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result["error"]["code"] == "INVALID_BLOCK_CHILDREN_RESPONSE"


def test_get_block_children_flags_wrong_object_type():
    raw_data = {
        "object": "page",
        "results": [],
        "has_more": False,
        "next_cursor": None,
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": raw_data},
        ),
    ):
        client = NotionAPIClient()
        result = client.get_block_children(BLOCK_ID)

    assert result["error"]["code"] == "INVALID_BLOCK_CHILDREN_RESPONSE"
