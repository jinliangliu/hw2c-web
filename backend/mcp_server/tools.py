"""MCP tool implementations.

P1 registers read-only tools only.  Generation and flashing tools land in P2/P3;
registering them early would expose a tool whose backing executor does not exist
yet — worse than not exposing it at all.
"""

from __future__ import annotations

from services import catalog_service, parse_service, validate_service

_TOOL_DESCRIPTIONS = {
    "parse_eda": (
        "把 EDA 网表（.enet/.net）与可选 BOM 解析为 hw2c 六层 YAML。"
        "返回 hardware/task/components/bind/params/pubsub 六层文本与 issues。 "
        "入参是文本，不是文件路径。"
    ),
    "validate_config": (
        "校验 hw2c 六层 YAML：YAML 语法、Pydantic schema、跨层引用一致性。"
        "layers 形如 {hardware, task?, components?, bind?, params?, pubsub?}，"
        "值为 YAML 文本。只返回结构化 issues，不修改任何文件。"
    ),
    "list_examples": "列出 hw2c 自带的所有六层示例及其 MCU/引脚摘要。",
    "get_example": "读取某个自带示例的六层 YAML；传 layer 只读其中一层。",
    "get_mcu_pinout": (
        "查询指定 MCU 型号在自带示例中出现过的引脚分配（含 AF）。"
        "未知型号返回空列表，绝不臆造引脚。"
    ),
}


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": str(message)[:200]}}


def parse_eda(
    netlist_text: str,
    bom_text: str = "",
    filename: str = "",
) -> dict:
    """Parse an EDA netlist into the six hw2c YAML layers."""
    return parse_service.parse_to_layers(
        netlist_text=netlist_text,
        bom_text=bom_text or None,
        filename=filename or None,
    )


def validate_config(layers: dict[str, str]) -> dict:
    """Validate six-layer YAML and return structured issues."""
    if not isinstance(layers, dict):
        return _fail("E_BAD_INPUT", "layers must be an object")
    return validate_service.validate_config(layers)


def list_examples() -> list[dict]:
    """List shipped hw2c examples."""
    return catalog_service.list_examples()


def get_example(name: str, layer: str = "") -> dict:
    """Read one shipped example's YAML layers."""
    try:
        return catalog_service.get_example(name, layer or None)
    except (ValueError, FileNotFoundError) as exc:
        return _fail("E_FORBIDDEN" if isinstance(exc, ValueError) else "E_NOT_FOUND", str(exc))


def get_mcu_pinout(part: str) -> dict:
    """Return known pin assignments for an MCU part."""
    try:
        return catalog_service.get_mcu_pinout(part)
    except ValueError as exc:
        return _fail("E_FORBIDDEN", str(exc))


TOOLS = (parse_eda, validate_config, list_examples, get_example, get_mcu_pinout)


def register_tools(mcp) -> None:
    """Register the P1 tool set on an MCP server instance."""
    for fn in TOOLS:
        mcp.add_tool(fn, description=_TOOL_DESCRIPTIONS[fn.__name__])
