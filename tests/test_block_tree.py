from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from notion_api import NotionAPIClient


PAGE_ID = "11111111-1111-1111-1111-111111111111"


def block(block_id, block_type, has_children=False):
    return {
        "object": "block",
        "id": block_id,
        "type": block_type,
        "has_children": has_children,
    }


def batch(results, has_more=False, next_cursor=None):
    return {
        "ok": True,
        "results": results,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def error(code, message="A request error.", retryable=False):
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "suggested_action": "See the error code.",
        }
    }


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


def test_empty_page():
    calls = []
    responses = {(PAGE_ID, None): batch([])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert result["ok"] is True
    assert result["complete"] is True
    assert result["blocks"] == []
    assert result["request_calls"] == 1
    assert calls == [(PAGE_ID, None)]


def test_multiple_root_batches_use_correct_cursors():
    calls = []
    b1 = block("b1", "paragraph")
    b2 = block("b2", "paragraph")
    responses = {
        (PAGE_ID, None): batch([b1], has_more=True, next_cursor="cursor-1"),
        (PAGE_ID, "cursor-1"): batch([b2]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert [e["block"]["id"] for e in result["blocks"]] == ["b1", "b2"]
    assert [e["depth"] for e in result["blocks"]] == [0, 0]
    assert [e["parent_id"] for e in result["blocks"]] == [PAGE_ID, PAGE_ID]
    assert calls == [(PAGE_ID, None), (PAGE_ID, "cursor-1")]
    assert result["request_calls"] == 2
    assert result["complete"] is True


def test_nested_blocks_use_depth_first_order():
    calls = []
    toggle = block("toggle-1", "toggle", has_children=True)
    paragraph = block("p-1", "paragraph")
    nested = block("nested-1", "paragraph")

    responses = {
        (PAGE_ID, None): batch([toggle, paragraph]),
        ("toggle-1", None): batch([nested]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert [e["block"]["id"] for e in result["blocks"]] == [
        "toggle-1",
        "nested-1",
        "p-1",
    ]
    assert [e["depth"] for e in result["blocks"]] == [0, 1, 0]
    assert [e["parent_id"] for e in result["blocks"]] == [
        PAGE_ID,
        "toggle-1",
        PAGE_ID,
    ]
    assert calls == [(PAGE_ID, None), ("toggle-1", None)]
    assert result["complete"] is True


def test_independent_pagination_for_root_and_nested_parent():
    calls = []
    toggle = block("toggle-1", "toggle", has_children=True)
    child_a = block("child-a", "paragraph")
    child_b = block("child-b", "paragraph")
    para = block("p-1", "paragraph")

    responses = {
        (PAGE_ID, None): batch(
            [toggle], has_more=True, next_cursor="root-cursor-1"
        ),
        ("toggle-1", None): batch(
            [child_a], has_more=True, next_cursor="cursor-1"
        ),
        ("toggle-1", "cursor-1"): batch([child_b]),
        (PAGE_ID, "root-cursor-1"): batch([para]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert [e["block"]["id"] for e in result["blocks"]] == [
        "toggle-1",
        "child-a",
        "child-b",
        "p-1",
    ]
    assert calls == [
        (PAGE_ID, None),
        ("toggle-1", None),
        ("toggle-1", "cursor-1"),
        (PAGE_ID, "root-cursor-1"),
    ]
    assert result["complete"] is True


def test_table_container_children_are_visited_without_rich_text():
    calls = []
    table = block("table-1", "table", has_children=True)
    row1 = block("row-1", "table_row")
    row2 = block("row-2", "table_row")

    responses = {
        (PAGE_ID, None): batch([table]),
        ("table-1", None): batch([row1, row2]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert [e["block"]["id"] for e in result["blocks"]] == [
        "table-1",
        "row-1",
        "row-2",
    ]
    assert [e["depth"] for e in result["blocks"]] == [0, 1, 1]
    assert result["complete"] is True


def test_max_depth_zero_skips_root_children():
    calls = []
    has_kids = block("x-1", "toggle", has_children=True)
    responses = {(PAGE_ID, None): batch([has_kids])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID, max_depth=0)

    assert [e["block"]["id"] for e in result["blocks"]] == ["x-1"]
    assert result["partial"]["max_depth_reached"] is True
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None)]


def test_deeper_depth_boundary_stops_one_level_further():
    calls = []
    toggle = block("toggle-1", "toggle", has_children=True)
    nested_toggle = block("nested-toggle", "toggle", has_children=True)

    responses = {
        (PAGE_ID, None): batch([toggle]),
        ("toggle-1", None): batch([nested_toggle]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID, max_depth=1)

    assert [
        (e["block"]["id"], e["depth"]) for e in result["blocks"]
    ] == [("toggle-1", 0), ("nested-toggle", 1)]
    assert result["partial"]["max_depth_reached"] is True
    assert calls == [(PAGE_ID, None), ("toggle-1", None)]


def test_deep_branch_followed_by_shallow_sibling():
    calls = []
    deep = block("deep-1", "toggle", has_children=True)
    shallow = block("shallow-1", "paragraph")
    leaf = block("leaf-1", "paragraph")

    responses = {
        (PAGE_ID, None): batch([deep, shallow]),
        ("deep-1", None): batch([leaf]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert [e["block"]["id"] for e in result["blocks"]] == [
        "deep-1",
        "leaf-1",
        "shallow-1",
    ]
    assert calls == [(PAGE_ID, None), ("deep-1", None)]


def test_request_budget_shared_across_pagination_and_nesting():
    calls = []
    toggle = block("toggle-1", "toggle", has_children=True)
    leaf = block("leaf-1", "paragraph")
    para = block("p-1", "paragraph")

    responses = {
        (PAGE_ID, None): batch(
            [toggle], has_more=True, next_cursor="root-cursor-1"
        ),
        ("toggle-1", None): batch([leaf]),
        (PAGE_ID, "root-cursor-1"): batch([para]),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID, max_request_calls=2)

    assert [e["block"]["id"] for e in result["blocks"]] == [
        "toggle-1",
        "leaf-1",
    ]
    assert result["request_calls"] == 2
    assert result["partial"]["max_requests_reached"] is True
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None), ("toggle-1", None)]


def test_exact_budget_with_no_remaining_work_is_complete():
    calls = []
    leaf = block("leaf-1", "paragraph")
    responses = {(PAGE_ID, None): batch([leaf])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID, max_request_calls=1)

    assert result["request_calls"] == 1
    assert result["partial"]["max_requests_reached"] is False
    assert result["complete"] is True


def test_exact_budget_with_remaining_work_is_truncated():
    calls = []
    leaf = block("leaf-1", "paragraph")
    responses = {
        (PAGE_ID, None): batch(
            [leaf], has_more=True, next_cursor="cursor-1"
        ),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID, max_request_calls=1)

    assert result["request_calls"] == 1
    assert result["partial"]["max_requests_reached"] is True
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None)]


def test_child_page_and_child_database_boundaries():
    calls = []
    child_page = block("page-1", "child_page", has_children=True)
    child_database = block("db-1", "child_database", has_children=False)

    responses = {(PAGE_ID, None): batch([child_page, child_database])}

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert [e["block"]["id"] for e in result["blocks"]] == [
        "page-1",
        "db-1",
    ]
    assert result["warnings"] == [
        {
            "type": "page_boundary",
            "block_id": "page-1",
            "block_type": "child_page",
        }
    ]
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None)]


def test_repeated_cursor_cycle_is_detected():
    calls = []
    responses = {
        (PAGE_ID, None): batch([], has_more=True, next_cursor="A"),
        (PAGE_ID, "A"): batch([], has_more=True, next_cursor="B"),
        (PAGE_ID, "B"): batch([], has_more=True, next_cursor="A"),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert result["request_calls"] == 3
    assert result["warnings"] == [
        {
            "type": "repeated_cursor",
            "parent_id": PAGE_ID,
            "cursor": "A",
        }
    ]
    assert result["complete"] is False
    assert calls == [(PAGE_ID, None), (PAGE_ID, "A"), (PAGE_ID, "B")]


def test_initial_request_failure_propagates_error():
    calls = []
    responses = {
        (PAGE_ID, None): error("AUTH_REQUIRED", "No cached credentials.")
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert result == responses[(PAGE_ID, None)]
    assert calls == [(PAGE_ID, None)]


def test_later_request_failure_preserves_partial_results():
    calls = []
    leaf = block("leaf-1", "paragraph")
    responses = {
        (PAGE_ID, None): batch(
            [leaf], has_more=True, next_cursor="cursor-1"
        ),
        (PAGE_ID, "cursor-1"): error(
            "RATE_LIMITED", "Notion rate-limited the request.", True
        ),
    }

    with patched_client(responses, calls):
        client = NotionAPIClient()
        result = client._walk_block_tree(PAGE_ID)

    assert result["ok"] is True
    assert [e["block"]["id"] for e in result["blocks"]] == ["leaf-1"]
    assert result["complete"] is False
    assert result["warnings"] == [
        {
            "type": "request_failed",
            "parent_id": PAGE_ID,
            "code": "RATE_LIMITED",
            "message": "Notion rate-limited the request.",
            "retryable": True,
        }
    ]
    assert result["request_calls"] == 2
    assert calls == [(PAGE_ID, None), (PAGE_ID, "cursor-1")]


def test_invalid_settings_rejected_before_any_request():
    calls = []
    responses = {}

    with patched_client(responses, calls):
        client = NotionAPIClient()

        bad_id = client._walk_block_tree("not-a-real-id")
        bad_depth = client._walk_block_tree(PAGE_ID, max_depth=11)
        bad_depth_bool = client._walk_block_tree(PAGE_ID, max_depth=True)
        bad_requests = client._walk_block_tree(
            PAGE_ID, max_request_calls=0
        )
        bad_page_size = client._walk_block_tree(PAGE_ID, page_size=101)

    assert bad_id["error"]["code"] == "INVALID_PAGE_ID"
    assert bad_depth["error"]["code"] == "INVALID_MAX_DEPTH"
    assert bad_depth_bool["error"]["code"] == "INVALID_MAX_DEPTH"
    assert bad_requests["error"]["code"] == "INVALID_MAX_REQUEST_CALLS"
    assert bad_page_size["error"]["code"] == "INVALID_PAGE_SIZE"
    assert calls == []
