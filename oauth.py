import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"


def load_oauth_config() -> dict[str, str]:
    """Load and validate the local Notion OAuth configuration."""
    if not ENV_PATH.is_file():
        raise ValueError(f"Can't find the env file: {ENV_PATH}")

    load_dotenv(ENV_PATH)

    config: dict[str, str] = {}

    required_keys = (
        "NOTION_CLIENT_ID",
        "NOTION_CLIENT_SECRET",
        "NOTION_REDIRECT_URI",
    )

    for key in required_keys:
        value = os.getenv(key, "").strip()

        if not value or value.startswith("replace_"):
            raise ValueError(f"Missing {key} in .env file, please add it.")

        config[key] = value

    if config["NOTION_REDIRECT_URI"] != "http://localhost:8765/callback":
        raise ValueError("NOTION_REDIRECT_URI must match the URI registered in Notion.")

    return config


def build_authorization_url(
    config: dict[str, str],
    state: str,
) -> str:
    """Build the Notion OAuth authorization URL."""
    params = {
        "client_id": config["NOTION_CLIENT_ID"],
        "redirect_uri": config["NOTION_REDIRECT_URI"],
        "response_type": "code",
        "owner": "user",
        "state": state,
    }

    query_string = urlencode(params)

    return f"https://api.notion.com/v1/oauth/authorize?{query_string}"


def exchange_code_for_tokens(
    config: dict[str, str],
    code: str,
) -> dict:
    """Exchange an authorization code for Notion OAuth tokens."""
    try:
        response = httpx.post(
            "https://api.notion.com/v1/oauth/token",
            auth=httpx.BasicAuth(
                config["NOTION_CLIENT_ID"],
                config["NOTION_CLIENT_SECRET"],
            ),
            headers={
                "Accept": "application/json",
                "Notion-Version": "2026-03-11",
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config["NOTION_REDIRECT_URI"],
            },
            timeout=20.0,
            follow_redirects=False,
        )
    except httpx.RequestError:
        raise RuntimeError(
            "Could not complete the token request. "
            "Check your connection and restart the login flow."
        ) from None

    if response.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed with HTTP {response.status_code}. "
            "Check your app credentials and redirect URI, "
            "then restart the login flow."
        )

    try:
        tokens = response.json()
    except ValueError:
        raise RuntimeError("Notion returned an invalid JSON response.") from None

    if not isinstance(tokens, dict):
        raise RuntimeError("Notion returned an unexpected token response.")

    access_token = tokens.get("access_token")

    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Notion did not return a valid access token.")

    return tokens


def receive_authorization_code(
    authorization_url: str,
    expected_state: str,
    timeout_seconds: int = 180,
) -> str:
    """Open the browser and receive a validated OAuth authorization code."""
    result: dict[str, str] = {}

    # 创建一个类，继承 Python 提供的 HTTP 请求处理功能。
    class CallbackHandler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format: str, *args) -> None:
            # Avoid logging callback URLs containing authorization codes.
            return

        def reply(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed_url = urlsplit(self.path)

            if parsed_url.path != "/callback":
                self.reply(404, "Not found.")
                return

            params = parse_qs(parsed_url.query, keep_blank_values=True)
            states = params.get("state", [])

            if (
                len(states) != 1
                or not secrets.compare_digest(
                    states[0].encode("utf-8"),
                    expected_state.encode("utf-8"),
                )
            ):
                result["error"] = (
                    "OAuth state validation failed. Restart the login flow."
                )
                self.reply(400, "Invalid OAuth state. Return to the terminal.")
                return

            if "error" in params:
                result["error"] = (
                    "Notion authorization was denied or failed. "
                    "Restart the login flow when ready."
                )
                self.reply(400, "Authorization failed. Return to the terminal.")
                return

            codes = params.get("code", [])

            if len(codes) != 1 or not codes[0]:
                result["error"] = "The callback did not contain a valid code."
                self.reply(400, "Missing authorization code.")
                return

            result["code"] = codes[0]
            self.reply(
                200,
                "Authorization code received. "
                "Return to the terminal to check the token exchange result.",
            )

    # 这里的 127.0.0.1 是程序监听地址，后台注册的 Redirect URI 仍然保持 http://localhost:8765/callback
    with HTTPServer(("127.0.0.1", 8765), CallbackHandler) as server:
        server.timeout = 1
        deadline = time.monotonic() + timeout_seconds

        print("INFO: Callback server is listening on localhost:8765")
        print("INFO: Opening the Notion authorization page")

        if not webbrowser.open(authorization_url):
            raise RuntimeError(
                "Could not open the browser. Check your default browser "
                "and restart the login flow."
            )

        while not result and time.monotonic() < deadline:
            server.handle_request()

    if "error" in result:
        raise RuntimeError(result["error"])

    if "code" not in result:
        raise TimeoutError("Authorization timed out. Restart the login flow.")
    return result["code"]

if __name__ == "__main__":
    try:
        config = load_oauth_config()
        state = secrets.token_urlsafe(32)
        authorization_url = build_authorization_url(config, state)

        print("PASS: OAuth configuration loaded")

        code = receive_authorization_code(authorization_url, state)
        print("PASS: Authorization code received and state verified")

        tokens = exchange_code_for_tokens(config, code)
        print("in running phase, the tokens is:   ")
        print("PASS: Access token obtained")

        refresh_token = tokens.get("refresh_token")

        if isinstance(refresh_token, str) and refresh_token:
            print("PASS: Refresh token obtained")
        else:
            print("WARNING: No usable refresh token was returned")

        print("INFO: Tokens are currently stored in memory only")
        print("INFO: Token caching and refresh are not implemented yet")

    except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

    except KeyboardInterrupt:
        print("\nINFO: Login cancelled")
        raise SystemExit(130)