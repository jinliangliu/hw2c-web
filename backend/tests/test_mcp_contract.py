"""Contract guardrails for the local MCP Connector.

The assert_* helpers are deliberately module-level: the mutation script feeds
them deliberately broken inputs and requires an AssertionError.  A guardrail
that stays green after mutation is a tautology and must be rewritten.
"""

from __future__ import annotations

import asyncio
import json
import sys
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

        def __enter__(self):
            return self

        def __exit__(self, kind, value, _tb):
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
from services import catalog_service  # noqa: E402
from services.validate_service import validate_config  # noqa: E402

EXPECTED_TOOLS = {
    "parse_eda",
    "validate_config",
    "list_examples",
    "get_example",
    "get_mcu_pinout",
}
EXPECTED_TEMPLATES = {
    "hw2c://requirements/{section}",
    "hw2c://docs/user-guide/{layer}-yaml",
    "hw2c://schema/{layer}",
    "hw2c://examples/{name}/{layer}.yaml",
    "hw2c://format/{name}.json",
    "hw2c://models/{name}.yaml",
}
HARDWARE_TOOLS = {"flash_firmware", "verify_flash", "list_probes", "capture_serial"}


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


def _registered():
    server = create_server()
    tools = asyncio.run(server.list_tools())
    static = asyncio.run(server.list_resources())
    templates = asyncio.run(server.list_resource_templates())
    return server, [t.name for t in tools], [r.uri for r in static], [t.uri_template for t in templates]


def test_p1_tool_set_is_exact() -> None:
    _, names, _, _ = _registered()
    assert_tool_set(names)


def test_no_unimplemented_hardware_or_generation_tools() -> None:
    _, names, _, _ = _registered()
    assert_no_hardware_tools(names)
    assert "generate_firmware" not in names, "no executor exists in P1"


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
        .replace("__HW2C_ROOT__", "hw2c"))
    assert_connector_meta_is_local_only(meta, generated)


def test_connector_template_has_no_machine_specific_path() -> None:
    template = (WEB_ROOT / "connector" / "local" / "mcp.json.template").read_text(encoding="utf-8")
    for placeholder in ("__HW2C_PYTHON__", "__HW2C_BACKEND__", "__HW2C_ROOT__"):
        assert placeholder in template
    assert "C:/" not in template and "C:\\" not in template


def test_skill_tells_the_model_about_current_limits() -> None:
    skill = (WEB_ROOT / "connector" / "local" / "skills" / "hw2c-firmware" / "SKILL.md").read_text(encoding="utf-8")
    assert "尚未注册" in skill
    assert "parse_eda" in skill and "validate_config" in skill


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
