"""End-to-end regression test for hw2c-web.

Verifies the highest-value contract: a real EDA netlist/BOM can be parsed
through the FastAPI backend and the returned six-layer YAML can be passed
back to generate a firmware ZIP containing the expected generated files.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from paths import get_hw2c_root  # noqa: E402

HW2C_ROOT = get_hw2c_root()
sys.path.insert(0, str(HW2C_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from app import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _read_upload(path: Path):
    return path.read_bytes()


def test_parse_then_generate_closed_loop(client: TestClient) -> None:
    netlist = HW2C_ROOT / "parser" / "hardware_design" / "stm32g0b1_demo.enet"
    bom = HW2C_ROOT / "parser" / "hardware_design" / "stm32g0b1_demo.csv"

    if not netlist.exists() or not bom.exists():
        pytest.skip("hw2c sample netlist/BOM not available")

    parse_resp = client.post(
        "/api/parse",
        files={
            "netlist": (netlist.name, _read_upload(netlist), "application/octet-stream"),
            "bom": (bom.name, _read_upload(bom), "text/csv"),
        },
    )
    assert parse_resp.status_code == 200, parse_resp.text
    parsed = parse_resp.json()

    assert parsed["hardware_yaml"]
    assert parsed["task_yaml"]
    assert parsed["components_yaml"]
    assert parsed["params_yaml"]
    assert parsed["pubsub_yaml"]

    generate_resp = client.post(
        "/api/generate",
        json={
            "hardware_yaml": parsed["hardware_yaml"],
            "task_yaml": parsed["task_yaml"],
            "components_yaml": parsed["components_yaml"],
            "bind_yaml": parsed["bind_yaml"],
            "params_yaml": parsed["params_yaml"],
            "pubsub_yaml": parsed["pubsub_yaml"],
            "project_name": "e2e_regression",
        },
    )
    assert generate_resp.status_code == 200, generate_resp.text

    archive = zipfile.ZipFile(io.BytesIO(generate_resp.content))
    names = archive.namelist()

    required_markers = [
        "CMakeLists.txt",
        "src/main.c",
        "component_registry.c",
        "component_bus.c",
        "param_registry.c",
        "led_component.c",
        "btn_component.c",
    ]
    for marker in required_markers:
        assert any(marker in name for name in names), f"missing generated file: {marker}"
