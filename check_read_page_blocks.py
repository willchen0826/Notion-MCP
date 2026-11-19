import argparse
import json

from notion_api import NotionAPIClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read a Notion page's block content as shaped text, "
            "with bounded depth, requests, and output size."
        )
    )
    parser.add_argument(
        "page_id",
        help="A real page ID returned by search_pages().",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum recorded block depth; direct children have depth 0.",
    )
    parser.add_argument(
        "--max-request-calls",
        type=int,
        default=20,
        help="Maximum number of get_block_children() calls.",
    )
    parser.add_argument(
        "--max-blocks",
        type=int,
        default=500,
        help="Maximum number of blocks kept in the output.",
    )
    parser.add_argument(
        "--max-characters",
        type=int,
        default=20000,
        help="Maximum total characters across all emitted text.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Maximum number of blocks requested per batch.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full shaped result as JSON.",
    )
    args = parser.parse_args()

    print("INFO: Creating Notion API client", flush=True)
    client = NotionAPIClient()

    print("INFO: Calling read_page_blocks()", flush=True)
    result = client.read_page_blocks(
        args.page_id,
        max_depth=args.max_depth,
        max_request_calls=args.max_request_calls,
        max_blocks=args.max_blocks,
        max_characters=args.max_characters,
        page_size=args.page_size,
    )

    if "error" in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("FAIL: read_page_blocks() failed")
        raise SystemExit(1)

    print(f"INFO: Blocks in output: {len(result['blocks'])}")
    print(f"INFO: Request calls: {result['request_calls']}")
    print(f"INFO: Complete: {result['complete']}")

    for index, entry in enumerate(result["blocks"]):
        indent = "  " * entry["depth"]
        text = entry["text"]
        shown_text = "<no text extracted>" if text is None else text

        print(
            f"{indent}[{index}] type={entry['type']} "
            f"depth={entry['depth']} id={entry['id']} "
            f"parent_id={entry['parent_id']}"
        )
        print(f"{indent}    {shown_text}")

    print("INFO: Partial flags:")
    print(json.dumps(result["partial"], indent=2))

    print("INFO: Unsupported block types:")
    print(json.dumps(result["unsupported_block_types"], indent=2))

    print("INFO: Warnings:")
    print(json.dumps(result["warnings"], indent=2, ensure_ascii=False))

    if args.json:
        print("INFO: Full result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result["complete"]:
        print("WARNING: Read returned partial content")
        raise SystemExit(2)

    print("PASS: Page content read completely")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nINFO: Check cancelled")
        raise SystemExit(130)
