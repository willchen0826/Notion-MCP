import json

from notion_api import NotionAPIClient


def main() -> None:
    client = NotionAPIClient()

    result = client.request(
        "POST",
        "/search",
        json_body={"page_size": 1},
        read_only=True,
    )

    if "error" in result:
        print(json.dumps(result, indent=2))
        raise SystemExit(1)

    data = result["data"]
    print("\n" + "data is:   ")
    print(data)

    if not isinstance(data.get("results"), list):
        print("ERROR: Search response does not contain a results list")
        raise SystemExit(1)

    print("PASS: Notion API request succeeded")
    print(f"INFO: Refreshed during request: {result['refreshed']}")
    print(f"INFO: Results returned: {len(data['results'])}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError):
        print("ERROR: Check local OAuth configuration and file permissions")
        raise SystemExit(1)