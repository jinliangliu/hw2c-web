"""Mutation check for the MCP contract guardrails.

Each mutant feeds a deliberately broken input to a guardrail helper.  If the
helper does not raise AssertionError, the guardrail is a tautology.
Run with an interpreter that has the MCP SDK:

    python tests/mutate_mcp_contract.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import test_mcp_contract as contract  # noqa: E402


def _expect_raises(label: str, fn) -> bool:
    try:
        fn()
    except AssertionError:
        print(f"CAUGHT  {label}")
        return True
    print(f"MISSED  {label}")
    return False


def main() -> int:
    local = contract.WEB_ROOT / "connector" / "local"
    meta = json.loads((local / "connector-meta.json").read_text(encoding="utf-8"))
    generated = json.loads(
        (local / "mcp.json.template").read_text(encoding="utf-8")
        .replace("__HW2C_PYTHON__", "python")
        .replace("__HW2C_BACKEND__", "backend")
        .replace("__HW2C_ROOT__", "hw2c")
    )

    mutants = []

    def add(label, fn):
        mutants.append((label, fn))

    add("delete one registered tool", lambda: contract.assert_tool_set(
        sorted(contract.EXPECTED_TOOLS - {"validate_config"})
    ))
    add("register an unimplemented flash tool", lambda: contract.assert_no_hardware_tools(
        sorted(contract.EXPECTED_TOOLS | {"flash_firmware"})
    ))
    add("drop a knowledge resource template", lambda: contract.assert_resources_cover(
        ["hw2c://requirements"],
        sorted(contract.EXPECTED_TEMPLATES - {"hw2c://format/{name}.json"}),
    ))
    add("add token auth to a local Connector", lambda: contract.assert_connector_meta_is_local_only(
        {**meta, "auth_mode": "token"}, generated
    ))
    bad_two = copy.deepcopy(generated)
    bad_two["mcpServers"]["second"] = {"type": "stdio", "command": "python"}
    add("configure two MCP servers", lambda: contract.assert_connector_meta_is_local_only(
        meta, bad_two
    ))
    bad_http = copy.deepcopy(generated)
    bad_http["mcpServers"]["hw2c-local"]["type"] = "streamableHttp"
    add("switch local Connector to HTTP", lambda: contract.assert_connector_meta_is_local_only(
        meta, bad_http
    ))

    # --- P2: async build contract ---
    add("return a finished build synchronously", lambda: contract.assert_async_envelope({
        "request_id": "0" * 12,
        "status": "succeeded",
        "artifact_manifest": [{"name": "base.bin"}],
    }))
    add("report passed with an incomplete toolchain", lambda: contract.assert_compile_state(
        "passed", missing=["cmake"]
    ))
    add("restore --force in the generator command", lambda: contract.assert_no_force([
        "python", "-m", "parser.cli", "gen",
        "-o", f"/tmp/{'0' * 12}/firmware", "--force",
    ]))
    add("let the caller choose the output directory", lambda: contract.assert_no_force([
        "python", "-m", "parser.cli", "gen", "-o", "/etc/firmware",
    ]))
    raw = "CMake Error at C:/Users/pc/project/CMakeLists.txt:12: error: unknown target"
    add("pass raw stderr through to the model", lambda: contract.assert_sanitized(
        [{"code": "E", "message": raw, "location": ""}], raw
    ))
    add("accept a traversal project name", lambda: contract.assert_build_input_rejected(
        lambda _layers, name, _options=None: {"ok": True}, name="../../etc"
    ))
    add("accept an unsafe artifact name", lambda: contract.assert_name_check(
        lambda name: name
    ))
    good = [{
        "name": name, "size": 100, "sha256": "a" * 64,
        "uri": f"hw2c://artifacts/{'0' * 12}/{name}",
    } for name in ("firmware.elf", "firmware.bin")]
    add("manifest with source only, no executable", lambda: contract.assert_artifact_manifest(
        good[:1]
    ))
    add("delete a P2 tool registration", lambda: contract.assert_tool_set(
        sorted(contract.EXPECTED_TOOLS - {"get_build_status"})
    ))
    add("drop the artifact resource template", lambda: contract.assert_resources_cover(
        ["hw2c://requirements"],
        sorted(contract.EXPECTED_TEMPLATES - {"hw2c://artifacts/{request_id}/{filename}"}),
    ))
    add("allow a fourth compile_check state", lambda: contract.assert_compile_state("ok"))

    caught = sum(_expect_raises(label, fn) for label, fn in mutants)
    print(f"\n{caught}/{len(mutants)} mutants caught")
    return 0 if caught == len(mutants) else 1


if __name__ == "__main__":
    raise SystemExit(main())
