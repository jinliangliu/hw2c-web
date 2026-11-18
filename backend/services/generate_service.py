"""Async firmware build service for the local MCP Connector.

The hw2c generator cannot be called in-process: ``parser.cli gen`` rewrites
``sys.argv``, ``generate_project()`` has 11 ``sys.exit`` paths and mutates the
global logging configuration.  Every build therefore runs in a fresh
subprocess, in a fresh directory, with no ``--force``.

No ``--force`` is also a correctness requirement, not just a safety one:
``generator/generate.py:1307`` skips the compile check entirely when it is
set.  A build that passed only because the check was skipped must never be
reported as ``compile_check=passed``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from paths import get_hw2c_root

_HW2C_ROOT = get_hw2c_root()
LAYERS = ("hardware", "task", "components", "bind", "params", "pubsub")
MAX_LAYER_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
GEN_TIMEOUT_S = 120
QUEUE_TIMEOUT_S = 30
MAX_CONCURRENT = 2
TASK_TTL_S = 3600
BUILD_IMPORTS = ("jinja2", "yaml", "pydantic")

# toolchain.cmake requires the whole GNU Arm toolchain, not just gcc.  If any
# of these is missing hw2c's own check silently returns success.
TOOLCHAIN = (
    "cmake", "ninja",
    "arm-none-eabi-gcc", "arm-none-eabi-g++",
    "arm-none-eabi-objcopy", "arm-none-eabi-objdump", "arm-none-eabi-size",
)
ARTIFACT_SUFFIXES = (".elf", ".bin", ".hex", ".map")
_REQUEST_ID = re.compile(r"^[0-9a-f]{12}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_PATH_IN_TEXT = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s:;'\"]+")
# Interpreter startup noise (e.g. a broken pywin32 .pth in a conda env) is not
# a build failure.  Filtering it keeps the model from reporting a false error.
_STARTUP_NOISE = (
    "pywin32_bootstrap", "Error processing line", "Remainder of file ignored",
    "frozen site",
)

_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT)
_LOCK = threading.Lock()
_TASKS: dict[str, dict] = {}


class BuildError(Exception):
    """A rejected build request, carrying a stable MCP error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message[:200]


def work_root() -> Path:
    """Directory holding per-request workspaces, overridable for tests."""
    configured = os.environ.get("HW2C_WORK_ROOT")
    base = Path(configured) if configured else Path(tempfile.gettempdir()) / "hw2c-mcp-builds"
    return base.resolve()


def build_python() -> str:
    """Interpreter used for the generator subprocess.

    This is deliberately separate from ``sys.executable``: the interpreter that
    hosts the MCP server only needs the SDK, while the generator needs the hw2c
    dependency set (jinja2/yaml/pydantic).  On this machine those are two
    different Python installations.  The Connector installer resolves and
    writes ``HW2C_BUILD_PYTHON``; without it we fall back to the MCP host and
    report missing modules as build issues rather than guessing a path.
    """
    return os.environ.get("HW2C_BUILD_PYTHON") or sys.executable


def _check_name(name: str, what: str = "name") -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or Path(name).name != name
        or not _SAFE_NAME.fullmatch(name)
    ):
        raise BuildError("E_FORBIDDEN", f"unsafe {what}: {name!r}")
    return name


def _check_request_id(request_id: str) -> str:
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise BuildError("E_NOT_FOUND", f"unknown request_id: {request_id!r}")
    return request_id


def _purge_expired(now: float | None = None) -> None:
    """Drop finished tasks after TTL; best-effort cleanup of their directories."""
    now = time.monotonic() if now is None else now
    with _LOCK:
        stale = [
            rid for rid, task in _TASKS.items()
            if task["status"] in ("succeeded", "failed", "cancelled")
            and now - task["finished_at"] > TASK_TTL_S
        ]
        for rid in stale:
            _TASKS.pop(rid, None)
    for rid in stale:
        try:
            shutil.rmtree(work_root() / rid, ignore_errors=True)
        except Exception:  # noqa: BLE001 - cleanup is best effort, never a tool result
            pass


