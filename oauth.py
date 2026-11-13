import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
import argparse
import json
import tempfile

import httpx
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"
TOKEN_DIR = PROJECT_DIR / ".tokens"
TOKEN_PATH = TOKEN_DIR / "notion.json"


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

def validate_tokens(tokens: object) -> dict:
    """Validate the token structure without exposing credentials."""
    if not isinstance(tokens, dict):
        raise ValueError("Token data must be a JSON object.")

    for key in ("access_token", "refresh_token"):
        value = tokens.get(key)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Token data is missing a valid {key}.")

    return tokens


def save_tokens(tokens: dict) -> None:
    """Save tokens using a private temporary file and atomic replacement."""
    validated_tokens = validate_tokens(tokens)

    TOKEN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    TOKEN_DIR.chmod(0o700)

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=TOKEN_DIR,
            prefix=".notion-",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            os.fchmod(file.fileno(), 0o600)

            json.dump(validated_tokens, file, indent=2)
            file.write("\n")

            file.flush()
            os.fsync(file.fileno())

        os.replace(temp_path, TOKEN_PATH)

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

# 这个函数可能返回： - dict：缓存存在且结构检查通过。 - None：没有缓存。
def load_tokens() -> dict | None:
    """Load cached tokens without starting browser authorization."""
    try:
        with TOKEN_PATH.open("r", encoding="utf-8") as file:
            tokens = json.load(file)

    except FileNotFoundError:
        return None

    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError(
            "Token cache is unreadable. Run 'python oauth.py login' "
            "to authorize again."
        ) from None

    try:
        return validate_tokens(tokens)

    except ValueError:
        raise RuntimeError(
            "Token cache has an invalid structure. "
            "Run 'python oauth.py login' to authorize again."
        ) from None

def error_result(
    code: str,
    message: str,
    retryable: bool,
    suggested_action: str,
) -> dict:
    """Build an actionable error without exposing credentials."""
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "suggested_action": suggested_action,
        }
    }

def refresh_cached_tokens(config: dict[str, str]) -> dict:
    """Refresh cached tokens and persist the new token pair."""
    tokens = load_tokens()

    if tokens is None:
        return error_result(
            "AUTH_REQUIRED",
            "No cached credentials were found.",
            False,
            "Run python oauth.py login.",
        )

    try:
        response = httpx.post(
            "https://api.notion.com/v1/oauth/token",
            auth=httpx.BasicAuth(
                config["NOTION_CLIENT_ID"],
                config["NOTION_CLIENT_SECRET"],
            ),
            headers={"Accept": "application/json"},
            json={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
            },
            timeout=20.0,
            follow_redirects=False,
        )
    except httpx.RequestError:
        return error_result(
            "REFRESH_NETWORK_ERROR",
            "The token refresh request could not be completed.",
            False,
            "Check connectivity. The refresh outcome may be unknown; "
            "if credentials no longer work, run python oauth.py login.",
        )

    if response.status_code != 200:
        if response.status_code == 429 or response.status_code >= 500:
            return error_result(
                "REFRESH_UNAVAILABLE",
                f"Token refresh returned HTTP {response.status_code}.",
                True,
                "Wait before retrying. Respect Retry-After if provided.",
            )

        return error_result(
            "REFRESH_REJECTED",
            f"Token refresh returned HTTP {response.status_code}.",
            False,
            "Check the app credentials, then run python oauth.py login.",
        )

    try:
        new_tokens = validate_tokens(response.json())
    except ValueError:
        return error_result(
            "INVALID_REFRESH_RESPONSE",
            "Notion did not return a valid token pair.",
            False,
            "Run python oauth.py login to obtain fresh credentials.",
        )

    try:
        save_tokens(new_tokens)
    except OSError:
        return error_result(
            "TOKEN_SAVE_FAILED",
            "New credentials were received but could not be saved.",
            False,
            "Fix cache directory permissions or disk space, "
            "then run python oauth.py login.",
        )

    return {"ok": True}


def verify_api_access(config: dict[str, str]) -> dict:
    """Check API access and refresh once if Notion returns HTTP 401."""
    refreshed = False

    for attempt in range(2):
        tokens = load_tokens()

        if tokens is None:
            return error_result(
                "AUTH_REQUIRED",
                "No cached credentials were found.",
                False,
                "Run python oauth.py login.",
            )

        try:
            response = httpx.post(
                "https://api.notion.com/v1/search",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "Notion-Version": "2026-03-11",
                },
                json={"page_size": 1},
                timeout=20.0,
                follow_redirects=False,
            )
        except httpx.RequestError:
            return error_result(
                "API_NETWORK_ERROR",
                "The read-only API request could not be completed.",
                True,
                "Check connectivity and retry.",
            )

        if response.status_code == 401:
            if attempt == 1:
                return error_result(
                    "AUTH_REQUIRED",
                    "Notion rejected the refreshed access token.",
                    False,
                    "Run python oauth.py login.",
                )

            refresh_result = refresh_cached_tokens(config)

            if "error" in refresh_result:
                return refresh_result

            refreshed = True
            continue

        if response.status_code != 200:
            retryable = (
                response.status_code == 429
                or response.status_code >= 500
            )
            return error_result(
                "API_REQUEST_FAILED",
                f"Notion returned HTTP {response.status_code}.",
                retryable,
                "Wait before retrying if rate limited or unavailable; "
                "otherwise check request parameters and capabilities.",
            )

        try:
            data = response.json()
        except ValueError:
            return error_result(
                "INVALID_API_RESPONSE",
                "Notion returned invalid JSON.",
                True,
                "Retry the read-only request later.",
            )

        if not isinstance(data, dict) or not isinstance(
            data.get("results"), list
        ):
            return error_result(
                "INVALID_API_RESPONSE",
                "Notion returned an unexpected search response.",
                False,
                "Check the API response contract.",
            )

        return {
            "ok": True,
            "refreshed": refreshed,
            "result_count": len(data["results"]),
        }

    raise RuntimeError("Unexpected end of API verification.")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manage local Notion OAuth credentials."
    )
    parser.add_argument(
        "command",
        choices=("login", "status", "verify", "refresh"),
        help="Authorize with Notion or inspect the local token cache.",
    )
    args = parser.parse_args()

    try:
        if args.command == "login":
            config = load_oauth_config()
            state = secrets.token_urlsafe(32)
            authorization_url = build_authorization_url(config, state)

            print("PASS: OAuth configuration loaded")

            code = receive_authorization_code(
                authorization_url,
                state,
            )
            print("PASS: Authorization code received and state verified")

            tokens = exchange_code_for_tokens(config, code)
            save_tokens(tokens)

            print("PASS: Access token and refresh token obtained")
            print("PASS: OAuth tokens saved")
            print("INFO: API access and token refresh are not verified yet")

        elif args.command == "status":
            tokens = load_tokens()

            if tokens is None:
                print("INFO: No token cache found")
                print("ACTION: Run 'python oauth.py login'")
                raise SystemExit(1)

            print("PASS: Token cache loaded")
            print("PASS: Access token is present")
            print("PASS: Refresh token is present")
            print("INFO: No browser authorization was started")
            print("INFO: Token validity has not been checked with Notion")
            
        elif args.command in ("verify", "refresh"):
            config = load_oauth_config()

            if args.command == "refresh":
                result = refresh_cached_tokens(config)
            else:
                result = verify_api_access(config)

            print(json.dumps(result, indent=2))

            if "error" in result:
                raise SystemExit(1)

    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

    except KeyboardInterrupt:
        print("\nINFO: Login cancelled")
        raise SystemExit(130)