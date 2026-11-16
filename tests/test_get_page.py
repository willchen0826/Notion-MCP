from unittest.mock import patch

from notion_api import NotionAPIClient


RAW_PAGE = {
    "object": "page",
    "id": "11111111-1111-1111-1111-111111111111",
    "url": "https://www.notion.so/Example-Page-111111111111",
    "properties": {
        "Name": {
            "type": "title",
            "title": [
                {"plain_text": "Example "},
                {"plain_text": "Page"},
            ],
        }
    },
}


def test_get_page_shapes_metadata():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": RAW_PAGE},
        ) as request,
    ):
        client = NotionAPIClient()
        result = client.get_page(RAW_PAGE["id"])

    assert result == {
        "ok": True,
        "page": {
            "id": RAW_PAGE["id"],
            "title": "Example Page",
            "url": RAW_PAGE["url"],
        },
    }

    assert request.call_args.args == ("GET", f"/pages/{RAW_PAGE['id']}")
    assert request.call_args.kwargs["read_only"] is True


def test_get_page_accepts_id_without_dashes():
    undashed_id = "11111111111111111111111111111111"

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": RAW_PAGE},
        ) as request,
    ):
        client = NotionAPIClient()
        result = client.get_page(undashed_id)

    assert result["ok"] is True
    assert request.call_args.args == ("GET", f"/pages/{undashed_id}")


def test_get_page_rejects_invalid_id_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.get_page("not-a-real-id")

    assert result["error"]["code"] == "INVALID_PAGE_ID"
    request.assert_not_called()


def test_get_page_rejects_non_string_id_without_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(NotionAPIClient, "request") as request,
    ):
        client = NotionAPIClient()
        result = client.get_page(None)

    assert result["error"]["code"] == "INVALID_PAGE_ID"
    request.assert_not_called()


def test_get_page_preserves_request_error():
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
        result = client.get_page(RAW_PAGE["id"])

    assert result == error


def test_get_page_flags_malformed_response():
    malformed = dict(RAW_PAGE)
    del malformed["properties"]

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient,
            "request",
            return_value={"ok": True, "data": malformed},
        ),
    ):
        client = NotionAPIClient()
        result = client.get_page(RAW_PAGE["id"])

    assert result["error"]["code"] == "INVALID_PAGE_RESPONSE"
