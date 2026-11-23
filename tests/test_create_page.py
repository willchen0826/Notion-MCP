from unittest.mock import patch

from notion_api import NotionAPIClient


PARENT_ID = "11111111-1111-1111-1111-111111111111"
PARENT_ID_NO_DASHES = PARENT_ID.replace("-", "")
NEW_PAGE_ID = "22222222-2222-2222-2222-222222222222"
NEW_PAGE_URL = f"https://www.notion.so/{NEW_PAGE_ID}"


def _client():
    with patch("notion_api.oauth.load_oauth_config", return_value={}):
        return NotionAPIClient()


def _page_response(page_id, title, url):
    return {
        "ok": True,
        "data": {
            "object": "page",
            "id": page_id,
            "url": url,
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": title}],
                }
            },
        },
        "refreshed": False,
    }


# --- Phase 2.4.1: local preview, zero request() calls -----------------


def test_create_page_preview_when_dry_run_omitted():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(
            PARENT_ID,
            "Week 2 notes",
            "Line one.\nLine two.",
        )

    assert result == {
        "ok": True,
        "dry_run": True,
        "created": False,
        "preview": {
            "parent_page_id": PARENT_ID,
            "title": "Week 2 notes",
            "content": "Line one.\nLine two.",
        },
    }
    request.assert_not_called()


def test_create_page_preview_with_explicit_dry_run_true():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(
            PARENT_ID, "Week 2 notes", "Body text", dry_run=True
        )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["created"] is False
    assert result["preview"]["parent_page_id"] == PARENT_ID
    request.assert_not_called()


def test_create_page_accepts_parent_id_without_dashes():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(
            PARENT_ID_NO_DASHES, "Title", "Content"
        )

    assert result["ok"] is True
    assert result["preview"]["parent_page_id"] == PARENT_ID_NO_DASHES
    request.assert_not_called()


def test_create_page_rejects_partially_dashed_parent_id():
    # Regression test: PAGE_ID_PATTERN used to make every dash
    # independently optional, so stripping out just one dash from an
    # otherwise valid UUID still matched. Each dash must now be
    # present (full UUID form) or absent (32 raw hex digits) together.
    partial_id = PARENT_ID.replace("-", "", 1)

    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(partial_id, "Week 2 notes", "Body text")

    assert result["error"]["code"] == "INVALID_PARENT_PAGE_ID"
    request.assert_not_called()


def test_create_page_preserves_multiline_and_blank_lines_in_content():
    content = "First line.\n\nSecond paragraph.\n   indented line\n"
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, "Title", content)

    assert result["preview"]["content"] == content
    request.assert_not_called()


def test_create_page_rejects_invalid_parent_id_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page("not-a-uuid", "Title", "Content")

    assert result["error"]["code"] == "INVALID_PARENT_PAGE_ID"
    request.assert_not_called()


def test_create_page_rejects_non_string_parent_id_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(12345, "Title", "Content")

    assert result["error"]["code"] == "INVALID_PARENT_PAGE_ID"
    request.assert_not_called()


def test_create_page_rejects_blank_title_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, "   ", "Content")

    assert result["error"]["code"] == "INVALID_TITLE"
    request.assert_not_called()


def test_create_page_rejects_non_string_title_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, None, "Content")

    assert result["error"]["code"] == "INVALID_TITLE"
    request.assert_not_called()


def test_create_page_rejects_title_over_length_limit_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, "x" * 2001, "Content")

    assert result["error"]["code"] == "INVALID_TITLE"
    request.assert_not_called()


def test_create_page_rejects_blank_content_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, "Title", "\n   \n")

    assert result["error"]["code"] == "INVALID_CONTENT"
    request.assert_not_called()


def test_create_page_rejects_non_string_content_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, "Title", 123)

    assert result["error"]["code"] == "INVALID_CONTENT"
    request.assert_not_called()


