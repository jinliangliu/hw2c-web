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
from mcp_server.tools import active_tools, register_tools


def create_server():
    """Build the server with the tool set enabled for this process."""
    instructions = (
        "hw2c 把用户定义的硬件资源转成基于 FreeRTOS 的 STM32 固件。"
        "先用 parse_eda 从网表得到六层 YAML，用 validate_config 校验，"
        "再用 resources 读需求/格式真源。"
        "生成固件用 generate_firmware（异步，立即返回 request_id），"
        "之后每 2 秒用 get_build_status 轮询，最多 180 秒；"
        "成功后再用 list_artifacts 拿 .elf/.bin。"
    )
    if "flash_firmware" in {fn.__name__ for fn in active_tools()}:
        instructions += (
            "烧录工具已启用：先 list_probes 确认探针，flash_firmware 不带 confirm "
            "只返回 dry-run；真正写板子必须由用户明确确认后带 confirm=true，"
            "写前会回读对拍；verify_flash 只读校验，capture_serial 抓串口并自检速率。"
        )
    else:
        instructions += "烧录工具未注册（需 HW2C_ENABLE_FLASH=1）。"
    server = MCPServer(name="hw2c-local", instructions=instructions)
    register_tools(server)
    register_resources(server)
    return server


def main() -> None:
    """Run over stdio — no network socket is opened."""
    create_server().run(transport="stdio")
