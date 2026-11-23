import argparse
import json
from uuid import UUID

from notion_api import NotionAPIClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the combined metadata and content of the W2 test page."
    )
    parser.add_argument("page_id", help="The Notion page ID")
    args = parser.parse_args()

    print("INFO: Calling get_page_content()", flush=True)

    client = NotionAPIClient()
    result = client.get_page_content(
        args.page_id,
        max_depth=1,
        max_blocks=6,
        page_size=2,
    )

    if "error" in result:
        print("FAIL: Could not read the page")
        print(json.dumps(result["error"], indent=2, ensure_ascii=False))
        return 1

    page = result["page"]
    blocks = result["blocks"]
    partial = result["partial"]

    print(f"INFO: Page title: {page['title']}")
    print(f"INFO: Page URL: {page['url']}")
    print(f"INFO: Blocks returned: {len(blocks)}")
    print(f"INFO: Child-block calls: {result['request_calls']}")
    print(f"INFO: Complete: {result['complete']}")
    print("INFO: Partial flags:")
    print(json.dumps(partial, indent=2))

    for index, block in enumerate(blocks):
        text = block["text"]
        if text is None:
            text = "<no text extracted>"
        elif text == "":
            text = "<empty>"
        print(f"[{index}] {block['type']} (depth {block['depth']}): {text}")

    expected_types = [
        "heading_3",
        "table",
        "table_row",
        "table_row",
        "table_row",
        "table_row",
    ]

    checks = {
        "Metadata identifies the W2 test page": (
            UUID(page["id"]) == UUID(args.page_id)
            and page["title"] == "W2 - New MCP"
            and bool(page["url"])
        ),
        "The first six blocks match the W2 page layout": (
            [block["type"] for block in blocks] == expected_types
        ),
        "The body includes the heading and the table header": (
            len(blocks) >= 3
            and blocks[0]["text"] == "三个 Notion Tools"
            and blocks[2]["text"] == "Tool | 类型 | 作用"
        ),
        "The result reports a partial read caused by the block limit": (
            result["ok"] is True
            and result["complete"] is False
            and partial["max_blocks_reached"] is True
        ),
    }

    for description, passed in checks.items():
        label = "PASS" if passed else "FAIL"
        print(f"{label}: {description}")

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)