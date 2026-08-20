"""Generate route — accepts YAML, runs hw2c gen, returns project zip stream."""
import shutil
import tempfile
import subprocess
import sys
import io
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from paths import get_hw2c_root

router = APIRouter(prefix="/api", tags=["generate"])

# hw2c project root (sibling layout in dev, in-workspace layout in CI)
_HW2C_ROOT = get_hw2c_root()


class GenerateRequest(BaseModel):
    """Request body for /api/generate."""
    hardware_yaml: str = Field(default="", description="hardware.yaml content")
    task_yaml: str = Field(default="", description="task.yaml content")
    components_yaml: str = Field(default="", description="components.yaml content (optional)")
    bind_yaml: str = Field(default="", description="bind.yaml content (optional)")
    params_yaml: str = Field(default="", description="params.yaml content (optional)")
    pubsub_yaml: str = Field(default="", description="pubsub.yaml content (optional)")
    project_name: str = Field(default="firmware", description="Top-level dir name in zip")
    yaml: str = Field(default="", description="[DEPRECATED] legacy monolithic YAML")


@router.post("/generate")
async def generate_firmware(req: GenerateRequest) -> StreamingResponse:
    """
    Accept hardware.yaml + task.yaml + components.yaml + bind.yaml + params.yaml
    + pubsub.yaml, run hw2c gen, return a .zip download stream.

    Backward compatible: if only "yaml" field is sent (old frontend), treat as legacy.
    """
    if not _HW2C_ROOT.exists():
        raise HTTPException(500, "hw2c project root not found at " + str(_HW2C_ROOT))

    # Backward compat: old frontend sends "yaml" only
    hardware_content = req.hardware_yaml or req.yaml
    task_content = req.task_yaml
    components_content = req.components_yaml
    bind_content = req.bind_yaml
    params_content = req.params_yaml
    pubsub_content = req.pubsub_yaml

    if not hardware_content:
        raise HTTPException(400, "hardware_yaml (or legacy yaml) is required")

    tmpdir = Path(tempfile.mkdtemp(prefix="hw2c_gen_"))
    hw_path = tmpdir / "hardware.yaml"
    output_dir = tmpdir / req.project_name

    try:
        # 1. Write YAML files
        hw_path.write_text(hardware_content, encoding="utf-8")

        task_path = None
        if task_content:
            task_path = tmpdir / "task.yaml"
            task_path.write_text(task_content, encoding="utf-8")

        components_path = None
        if components_content:
            components_path = tmpdir / "components.yaml"
            components_path.write_text(components_content, encoding="utf-8")

        bind_path = None
        if bind_content:
            bind_path = tmpdir / "bind.yaml"
            bind_path.write_text(bind_content, encoding="utf-8")

        params_path = None
        if params_content:
            params_path = tmpdir / "params.yaml"
            params_path.write_text(params_content, encoding="utf-8")

        pubsub_path = None
        if pubsub_content:
            pubsub_path = tmpdir / "pubsub.yaml"
            pubsub_path.write_text(pubsub_content, encoding="utf-8")

        # 2. Run hw2c gen with six-layer support
        cmd = [
            sys.executable, "-m", "parser.cli", "gen",
            "-i", str(hw_path),
            "-o", str(output_dir),
            "--force",
        ]
        if task_path:
            cmd.extend(["--task", str(task_path)])
        if components_path:
            cmd.extend(["--components", str(components_path)])
        if bind_path:
            cmd.extend(["--bind", str(bind_path)])
        if params_path:
            cmd.extend(["--params", str(params_path)])
        if pubsub_path:
            cmd.extend(["--pubsub", str(pubsub_path)])

        result = subprocess.run(
            cmd,
            cwd=str(_HW2C_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            detail = result.stderr[-800:] or result.stdout[-800:] or "Unknown error"
            raise HTTPException(500, f"hw2c gen failed:\n{detail}")

        # 3. Zip output directory in memory
        zip_buf = io.BytesIO()
        shutil.make_archive(
            str(tmpdir / req.project_name),
            "zip",
            str(output_dir),
        )
        with open(str(tmpdir / f"{req.project_name}.zip"), "rb") as f:
            zip_buf.write(f.read())
        zip_buf.seek(0)

        zip_filename = f"{req.project_name}.zip"

        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_filename}"',
                "X-Generated-Files": str(sum(1 for _ in output_dir.rglob("*") if _.is_file())),
            },
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(500, "Generation timed out (>120s)")
    finally:
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)
