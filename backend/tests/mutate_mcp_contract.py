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

    caught = sum(_expect_raises(label, fn) for label, fn in mutants)
    print(f"\n{caught}/{len(mutants)} mutants caught")
    return 0 if caught == len(mutants) else 1


if __name__ == "__main__":
    raise SystemExit(main())
