import re
from typing import Any

import httpx

import oauth

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2026-03-11"



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