from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from notion_api import NotionAPIClient


PAGE_ID = "11111111-1111-1111-1111-111111111111"


def block(block_id, block_type, has_children=False, **type_data):
    data = {
        "object": "block",
        "id": block_id,
        "type": block_type,
        "has_children": has_children,
    }
    if type_data:
        data[block_type] = type_data
    return data


def rich(*texts):
    return [{"plain_text": text} for text in texts]


def batch(results, has_more=False, next_cursor=None):
    return {
        "ok": True,
        "results": results,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def error(code, message="A request error.", retryable=False, **extra):
    err = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "suggested_action": "See the error code.",
    }
    err.update(extra)
    return {"error": err}


@contextmanager
def patched_client(responses, calls):
    def fake_get_block_children(
        block_id, page_size=100, start_cursor=None
    ):
        calls.append((block_id, start_cursor))
        return responses[(block_id, start_cursor)]

    with ExitStack() as stack:
        stack.enter_context(
            patch("notion_api.oauth.load_oauth_config", return_value={})
        )
        stack.enter_context(
            patch.object(
                NotionAPIClient,
                "get_block_children",
                side_effect=fake_get_block_children,
            )
        )
        yield


def test_multiple_rich_text_fragments_and_unicode():
    calls = []
    paragraph = block(
        "p-1",
        "paragraph",
        rich_text=rich("Café ", "notes — ", "日本語"),
    )
    responses = {(PAGE_ID, None): batch([paragraph])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    assert result["blocks"] == [
        {
            "id": "p-1",
            "parent_id": PAGE_ID,
            "type": "paragraph",
            "depth": 0,
            "text": "Café notes — 日本語",
        }
    ]
    assert result["complete"] is True
    assert result["unsupported_block_types"] == []


def test_nested_text_preserves_traversal_order():
    calls = []
    toggle = block(
        "toggle-1", "toggle", has_children=True, rich_text=rich("Outer")
    )
    nested = block("nested-1", "paragraph", rich_text=rich("Inner"))
    para = block("p-1", "paragraph", rich_text=rich("After"))

    responses = {
        (PAGE_ID, None): batch([toggle, para]),
        ("toggle-1", None): batch([nested]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    assert [e["text"] for e in result["blocks"]] == [
        "Outer",
        "Inner",
        "After",
    ]
    assert [e["depth"] for e in result["blocks"]] == [0, 1, 0]
    assert [e["parent_id"] for e in result["blocks"]] == [
        PAGE_ID,
        "toggle-1",
        PAGE_ID,
    ]
    assert result["complete"] is True


def test_table_rows_and_structural_containers():
    calls = []
    table = block("table-1", "table", has_children=True)
    row1 = block("row-1", "table_row", cells=[rich("A1"), rich("B1")])
    row2 = block("row-2", "table_row", cells=[rich("A2"), rich("B2")])

    responses = {
        (PAGE_ID, None): batch([table]),
        ("table-1", None): batch([row1, row2]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    assert [e["text"] for e in result["blocks"]] == [
        "",
        "A1 | B1",
        "A2 | B2",
    ]
    assert result["unsupported_block_types"] == []
    assert result["complete"] is True


def test_empty_text_code_line_breaks_and_todo_state():
    calls = []
    empty_paragraph = block("p-1", "paragraph", rich_text=[])
    code = block(
        "code-1",
        "code",
        rich_text=rich("line one\nline two"),
        language="python",
    )
    todo_done = block(
        "todo-1", "to_do", rich_text=rich("Buy milk"), checked=True
    )
    todo_open = block(
        "todo-2", "to_do", rich_text=rich("Walk dog"), checked=False
    )

    responses = {
        (PAGE_ID, None): batch(
            [empty_paragraph, code, todo_done, todo_open]
        ),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    texts = [e["text"] for e in result["blocks"]]
    assert texts == [
        "",
        "line one\nline two",
        "[x] Buy milk",
        "[ ] Walk dog",
    ]
    assert result["unsupported_block_types"] == []
    assert result["complete"] is True


def test_unsupported_block_is_reported_not_crashed():
    calls = []
    image = block("img-1", "image")
    para = block("p-1", "paragraph", rich_text=rich("Hello"))

    responses = {(PAGE_ID, None): batch([image, para])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    assert [e["text"] for e in result["blocks"]] == [None, "Hello"]
    assert result["unsupported_block_types"] == ["image"]
    assert result["complete"] is False


def test_child_page_and_child_database_report_title_text():
    calls = []
    child_page = block(
        "cp-1", "child_page", has_children=True, title="Nested Page"
    )
    child_db = block("cd-1", "child_database", title="Tracker")

    responses = {(PAGE_ID, None): batch([child_page, child_db])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    assert [e["text"] for e in result["blocks"]] == [
        "Nested Page",
        "Tracker",
    ]
    assert result["unsupported_block_types"] == []
    assert result["warnings"] == [
        {
            "type": "page_boundary",
            "block_id": "cp-1",
            "block_type": "child_page",
        }
    ]
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None)]


def test_max_blocks_exact_boundary_is_complete():
    calls = []
    b1 = block("b1", "paragraph", rich_text=rich("one"))
    b2 = block("b2", "paragraph", rich_text=rich("two"))
    responses = {(PAGE_ID, None): batch([b1, b2])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID, max_blocks=2)

    assert len(result["blocks"]) == 2
    assert result["partial"]["max_blocks_reached"] is False
    assert result["complete"] is True


def test_max_blocks_boundary_truncates_without_extra_request():
    calls = []
    b1 = block("b1", "paragraph", rich_text=rich("one"))
    b2 = block("b2", "paragraph", rich_text=rich("two"))
    b3 = block(
        "b3", "toggle", has_children=True, rich_text=rich("three")
    )
    responses = {
        (PAGE_ID, None): batch([b1, b2, b3]),
        ("b3", None): batch(
            [block("b3-child", "paragraph", rich_text=rich("hidden"))]
        ),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID, max_blocks=2)

    assert [e["id"] for e in result["blocks"]] == ["b1", "b2"]
    assert result["partial"]["max_blocks_reached"] is True
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None)]


def test_max_characters_exact_boundary_is_complete():
    calls = []
    b1 = block("b1", "paragraph", rich_text=rich("12345"))
    responses = {(PAGE_ID, None): batch([b1])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID, max_characters=5)

    assert result["blocks"][0]["text"] == "12345"
    assert result["partial"]["max_characters_reached"] is False
    assert result["complete"] is True


def test_max_characters_boundary_stops_before_oversized_block():
    calls = []
    b1 = block("b1", "paragraph", rich_text=rich("12345"))
    b2 = block("b2", "paragraph", rich_text=rich("6"))
    responses = {(PAGE_ID, None): batch([b1, b2])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID, max_characters=5)

    assert [e["id"] for e in result["blocks"]] == ["b1"]
    assert result["partial"]["max_characters_reached"] is True
    assert result["complete"] is False


def test_no_additional_request_after_block_limit_stops_mid_batch():
    calls = []
    b1 = block("b1", "paragraph", rich_text=rich("one"))
    b2 = block(
        "b2", "toggle", has_children=True, rich_text=rich("two")
    )
    responses = {
        (PAGE_ID, None): batch([b1, b2]),
        ("b2", None): batch(
            [block("hidden", "paragraph", rich_text=rich("x"))]
        ),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID, max_blocks=1)

    assert [e["id"] for e in result["blocks"]] == ["b1"]
    assert calls == [(PAGE_ID, None)]
    assert result["partial"]["max_blocks_reached"] is True


def test_request_failure_warning_preserves_suggested_action_and_retry_after():
    calls = []
    b1 = block("b1", "paragraph", rich_text=rich("one"))
    responses = {
        (PAGE_ID, None): batch(
            [b1], has_more=True, next_cursor="cursor-1"
        ),
        (PAGE_ID, "cursor-1"): error(
            "RATE_LIMITED",
            "Notion rate-limited the request.",
            True,
            retry_after="30",
        ),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client.read_page_blocks(PAGE_ID)

    assert result["ok"] is True
    assert [e["id"] for e in result["blocks"]] == ["b1"]
    assert result["warnings"] == [
        {
            "type": "request_failed",
            "parent_id": PAGE_ID,
            "code": "RATE_LIMITED",
            "message": "Notion rate-limited the request.",
            "retryable": True,
            "suggested_action": "See the error code.",
            "retry_after": "30",
        }
    ]
    assert result["complete"] is False


def test_invalid_limit_settings_rejected_before_any_request():
    calls = []
    responses = {}

    with patched_client(responses, calls):
        client = NotionAPIClient()

        bad_blocks = client.read_page_blocks(PAGE_ID, max_blocks=0)
        bad_blocks_bool = client.read_page_blocks(
            PAGE_ID, max_blocks=True
        )
        bad_chars = client.read_page_blocks(PAGE_ID, max_characters=0)
        bad_chars_bool = client.read_page_blocks(
            PAGE_ID, max_characters=True
        )
        bad_depth = client.read_page_blocks(PAGE_ID, max_depth=11)

    assert bad_blocks["error"]["code"] == "INVALID_MAX_BLOCKS"
    assert bad_blocks_bool["error"]["code"] == "INVALID_MAX_BLOCKS"
    assert bad_chars["error"]["code"] == "INVALID_MAX_CHARACTERS"
    assert bad_chars_bool["error"]["code"] == "INVALID_MAX_CHARACTERS"
    assert bad_depth["error"]["code"] == "INVALID_MAX_DEPTH"
    assert calls == []
