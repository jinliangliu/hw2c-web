"""MCP resources — read-only knowledge surface for hw2c.

Resources complement (not duplicate) the existing codegraph MCP: codegraph
indexes Python and vendored C but has zero entries for ``.j2`` / ``.ld``, so
requirements, six-layer contracts and format truth files must be exposed here.
``.workbuddy/`` and ``static/`` are deliberately never exposed.
"""

from __future__ import annotations

import json

from services import catalog_service, generate_service

_FORMATS = ("fota_format", "ymodem_format")


def _text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def register_resources(mcp) -> None:
    """Register the read-only resource set on an MCP server instance."""

    @mcp.resource(
        "hw2c://requirements",
        name="hw2c requirements",
        description="hw2c 需求唯一入口 docs/requirements.md（FR/NFR/接口契约/路线图）",
        mime_type="text/markdown",
    )
    def requirements() -> str:
        return catalog_service.get_requirements()

    @mcp.resource(
        "hw2c://requirements/{section}",
        name="hw2c requirements section",
        description="需求文档的一个二级章节，section 为标题文字（如 9. 路线图）",
        mime_type="text/markdown",
    )
    def requirements_section(section: str) -> str:
        return catalog_service.get_requirements(section)

    @mcp.resource(
        "hw2c://docs/user-guide/{layer}-yaml",
        name="hw2c layer guide",
        description="六层 YAML 的用户指南（hardware/task/components/bind/params/pubsub）",
        mime_type="text/markdown",
    )
    def layer_guide(layer: str) -> str:
        if layer not in catalog_service.LAYERS:
            raise ValueError(f"E_FORBIDDEN: unknown layer {layer!r}")
        return catalog_service._safe_read(
            catalog_service._HW2C_ROOT / "docs" / "user-guide", f"{layer}-yaml.md"
        )

    @mcp.resource(
        "hw2c://schema/{layer}",
        name="hw2c layer schema",
        description="由权威 Pydantic 模型动态生成的 JSON schema（不是手抄副本）",
        mime_type="application/json",
    )
    def layer_schema(layer: str) -> str:
        return _text(catalog_service.get_schema(layer))

    @mcp.resource(
        "hw2c://examples/{name}/{layer}.yaml",
        name="hw2c example layer",
        description="某个自带示例的一层 YAML",
        mime_type="text/yaml",
    )
    def example_layer(name: str, layer: str) -> str:
        return catalog_service.get_example(name, layer)["yaml"]

    @mcp.resource(
        "hw2c://format/{name}.json",
        name="hw2c format truth",
        description="FOTA / YMODEM 格式的唯一真源（fota_format / ymodem_format）",
        mime_type="application/json",
    )
    def format_truth(name: str) -> str:
        if name not in _FORMATS:
            raise ValueError(f"E_FORBIDDEN: unknown format {name!r}")
        return catalog_service._safe_read(
            catalog_service._HW2C_ROOT / "generator" / "data", f"{name}.json"
        )

    @mcp.resource(
        "hw2c://models/{name}.yaml",
        name="hw2c peripheral model",
        description="外设模型 YAML（models/ 目录）",
        mime_type="text/yaml",
    )
    def peripheral_model(name: str) -> str:
        return catalog_service._safe_read(catalog_service._HW2C_ROOT / "models", name)

    @mcp.resource(
        "hw2c://artifacts/{request_id}/{filename}",
        name="hw2c build artifact",
        description="某次构建产出的固件镜像（.elf/.bin/.hex/.map），仅 manifest 内的文件可读",
        mime_type="application/octet-stream",
    )
    def build_artifact(request_id: str, filename: str) -> bytes:
        return generate_service.read_artifact(request_id, filename)
