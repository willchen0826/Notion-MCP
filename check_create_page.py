import json
from unittest.mock import patch

from notion_api import NotionAPIClient


PARENT_ID = "11111111-1111-1111-1111-111111111111"
NEW_PAGE_ID = "22222222-2222-2222-2222-222222222222"
TITLE = "Week 2 notes"
CONTENT = "Review OAuth.\n\n    Check token refresh."
PAGE_URL = f"https://example.com/pages/{NEW_PAGE_ID}"


def show(label, value):
    print(label)
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main():
    # Simulate a successful response from the shared request layer.
    mock_response = {
        "ok": True,
        "data": {
            "object": "page",
            "id": NEW_PAGE_ID,
            "url": PAGE_URL,
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": TITLE}],
                }
            },
        },
    }

    with (
        patch("notion_api.oauth.load_oauth_config", return_value={}),
        patch.object(
            NotionAPIClient, "request", return_value=mock_response
        ) as request,
    ):
        client = NotionAPIClient()

        # Check 1: omit dry_run to exercise the default.
        preview = client.create_page(PARENT_ID, TITLE, CONTENT)
        show("1. Local preview", preview)

        request.assert_not_called()
        assert preview == {
            "ok": True,
            "dry_run": True,
            "created": False,
            "preview": {
                "parent_page_id": PARENT_ID,
                "title": TITLE,
                "content": CONTENT,
            },
        }
        print("PASS: Preview preserved the inputs and made zero requests.")

        # Check 2: run the write branch with the request layer mocked.
        result = client.create_page(PARENT_ID, TITLE, CONTENT, dry_run=False)

        request.assert_called_once()
        call = request.call_args
        assert call.args == ("POST", "/pages")
        assert call.kwargs["read_only"] is False

        payload = call.kwargs["json_body"]
        show("\n2. Payload prepared for POST /pages", payload)

        assert payload["parent"]["page_id"] == PARENT_ID
        title_parts = payload["properties"]["title"]["title"]
        assert "".join(part["text"]["content"] for part in title_parts) == TITLE

        # Rebuild each line from its paragraph, including the empty line.
        lines = []
        for block in payload["children"]:
            assert block["type"] == "paragraph"
            parts = block["paragraph"]["rich_text"]
            line = "".join(part["text"]["content"] for part in parts)
            lines.append(line)

        assert "\n".join(lines) == CONTENT
        print("PASS: The payload preserved the title, blank line, and indentation.")

        show("\n3. Result returned by create_page()", result)
        assert result == {
            "ok": True,
            "dry_run": False,
            "created": True,
            "page": {
                "id": NEW_PAGE_ID,
                "title": TITLE,
                "url": PAGE_URL,
            },
        }
        print("PASS: The result contains the new page ID and URL.")
        print("INFO: The request was mocked. No Notion page was created.")


if __name__ == "__main__":
    main()