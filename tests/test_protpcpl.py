import asyncio
from pathlib import Path

from fastmcp import Client

SERVER_PATH = (
    Path(__file__).resolve().parents[1] / "server.py"
)

async def check_server():
     # Launch server.py as a subprocess over stdio
     async with Client(SERVER_PATH) as client:
         
        # MCP tools/list
        tools = await client.list_tools()
        names = [tool.name for tool in tools]
        
        assert "health" in names
        
        # MCP tools/call
        result = await client.call_tool("health", {})
        
        assert result.data["status"] =="ready"
        
        print("PASS: tools/list")
        print("PASS: tools/call")
        print("PASS: MCP stdio protocol")
        

def test_mcp_protocol():
    asyncio.run(check_server())
    

if __name__ == "__main__":
    test_mcp_protocol()