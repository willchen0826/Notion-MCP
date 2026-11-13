from unittest.mock import patch

import httpx

from notion_api import NotionAPIClient


def test_request_refreshes_once_and_uses_new_token():
    old_tokens = {
        "access_token": "old-access",
        "refresh_token": "old-refresh",
    }
    new_tokens = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch(
            "notion_api.oauth.load_tokens",
            side_effect=[old_tokens, new_tokens],
        ),
        patch(
            "notion_api.oauth.refresh_cached_tokens",
            return_value={"ok": True},
        ) as refresh,
        patch(
            "notion_api.httpx.request",
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json={"results": []}),
            ],
        ) as request,
        patch("oauth.webbrowser.open") as browser,
    ):
        client = NotionAPIClient()
        result = client.request(
            "POST",
            "/search",
            json_body={"page_size": 1},
            read_only=True,
        )

    assert result["ok"] is True
    assert result["refreshed"] is True
    assert request.call_count == 2
    refresh.assert_called_once()
    browser.assert_not_called()

    second_call = request.call_args_list[1]
    assert (
        second_call.kwargs["headers"]["Authorization"]
        == "Bearer new-access"
    )


def test_broken_cache_returns_error_without_network_request():
    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch(
            "notion_api.oauth.load_tokens",
            side_effect=RuntimeError("Invalid cache"),
        ),
        patch("notion_api.httpx.request") as request,
    ):
        client = NotionAPIClient()
        result = client.request("GET", "/pages/example")

    assert result["error"]["code"] == "TOKEN_CACHE_ERROR"
    request.assert_not_called()