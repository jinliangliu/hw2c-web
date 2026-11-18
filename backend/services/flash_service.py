"""Hardware tools for the local MCP Connector (opt-in, never registered by default).

Everything here runs on the user's own machine.  The safe defaults are the
contract: no probe call unless ``confirm is True``, no whole-chip erase when
writing one slot, and no guessed link address.  The image's Reset_Handler is
compared with the *rendered* linker scripts from the same build, which is the
same check CI performs for slot images (tools/ci/verify_slot_images.py).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from services import generate_service as builds

FLASH_BASE = 0x08000000
MAX_FLASH_BYTES = 32 * 1024 * 1024
MAX_SERIAL_SECONDS = 30.0
MAX_SERIAL_CHARS = 64 * 1024
SERIAL_BAUD = 115200
# Only parts we can name a pyOCD target for.  An unknown part is rejected, never
# guessed: a wrong target can put a STM32G0 into the wrong flash geometry.
PYOCD_TARGETS = {
    "stm32g0b1ret6": "stm32g0b1retx",
    "stm32g0b1vet6": "stm32g0b1vetx",
}
SLOTS = ("A", "B")
_REGION_RE = re.compile(
    r"\bFLASH\b[^:{}]*:\s*ORIGIN\s*=\s*([^,]+),\s*LENGTH\s*=\s*([^\s}]+)",
    re.IGNORECASE,
)
_PART_RE = re.compile(r"^\s*part:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
_PORT_RE = re.compile(r"^(?:COM[1-9][0-9]{0,3}|/dev/[A-Za-z0-9_./-]+)$", re.IGNORECASE)


class FlashError(Exception):
    """A rejected hardware request, carrying a stable MCP error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = _safe(message)


