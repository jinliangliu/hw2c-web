"""MCP tool implementations.

Generation tools are asynchronous: the 30 s WorkBuddy tool timeout is shorter
than a real hw2c build (60–180 s), so the executor returns a request_id and the
model polls for status.  Flashing tools stay unregistered until P3.
"""

from __future__ import annotations

from services import (
    catalog_service, flash_service, generate_service, parse_service, validate_service,
)

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
    "list_probes": (
        "列出本机接入的调试探针（pyOCD，只读）。只有 HW2C_ENABLE_FLASH=1 时注册。"
    ),
    "flash_firmware": (
        "把某次构建的镜像烧到本机板子。confirm 必须为布尔 true 才会真正写 flash；"
        "否则只返回 dry-run 计划（目标地址/镜像 sha256），绝不调用 pyOCD。"
        "带 bootloader 的工程用 combined.bin 烧 0x08000000；应用镜像必须显式 slot='A'|'B'，"
        "且镜像的 Reset_Handler 必须落在该槽区间（槽 B 需单独按槽 B 基址链接的构建）。"
        "写前回读对拍，一致则不写；写后再逐字节校验；烧完保持停机、不自动复位。"
    ),
    "verify_flash": (
        "只读回读 flash，与某次构建的镜像逐字节对拍（含 sha256 与首个差异偏移）。"
        "传 request_id 与 artifact；应用镜像可传 slot='A'|'B'，省略时按向量表自动定位。"
    ),
    "capture_serial": (
        "只读抓取本机串口一段时间的文本（不向设备写任何字节）。"
        "port 形如 COM5 或 /dev/ttyACM0，seconds 最大 30；可选 trigger 为正则，"
        "返回是否命中。返回中带物理速率自检结果与首包 purge 标志："
        "rate_guard_trips>0 表示该窗口是主机侧陈旧缓冲回放，不可当成固件输出。"
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


def _hardware_error(exc: Exception) -> dict:
    code = getattr(exc, "code", "E_INTERNAL")
    message = getattr(exc, "message", "hardware tool error")
    return _fail(code, message)


def list_probes() -> dict:
    """Enumerate attached debug probes (read-only)."""
    try:
        return flash_service.list_probes()
    except (flash_service.FlashError, generate_service.BuildError) as exc:
        return _hardware_error(exc)


def flash_firmware(request_id: str, artifact: str, slot: str = "",
                   # Deliberately untyped: a `bool` annotation lets the MCP SDK
                   # coerce the string "true" into True before we see it.  Only
                   # the literal JSON boolean is a confirmation.
                   confirm: object = False) -> dict:
    """Dry-run unless confirm is exactly True; write only after a readback check."""
    try:
        plan = flash_service.plan_flash(request_id, artifact, slot, for_write=True)
        if confirm is not True:
            return flash_service.public_plan(plan)
        return flash_service.flash(plan)
    except (flash_service.FlashError, generate_service.BuildError) as exc:
        return _hardware_error(exc)


def verify_flash(request_id: str, artifact: str, slot: str = "") -> dict:
    """Read flash and compare byte-for-byte with a build artifact."""
    try:
        return flash_service.verify_flash(request_id, artifact, slot)
    except (flash_service.FlashError, generate_service.BuildError) as exc:
        return _hardware_error(exc)


def capture_serial(port: str, seconds: float = 5.0, trigger: str = "") -> dict:
    """Read a serial port without transmitting; guard against stale replay."""
    try:
        return flash_service.capture_serial(port, seconds, trigger)
    except (flash_service.FlashError, generate_service.BuildError) as exc:
        return _hardware_error(exc)


BASE_TOOLS = (
    parse_eda, validate_config, list_examples, get_example, get_mcu_pinout,
    generate_firmware, get_build_status, list_artifacts,
)
FLASH_TOOLS = (list_probes, flash_firmware, verify_flash, capture_serial)


def active_tools() -> tuple:
    """Hardware tools are opt-in; the default server never exposes them."""
    return BASE_TOOLS + (FLASH_TOOLS if flash_service.enabled() else ())


TOOLS = active_tools()


def register_tools(mcp) -> None:
    """Register the tool set enabled for this process."""
    for fn in active_tools():
        mcp.add_tool(fn, description=_TOOL_DESCRIPTIONS[fn.__name__])
