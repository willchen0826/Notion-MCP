import argparse
import json

from notion_api import NotionAPIClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search Notion pages by title."
    )
    parser.add_argument("query")
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--cursor", default=None)

    args = parser.parse_args()

    client = NotionAPIClient()

    result = client.search_pages(
        query=args.query,
        page_size=args.page_size,
        start_cursor=args.cursor,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if "error" in result:
        raise SystemExit(1)

    print("PASS: Page search succeeded")
    print(f"INFO: Pages returned: {len(result['pages'])}")
    print(f"INFO: More results available: {result['has_more']}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError):
        print("ERROR: Check OAuth configuration and local file permissions")
        raise SystemExit(1)