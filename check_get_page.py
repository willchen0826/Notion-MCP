import argparse
import json

from notion_api import NotionAPIClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve metadata for a Notion page."
    )
    parser.add_argument(
        "page_id",
        help="A real page ID returned by search_pages().",
    )
    args = parser.parse_args()

    print("INFO: Creating Notion API client", flush=True)
    client = NotionAPIClient()

    print("INFO: Calling get_page()", flush=True)
    result = client.get_page(args.page_id)

    print("\nINFO: Final result returned by get_page():")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if "error" in result:
        print("FAIL: Page metadata retrieval failed")
        raise SystemExit(1)

    print("PASS: Page metadata retrieved")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)