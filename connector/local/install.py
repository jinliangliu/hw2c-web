"""Generate connector/local/mcp.json with this machine's absolute paths.

The Connector spec forbids a managed runtime for Python stdio servers, so the
command must be an absolute interpreter path.  Never commit a generated
mcp.json — it is machine-specific.

Usage:  python connector/local/install.py [python_executable] [--enable-flash]

Hardware tools stay unregistered unless --enable-flash is passed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB_ROOT = HERE.parent.parent
BACKEND = WEB_ROOT / "backend"
HW2C_ROOT = WEB_ROOT.parent / "hw2c"

# Both must be true for the stdio server to import hw2c's pure functions.
PROBE = "import mcp; from mcp_server.server import create_server; create_server()"
# The generator is a separate subprocess and needs the hw2c dependency set.
# On this machine the MCP-capable Python does NOT have jinja2.
BUILD_PROBE = "import jinja2, yaml, pydantic"


def _candidates(explicit: str | None) -> list[Path]:
    if explicit:
        return [Path(explicit).resolve()]
    out: list[Path] = [Path(sys.executable).resolve()]
    home = Path.home()
    envs = home / ".workbuddy" / "binaries" / "python" / "envs"
    if envs.is_dir():
        out.extend(sorted(envs.glob("*/Scripts/python.exe")))
        out.extend(sorted(envs.glob("*/bin/python")))
    return out


def _usable(python: Path) -> bool:
    if not python.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python), "-c", PROBE],
            cwd=str(BACKEND),
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _build_candidates(host: Path) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    raw = (
        os.environ.get("HW2C_BUILD_PYTHON"),
        shutil.which("python"),
        shutil.which("python3"),
        str(Path.home() / "anaconda3" / "python.exe"),
        str(Path.home() / "miniconda3" / "python.exe"),
        str(host),
    )
    for item in raw:
        if not item:
            continue
        path = Path(item).resolve()
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _usable_build(python: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python), "-c", BUILD_PROBE],
            cwd=str(WEB_ROOT), capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _has_pyocd(python: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python), "-c", "import pyocd"],
            cwd=str(WEB_ROOT), capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _pyocd_setup(host: Path) -> tuple[str, str]:
    """Return (executable, python) for pyOCD; empty strings when unused."""
    binary = os.environ.get("HW2C_PYOCD") or shutil.which("pyocd") or ""
    candidates = [Path(os.environ["HW2C_PYOCD_PYTHON"])] if os.environ.get("HW2C_PYOCD_PYTHON") else []
    if binary:
        parent = Path(binary).resolve().parent
        candidates.extend([parent / "python.exe", parent / "python"])
    candidates.extend([host, Path(sys.executable)])
    for path in candidates:
        try:
            if path.is_file() and _has_pyocd(path.resolve()):
                return binary, str(path.resolve()).replace("\\", "/")
        except OSError:
            continue
    return binary, ""


def main() -> int:
    args = sys.argv[1:]
    enable_flash = "--enable-flash" in args
    explicit = next((item for item in args if not item.startswith("--")), None)
    if not (BACKEND / "hw2c_connector" / "local.py").is_file():
        print(f"ERROR: server package not found under {BACKEND}", file=sys.stderr)
        return 2

    python = next((p for p in _candidates(explicit) if _usable(p)), None)
    if python is None:
        print(
            "ERROR: no Python with the 'mcp' SDK found. Install it into the "
            "interpreter you want WorkBuddy to use, then pass its path explicitly.",
            file=sys.stderr,
        )
        return 3

    build_python = next(
        (p for p in _build_candidates(python) if _usable_build(p)), None
    )
    if build_python is None:
        print(
            "ERROR: no Python with hw2c's generator dependencies "
            "(jinja2, yaml, pydantic) found; generation would fail.",
            file=sys.stderr,
        )
        return 4

    hw2c_root = Path(HW2C_ROOT)
    if not (hw2c_root / "generator" / "schemas").is_dir():
        env_root = __import__("os").environ.get("HW2C_ROOT")
        if env_root:
            hw2c_root = Path(env_root).resolve()

    work_root = Path(tempfile.gettempdir()) / "hw2c-mcp-builds"
    pyocd_bin, pyocd_python = _pyocd_setup(python)
    if enable_flash and (not pyocd_bin or not pyocd_python):
        print(
            "ERROR: --enable-flash needs pyocd on PATH and a Python that can "
            "import pyocd (set HW2C_PYOCD / HW2C_PYOCD_PYTHON if detection fails).",
            file=sys.stderr,
        )
        return 5
    template = (HERE / "mcp.json.template").read_text(encoding="utf-8")
    rendered = (
        template
        .replace("__HW2C_PYTHON__", str(python).replace("\\", "/"))
        .replace("__HW2C_BACKEND__", str(BACKEND).replace("\\", "/"))
        .replace("__HW2C_ROOT__", str(hw2c_root).replace("\\", "/"))
        .replace("__HW2C_BUILD_PYTHON__", str(build_python).replace("\\", "/"))
        .replace("__HW2C_WORK_ROOT__", str(work_root).replace("\\", "/"))
        .replace("__HW2C_ENABLE_FLASH__", "1" if enable_flash else "0")
        .replace("__HW2C_PYOCD__", pyocd_bin.replace("\\", "/"))
        .replace("__HW2C_PYOCD_PYTHON__", pyocd_python)
    )
    target = HERE / "mcp.json"
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target}")
    print(f"  python    = {python}")
    print(f"  cwd       = {BACKEND}")
    print(f"  HW2C_ROOT = {hw2c_root}")
    print(f"  build py  = {build_python}")
    print(f"  work root = {work_root}")
    print(f"  flash     = {'enabled' if enable_flash else 'disabled'} (pyocd={pyocd_bin or '-'})")
    print("Install this folder as a local Connector in WorkBuddy (no publish/review needed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
