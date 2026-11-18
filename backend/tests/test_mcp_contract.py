"""Contract guardrails for the local MCP Connector.

The assert_* helpers are deliberately module-level: the mutation script feeds
them deliberately broken inputs and requires an AssertionError.  A guardrail
that stays green after mutation is a tautology and must be rewritten.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
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
from services import catalog_service, generate_service as builds  # noqa: E402
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
        .replace("__HW2C_WORK_ROOT__", "work-root"))
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
