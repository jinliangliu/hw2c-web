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
        .replace("__HW2C_BUILD_PYTHON__", "build-python")
        .replace("__HW2C_WORK_ROOT__", "work-root")
        .replace("__HW2C_ENABLE_FLASH__", "0")
        .replace("__HW2C_PYOCD__", "")
        .replace("__HW2C_PYOCD_PYTHON__", ""))

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
    raw = "CMake Error at C:/Users/builder/project/CMakeLists.txt:12: error: unknown target"
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

    # --- P3: hardware tools ---
    add("register hardware tools by default", lambda: contract.assert_flash_tool_set(
        sorted(set(contract.EXPECTED_TOOLS) | contract.HARDWARE_TOOLS), False
    ))
    add("omit a tool when flash is enabled", lambda: contract.assert_flash_tool_set(
        sorted(contract.HARDWARE_TOOL_SET - {"verify_flash"}), True
    ))
    add("enable hardware tools in the shipped config", lambda: contract.assert_connector_meta_is_local_only(
        meta, {**generated, "mcpServers": {"hw2c-local": {
            **generated["mcpServers"]["hw2c-local"],
            "env": {**generated["mcpServers"]["hw2c-local"]["env"], "HW2C_ENABLE_FLASH": "1"},
        }}}
    ))
    add("cut off a full readback at 30 s", lambda: contract.assert_connector_meta_is_local_only(
        meta, {**generated, "mcpServers": {"hw2c-local": {
            **generated["mcpServers"]["hw2c-local"], "timeout": 30000,
        }}}
    ))
    image = b"\x00" * 64
    add("touch pyOCD during an unconfirmed dry-run", lambda: contract.assert_dry_run(
        {"dry_run": True, "confirm_required": True}, ["pyocd load"]
    ))
    add("treat the string 'true' as confirmation", lambda: contract.assert_dry_run(
        {"dry_run": False, "confirm_required": True, "written": True}, []
    ))
    add("leak raw image bytes in a dry-run result", lambda: contract.assert_dry_run(
        {"dry_run": True, "confirm_required": True, "_image": image}, []
    ))
    good_plan = {
        "artifact": "combined.bin", "address": contract.BOOTLOADER, "slot": "",
        "region": "bootloader", "erase": "sector", "reset_after": False,
        "dry_run": True, "sha256": "a" * 64,
    }
    add("flash combined.bin into slot B", lambda: contract.assert_flash_plan(
        {**good_plan, "address": contract.SLOT_B}, "combined.bin", contract.BOOTLOADER, ""
    ))
    add("whole-chip erase on a slot write", lambda: contract.assert_flash_plan(
        {**good_plan, "erase": "chip"}, "combined.bin", contract.BOOTLOADER, ""
    ))
    add("accept slot A image for slot B", lambda: contract.assert_slot_link(
        {"region": "slot_a", "address": contract.SLOT_A}, "B"
    ))
    add("write an already-identical image", lambda: contract.assert_write_result(
        {"dry_run": False, "before_sha256": contract._sha(image),
         "image_sha256": contract._sha(image), "written": True, "match": True,
         "reset_performed": False}, image, image, []
    ))
    device = bytearray(image)
    device[3] = 0xFF
    add("report match despite a differing byte", lambda: contract.assert_verify_result(
        {"match": True, "first_diff_offset": 3,
         "image_sha256": contract._sha(image), "device_sha256": contract._sha(bytes(device))},
        image, bytes(device)
    ))
    add("accept replayed serial data without a rate guard", lambda: contract.assert_serial_frame(
        {"purged_on_open": True, "rate_guard_trips": 0, "text": "REPLAY\r\n"}, replay=True
    ))
    add("guess an unknown pyOCD target", lambda: contract.assert_target_is_explicit("auto"))
    add("reject combined.bin for spanning two regions", lambda: contract.assert_image_fits(
        {"address": contract.BOOTLOADER, "size": 122668}, contract.SLOT_A
    ))

    def typed_confirm(request_id: str, artifact: str, confirm: bool = False) -> dict:
        return {}

    add("let the SDK coerce 'true' into a confirmation", lambda: contract.assert_confirm_is_not_coercible(
        typed_confirm
    ))

    caught = sum(_expect_raises(label, fn) for label, fn in mutants)
    print(f"\n{caught}/{len(mutants)} mutants caught")
    return 0 if caught == len(mutants) else 1


if __name__ == "__main__":
    raise SystemExit(main())