def _safe(message: object) -> str:
    """No local path or unbounded pyOCD traceback crosses the tool boundary."""
    text = str(message)
    text = re.sub(r"Error processing line.*?Remainder of file ignored", "", text, flags=re.S)
    text = builds._PATH_IN_TEXT.sub("<path>", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


def enabled() -> bool:
    """Hardware tools are registered only when explicitly opted in."""
    return os.environ.get("HW2C_ENABLE_FLASH") == "1"


def require_enabled() -> None:
    if not enabled():
        raise FlashError("E_FORBIDDEN", "flash tools are disabled (set HW2C_ENABLE_FLASH=1)")


def pyocd_binary() -> str:
    binary = os.environ.get("HW2C_PYOCD") or shutil.which("pyocd")
    if not binary:
        raise FlashError("E_NOT_FOUND", "pyocd executable not found")
    return binary


def pyocd_python() -> str:
    """Interpreter that owns pyocd; may differ from the MCP host interpreter."""
    return os.environ.get("HW2C_PYOCD_PYTHON") or sys.executable


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise FlashError("E_TIMEOUT", f"pyocd timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise FlashError("E_NOT_FOUND", f"cannot start pyocd: {type(exc).__name__}") from exc


def _number(text: str) -> int:
    value = text.strip().rstrip(",")
    if value.lower().startswith("0x"):
        return int(value, 16)
    match = re.fullmatch(r"(\d+)\s*([KMGkmg]?)", value)
    if not match:
        raise FlashError("E_INTERNAL", f"unparseable linker address {value!r}")
    return int(match.group(1)) * {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[match.group(2).upper()]


def _parse_region(path: Path) -> tuple[int, int]:
    """FLASH (ORIGIN, LENGTH) from a rendered linker script; never guess."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FlashError("E_NOT_FOUND", f"cannot read linker script {path.name}") from exc
    match = _REGION_RE.search(text)
    if not match:
        raise FlashError("E_INTERNAL", f"no FLASH ORIGIN/LENGTH in {path.name}")
    origin, length = _number(match.group(1)), _number(match.group(2))
    if origin < FLASH_BASE or length <= 0:
        raise FlashError("E_INTERNAL", f"invalid FLASH region in {path.name}")
    return origin, length


def _regions(project_dir: Path) -> dict[str, tuple[int, int]]:
    """All known flash regions of this build, keyed by bootloader/slot_a/slot_b/base."""
    linker = project_dir / "linker"
    if not linker.is_dir():
        raise FlashError("E_NOT_FOUND", "generated project has no linker/ directory")
    wanted = {
        "bootloader": "bootloader.ld",
        "slot_a": "app_slot_a.ld",
        "slot_b": "app_slot_b.ld",
    }
    found = {
        key: _parse_region(linker / filename)
        for key, filename in wanted.items() if (linker / filename).is_file()
    }
    if not found:
        # Non-bootloader projects ship a single FLASH.ld at 0x08000000.
        generic = sorted(linker.glob("*FLASH*.ld"))
        if generic:
            found["base"] = _parse_region(generic[0])
    if not found:
        raise FlashError("E_NOT_FOUND", "no readable FLASH region in generated linker scripts")
    return found


def _target(project_dir: Path) -> str:
    override = os.environ.get("HW2C_PYOCD_TARGET")
    if override:
        return override
    hardware = project_dir.parent / "hardware.yaml"
    try:
        text = hardware.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FlashError("E_NOT_FOUND", "hardware.yaml missing from build workspace") from exc
    match = _PART_RE.search(text)
    if not match:
        raise FlashError("E_FORBIDDEN", "hardware.yaml has no mcu.part")
    target = PYOCD_TARGETS.get(match.group(1).lower())
    if target is None:
        raise FlashError("E_FORBIDDEN", f"no known pyOCD target for {match.group(1)}")
    return target


def _project_dir(request_id: str) -> Path:
    dirs = builds._project_dirs(request_id)
    if not dirs:
        raise FlashError("E_NOT_FOUND", "build workspace is missing")
    return next((path for path in dirs if (path / "linker").is_dir()), dirs[0])


def plan_flash(request_id: str, artifact: str, slot: str = "", *,
               for_write: bool = False) -> dict:
    """Resolve a manifest image to a verified flash address.  No hardware I/O."""
    require_enabled()
    request_id = builds._check_request_id(request_id)
    name = builds._check_name(artifact, "artifact")
    if not name.lower().endswith(".bin"):
        raise FlashError("E_FORBIDDEN", "only a manifest .bin image can be flashed; use .hex/.elf for inspection")

    entry = next(
        (item for item in builds.list_artifacts(request_id) if item["name"] == name), None
    )
    if entry is None:
        raise FlashError("E_NOT_FOUND", f"artifact not in manifest: {name}")
    image = builds.read_artifact(request_id, name)
    if len(image) != entry["size"] or hashlib.sha256(image).hexdigest() != entry["sha256"]:
        raise FlashError("E_INTEGRITY", "artifact changed since the build manifest was written")
    if len(image) > MAX_FLASH_BYTES:
        raise FlashError("E_TOO_LARGE", f"artifact exceeds {MAX_FLASH_BYTES} bytes")
    if len(image) < 8:
        raise FlashError("E_FORBIDDEN", "artifact is too small to contain a vector table")

    reset_handler = struct.unpack_from("<I", image, 4)[0]
    regions = _regions(_project_dir(request_id))
    matches = [key for key, (base, size) in regions.items() if base <= reset_handler < base + size]
    if not matches:
        raise FlashError("E_FORBIDDEN", f"Reset_Handler 0x{reset_handler:08X} is outside every known flash region")

    requested = slot.upper() if isinstance(slot, str) else ""
    if requested and requested not in SLOTS:
        raise FlashError("E_FORBIDDEN", f"unknown slot: {slot!r}")
    if requested:
        region = f"slot_{requested.lower()}"
        if region not in regions:
            raise FlashError("E_FORBIDDEN", f"this build has no slot {requested} linker script")
        if region not in matches:
            raise FlashError(
                "E_FORBIDDEN",
                f"image is linked at 0x{reset_handler:08X} ({'/'.join(matches)}), not slot {requested}; "
                "slot B needs a separate cmake -DHW2C_APP_SLOT=B build",
            )
    else:
        region = matches[0]
        if region.startswith("slot_") and for_write:
            raise FlashError(
                "E_FORBIDDEN",
                f"application image linked at 0x{reset_handler:08X} (slot {region[-1].upper()}); "
                "specify slot explicitly, or flash combined.bin at 0x08000000",
            )
        if region == "bootloader" and name.lower() != "combined.bin":
            raise FlashError("E_FORBIDDEN", "bootloader-linked image must be combined.bin (it contains the application)")

    address, length = regions[region]
    limit = length
    if region == "bootloader" and name.lower() == "combined.bin" and "slot_a" in regions:
        # combined.bin deliberately spans the bootloader **and** slot A.
        slot_a_base, slot_a_len = regions["slot_a"]
        limit = slot_a_base + slot_a_len - address
    if len(image) > limit:
        raise FlashError("E_FORBIDDEN", f"image ({len(image)} B) does not fit {region} ({limit} B)")
    plan = {
        "ok": True,
        "dry_run": True,
        "confirm_required": True,
        "request_id": request_id,
        "artifact": name,
        "slot": requested or (region[-1].upper() if region.startswith("slot_") else ""),
        "target": _target(_project_dir(request_id)),
        "address": address,
        "size": len(image),
        "sha256": entry["sha256"],
        "reset_handler": f"0x{reset_handler:08X}",
        "region": region,
        "erase": "sector",
        "reset_after": False,
        "_image": image,
    }
    return plan


def public_plan(plan: dict) -> dict:
    """A dry-run plan never carries the raw image or other private fields."""
    return {key: value for key, value in plan.items() if not key.startswith("_")}


def read_flash(plan: dict) -> bytes:
    """Read flash through pyocd's Python API (its CLI savemem mangles paths)."""
    require_enabled()
    helper = Path(__file__).with_name("pyocd_readback.py")
    with tempfile.TemporaryDirectory(prefix="hw2c-readback-") as tmp:
        output = Path(tmp) / "readback.bin"
        cmd = [
            pyocd_python(), str(helper),
            "--target", plan["target"],
            "--address", hex(plan["address"]),
            "--length", str(plan["size"]),
            "--out", str(output),
        ]
        proc = _run(cmd, timeout=180)
        if proc.returncode != 0:
            raise FlashError("E_PROBE", _safe(proc.stderr or proc.stdout or "pyocd readback failed"))
        if not output.is_file():
            raise FlashError("E_PROBE", "pyocd produced no readback file")
        data = output.read_bytes()
    if len(data) != plan["size"]:
        raise FlashError("E_PROBE", f"readback size {len(data)} != expected {plan['size']}")
    return data


def _write_flash(plan: dict) -> None:
    """Sector-erase only the addressed range; never -e chip on a slot write."""
    with tempfile.TemporaryDirectory(prefix="hw2c-flash-") as tmp:
        image = Path(tmp) / plan["artifact"]
        image.write_bytes(plan["_image"])
        cmd = [
            pyocd_binary(), "load",
            "-t", plan["target"],
            "-e", "sector",
            "-a", hex(plan["address"]),
            "--no-reset",
            str(image),
        ]
        proc = _run(cmd, timeout=180)
    if proc.returncode != 0:
        raise FlashError("E_FLASH_FAILED", _safe(proc.stderr or proc.stdout or "pyocd load failed"))


def flash(plan: dict) -> dict:
    """Read → compare → (maybe) write → read again.  ``confirm`` is checked by the tool."""
    require_enabled()
    before = read_flash(plan)
    before_sha = hashlib.sha256(before).hexdigest()
    result = {
        "ok": True,
        "dry_run": False,
        "address": plan["address"],
        "target": plan["target"],
        "slot": plan["slot"],
        "size": plan["size"],
        "image_sha256": plan["sha256"],
        "before_sha256": before_sha,
        "reset_performed": False,
    }
    if before == plan["_image"]:
        result.update(written=False, match=True, already_identical=True,
                      after_sha256=before_sha, first_diff_offset=None)
        return result
    _write_flash(plan)
    after = read_flash(plan)
    match = after == plan["_image"]
    result.update(
        written=True, match=match, already_identical=False,
        after_sha256=hashlib.sha256(after).hexdigest(),
        first_diff_offset=None if match else next(
            (i for i, (a, b) in enumerate(zip(after, plan["_image"])) if a != b), -1
        ),
    )
    if not match:
        result["ok"] = False
        result["error"] = {"code": "E_VERIFY_FAILED", "message": "readback differs from image"}
    return result


def verify_flash(request_id: str, artifact: str, slot: str = "") -> dict:
    """Read-only byte-for-byte comparison with a manifest image."""
    plan = plan_flash(request_id, artifact, slot, for_write=False)
    device = read_flash(plan)
    image = plan["_image"]
    first_diff = next((i for i, (a, b) in enumerate(zip(device, image)) if a != b), None)
    if first_diff is None and len(device) != len(image):
        first_diff = min(len(device), len(image))
    return {
        "ok": True,
        "match": device == image,
        "address": plan["address"],
        "target": plan["target"],
        "slot": plan["slot"],
        "size": plan["size"],
        "image_sha256": plan["sha256"],
        "device_sha256": hashlib.sha256(device).hexdigest(),
        "first_diff_offset": first_diff,
    }


def list_probes() -> dict:
    """Enumerate locally attached debug probes.  Read-only."""
    require_enabled()
    proc = _run([pyocd_binary(), "list", "-p"], timeout=30)
    if proc.returncode != 0:
        raise FlashError("E_PROBE", _safe(proc.stderr or proc.stdout or "pyocd list failed"))
    probes = []
    for line in (proc.stdout or "").splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2 and parts[0].isdigit():
            probes.append({
                "index": int(parts[0]),
                "description": _safe(parts[1]),
                # pyocd's 4th column is the (often empty) board target, not the UID.
                "uid": _safe(parts[2]) if len(parts) > 2 else "",
            })
    return {"ok": True, "count": len(probes), "probes": probes}


def capture_serial(port: str, seconds: float = 5.0, trigger: str = "") -> dict:
    """Read a serial port with a physical-rate guard; never writes to the device.

    The USB-serial adapter in this machine has replayed stale buffers at 7x the
    UART line rate.  A guard trip discards that window instead of letting the
    model interpret replayed bytes as firmware output.
    """
    require_enabled()
    if not isinstance(port, str) or not _PORT_RE.fullmatch(port):
        raise FlashError("E_FORBIDDEN", f"invalid serial port: {port!r}")
    try:
        duration = float(seconds)
    except (TypeError, ValueError) as exc:
        raise FlashError("E_BAD_INPUT", "seconds must be a number") from exc
    if not 0 < duration <= MAX_SERIAL_SECONDS:
        raise FlashError("E_BAD_INPUT", f"seconds must be in (0, {MAX_SERIAL_SECONDS:g}]")
    if not isinstance(trigger, str) or len(trigger) > 200:
        raise FlashError("E_TOO_LARGE", "trigger regex exceeds 200 chars")
    try:
        pattern = re.compile(trigger) if trigger else None
    except re.error as exc:
        raise FlashError("E_BAD_INPUT", f"invalid trigger regex: {exc}") from exc

    try:
        import serial  # noqa: PLC0415 - optional hardware dependency
    except ImportError as exc:
        raise FlashError("E_NOT_FOUND", "pyserial is not installed") from exc
    try:
        handle = serial.Serial(port, SERIAL_BAUD, timeout=0.05)
    except Exception as exc:  # noqa: BLE001 - a busy port is a tool result, not a crash
        return {"ok": False, "error": {"code": "E_PORT",
                                       "message": _safe(f"{type(exc).__name__}: {exc}")}}
    chunks: list[str] = []
    total = trips = 0
    purged = True
    try:
        try:
            handle.reset_input_buffer()
            handle.reset_output_buffer()
        except Exception:  # noqa: BLE001 - purge failure is recorded, not fatal
            purged = False
        deadline = time.monotonic() + duration
        window_start, window_bytes = time.monotonic(), 0
        line_limit = SERIAL_BAUD / 10.0 * 1.5
        while time.monotonic() < deadline:
            raw = handle.read(4096)
            if not raw:
                continue
            total += len(raw)
            window_bytes += len(raw)
            now = time.monotonic()
            span = now - window_start
            if span >= 1.0:
                rate = window_bytes / span
                if rate > line_limit:
                    trips += 1
                    chunks.clear()  # stale replay is not firmware output
                    total = 0
                    try:
                        handle.reset_input_buffer()
                    except Exception:  # noqa: BLE001
                        purged = False
                window_start, window_bytes = now, 0
                if trips:
                    continue
            chunks.append(raw.decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 - always close the port
        return {"ok": False, "error": {"code": "E_PORT",
                                       "message": _safe(f"{type(exc).__name__}: {exc}")}}
    finally:
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass

    text = "".join(chunks)
    truncated = len(text) > MAX_SERIAL_CHARS
    if truncated:
        text = text[:MAX_SERIAL_CHARS]
    return {
        "ok": True,
        "port": port,
        "baud": SERIAL_BAUD,
        "seconds": duration,
        "bytes": total,
        "text": text,
        "trigger_matched": bool(pattern.search(text)) if pattern else None,
        "rate_guard_trips": trips,
        "purged_on_open": purged,
        "truncated": truncated,
    }