def test_create_page_rejects_too_many_content_lines_without_request():
    # 101 lines would need 101 paragraph blocks, one over the 100
    # child-block limit enforced for both preview and creation.
    content = "\n".join(["line"] * 101)

    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result = client.create_page(PARENT_ID, "Title", content)

    assert result["error"]["code"] == "CONTENT_TOO_LARGE"
    request.assert_not_called()


def test_create_page_rejects_non_boolean_dry_run_without_request():
    with patch.object(NotionAPIClient, "request") as request:
        client = _client()
        result_int = client.create_page(
            PARENT_ID, "Title", "Content", dry_run=1
        )
        result_str = client.create_page(
            PARENT_ID, "Title", "Content", dry_run="True"
        )

    assert result_int["error"]["code"] == "INVALID_DRY_RUN"
    assert result_str["error"]["code"] == "INVALID_DRY_RUN"
    request.assert_not_called()


# --- Phase 2.4.2: live creation (dry_run=False) ------------------------


def test_create_page_creates_page_when_dry_run_false():
    with patch.object(NotionAPIClient, "request") as request:
        request.return_value = _page_response(
            NEW_PAGE_ID, "Week 2 notes", NEW_PAGE_URL
        )
        client = _client()
        result = client.create_page(
            PARENT_ID,
            "Week 2 notes",
            "Line one.\nLine two.",
            dry_run=False,
        )

    assert result == {
        "ok": True,
        "dry_run": False,
        "created": True,
        "page": {
            "id": NEW_PAGE_ID,
            "title": "Week 2 notes",
            "url": NEW_PAGE_URL,
        },
    }

    request.assert_called_once()
    args, kwargs = request.call_args
    assert args == ("POST", "/pages")
    assert kwargs["read_only"] is False

    payload = kwargs["json_body"]
    assert payload["parent"] == {"page_id": PARENT_ID}
    assert payload["properties"]["title"]["title"] == [
        {"type": "text", "text": {"content": "Week 2 notes"}}
    ]
    assert payload["children"] == [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Line one."}}
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Line two."}}
                ]
            },
        },
    ]


def test_create_page_dry_run_false_preserves_blank_lines_and_indentation():
    content = "First line.\n\nSecond paragraph.\n   indented line"

    with patch.object(NotionAPIClient, "request") as request:
        request.return_value = _page_response(
            NEW_PAGE_ID, "Title", NEW_PAGE_URL
        )
        client = _client()
        client.create_page(PARENT_ID, "Title", content, dry_run=False)

    payload = request.call_args.kwargs["json_body"]
    paragraphs = [
        block["paragraph"]["rich_text"] for block in payload["children"]
    ]

    assert paragraphs == [
        [{"type": "text", "text": {"content": "First line."}}],
        [],
        [{"type": "text", "text": {"content": "Second paragraph."}}],
        [{"type": "text", "text": {"content": "   indented line"}}],
    ]


def test_create_page_dry_run_false_passes_through_request_error():
    error_response = {
        "error": {
            "code": "NOT_FOUND_OR_INACCESSIBLE",
            "message": "The resource was not found or is not accessible.",
            "retryable": False,
            "suggested_action": "Check the resource ID and whether "
            "access was granted.",
        }
    }

    with patch.object(NotionAPIClient, "request") as request:
        request.return_value = error_response
        client = _client()
        result = client.create_page(
            PARENT_ID, "Title", "Content", dry_run=False
        )

    assert result == error_response
    request.assert_called_once()


def test_create_page_dry_run_false_rejects_malformed_success_response():
    with patch.object(NotionAPIClient, "request") as request:
        request.return_value = {
            "ok": True,
            "data": {"object": "page"},
            "refreshed": False,
        }
        client = _client()
        result = client.create_page(
            PARENT_ID, "Title", "Content", dry_run=False
        )

    assert result["error"]["code"] == "INVALID_CREATE_PAGE_RESPONSE"
    request.assert_called_once()
