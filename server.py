from fastmcp import FastMCP

mcp = FastMCP(
    name="Notion Study Assistant",
    instructions=(
        "Search for a Notion page before reading it. "
        "Use the page ID returned by search tools. "
        "Preview any write operation before committing changes."
    ),
)

@mcp.tool(
    annotations = {"readOnlyHint": True}
)
def health() -> dict[str, str]:
    """
    Check whether the local MCP server is running.

    This tool does not connect to Notion.
    """
    return {
        "server": "notion-study-assistant",
        "status": "ready",
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")