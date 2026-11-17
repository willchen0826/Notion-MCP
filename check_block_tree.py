import argparse
import json

from notion_api import NotionAPIClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a bounded traversal of a Notion block tree."
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
        "--page-size",
        type=int,
        default=100,
        help="Maximum number of blocks requested per batch.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full traversal result, including raw block data.",
    )
    args = parser.parse_args()

    print("INFO: Creating Notion API client", flush=True)
    client = NotionAPIClient()

    print("INFO: Starting bounded block-tree traversal", flush=True)
    result = client._walk_block_tree(
        args.page_id,
        max_depth=args.max_depth,
        max_request_calls=args.max_request_calls,
        page_size=args.page_size,
    )

    if "error" in result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("FAIL: Block-tree traversal failed")
        raise SystemExit(1)

    print(f"INFO: Blocks recorded: {len(result['blocks'])}")
    print(f"INFO: Request calls: {result['request_calls']}")
    print(f"INFO: Traversal complete: {result['complete']}")

    for index, entry in enumerate(result["blocks"]):
        block = entry["block"]
        depth = entry["depth"]
        indent = "  " * depth

        print(
            f"{indent}[{index}] "
            f"type={block['type']} "
            f"depth={depth} "
            f"has_children={block['has_children']}"
        )
        print(f"{indent}    id={block['id']}")
        print(f"{indent}    parent_id={entry['parent_id']}")

    print("INFO: Partial flags:")
    print(json.dumps(result["partial"], indent=2))

    print("INFO: Warnings:")
    print(json.dumps(result["warnings"], indent=2, ensure_ascii=False))

    if args.json:
        print("INFO: Full traversal result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result["complete"]:
        print("WARNING: Traversal returned partial results")
        raise SystemExit(2)

    print("PASS: Block-tree traversal completed")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nINFO: Check cancelled")
        raise SystemExit(130)