"""Contract guardrails for the local MCP Connector.

The assert_* helpers are deliberately module-level: the mutation script feeds
them deliberately broken inputs and requires an AssertionError.  A guardrail
that stays green after mutation is a tautology and must be rewritten.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
WEB_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    import pytest  # noqa: F811 - the fallback below is only for the stdlib runner
except ImportError:  # allow `python tests/test_mcp_contract.py` without pytest
    class _Raises:
        def __init__(self, exc):
            self.exc = exc
            self.value = None

        def __enter__(self):
            return self

        def __exit__(self, kind, value, _tb):
            self.value = value
            return isinstance(value, self.exc)

    class pytest:  # type: ignore[no-redef]
        @staticmethod
        def raises(exc):
            return _Raises(exc)

        @staticmethod
        def importorskip(_name, reason=""):
            return None

pytest.importorskip("mcp", reason="MCP SDK is required only for Connector tests")

from mcp_server.server import create_server  # noqa: E402
from mcp_server import tools as mcp_tools  # noqa: E402
from services import catalog_service, flash_service as flash, generate_service as builds  # noqa: E402
from services.validate_service import validate_config  # noqa: E402

EXPECTED_TOOLS = {
    "parse_eda",
    "validate_config",
    "list_examples",
    "get_example",
    "get_mcu_pinout",
    "generate_firmware",
    "get_build_status",
    "list_artifacts",
}
EXPECTED_TEMPLATES = {
    "hw2c://requirements/{section}",
    "hw2c://docs/user-guide/{layer}-yaml",
    "hw2c://schema/{layer}",
    "hw2c://examples/{name}/{layer}.yaml",
    "hw2c://format/{name}.json",
    "hw2c://models/{name}.yaml",
    "hw2c://artifacts/{request_id}/{filename}",
}
HARDWARE_TOOLS = {"flash_firmware", "verify_flash", "list_probes", "capture_serial"}
BUILD_TOOLS = {"generate_firmware", "get_build_status", "list_artifacts"}
COMPILE_STATES = {"passed", "failed", "skipped"}


def assert_tool_set(names) -> None:
    assert set(names) == EXPECTED_TOOLS, f"tool set drifted: {sorted(names)}"


def assert_no_hardware_tools(names) -> None:
    leaked = set(names) & HARDWARE_TOOLS
    assert not leaked, f"hardware tools registered without an executor: {sorted(leaked)}"


def assert_resources_cover(static_uris, template_uris) -> None:
    assert "hw2c://requirements" in set(static_uris)
    assert EXPECTED_TEMPLATES <= set(template_uris), (
        f"missing resource templates: {sorted(EXPECTED_TEMPLATES - set(template_uris))}"
    )


def assert_connector_meta_is_local_only(meta: dict, mcp_cfg: dict) -> None:
    for forbidden in ("auth_mode", "token-schema", "server_auth"):
        assert forbidden not in meta, f"local Connector must not declare {forbidden}"
    assert meta.get("type") == "mcp"
    assert meta.get("source") == "hw2c-local"
    servers = mcp_cfg.get("mcpServers", {})
    assert len(servers) == 1, "WorkBuddy reads only the first MCP server"
    cfg = next(iter(servers.values()))
    assert cfg.get("type") == "stdio"
    assert "command" in cfg and cfg["command"]
    assert cfg.get("cwd"), "Python stdio server needs cwd (v4.22.15+)"
    assert "-m" in cfg.get("args", [])
    assert cfg.get("env", {}).get("HW2C_ENABLE_FLASH") in ("0", None), (
        "hardware tools must be opt-in in the shipped Connector config"
    )
    assert cfg.get("timeout", 0) >= 180000, (
        "a full flash readback + verify cannot finish inside WorkBuddy's 30 s default"
    )


def assert_async_envelope(result) -> None:
    """generate_firmware must return a ticket, never a finished build."""
    assert isinstance(result, dict), "async ticket must be a JSON object"
    rid = result.get("request_id")
    assert isinstance(rid, str) and re.fullmatch(r"[0-9a-f]{12}", rid), (
        f"missing/ill-formed request_id: {rid!r}"
    )
    assert result.get("status") == "queued", f"expected queued, got {result.get('status')!r}"
    for leaked in ("artifact_manifest", "artifacts", "compile_check", "elf", "bin",
                   "zip", "files", "stdout", "stderr"):
        assert leaked not in result, (
            f"{leaked!r} in the immediate result — the call is synchronous and "
            "will be cut off by WorkBuddy's 30 s tool timeout"
        )


def assert_artifact_manifest(items) -> None:
    """The deliverable is an executable image, not just a source tree."""
    assert isinstance(items, list) and items, "empty artifact_manifest"
    names = {item["name"] for item in items}
    assert any(name.endswith(".elf") for name in names), "no .elf in manifest"
    assert any(name.endswith(".bin") for name in names), "no .bin in manifest"
    for item in items:
        for field in ("name", "size", "sha256", "uri"):
            assert field in item, f"artifact missing {field}: {item}"
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "sha256 must be 64 hex chars"
        assert isinstance(item["size"], int) and item["size"] > 0, "bad artifact size"
        assert item["uri"].startswith("hw2c://artifacts/"), "artifact uri is not readable"


def assert_compile_state(state, missing=()) -> None:
    assert state in COMPILE_STATES, f"compile_check must be one of {COMPILE_STATES}: {state!r}"
    if missing:
        assert state != "passed", (
            "toolchain is incomplete but compile_check=passed — hw2c's silent "
            "green was reported as a real build"
        )


def assert_no_force(cmd) -> None:
    """Generation must keep the compile check and never accept a user path."""
    assert isinstance(cmd, list) and "-o" in cmd
    assert "--force" not in cmd, "--force skips hw2c's compile check (generate.py:1307)"
    assert all(not str(arg).startswith("--force") for arg in cmd)
    out = Path(cmd[cmd.index("-o") + 1])
    assert re.fullmatch(r"[0-9a-f]{12}", out.parent.name), (
        "output directory is not an isolated request workspace"
    )


def assert_sanitized(issues, raw) -> None:
    assert isinstance(issues, list) and issues, "no structured issues from raw output"
    joined = json.dumps(issues, ensure_ascii=False)
    for needle in ("C:/Users", "C:\\\\Users", "/home/"):
        assert needle not in joined, f"raw local path leaked into tool result: {needle}"
    assert raw.strip() not in joined, "raw stderr was passed through unchanged"
    for item in issues:
        assert {"code", "message", "location"} <= set(item), f"bad issue shape: {item}"
        assert len(item["message"]) <= 200, "issue message exceeds 200 chars"


def assert_build_input_rejected(fn, layers=None, name="firmware", options=None,
                                expected=None) -> None:
    args = [layers if layers is not None else {"hardware": "mcu: {}"}, name]
    if options is not None:
        args.append(options)
    try:
        fn(*args)
    except builds.BuildError as exc:
        if expected is not None:
            assert exc.code == expected, f"expected {expected}, got {exc.code}"
        return
    raise AssertionError("unsafe build input was accepted")


def assert_name_check(check) -> None:
    for bad in ("../x", "..", "C:/x", "a/b", "/etc/passwd"):
        try:
            check(bad)
        except builds.BuildError:
            continue
        raise AssertionError(f"unsafe name accepted: {bad!r}")


# --- P3: hardware tools ---
SLOT_A, SLOT_B, BOOTLOADER = 0x08002000, 0x08040000, 0x08000000
HARDWARE_TOOL_SET = {
    "list_probes", "flash_firmware", "verify_flash", "capture_serial",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_flash_tool_set(names, enabled: bool) -> None:
    present = set(names) & HARDWARE_TOOL_SET
    if enabled:
        assert present == HARDWARE_TOOL_SET, f"flash tools missing: {sorted(HARDWARE_TOOL_SET - present)}"
    else:
        assert not present, f"hardware tools registered by default: {sorted(present)}"


def assert_dry_run(result, hardware_calls) -> None:
    """confirm=false must return a plan and never reach pyOCD/pyserial."""
    assert isinstance(result, dict)
    assert result.get("dry_run") is True, "an unconfirmed call tried to write"
    assert result.get("confirm_required") is True
    assert "written" not in result and "match" not in result
    assert not any(key.startswith("_") for key in result), "private image bytes leaked"
    assert list(hardware_calls) == [], f"pyOCD called during dry-run: {hardware_calls}"


def assert_flash_plan(plan, artifact: str, address: int, slot: str) -> None:
    assert plan["artifact"] == artifact
    assert int(plan["address"]) == address, f"wrong flash base for {artifact}: {plan['address']}"
    assert plan["slot"] == slot
    assert plan["region"] in ("bootloader", "base", "slot_a", "slot_b")
    assert plan["erase"] == "sector", "whole-chip erase would destroy another slot"
    assert plan["reset_after"] is False
    assert plan["dry_run"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", plan["sha256"])


def assert_slot_link(plan, requested_slot: str) -> None:
    """An image linked for slot A must never be accepted for slot B."""
    if requested_slot:
        assert plan["region"] == "slot_" + requested_slot.lower(), (
            f"{requested_slot} requested but image is linked to {plan['region']}"
        )
        assert plan["address"] == (SLOT_A if requested_slot == "A" else SLOT_B)
    else:
        assert plan["region"] != "slot_b", "slot B needs an explicit slot argument"


def assert_write_result(result, before: bytes, image: bytes, write_calls) -> None:
    assert result["dry_run"] is False
    assert result["before_sha256"] == _sha(before), "no readback before writing"
    assert result["image_sha256"] == _sha(image)
    assert result["reset_performed"] is False
    if before == image:
        assert result["written"] is False and not write_calls, "wrote an already-identical image"
        assert result["match"] is True
    else:
        assert result["written"] is True and write_calls, "erase/write step was skipped"
        assert result["match"] is True, "no readback after writing"
        assert result["after_sha256"] == _sha(image)


def assert_verify_result(result, image: bytes, device: bytes) -> None:
    expected = next((i for i, (a, b) in enumerate(zip(device, image)) if a != b), None)
    if expected is None and len(device) != len(image):
        expected = min(len(device), len(image))
    assert result["match"] is (device == image), "compare result contradicts the bytes"
    assert result["first_diff_offset"] == expected
    assert result["image_sha256"] == _sha(image)
    assert result["device_sha256"] == _sha(device)
    assert "written" not in result, "read-only verify tried to write"


def assert_serial_frame(frame, replay: bool = False) -> None:
    assert frame.get("purged_on_open") is True, "stale adapter buffer was not purged"
    assert isinstance(frame.get("rate_guard_trips"), int)
    assert len(frame.get("text", "")) <= flash.MAX_SERIAL_CHARS
    if replay:
        assert frame["rate_guard_trips"] > 0, "replay window was accepted as firmware output"
        assert "REPLAY" not in frame["text"]


def assert_target_is_explicit(target: str) -> None:
    assert target in set(flash.PYOCD_TARGETS.values()), f"guessed pyOCD target: {target!r}"
    assert target not in ("", "auto", "guess")


def assert_image_fits(plan: dict, slot_a_end: int) -> None:
    """combined.bin is allowed to span the bootloader and slot A, not chip erase."""
    assert int(plan["address"]) + int(plan["size"]) <= slot_a_end, (
        f"image does not fit: 0x{int(plan['address']):08X}+{plan['size']}"
    )


def assert_confirm_is_not_coercible(fn) -> None:
    """A `bool` annotation lets the MCP SDK turn the string 'true' into True."""
    annotation = inspect.signature(fn).parameters["confirm"].annotation
    assert annotation in (object, "object"), (
        f"confirm is annotated {annotation!r}; the SDK coerces strings before our gate"
    )


@contextlib.contextmanager
def fake_build(reset_handler: int, *, name: str = "combined.bin",
               part: str = "STM32G0B1RET6", size: int = 64):
    """A manifest + generated linker scripts, with no build subprocess."""
    request_id = "1" * 12
    tmp = Path(tempfile.mkdtemp(prefix="hw2c-p3-contract-"))
    request_dir = tmp / request_id
    project = request_dir / "firmware"
    (project / "build").mkdir(parents=True)
    (project / "linker").mkdir()
    image = bytearray(size)
    struct.pack_into("<I", image, 4, reset_handler)
    (project / "build" / name).write_bytes(image)
    regions = {
        "bootloader.ld": (BOOTLOADER, "8K"),
        "app_slot_a.ld": (SLOT_A, "248K"),
        "app_slot_b.ld": (SLOT_B, "248K"),
    }
    for filename, (origin, length) in regions.items():
        (project / "linker" / filename).write_text(
            f"MEMORY\n{{\n  FLASH (rx) : ORIGIN = {hex(origin)}, LENGTH = {length}\n}}\n",
            encoding="utf-8",
        )
    (request_dir / "hardware.yaml").write_text(f"mcu:\n  part: {part}\n", encoding="utf-8")
    entry = {"name": name, "size": len(image), "sha256": _sha(bytes(image)), "uri": "hw2c://x"}

    saved_env = dict(os.environ)
    saved_list, saved_read = builds.list_artifacts, builds.read_artifact
    os.environ["HW2C_ENABLE_FLASH"] = "1"
    os.environ["HW2C_WORK_ROOT"] = str(tmp)
    builds.list_artifacts = lambda _rid: [entry]
    builds.read_artifact = lambda _rid, _name: bytes(image)
    try:
        yield request_id, project, bytes(image)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
        builds.list_artifacts, builds.read_artifact = saved_list, saved_read
        shutil.rmtree(tmp, ignore_errors=True)


def _registered():
    server = create_server()
    tools = asyncio.run(server.list_tools())
    static = asyncio.run(server.list_resources())
    templates = asyncio.run(server.list_resource_templates())
    return server, [t.name for t in tools], [r.uri for r in static], [t.uri_template for t in templates]


def test_p1_tool_set_is_exact() -> None:
    _, names, _, _ = _registered()
    assert_tool_set(names)


def test_no_unimplemented_hardware_tools() -> None:
    _, names, _, _ = _registered()
    assert_no_hardware_tools(names)
    assert BUILD_TOOLS <= set(names), "generation tools must all be registered"


def test_resources_cover_knowledge_surface() -> None:
    _, _, static, templates = _registered()
    assert_resources_cover([str(uri) for uri in static], templates)


def test_schema_resource_comes_from_authoritative_model() -> None:
    from generator.schemas.hardware import HardwareModel

    assert catalog_service.get_schema("hardware") == HardwareModel.model_json_schema()


def test_path_traversal_is_rejected() -> None:
    root = catalog_service._HW2C_ROOT / "docs"
    with pytest.raises(ValueError):
        catalog_service._safe_read(root, "../requirements.md")
    with pytest.raises(ValueError):
        catalog_service.get_example("../../etc")
    with pytest.raises(ValueError):
        catalog_service.get_schema("../../generator/schemas/hardware")


def test_unknown_mcu_does_not_invent_pins() -> None:
    result = catalog_service.get_mcu_pinout("STM32F999XYZ")
    assert result["pins"] == []


def test_validation_reports_yaml_syntax_without_raising() -> None:
    result = validate_config({"hardware": "mcu: ["})
    assert result["ok"] is False
    assert any(item["code"] == "E_YAML_SYNTAX" for item in result["issues"])


def test_validation_warning_does_not_fail_the_config() -> None:
    result = validate_config({"hardware": "mcu:\n  part: STM32G0B1RET6\npins: []\n"})
    assert result["ok"] is True
    assert any(item["severity"] == "WARNING" for item in result["issues"])


def test_stdio_server_opens_no_network_socket() -> None:
    source = (BACKEND / "mcp_server" / "server.py").read_text(encoding="utf-8")
    assert 'transport="stdio"' in source
    for forbidden in ("0.0.0.0", "run_streamable_http", "uvicorn", "streamable_http_app"):
        assert forbidden not in source, f"network listener leaked into local server: {forbidden}"


def test_connector_package_declares_no_auth_and_one_stdio_server() -> None:
    local = WEB_ROOT / "connector" / "local"
    meta = json.loads((local / "connector-meta.json").read_text(encoding="utf-8"))
    template = (local / "mcp.json.template").read_text(encoding="utf-8")
    generated = json.loads(template
        .replace("__HW2C_PYTHON__", "python")
        .replace("__HW2C_BACKEND__", "backend")
        .replace("__HW2C_ROOT__", "hw2c")
        .replace("__HW2C_BUILD_PYTHON__", "build-python")
        .replace("__HW2C_WORK_ROOT__", "work-root")
        .replace("__HW2C_ENABLE_FLASH__", "0")
        .replace("__HW2C_PYOCD__", "")
        .replace("__HW2C_PYOCD_PYTHON__", ""))
    assert_connector_meta_is_local_only(meta, generated)


def test_connector_template_has_no_machine_specific_path() -> None:
    template = (WEB_ROOT / "connector" / "local" / "mcp.json.template").read_text(encoding="utf-8")
    for placeholder in ("__HW2C_PYTHON__", "__HW2C_BACKEND__", "__HW2C_ROOT__",
                        "__HW2C_BUILD_PYTHON__", "__HW2C_WORK_ROOT__"):
        assert placeholder in template
    assert "C:/" not in template and "C:\\" not in template


def test_skill_tells_the_model_about_async_build_and_limits() -> None:
    skill = (WEB_ROOT / "connector" / "local" / "skills" / "hw2c-firmware" / "SKILL.md").read_text(encoding="utf-8")
    for tool in ("parse_eda", "validate_config", "generate_firmware",
                 "get_build_status", "list_artifacts"):
        assert tool in skill, f"SKILL.md does not mention {tool}"
    assert "异步" in skill and "request_id" in skill
    assert "skipped" in skill, "the model must not call a skipped compile 'passed'"
    assert "烧录" in skill


def test_generate_firmware_returns_a_ticket_in_under_a_second() -> None:
    original = builds._run_build
    builds._run_build = lambda *_args, **_kwargs: None  # no real build in a unit test
    try:
        started = time.monotonic()
        result = mcp_tools.generate_firmware({"hardware": "mcu:\n  part: STM32G0B1RET6\n"})
        elapsed = time.monotonic() - started
    finally:
        builds._run_build = original
    assert_async_envelope(result)
    assert elapsed < 1.0, f"generation blocked for {elapsed:.2f}s"


def test_project_name_traversal_is_rejected() -> None:
    for bad in ("../../etc", "..", "C:/windows", "a/b"):
        assert_build_input_rejected(
            builds.submit_build, name=bad, expected="E_FORBIDDEN"
        )


def test_force_option_is_rejected() -> None:
    assert_build_input_rejected(
        builds.submit_build, options={"force": True}, expected="E_FORBIDDEN"
    )
    assert_build_input_rejected(
        builds.submit_build, options={"output": "/tmp/x"}, expected="E_FORBIDDEN"
    )


def test_unknown_layer_and_oversized_input_are_rejected() -> None:
    assert_build_input_rejected(
        builds.submit_build, layers={"hardware": "mcu: {}", "evil": "x"},
        expected="E_FORBIDDEN",
    )
    assert_build_input_rejected(
        builds.submit_build, layers={"hardware": "x" * (builds.MAX_LAYER_BYTES + 1)},
        expected="E_TOO_LARGE",
    )


def test_build_command_never_carries_force_or_user_path() -> None:
    request_dir = builds.work_root() / ("0" * 12)
    cmd = builds._build_command(request_dir, "firmware", ["hardware", "bind"])
    assert_no_force(cmd)
    assert "--bind" in cmd and str(request_dir / "bind.yaml") in cmd


def test_named_check_rejects_traversal() -> None:
    assert_name_check(builds._check_name)
    assert_name_check(builds._check_request_id)


def test_stderr_is_sanitized_into_short_issues() -> None:
    raw = (
        "Error processing line 7 of C:\\Users\\pc\\anaconda3\\pywin32.pth:\n"
        "  Traceback (most recent call last):\n"
        "    ModuleNotFoundError: No module named 'pywin32_bootstrap'\n"
        "Remainder of file ignored\n"
        "CMake Error at C:/Users/pc/Documents/project/CMakeLists.txt:12:\n"
        "  error: unknown target\n"
    )
    issues = builds.sanitize_stderr(raw)
    assert_sanitized(issues, raw)
    assert not any("pywin32" in item["message"] for item in issues)


def test_compile_check_is_three_state_and_toolchain_aware() -> None:
    for state in ("passed", "failed", "skipped"):
        assert_compile_state(state)
    with pytest.raises(AssertionError):
        assert_compile_state("ok")
    with pytest.raises(AssertionError):
        assert_compile_state("passed", missing=["cmake"])


def test_artifact_manifest_has_executable_images() -> None:
    good = [{
        "name": name, "size": 100, "sha256": "a" * 64,
        "uri": f"hw2c://artifacts/{'0' * 12}/{name}",
    } for name in ("firmware.elf", "firmware.bin")]
    assert_artifact_manifest(good)
    with pytest.raises(AssertionError):
        assert_artifact_manifest(good[:1])  # source tree only is not a deliverable
    broken = [dict(good[0], sha256="not-a-hash"), good[1]]
    with pytest.raises(AssertionError):
        assert_artifact_manifest(broken)


def test_artifacts_are_readable_only_through_manifest() -> None:
    with pytest.raises(builds.BuildError) as exc:
        builds.read_artifact("0" * 12, "../etc/passwd")
    assert exc.value.code == "E_FORBIDDEN"
    with pytest.raises(builds.BuildError):
        builds.read_artifact("bad-id", "firmware.bin")


def test_build_python_is_explicitly_separate_from_mcp_host() -> None:
    template = (WEB_ROOT / "connector" / "local" / "mcp.json.template").read_text(encoding="utf-8")
    assert '"HW2C_BUILD_PYTHON": "__HW2C_BUILD_PYTHON__"' in template, (
        "generator needs dependencies (jinja2) that the MCP host may not have"
    )
    source = (BACKEND / "services" / "generate_service.py").read_text(encoding="utf-8")
    cmd_source = source.split("def _build_command", 1)[1].split("\ndef ", 1)[0]
    assert '"--force"' not in cmd_source, "--force would skip the compile check"


def test_confirm_cannot_be_coerced_by_the_mcp_sdk() -> None:
    assert_confirm_is_not_coercible(mcp_tools.flash_firmware)

    def typed_confirm(request_id: str, artifact: str, confirm: bool = False) -> dict:
        return {}

    with pytest.raises(AssertionError):
        assert_confirm_is_not_coercible(typed_confirm)


def test_flash_tools_are_registered_only_when_enabled() -> None:
    _, names, _, _ = _registered()
    assert_flash_tool_set(names, enabled=False)
    previous = os.environ.get("HW2C_ENABLE_FLASH")
    os.environ["HW2C_ENABLE_FLASH"] = "1"
    try:
        _, names, _, _ = _registered()
        assert_flash_tool_set(names, enabled=True)
    finally:
        if previous is None:
            os.environ.pop("HW2C_ENABLE_FLASH", None)
        else:
            os.environ["HW2C_ENABLE_FLASH"] = previous


def test_unconfirmed_flash_is_a_plan_without_any_hardware_call() -> None:
    calls: list[str] = []
    original_read, original_write = flash.read_flash, flash._write_flash
    flash.read_flash = lambda _plan: calls.append("read") or b""
    flash._write_flash = lambda _plan: calls.append("write")
    try:
        with fake_build(0x08000DE5) as (request_id, _, _):
            plan = mcp_tools.flash_firmware(request_id, "combined.bin", confirm=False)
            assert_dry_run(plan, calls)
            assert_flash_plan(plan, "combined.bin", BOOTLOADER, "")
            truthy_string = mcp_tools.flash_firmware(request_id, "combined.bin", confirm="true")
            assert_dry_run(truthy_string, calls)
    finally:
        flash.read_flash, flash._write_flash = original_read, original_write


def test_flash_plan_rejects_an_image_linked_for_another_slot() -> None:
    with fake_build(0x08005DE5, name="app.bin") as (request_id, _, _):
        with pytest.raises(flash.FlashError) as exc:
            flash.plan_flash(request_id, "app.bin", "B", for_write=True)
        assert exc.value.code == "E_FORBIDDEN"
        with pytest.raises(flash.FlashError):
            flash.plan_flash(request_id, "app.bin", for_write=True)
        accepted = flash.plan_flash(request_id, "app.bin", "A", for_write=True)
        assert_slot_link(accepted, "A")
        assert_flash_plan(accepted, "app.bin", SLOT_A, "A")
        # verify is read-only: it may auto-locate the slot from the vector table.
        verified = flash.plan_flash(request_id, "app.bin", for_write=False)
        assert_slot_link(verified, "")
        assert_flash_plan(verified, "app.bin", SLOT_A, "A")


def test_combined_image_may_span_bootloader_and_slot_a() -> None:
    with fake_build(0x08000DE5, size=16 * 1024) as (request_id, _, _):
        plan = flash.plan_flash(request_id, "combined.bin", for_write=True)
        assert_flash_plan(plan, "combined.bin", BOOTLOADER, "")
        assert_image_fits(plan, SLOT_B)


def test_flash_compares_before_writing_and_after_writing() -> None:
    with fake_build(0x08000DE5) as (request_id, _, image):
        plan = flash.plan_flash(request_id, "combined.bin", for_write=True)
        different = bytearray(image)
        different[10] ^= 0xFF
        sequence = iter([bytes(different), image])
        writes: list[str] = []
        original_read, original_write = flash.read_flash, flash._write_flash
        flash.read_flash = lambda _plan: next(sequence)
        flash._write_flash = lambda _plan: writes.append("write")
        try:
            result = flash.flash(plan)
            assert_write_result(result, bytes(different), image, writes)
            writes.clear()
            flash.read_flash = lambda _plan: image
            same = flash.flash(plan)
            assert_write_result(same, image, image, writes)
        finally:
            flash.read_flash, flash._write_flash = original_read, original_write


def test_verify_flash_reports_first_differing_byte() -> None:
    with fake_build(0x08000DE5) as (request_id, _, image):
        device = bytearray(image)
        device[7] = 0x5A
        original_read = flash.read_flash
        flash.read_flash = lambda _plan: bytes(device)
        try:
            result = mcp_tools.verify_flash(request_id, "combined.bin")
            assert_verify_result(result, image, bytes(device))
        finally:
            flash.read_flash = original_read


def test_serial_port_validation_and_replay_guard() -> None:
    for bad in ("", "COM0", "/etc/passwd;rm", "COM5;ls"):
        with pytest.raises(flash.FlashError):
            flash.capture_serial(bad)
    with pytest.raises(flash.FlashError):
        flash.capture_serial("COM5", seconds=999)
    with pytest.raises(flash.FlashError):
        flash.capture_serial("COM5", trigger="(")
    assert_serial_frame({
        "purged_on_open": True, "rate_guard_trips": 0, "text": "System ready\r\n",
    })
    assert_serial_frame({
        "purged_on_open": True, "rate_guard_trips": 2, "text": "System ready\r\n",
    }, replay=True)


def test_pyocd_target_is_derived_from_hardware_yaml_not_guessed() -> None:
    with fake_build(0x080005DE5) as (_, project, _):
        assert_target_is_explicit(flash._target(project))
    with fake_build(0x080005DE5, part="STM32F999XYZ") as (_, project, _):
        with pytest.raises(flash.FlashError) as exc:
            flash._target(project)
        assert exc.value.code == "E_FORBIDDEN"


def test_connector_opt_in_and_skill_describe_hardware_safety() -> None:
    template = (WEB_ROOT / "connector" / "local" / "mcp.json.template").read_text(encoding="utf-8")
    for placeholder in ("__HW2C_ENABLE_FLASH__", "__HW2C_PYOCD__", "__HW2C_PYOCD_PYTHON__"):
        assert placeholder in template, f"installer cannot configure {placeholder}"
    skill = (WEB_ROOT / "connector" / "local" / "skills" / "hw2c-firmware" / "SKILL.md").read_text(encoding="utf-8")
    for tool in HARDWARE_TOOL_SET:
        assert tool in skill, f"SKILL.md does not mention {tool}"
    assert "confirm" in skill and "布尔 true" in skill, "model must not treat a string as confirmation"
    assert "combined.bin" in skill and "槽 B" in skill
    assert "rate_guard_trips" in skill


if __name__ == "__main__":
    # Stdlib runner for environments that have the MCP SDK but not pytest.
    failures: list[str] = []
    for _name, _fn in sorted(list(globals().items())):
        if not _name.startswith("test_") or not callable(_fn):
            continue
        try:
            _fn()
            print(f"PASS {_name}")
        except Exception as _exc:  # noqa: BLE001
            failures.append(f"FAIL {_name}: {type(_exc).__name__}: {_exc}")
            print(failures[-1])
    raise SystemExit(1 if failures else 0)
