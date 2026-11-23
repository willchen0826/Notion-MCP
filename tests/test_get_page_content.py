from unittest.mock import patch

from notion_api import NotionAPIClient


PAGE_ID = "11111111-1111-1111-1111-111111111111"

PAGE_RESULT = {
    "ok": True,
    "page": {
        "id": PAGE_ID,
        "title": "Example Page",
        "url": "https://www.notion.so/Example-Page-111111111111",
    },
}

COMPLETE_BODY_RESULT = {
    "ok": True,
    "complete": True,
    "blocks": [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "parent_id": PAGE_ID,
            "type": "paragraph",
            "depth": 0,
            "text": "Hello",
        }
    ],
    "request_calls": 1,
    "partial": {
        "max_depth_reached": False,
        "max_requests_reached": False,
        "max_blocks_reached": False,
        "max_characters_reached": False,
    },
    "warnings": [],
    "unsupported_block_types": [],
}

PARTIAL_BODY_RESULT = {
    "ok": True,
    "complete": False,
    "blocks": [
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "parent_id": PAGE_ID,
            "type": "paragraph",
            "depth": 0,
            "text": "Only this much",
        }
    ],
    "request_calls": 5,
    "partial": {
        "max_depth_reached": False,
        "max_requests_reached": True,
        "max_blocks_reached": False,
        "max_characters_reached": False,
    },
    "warnings": [
        {
            "type": "request_failed",
            "parent_id": PAGE_ID,
            "code": "RATE_LIMITED",
            "message": "Notion rate-limited the request.",
            "retryable": True,
            "suggested_action": "Wait before retrying.",
            "retry_after": "2",
        }
    ],
    "unsupported_block_types": ["embed"],
}

PAGE_ERROR = {
    "error": {
        "code": "NOT_FOUND_OR_INACCESSIBLE",
        "message": "The resource was not found or is not accessible.",
        "retryable": False,
        "suggested_action": (
            "Check the resource ID and whether access was granted."
        ),
    }
}

BODY_ERROR = {
    "error": {
        "code": "AUTH_REQUIRED",
        "message": "No cached credentials were found.",
        "retryable": False,
        "suggested_action": "Run python oauth.py login.",
    }
}


def test_get_page_content_combines_metadata_and_body_and_forwards_limits():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient, "get_page", return_value=PAGE_RESULT
        ) as get_page,
        patch.object(
            NotionAPIClient,
            "read_page_blocks",
            return_value=COMPLETE_BODY_RESULT,
        ) as read_page_blocks,
    ):
        client = NotionAPIClient()
        result = client.get_page_content(
            PAGE_ID,
            max_depth=1,
            max_request_calls=5,
            max_blocks=10,
            max_characters=200,
            page_size=50,
        )

    assert result == {
        **COMPLETE_BODY_RESULT,
        "page": PAGE_RESULT["page"],
    }

    get_page.assert_called_once_with(PAGE_ID)
    read_page_blocks.assert_called_once_with(
        PAGE_ID,
        max_depth=1,
        max_request_calls=5,
        max_blocks=10,
        max_characters=200,
        page_size=50,
    )


def test_get_page_content_preserves_partial_body_and_its_reason():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient, "get_page", return_value=PAGE_RESULT
        ),
        patch.object(
            NotionAPIClient,
            "read_page_blocks",
            return_value=PARTIAL_BODY_RESULT,
        ),
    ):
        client = NotionAPIClient()
        result = client.get_page_content(PAGE_ID)

    assert result["complete"] is False
    assert result["blocks"] == PARTIAL_BODY_RESULT["blocks"]
    assert result["partial"]["max_requests_reached"] is True
    assert result["warnings"] == PARTIAL_BODY_RESULT["warnings"]
    assert result["unsupported_block_types"] == ["embed"]
    assert result["request_calls"] == 5
    assert result["page"] == PAGE_RESULT["page"]


def test_get_page_content_returns_metadata_error_without_reading_body():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient, "get_page", return_value=PAGE_ERROR
        ),
        patch.object(
            NotionAPIClient, "read_page_blocks"
        ) as read_page_blocks,
    ):
        client = NotionAPIClient()
        result = client.get_page_content(PAGE_ID)

    assert result == PAGE_ERROR
    read_page_blocks.assert_not_called()


def test_get_page_content_returns_body_error_unchanged():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient, "get_page", return_value=PAGE_RESULT
        ),
        patch.object(
            NotionAPIClient, "read_page_blocks", return_value=BODY_ERROR
        ),
    ):
        client = NotionAPIClient()
        result = client.get_page_content(PAGE_ID)

    assert result == BODY_ERROR
