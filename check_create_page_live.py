import argparse
import json

from notion_api import NotionAPIClient


# Clearly identifiable so a stray run is easy to recognize and delete
# in Notion. The exact same title/content are used for the preview
# and, with --create, for the real write -- the preview is only
# meaningful as a rehearsal of this phase's actual check if both use
# identical inputs.
TEST_TITLE = "W2 MCP Live Check -- Phase 2.4.3 (safe to delete)"
TEST_CONTENT = (
    "This page was created by check_create_page_live.py (Phase 2.4.3).\n"
    "\n"
    "    This line is indented to check whitespace preservation."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview a child page, and optionally create it live and "
            "read it back, to check Phase 2.4.3 (create_page() + "
            "get_page_content())."
        )
    )
    parser.add_argument("parent_page_id", help="Existing parent page ID")
    parser.add_argument(
        "--create",
        action="store_true",
        help=(
            "Actually create the page and read it back. Without this "
            "flag, only the local preview is shown and nothing is "
            "written to Notion."
        ),
    )
    args = parser.parse_args()

    client = NotionAPIClient()

    print("INFO: Calling create_page() with dry_run=True (preview)")
    preview = client.create_page(
        args.parent_page_id,
        TEST_TITLE,
        TEST_CONTENT,
        dry_run=True,
    )
    print(json.dumps(preview, indent=2, ensure_ascii=False))

    if "error" in preview:
        print("FAIL: Preview failed. Stopping before any write.")
        return 1

    print("PASS: Preview succeeded.")

    if not args.create:
        print("INFO: --create not given. Exiting after preview.")
        return 0

    print("INFO: Calling create_page() with dry_run=False (live write)")
    created = client.create_page(
        args.parent_page_id,
        TEST_TITLE,
        TEST_CONTENT,
        dry_run=False,
    )

    if "error" in created:
        print("FAIL: Page creation failed.")
        print(json.dumps(created["error"], indent=2, ensure_ascii=False))
        print(
            "ACTION: Follow the suggested_action above. No page was "
            "confirmed created; do not retry by creating another page "
            "without investigating first."
        )
        return 1

    new_page = created["page"]
    print(f"PASS: Page created. id={new_page['id']}")
    print(f"PASS: New page URL: {new_page['url']}")

    print("INFO: Reading the new page back with get_page_content()")
    read_back = client.get_page_content(new_page["id"])

    if "error" in read_back:
        print("FAIL: Could not read the new page back.")
        print(json.dumps(read_back["error"], indent=2, ensure_ascii=False))
        print(
            f"ACTION: The page was created (id={new_page['id']}, "
            f"url={new_page['url']}) but could not be read back. "
            "Inspect it manually in Notion. Do not create another page."
        )
        return 1

    if not read_back["complete"]:
        print("FAIL: Read-back was incomplete (complete=False).")
        print(
            json.dumps(read_back["partial"], indent=2, ensure_ascii=False)
        )
        print(
            f"ACTION: The page was created (id={new_page['id']}, "
            f"url={new_page['url']}) but the body read did not finish. "
            "Inspect it manually. Do not create another page."
        )
        return 1

    expected_paragraphs = TEST_CONTENT.split("\n")
    actual_paragraphs = [block["text"] for block in read_back["blocks"]]

    checks = {
        "Title matches": read_back["page"]["title"] == TEST_TITLE,
        "Paragraph count matches": (
            len(actual_paragraphs) == len(expected_paragraphs)
        ),
        "Paragraph texts match, including the blank and indented line": (
            actual_paragraphs == expected_paragraphs
        ),
    }

    for description, passed in checks.items():
        label = "PASS" if passed else "FAIL"
        print(f"{label}: {description}")

    if not all(checks.values()):
        print(f"INFO: Expected paragraphs: {expected_paragraphs}")
        print(f"INFO: Actual paragraphs: {actual_paragraphs}")
        print(
            f"ACTION: The page was created (id={new_page['id']}, "
            f"url={new_page['url']}) but its content did not match "
            "what was sent. Inspect it manually. Do not create another "
            "page."
        )
        return 1

    print("PASS: Live create-and-read-back check succeeded.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
