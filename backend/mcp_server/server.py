"""MCP server assembly for the local WorkBuddy Connector.

The SDK's package is also named ``mcp``; this package is deliberately named
``mcp_server`` so it cannot shadow the SDK on sys.path.
"""

from __future__ import annotations

try:  # MCP SDK 2.x
    from mcp.server.mcpserver import MCPServer
except ImportError:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[assignment]

from mcp_server.resources import register_resources
from mcp_server.tools import register_tools


def create_server():
    """Build the server with the P1 tool/resource set."""
    server = MCPServer(
        name="hw2c-local",
        instructions=(
            "hw2c 把用户定义的硬件资源转成基于 FreeRTOS 的 STM32 固件。"
            "先用 parse_eda 从网表得到六层 YAML，用 validate_config 校验，"
            "再用 resources 读需求/格式真源。生成与烧录工具在后续阶段提供。"
        ),
    )
    register_tools(server)
    register_resources(server)
    return server


def main() -> None:
    """Run over stdio — no network socket is opened."""
    create_server().run(transport="stdio")
