import argparse
import json
from notion_api import NotionAPIClient

def main() -> None:
    parser = argparse.ArgumentParser(
        description = "Read one batch of Notion child blocks."
    )
    parser.add_argument(
        "block_id",
        help="A real page ID or block ID accessible to your connection", 
    )
    parser.add_argument(
        "--cursor",
        default=None,
        help="The next_cursor returned by a previous request."
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=2,
    )
    args = parser.parse_args()
    
    client = NotionAPIClient()
    
    result = client.get_block_children(
        block_id=args.block_id,
        page_size = args.page_size,
        start_cursor = args.cursor,
    )
    
    print("INFO: get_block_children() returned: ")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if "error" in result:
        print("FAIL: Could not retrieve child blocks")
        raise SystemExit(1)
    
    print("PASS: Child blocks retrieved")
    print(f"INFO: Block returned: {len(result['results'])}")
    print(f"INFO: More batches available: {result['has_more']}")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)