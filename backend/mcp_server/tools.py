"""MCP tool implementations.

Generation tools are asynchronous: the 30 s WorkBuddy tool timeout is shorter
than a real hw2c build (60–180 s), so the executor returns a request_id and the
model polls for status.  Flashing tools stay unregistered until P3.
"""

from __future__ import annotations

from services import catalog_service, generate_service, parse_service, validate_service

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
    "generate_firmware": (
        "用六层 YAML 生成并编译固件，异步执行。立即返回 request_id（不等待编译），"
        "随后用 get_build_status 轮询。layers 形如 {hardware, task?, components?, "
        "bind?, params?, pubsub?}，值为 YAML 文本；project_name 只是产物目录名。"
        "不接受输出路径或 --force；编译检查绝不会被跳过。"
    ),
    "get_build_status": (
        "查询 generate_firmware 的异步构建状态：status 为 queued/running/"
        "succeeded/failed，compile_check 为 passed/failed/skipped，"
        "succeeded 时附 artifact_manifest（.elf/.bin 的 size 与 sha256）。"
        "每 2 秒轮询一次，最多 180 秒。"
    ),
    "list_artifacts": (
        "列出某次构建的可执行固件产物（name/size/sha256/uri）。"
        "uri 可用 hw2c://artifacts/ 资源读取；构建未完成或无产物时返回空列表。"
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


def generate_firmware(layers: dict[str, str], project_name: str = "firmware") -> dict:
    """Queue an isolated firmware build; return a request_id immediately."""
    try:
        return generate_service.submit_build(layers, project_name)
    except generate_service.BuildError as exc:
        return _fail(exc.code, exc.message)


def get_build_status(request_id: str) -> dict:
    """Poll an asynchronous build without blocking."""
    try:
        return generate_service.get_status(request_id)
    except generate_service.BuildError as exc:
        return _fail(exc.code, exc.message)


def list_artifacts(request_id: str) -> list[dict]:
    """List executable images from a finished build."""
    try:
        return generate_service.list_artifacts(request_id)
    except generate_service.BuildError as exc:
        return [_fail(exc.code, exc.message)]


TOOLS = (
    parse_eda, validate_config, list_examples, get_example, get_mcu_pinout,
    generate_firmware, get_build_status, list_artifacts,
)


def register_tools(mcp) -> None:
    """Register the P1+P2 tool set on an MCP server instance."""
    for fn in TOOLS:
        mcp.add_tool(fn, description=_TOOL_DESCRIPTIONS[fn.__name__])
