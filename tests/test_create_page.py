from unittest.mock import patch

from notion_api import NotionAPIClient


PARENT_ID = "11111111-1111-1111-1111-111111111111"
PARENT_ID_NO_DASHES = PARENT_ID.replace("-", "")


def test_create_page_preview_when_dry_run_omitted():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
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
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(
            PARENT_ID, "Week 2 notes", "Body text", dry_run=True
        )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["created"] is False
    assert result["preview"]["parent_page_id"] == PARENT_ID
    request.assert_not_called()


def test_create_page_accepts_parent_id_without_dashes():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(
            PARENT_ID_NO_DASHES, "Title", "Content"
        )

    assert result["ok"] is True
    assert result["preview"]["parent_page_id"] == PARENT_ID_NO_DASHES
    request.assert_not_called()


def test_create_page_explicit_dry_run_false_returns_not_implemented_error():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(
            PARENT_ID, "Title", "Content", dry_run=False
        )

    assert result["error"]["code"] == "PAGE_CREATION_NOT_IMPLEMENTED"
    request.assert_not_called()


def test_create_page_preserves_multiline_and_blank_lines_in_content():
    content = "First line.\n\nSecond paragraph.\n   indented line\n"
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(PARENT_ID, "Title", content)

    assert result["preview"]["content"] == content
    request.assert_not_called()


def test_create_page_rejects_invalid_parent_id_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page("not-a-uuid", "Title", "Content")

    assert result["error"]["code"] == "INVALID_PARENT_PAGE_ID"
    request.assert_not_called()


def test_create_page_rejects_non_string_parent_id_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(12345, "Title", "Content")

    assert result["error"]["code"] == "INVALID_PARENT_PAGE_ID"
    request.assert_not_called()


def test_create_page_rejects_blank_title_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(PARENT_ID, "   ", "Content")

    assert result["error"]["code"] == "INVALID_TITLE"
    request.assert_not_called()


def test_create_page_rejects_non_string_title_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(PARENT_ID, None, "Content")

    assert result["error"]["code"] == "INVALID_TITLE"
    request.assert_not_called()


def test_create_page_rejects_blank_content_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(PARENT_ID, "Title", "\n   \n")

    assert result["error"]["code"] == "INVALID_CONTENT"
    request.assert_not_called()


def test_create_page_rejects_non_string_content_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.create_page(PARENT_ID, "Title", 123)

    assert result["error"]["code"] == "INVALID_CONTENT"
    request.assert_not_called()


def test_create_page_rejects_non_boolean_dry_run_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result_int = client.create_page(
            PARENT_ID, "Title", "Content", dry_run=1
        )
        result_str = client.create_page(
            PARENT_ID, "Title", "Content", dry_run="True"
        )

    assert result_int["error"]["code"] == "INVALID_DRY_RUN"
    assert result_str["error"]["code"] == "INVALID_DRY_RUN"
    request.assert_not_called()

