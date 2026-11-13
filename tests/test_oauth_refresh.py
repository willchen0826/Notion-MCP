from unittest.mock import patch

import httpx

from oauth import verify_api_access


CONFIG = {
    "NOTION_CLIENT_ID": "test-client",
    "NOTION_CLIENT_SECRET": "test-secret",
}

OLD_TOKENS = {
    "access_token": "old-access",
    "refresh_token": "old-refresh",
}

NEW_TOKENS = {
    "access_token": "new-access",
    "refresh_token": "new-refresh",
}


def test_401_refreshes_saves_and_retries():
    with (
        patch(
            "oauth.load_tokens",
            side_effect=[OLD_TOKENS, OLD_TOKENS, NEW_TOKENS],
        ),
        patch("oauth.save_tokens") as save,
        patch("oauth.webbrowser.open") as browser,
        patch(
            "oauth.httpx.post",
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json=NEW_TOKENS),
                httpx.Response(200, json={"results": []}),
            ],
        ) as post,
    ):
        result = verify_api_access(CONFIG)

    assert result["ok"] is True
    assert result["refreshed"] is True
    save.assert_called_once_with(NEW_TOKENS)
    browser.assert_not_called()

    calls = post.call_args_list
    assert calls[1].kwargs["json"]["grant_type"] == "refresh_token"
    assert calls[2].kwargs["headers"]["Authorization"] == "Bearer new-access"


def test_rejected_refresh_returns_error_without_browser():
    with (
        patch("oauth.load_tokens", return_value=OLD_TOKENS),
        patch("oauth.save_tokens") as save,
        patch("oauth.webbrowser.open") as browser,
        patch(
            "oauth.httpx.post",
            side_effect=[
                httpx.Response(401),
                httpx.Response(400, json={"error": "invalid_grant"}),
            ],
        ),
    ):
        result = verify_api_access(CONFIG)

    assert result["error"]["code"] == "REFRESH_REJECTED"
    assert result["error"]["retryable"] is False
    assert "login" in result["error"]["suggested_action"]
    save.assert_not_called()
    browser.assert_not_called()