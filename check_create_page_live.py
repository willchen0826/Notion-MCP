import argparse
import json
from uuid import UUID

from notion_api import NotionAPIClient


# Fixed so the preview and the live write always agree. The body has
# exactly three lines when split on "\n": a sentence, a blank line,
# and an indented line -- used below to check that get_page_content()
# reads back the same three paragraphs, blank line and indentation
# included.
TITLE = "W2 MCP round-trip check"
CONTENT = "Review OAuth.\n\n    Check token refresh."


def _verify_read_back(client, page_id, expected_title, expected_paragraphs):
    """Read page_id back and check it matches what was sent.

    Used both right after a live create_page() call and, via
    --verify-id, to retry only this read without creating another
    page.
    """
    print(f"INFO: Reading back page_id={page_id} with get_page_content()")
    read_back = client.get_page_content(page_id)

    if "error" in read_back:
        print("FAIL: Could not read the page back.")
        print(json.dumps(read_back["error"], indent=2, ensure_ascii=False))
        return False

    try:
        id_matches = UUID(read_back["page"]["id"]) == UUID(page_id)
    except (KeyError, TypeError, ValueError):
        id_matches = False

    actual_paragraphs = [block["text"] for block in read_back["blocks"]]

    checks = {
        "Read is complete": read_back["complete"] is True,
        "Returned page ID matches": id_matches,
        "Title matches": read_back["page"]["title"] == expected_title,
        "Exactly three top-level paragraphs": (
            len(actual_paragraphs) == 3
        ),
        "Paragraph texts match (blank line and indentation preserved)": (
            actual_paragraphs == expected_paragraphs
        ),
    }

    for description, passed in checks.items():
        label = "PASS" if passed else "FAIL"
        print(f"{label}: {description}")

    if not all(checks.values()):
        print(f"INFO: Expected paragraphs: {expected_paragraphs!r}")
        print(f"INFO: Actual paragraphs: {actual_paragraphs!r}")
        if not read_back.get("complete"):
            print(
                json.dumps(
                    read_back.get("partial"), indent=2, ensure_ascii=False
                )
            )
        return False

    print("PASS: Read-back matched the original inputs.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview, and optionally create and read back, a live "
            "Notion child page to check Phase 2.4.3 (create_page() + "
            "get_page_content())."
        )
    )
    parser.add_argument("parent_page_id", help="Existing parent page ID")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--create",
        action="store_true",
        help=(
            "After a successful preview, actually create the page and "
            "read it back. Without this flag (and without --verify-id), "
            "only the local preview is shown and nothing is written to "
            "Notion."
        ),
    )
    mode.add_argument(
        "--verify-id",
        metavar="NEW_PAGE_ID",
        default=None,
        help=(
            "Skip preview and creation; only read back an already-"
            "created page by ID. Use this to retry a failed read-back "
            "without creating another page."
        ),
    )

    args = parser.parse_args()
    client = NotionAPIClient()
    expected_paragraphs = CONTENT.split("\n")

    if args.verify_id:
        print(f"INFO: Verifying existing page_id={args.verify_id}")
        ok = _verify_read_back(
            client, args.verify_id, TITLE, expected_paragraphs
        )
        return 0 if ok else 1

    print("INFO: Calling create_page() with dry_run=True (preview)")
    preview = client.create_page(
        args.parent_page_id, TITLE, CONTENT, dry_run=True
    )
    print(f"INFO: parent_page_id={args.parent_page_id!r}")
    print(f"INFO: title={TITLE!r}")
    print(f"INFO: body={CONTENT!r}")
    print(json.dumps(preview, indent=2, ensure_ascii=False))

    if "error" in preview:
        print("FAIL: Preview failed.")
        print(json.dumps(preview["error"], indent=2, ensure_ascii=False))
        return 1

    print("PASS: Preview succeeded.")

    if not args.create:
        print("INFO: --create not given. Exiting after preview.")
        return 0

    print("INFO: Calling create_page() with dry_run=False (live write)")
    created = client.create_page(
        args.parent_page_id, TITLE, CONTENT, dry_run=False
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
    new_page_id = new_page["id"]
    print(f"PASS: Page created. id={new_page_id}")
    print(f"PASS: New page URL: {new_page['url']}")

    ok = _verify_read_back(client, new_page_id, TITLE, expected_paragraphs)

    if not ok:
        print(
            f"ACTION: The page was created (id={new_page_id}, "
            f"url={new_page['url']}) but the read-back above failed. "
            "Retry only the read with: python check_create_page_live.py "
            f"{args.parent_page_id} --verify-id {new_page_id}. Do not "
            "create another page."
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