def missing_tools() -> list[str]:
    """Tools that hw2c's compile check needs but this machine lacks."""
    return [name for name in TOOLCHAIN if shutil.which(name) is None]


def sanitize_stderr(raw: str) -> list[dict]:
    """Turn build output into short issues without leaking local paths.

    The raw stream is never returned: it contains absolute paths, the user
    name and occasionally environment details.  Only error-shaped lines are
    kept, and every absolute path is replaced with ``<path>``.
    """
    issues: list[dict] = []
    # Conda's broken .pth prints a multi-line traceback at interpreter startup.
    # Drop the whole block before looking for error-shaped lines; otherwise the
    # model sees a "Traceback" that has nothing to do with the build.
    text = re.sub(
        r"Error processing line.*?Remainder of file ignored",
        "", raw or "", flags=re.S,
    )
    for line in text.splitlines():
        if not re.search(r"error|fatal|critical|traceback|failed", line, re.I):
            continue
        if any(noise in line for noise in _STARTUP_NOISE):
            continue
        clean = _PATH_IN_TEXT.sub("<path>", line).strip()
        clean = re.sub(r"\s+", " ", clean)[:200]
        if not clean:
            continue
        issues.append({
            "code": "E_BUILD_OUTPUT",
            "message": clean,
            "location": "",
        })
        if len(issues) >= 20:
            break
    return issues


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_artifacts(request_dir: Path, project_name: str, request_id: str) -> list[dict]:
    """Collect executable images from the generated project's build/ tree."""
    project_dir = request_dir / project_name
    build_dir = project_dir / "build"
    if not build_dir.is_dir():
        return []
    found: list[dict] = []
    # Only top-level build/ images are firmware.  Recursive scanning picks up
    # CMake's CompilerIdC/CMakeDetermineCompilerABI_*.bin probes.
    for path in sorted(build_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ARTIFACT_SUFFIXES:
            continue
        size = path.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise BuildError("E_TOO_LARGE", f"artifact too large: {path.name}")
        found.append({
            "name": path.name,
            "size": size,
            "sha256": _sha256(path),
            "uri": f"hw2c://artifacts/{request_id}/{path.name}",
        })
    return found


def _write_layers(request_dir: Path, layers: dict[str, str]) -> list[str]:
    written: list[str] = []
    for layer in LAYERS:
        text = layers.get(layer)
        if not text:
            continue
        path = request_dir / f"{layer}.yaml"
        path.write_text(text, encoding="utf-8")
        written.append(layer)
    return written


def _build_command(request_dir: Path, project_name: str, written: list[str]) -> list[str]:
    """Build the CLI command.  Never emits --force or an output path from input."""
    cmd = [
        build_python(), "-m", "parser.cli", "gen",
        "-i", str(request_dir / "hardware.yaml"),
        "-o", str(request_dir / project_name),
    ]
    for layer in written:
        if layer != "hardware":
            cmd.extend([f"--{layer}", str(request_dir / f"{layer}.yaml")])
    return cmd


def _compile_in_place(project_dir: Path, missing: list[str]) -> tuple[bool, str]:
    """Build the delivered source tree so build/ contains real images.

    hw2c compiles in a staging directory and does **not** carry build/ over
    during the atomic commit.  Without this step the artifact manifest would
    always be empty even though the generator reported a successful build.
    """
    if missing:
        return False, "compile check skipped: missing tools " + ", ".join(missing)
    if not (project_dir / "CMakeLists.txt").is_file():
        return False, "error: generated project has no CMakeLists.txt"

    cmake_text = (project_dir / "CMakeLists.txt").read_text(encoding="utf-8", errors="replace")
    commands = [
        ["cmake", "-B", "build", "-G", "Ninja",
         "-DCMAKE_TOOLCHAIN_FILE=toolchain.cmake"],
        ["cmake", "--build", "build", "-j"],
    ]
    # Bootloader projects declare these as add_custom_target, i.e. they are
    # NOT part of the default build.  combined.bin is the image to flash.
    if "add_custom_target(bootloader" in cmake_text:
        commands.append(["cmake", "--build", "build", "--target", "bootloader"])
        commands.append(["cmake", "--build", "build", "--target", "app"])
        commands.append(["cmake", "--build", "build", "--target", "combined"])

    output: list[str] = []
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd, cwd=str(project_dir), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=GEN_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return False, f"error: cmake step timed out: {cmd[2] if len(cmd) > 2 else cmd[1]}"
        output.append(proc.stdout or "")
        output.append(proc.stderr or "")
        if proc.returncode != 0:
            return False, "\n".join(output)
    return True, "\n".join(output)


def _stop_process(proc: subprocess.Popen) -> None:
    """Kill the generator and anything it spawned (cross-platform)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001 - the primary kill below still applies
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _set(request_id: str, **changes) -> None:
    with _LOCK:
        _TASKS[request_id].update(changes)


def _run_build(request_id: str, layers: dict[str, str], project_name: str) -> None:
    request_dir = work_root() / request_id
    warnings: list[str] = []
    issues: list[dict] = []
    compile_check = "skipped"
    artifacts: list[dict] = []
    status = "failed"

    acquired = _SEMAPHORE.acquire(timeout=QUEUE_TIMEOUT_S)
    if not acquired:
        _set(request_id, status="failed", progress=100,
             error={"code": "E_QUEUE_TIMEOUT", "message": "build queue full"},
             finished_at=time.monotonic())
        return

    try:
        _set(request_id, status="running", progress=20)
        missing = missing_tools()
        if missing:
            warnings.append(
                "compile check skipped: missing tools " + ", ".join(missing)
            )
            compile_check = "skipped"

        written = _write_layers(request_dir, layers)
        cmd = _build_command(request_dir, project_name, written)
        # Keep the raw log on disk only.  Tool results get sanitized issues.
        (request_dir / "generation.log").write_text(
            "command: " + " ".join(cmd) + "\n", encoding="utf-8"
        )

        proc = subprocess.Popen(
            cmd,
            cwd=str(_HW2C_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name != "nt"),
        )
        try:
            stdout, stderr = proc.communicate(timeout=GEN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            _stop_process(proc)
            stdout, stderr = proc.communicate(timeout=10)
            issues.append({"code": "E_TIMEOUT",
                           "message": f"generation exceeded {GEN_TIMEOUT_S}s",
                           "location": ""})
        with (request_dir / "generation.log").open("a", encoding="utf-8") as log:
            log.write("\n--- stdout ---\n" + (stdout or ""))
            log.write("\n--- stderr ---\n" + (stderr or ""))

        _set(request_id, progress=75)
        issues.extend(sanitize_stderr(stderr))
        issues.extend(sanitize_stderr(stdout))

        if proc.returncode != 0:
            if not any(item["code"] == "E_TIMEOUT" for item in issues):
                issues.insert(0, {
                    "code": "E_GENERATOR",
                    "message": f"hw2c gen exited with {proc.returncode}",
                    "location": "",
                })
            compile_check = "failed"
        else:
            if missing:
                # hw2c's own check silently returns success here; never call
                # that state "passed".
                compile_check = "skipped"
            else:
                ok, compile_output = _compile_in_place(
                    request_dir / project_name, missing
                )
                issues.extend(sanitize_stderr(compile_output))
                if not ok:
                    compile_check = "failed"
                    issues.insert(0, {
                        "code": "E_COMPILE",
                        "message": "cmake build failed after generation",
                        "location": "",
                    })

            if compile_check != "failed":
                artifacts = _collect_artifacts(request_dir, project_name, request_id)
                has_image = any(
                    item["name"].endswith((".elf", ".bin")) for item in artifacts
                )
                if missing:
                    compile_check = "skipped"
                elif not has_image:
                    compile_check = "skipped"
                    warnings.append("no .elf/.bin in build/ — compile status unverified")
                else:
                    compile_check = "passed"
                if not has_image:
                    warnings.append("no executable image found; source tree is still available")
                status = "succeeded"

        if not artifacts:
            warnings.append("artifact_manifest is empty")
    except BuildError as exc:
        issues.append({"code": exc.code, "message": exc.message, "location": ""})
    except Exception as exc:  # noqa: BLE001 - must never kill the MCP process
        # Only the exception class crosses the boundary: repr()/str() may carry
        # an absolute path or a user name straight out of the subprocess.
        issues.append({
            "code": "E_INTERNAL",
            "message": f"internal build error ({type(exc).__name__})",
            "location": "",
        })
    finally:
        _SEMAPHORE.release()
        _set(
            request_id,
            status=status,
            progress=100,
            compile_check=compile_check,
            artifact_manifest=artifacts,
            warnings=warnings,
            issues=issues[:20],
            finished_at=time.monotonic(),
        )


def submit_build(layers: dict, project_name: str = "firmware", options: dict | None = None) -> dict:
    """Validate and queue a build, returning a request_id within milliseconds."""
    _purge_expired()
    if not isinstance(layers, dict) or "hardware" not in layers:
        raise BuildError("E_BAD_INPUT", "layers.hardware is required")
    if options:
        raise BuildError("E_FORBIDDEN", "build options are not accepted; no --force/output paths")

    total = 0
    for layer, text in layers.items():
        if layer not in LAYERS:
            raise BuildError("E_FORBIDDEN", f"unknown layer: {layer!r}")
        if not isinstance(text, str):
            raise BuildError("E_BAD_INPUT", f"layer {layer} must be YAML text")
        size = len(text.encode("utf-8"))
        if size > MAX_LAYER_BYTES:
            raise BuildError("E_TOO_LARGE", f"layer {layer} exceeds {MAX_LAYER_BYTES} bytes")
        total += size
    if total > MAX_TOTAL_BYTES:
        raise BuildError("E_TOO_LARGE", f"layers exceed {MAX_TOTAL_BYTES} bytes in total")

    project_name = _check_name(project_name, "project_name")
    if not _HW2C_ROOT.is_dir():
        raise BuildError("E_NOT_FOUND", "hw2c project root not found")

    request_id = uuid.uuid4().hex[:12]
    request_dir = work_root() / request_id
    request_dir.mkdir(parents=True, exist_ok=True)

    with _LOCK:
        _TASKS[request_id] = {
            "request_id": request_id,
            "status": "queued",
            "progress": 0,
            "compile_check": "skipped",
            "artifact_manifest": [],
            "warnings": [],
            "issues": [],
            "created_at": time.monotonic(),
            "finished_at": 0.0,
        }

    thread = threading.Thread(
        target=_run_build, args=(request_id, dict(layers), project_name),
        name=f"hw2c-build-{request_id}", daemon=True,
    )
    thread.start()
    return {"request_id": request_id, "status": "queued", "poll_interval_s": 2}


def get_status(request_id: str) -> dict:
    """Return the current state of a build.  Never blocks on the subprocess."""
    _purge_expired()
    request_id = _check_request_id(request_id)
    with _LOCK:
        task = _TASKS.get(request_id)
        if task is None:
            raise BuildError("E_NOT_FOUND", f"unknown request_id: {request_id!r}")
        return {key: value for key, value in task.items()
                if key not in ("created_at", "finished_at")}


def list_artifacts(request_id: str) -> list[dict]:
    """List executable images produced by a build."""
    _purge_expired()
    request_id = _check_request_id(request_id)
    with _LOCK:
        task = _TASKS.get(request_id)
        if task is None:
            raise BuildError("E_NOT_FOUND", f"unknown request_id: {request_id!r}")
        return [dict(item) for item in task["artifact_manifest"]]


def read_artifact(request_id: str, filename: str) -> bytes:
    """Read one artifact for an MCP resource; only manifest entries are allowed."""
    request_id = _check_request_id(request_id)
    filename = _check_name(filename, "filename")
    allowed = {item["name"] for item in list_artifacts(request_id)}
    if filename not in allowed:
        raise BuildError("E_FORBIDDEN", f"artifact not in manifest: {filename!r}")
    project_dirs = [
        path for path in (work_root() / request_id).iterdir()
        if path.is_dir() and path.name != "__pycache__"
    ] if (work_root() / request_id).is_dir() else []
    for project in project_dirs:
        path = (project / "build" / filename).resolve()
        if (project / "build").resolve() == path.parent and path.is_file():
            return path.read_bytes()
    raise BuildError("E_NOT_FOUND", f"artifact missing on disk: {filename!r}")
