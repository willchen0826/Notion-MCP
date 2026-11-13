from unittest.mock import patch

from notion_api import NotionAPIClient


def test_search_shapes_title_and_preserves_pagination():
    raw_data = {
        "results": [
            {
                "object": "page",
                "id": "page-1",
                "url": "https://www.notion.so/page-1",
                "created_time": "2026-11-13T00:00:00Z",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [
                            {"plain_text": "W2 - "},
                            {"plain_text": "New MCP"},
                        ],
                    }
                },
            }
        ],
        "has_more": True,
        "next_cursor": "next-batch",
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

        result = client.search_pages(
            "W2",
            page_size=1,
            start_cursor="previous-batch",
        )

    assert result == {
        "ok": True,
        "pages": [
            {
                "id": "page-1",
                "title": "W2 - New MCP",
                "url": "https://www.notion.so/page-1",
            }
        ],
        "has_more": True,
        "next_cursor": "next-batch",
    }

    body = request.call_args.kwargs["json_body"]
    assert body["start_cursor"] == "previous-batch"
    assert body["filter"] == {"property": "object", "value": "page"}
    assert request.call_args.kwargs["read_only"] is True


def test_search_preserves_request_error():
    error = {
        "error": {
            "code": "AUTH_REQUIRED",
            "message": "No cached credentials were found.",
            "retryable": False,
            "suggested_action": "Run python oauth.py login.",
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
        result = client.search_pages("W2")

    assert result == error