import os

from mcp.server.fastmcp import FastMCP

from tools import vdr, sec_edgar, logo

mcp = FastMCP("mcp-server")
_caller_uid = int(os.environ.get("MCP_CALLER_UID", os.getuid()))

vdr.register(mcp, _caller_uid)
sec_edgar.register(mcp, _caller_uid)
logo.register(mcp, _caller_uid)

if __name__ == "__main__":
    mcp.run(transport="stdio")
